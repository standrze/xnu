#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Strict offline checker for the discard-only physmap verification image."""
import argparse, hashlib, json
from pathlib import Path
import re


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def marker_errors(manifest, image):
    tag = manifest.get("tag", "")
    marker = manifest.get("trial_marker", "")
    expected = f"RPI5XNU:CPU_RINGS:ENTRY TAG={tag} CPUS=1 NO_CPU_ON NO_QUEUE NO_DMA"
    errors = []
    if not re.fullmatch(r"[0-9a-f]{32}", tag) or marker != expected:
        errors.append("manifest tag/trial marker differs")
    if image.count(marker.encode()) != 1:
        errors.append("image does not contain exact manifest marker once")
    return errors


def replacement_errors(manifest):
    replacements = manifest.get("replaced_objects", {})
    expected = {"pmap.o": "pmap-enabled.o", "arm_vm_init.o": "arm_vm_init-enabled.o",
        "loose_ends.o": "loose_ends-enabled.o"}
    names = {Path(old).name: Path(new).name for old, new in replacements.items()
        if Path(old).name in expected}
    return [] if names == expected else ["linked VM object replacement differs"]


def check(package):
    package = Path(package).resolve()
    manifest = json.loads((package / "manifest.json").read_text())
    errors = []
    expect = {
        "profile": "bcm2712-gem-page-granular-mapping-verification-v1",
        "build_opt_in": "RPI5_GEM_PAGE_GRANULAR_PHYSMAP=1",
        "verification_only": True, "discard_before_route": True, "mapping_rows": 4,
        "descriptor_stores": 0, "route_calls": 0, "queue_publication": False,
        "bme_enable": False, "dma_activation": False, "irq_activation": False,
        "packet_mapping": False, "hardware_executed": False, "staged": False,
    }
    for key, value in expect.items():
        if manifest.get(key) != value:
            errors.append(f"manifest {key} differs")
    for field in ("kernel", "image"):
        path = Path(manifest.get(field, ""))
        if not path.is_file() or sha(path) != manifest.get(field + "_sha256"):
            errors.append(f"{field} hash differs")
    image_path = Path(manifest.get("image", ""))
    if image_path.is_file():
        errors.extend(marker_errors(manifest, image_path.read_bytes()))
    qualification = Path(manifest.get("canonical_build_qualification", ""))
    if (not qualification.is_file() or sha(qualification) != manifest.get("canonical_build_qualification_sha256")):
        errors.append("canonical build qualification differs")
    else:
        canonical = json.loads(qualification.read_text())
        if (canonical.get("predicted_maximum_table_bytes") != 4243456 or
                canonical.get("predicted_maximum_table_pages") != 259 or
                canonical.get("predicted_maximum_physmap_hierarchy_pages") != 258 or
                canonical.get("preallocated_upper_pages") != 1 or
                canonical.get("affected_units") != ["pmap.c", "arm_vm_init.c", "loose_ends.c"] or
                not canonical.get("linked_symbols_verified")):
            errors.append("canonical full-build proof differs")
    generated = manifest.get("generated_sha256", {})
    for path, digest in generated.items():
        if not Path(path).is_file() or sha(path) != digest:
            errors.append(f"generated hash differs: {path}")

    provider = (package / "overlay/BCM2712GEMDMABatch.cpp").read_text()
    header = (package / "overlay/BCM2712GEMDMABatch.h").read_text()
    progress = (package / "overlay/BCM2712PCIeIDTrialProgress.inc").read_text()
    identify = (package / "overlay/BCM2712RP1GEMIdentifyTransport.inc").read_text()
    prepare = provider[provider.index("bool BCM2712GEMDMABatch::prepare()"):
        provider.index("bool BCM2712GEMDMABatch::discardBeforeAdmission()")]
    after_mapping = prepare[prepare.index("if (!mapping())"):]
    if "route(" in after_mapping or "discardBeforeAdmission()" not in after_mapping or "state_=Rejected" not in after_mapping:
        errors.append("prepare does not discard immediately after mapping")
    if "state_=Prepared" in prepare or "stageCPUOwned" in prepare:
        errors.append("verification prepare can publish a prepared/staged state")
    if provider.count('at s1e1r') != 1 or provider.count('at s1e1w') != 1 or \
            provider.count('msr par_el1, %0') != 1 or provider.count('ml_set_interrupts_enabled(interrupts)') != 1:
        errors.append("AT/PAR/interrupt preservation differs")
    for token in ("mappingEvidence_[page][0]", "mappingEvidence_[page][1]", "account.maximum_pages>259",
                  "account.edge_pages>2", "account.preallocated_upper_pages!=1",
                  "rpi5_reservation_kernel_buffer(currentRecord,account.table_start,account.table_bytes)"):
        if token not in provider:
            errors.append("provider evidence predicate absent: " + token)
    if "verificationDiscarded()" not in header or "physmapAccounting()" not in header:
        errors.append("bounded evidence API absent")
    entry = progress[progress.index('extern "C" void rpi5_pcie_id_trial_start(void)\n') :]
    if "runBoundedRP1Trial(&observed)" in entry or "pe_rpi5_pcie_owner_trace(" in entry or entry.count("RPI5XNU:PCIEID:DMA_ALIAS") != 1 or \
            "page<2" not in entry or "vaClass<=2" not in entry or "RPI5XNU:PCIEID:DMA_PGTABLE" not in entry:
        errors.append("terminal four-row caller differs")
    if "dmaMemory->verificationDiscarded()" not in identify or "dmaMemory->qualify(" in identify[identify.index("prepareCPUOwnedRings"):]:
        errors.append("transport does not stop at discarded verification")

    errors.extend(replacement_errors(manifest))
    commands = manifest.get("commands", [])
    wanted_logs = ("physmap-arm-object.log", "physmap-pmap-object.log", "physmap-loose-ends-object.log")
    for log in wanted_logs:
        rows = [row for row in commands if row["log"].endswith("/" + log)]
        if len(rows) != 1 or "-DRPI5_GEM_PAGE_GRANULAR_PHYSMAP=1" not in rows[0]["command"] or rows[0]["returncode"]:
            errors.append("opt-in VM object was not compiled: " + log)
    symbols = (package / "kernel-symbols.log").read_text()
    if "_rpi5_gem_physmap_accounting" not in symbols:
        errors.append("accounting API absent from linked kernel")
    pmap_dis = (package / "physmap-pmap-disassembly.log").read_text()
    arm_dis = (package / "physmap-arm-disassembly.log").read_text()
    loose_dis = (package / "physmap-loose-ends-disassembly.log").read_text()
    if "_pmap_update_cache_attributes_locked" not in pmap_dis or "_phystokv" not in pmap_dis:
        errors.append("physmap PTE update absent from linked pmap object")
    if "_rpi5_gem_physmap_stats" not in arm_dis or "_arm_vm_physmap_slide" not in arm_dis:
        errors.append("accounted page-granular arm object absent")
    if "_bcopy_phys_internal" not in loose_dis or "_phystokv_range" not in loose_dis:
        errors.append("enabled loose-ends physmap path absent")
    transport_dis = (package / "transport-disassembly.log").read_text()
    entry_marker = "<_rpi5_pcie_id_trial_start>:"
    if entry_marker not in transport_dis:
        errors.append("compiled terminal entry absent")
    else:
        entry_dis = transport_dis[transport_dis.index(entry_marker):]
        next_symbol = entry_dis.find("\n\n", len(entry_marker))
        entry_dis = entry_dis if next_symbol < 0 else entry_dis[:next_symbol]
        forbidden = ("runBoundedRP1Trial", "pe_rpi5_pcie_owner_trace", "stageCPUOwned", "qualify", "route")
        if any(token in entry_dis for token in forbidden) or "prepareCPUOwnedRings" not in entry_dis:
            errors.append("compiled entry escapes terminal mapping/discard path")
    provider_dis = (package / "provider-disassembly.log").read_text()
    prepare_marker = "<__ZN18BCM2712GEMDMABatch7prepareEv>:"
    if prepare_marker not in provider_dis:
        errors.append("compiled provider preparation absent")
    else:
        prepare_dis = provider_dis[provider_dis.index(prepare_marker):]
        next_symbol = prepare_dis.find("\n\n", len(prepare_marker))
        prepare_dis = prepare_dis if next_symbol < 0 else prepare_dis[:next_symbol]
        if "discardBeforeAdmission" not in prepare_dis or "5route" in prepare_dis or "stageCPUOwned" in prepare_dis:
            errors.append("compiled provider does not discard before route/stage")
    if errors:
        raise ValueError("; ".join(errors))
    return {"status": "pass", "package": str(package), "manifest_sha256": sha(package / "manifest.json"),
        "kernel_sha256": manifest["kernel_sha256"], "image_sha256": manifest["image_sha256"],
        "maximum_page_table_bytes": 259 * 0x4000}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    print(json.dumps(check(parser.parse_args().package), sort_keys=True))
