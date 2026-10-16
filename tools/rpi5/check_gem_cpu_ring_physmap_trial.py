#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Strict offline checker for the physmap-enabled CPU-ring successor."""
import argparse
import json
from pathlib import Path
import re

from tools.rpi5 import build_gem_cpu_ring_physmap_trial as build


def _slice(text, begin, end):
    return text[text.index(begin):text.index(end, text.index(begin))]


def check(package, expected_manifest_sha256):
    package = Path(package).resolve()
    if (package.parent != build.ROOT / "build/rpi5" or
            not package.name.startswith("gem-cpu-ring-physmap-trial-")):
        raise ValueError("exact distinct ring/physmap package required")
    manifest_path = package / "manifest.json"
    if build.sha(manifest_path) != expected_manifest_sha256:
        raise ValueError("manifest pin differs")
    manifest = json.loads(manifest_path.read_text())
    errors = []
    exact = {"profile": build.PROFILE,
        "build_opt_in": "RPI5_GEM_PAGE_GRANULAR_PHYSMAP=1",
        "allocation_bytes": 32768, "descriptor_pages": 2, "packet_spans": 0,
        "preparation_steps": 17, "maximum_table_pages": 259,
        "maximum_table_bytes": 4243456, "preallocated_upper_pages": 1}
    truth = ("preferred_ram_route_only", "page_granular_physmap",
        "cpu_ring_structure_validation", "cpu_owned_descriptors_only")
    false = ("queue_publication", "bme_enable", "dma_activation",
        "irq_activation", "packet_mapping", "packet_submission", "tx_enable",
        "hardware_executed", "staged")
    if any(manifest.get(key) != value for key, value in exact.items()):
        errors.append("typed package contract differs")
    if any(manifest.get(key) is not True for key in truth):
        errors.append("required ring/physmap predicate differs")
    if any(manifest.get(key) is not False for key in false):
        errors.append("forbidden activation predicate differs")

    pins = ((build.RING_PARENT, build.RING_PARENT_SHA),
        (build.PHYSMAP_PARENT, build.PHYSMAP_PARENT_SHA),
        (build.GATE / "manifest.json", build.GATE_MANIFEST_SHA),
        (build.CANONICAL, build.CANONICAL_SHA),
        (build.DISPLAY_PMAP, build.DISPLAY_PMAP_SHA))
    for path, digest in pins:
        if build.sha(path) != digest or manifest.get("inputs_sha256", {}).get(str(path)) != digest:
            errors.append("foundation pin differs: " + str(path))
    generated = manifest.get("generated_sha256", {})
    members = {str(path) for path in package.rglob("*") if path.is_file() and path != manifest_path}
    if set(generated) != members:
        errors.append("generated closure differs")
    for path, digest in [*manifest.get("inputs_sha256", {}).items(), *generated.items()]:
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or not Path(path).is_file() or build.sha(path) != digest:
            errors.append("byte pin differs: " + path)

    # Reconstruct the complete recipe without executing it.  This binds every
    # command, emitted source, dependency closure and linked object selection
    # to the checked builder rather than trusting manifest vocabulary alone.
    build.configure()
    rows, scans = build.plan(package, manifest.get("tag", ""))
    expected_commands = {label: {"command": args, "cwd": cwd}
        for label, args, cwd in rows}
    observed_commands = {}
    for row in manifest.get("commands", []):
        label = Path(row.get("log", "")).stem
        if (label in observed_commands or row.get("returncode") != 0 or
                row.get("log") != str(package / (label + ".log")) or
                build.sha(row["log"]) != row.get("log_sha256")):
            errors.append("command receipt differs: " + label)
            continue
        observed_commands[label] = {"command": row.get("command"), "cwd": row.get("cwd")}
    if observed_commands != expected_commands:
        errors.append("complete canonical command recipe differs")
    for path in build.sources():
        if manifest.get("inputs_sha256", {}).get(str(path.resolve())) != build.sha(path):
            errors.append("required source omitted: " + str(path))
    for name, data in build.derived_sources().items():
        if (package / name).read_bytes() != data:
            errors.append("emitted source differs: " + name)
    objects, expected_replacements, extras, added = build.kernel_objects(package)
    if (package / "kernel.filelist").read_text() != "\n".join(objects) + "\n":
        errors.append("linked object list differs")
    if (manifest.get("replaced_objects") != expected_replacements or
            manifest.get("inherited_extra_objects") != extras or
            manifest.get("added_objects") != added):
        errors.append("linked object ownership differs")
    for label, record in scans.items():
        before = build.composer.old.display.dependencies(package / (label + ".scan.d"), record["cwd"])
        after = build.composer.old.display.dependencies(package / (label + ".d"), record["cwd"])
        if (before != after or sorted(before) != manifest.get("compiler_scans", {}).get(label)):
            errors.append("compiler dependency receipt differs: " + label)

    marker = manifest.get("trial_marker", "")
    image = (package / "probe.bin").read_bytes()
    if (not re.fullmatch(r"[0-9a-f]{32}", manifest.get("tag", "")) or
            image.count(marker.encode()) != 1 or "NO_QUEUE NO_DMA" not in marker):
        errors.append("unique inert trial identity differs")
    replacements = {Path(old).name: Path(new).name
        for old, new in manifest.get("replaced_objects", {}).items()
        if Path(old).name in ("pmap.o", "arm_vm_init.o", "loose_ends.o")}
    if replacements != {"pmap.o": "pmap-enabled.o", "arm_vm_init.o": "arm_vm_init-enabled.o",
            "loose_ends.o": "loose_ends-enabled.o"}:
        errors.append("all three enabled VM objects are not linked")

    commands = manifest.get("commands", [])
    for label in ("physmap-arm-object", "physmap-pmap-object", "physmap-loose-ends-object"):
        rows = [row for row in commands if Path(row["log"]).stem == label]
        if (len(rows) != 1 or rows[0]["returncode"] != 0 or
                "-DRPI5_GEM_PAGE_GRANULAR_PHYSMAP=1" not in rows[0]["command"]):
            errors.append("enabled VM compile receipt differs: " + label)
    canonical = json.loads(build.CANONICAL.read_text())
    if (canonical.get("affected_units") != ["pmap.c", "arm_vm_init.c", "loose_ends.c"] or
            canonical.get("predicted_maximum_table_pages") != 259 or
            canonical.get("preallocated_upper_pages") != 1 or
            not canonical.get("linked_symbols_verified")):
        errors.append("canonical full-build proof differs")
    if (str(build.ROOT / "makedefs/MakeInc.def") not in manifest.get("inputs_sha256", {}) or
            str(build.ROOT / "Makedefs/MakeInc.def") in manifest.get("inputs_sha256", {})):
        errors.append("canonical lowercase makedefs pin differs")

    provider = (package / "overlay/BCM2712GEMDMABatch.cpp").read_text()
    transport = (package / "overlay/BCM2712RP1GEMIdentifyTransport.inc").read_text()
    progress = (package / "overlay/BCM2712PCIeIDTrialProgress.inc").read_text()
    prepare = _slice(provider, "bool BCM2712GEMDMABatch::prepare()",
        "bool BCM2712GEMDMABatch::discardBeforeAdmission()")
    stage = _slice(provider, "bool BCM2712GEMDMABatch::stageCPUOwned(", "failed:\n")
    entry = progress[progress.index('extern "C" void rpi5_pcie_id_trial_start(void)\n'):]
    for token in ("if (!mapping())", "if (!route(&expected_,&geometry))", "state_=Prepared",
                  "rpi5_gem_ring_only_batch", "ringRequest_.packet_granule=0"):
        if token not in provider:
            errors.append("ring-only provider token absent: " + token)
    for token in ("prepareCPUOwnedRings()", "stagePreparedCPUOwnedRings()"):
        if token not in transport + entry:
            errors.append("CPU-owned ring caller absent: " + token)
    forbidden = ("setBusMasterEnable", "enableBusMaster", "publishQueue", "submitPacket",
        "transmitPacket", "enableIRQ", "activateDMA")
    if any(token in prepare + stage + entry for token in forbidden):
        errors.append("activation call appears in reachable ring trial")
    if ("packet[r][i]" in stage or "RPI5_GEM_BUFFER_BYTES" in stage or
            "packet_granule=256" in stage):
        errors.append("packet memory appears in ring-only stage")
    if "runBoundedRP1Trial(&observed)" not in entry:
        errors.append("bounded capability/ring structure observation absent")

    symbols = (package / "kernel-symbols.log").read_text()
    for symbol in ("_rpi5_gem_ring_only_batch", "_rpi5_gem_physmap_accounting"):
        if symbol not in symbols:
            errors.append("linked symbol absent: " + symbol)
    if "_rpi5_gem_ring_batch" in symbols:
        errors.append("packet-capable ring batch is linked")
    provider_disassembly = (package / "provider-disassembly.log").read_text()
    transport_disassembly = (package / "transport-disassembly.log").read_text()
    if ("<__ZN18BCM2712GEMDMABatch13stageCPUOwned" not in provider_disassembly or
            "ARM64_RELOC_BRANCH26\t_rpi5_gem_ring_only_batch" not in provider_disassembly):
        errors.append("compiled CPU-owned ring stage differs")
    if ("<__ZN23BCM2712PCIePHYTransport20prepareCPUOwnedRingsEv>" not in transport_disassembly or
            "ARM64_RELOC_BRANCH26\t__ZN23BCM2712PCIePHYTransport20prepareCPUOwnedRingsEv" not in
            transport_disassembly):
        errors.append("compiled ring caller differs")
    for name, tokens in (("physmap-pmap-disassembly.log",
            ("_pmap_update_cache_attributes_locked", "_phystokv")),
        ("physmap-arm-disassembly.log", ("_rpi5_gem_physmap_stats", "_arm_vm_physmap_slide")),
        ("physmap-loose-ends-disassembly.log", ("_bcopy_phys_internal", "_phystokv_range"))):
        data = (package / name).read_text()
        if any(token not in data for token in tokens):
            errors.append("enabled VM disassembly differs: " + name)
    if errors:
        raise ValueError("; ".join(errors))
    return {"status": "pass", "package": str(package),
        "manifest_sha256": expected_manifest_sha256,
        "kernel_sha256": manifest["kernel_sha256"],
        "image_sha256": manifest["image_sha256"],
        "tag": manifest["tag"], "trial_marker": marker,
        "descriptor_pages": 2, "packet_spans": 0,
        "preferred_ram_route_only": True, "page_granular_physmap": True,
        "cpu_owned_ring_structure_only": True, "bme": False, "queues": False,
        "dma": False, "irq": False, "packets": False, "tx": False,
        "hardware_executed": False, "staged": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = check(args.package, args.manifest_sha256)
    if args.report:
        with args.report.resolve().open("x") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
    print(json.dumps(result, sort_keys=True))
