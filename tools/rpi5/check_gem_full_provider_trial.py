#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Strict offline checker for the observation-only full-provider image."""
import argparse
import json
from pathlib import Path
import re

from tools.rpi5 import build_gem_full_provider_trial as build


def check(package, expected_manifest_sha256):
    package = Path(package).resolve()
    if package.parent != build.ROOT / "build/rpi5" or not package.name.startswith("gem-full-provider-trial-"):
        raise ValueError("exact distinct full-provider trial package required")
    manifest_path = package / "manifest.json"
    if build.sha(manifest_path) != expected_manifest_sha256:
        raise ValueError("manifest pin differs")
    manifest = json.loads(manifest_path.read_text())
    errors = []
    exact = {"profile": build.PROFILE, "allocation_bytes": 0x48000,
        "descriptor_pages": 2, "packet_spans": 128, "packet_bytes": 0x800,
        "mapping_pages": 18, "detailed_evidence_records": 146,
        "serial_input_bytes": 0, "gem_imr_all_masked_value": 0x3fffffff}
    true = ("ordered_page_proofs", "retained_and_static_translation_proofs",
        "full_provider_retained_until_reset", "quiescence_before_after",
        "command_bme_zero_required", "gem_ncr_zero_required",
        "gem_imr_all_masked_required", "queue_registers_unchanged_required")
    false = ("queue_publication", "bme_enable", "dma_activation", "irq_activation",
        "packet_submission", "tx_enable", "hardware_executed", "staged")
    if any(manifest.get(key) != value for key, value in exact.items()):
        errors.append("typed trial contract differs")
    if any(manifest.get(key) is not True for key in true):
        errors.append("required observation predicate differs")
    if any(manifest.get(key) is not False for key in false):
        errors.append("forbidden activation predicate differs")
    if build.sha(build.PROVIDER) != build.PROVIDER_SHA or \
            manifest.get("full_provider_manifest_sha256") != build.PROVIDER_SHA:
        errors.append("full-provider v2 foundation differs")

    generated = manifest.get("generated_sha256", {})
    members = {str(path) for path in package.rglob("*") if path.is_file() and path != manifest_path}
    if set(generated) != members:
        errors.append("generated closure differs")
    for path, digest in [*manifest.get("inputs_sha256", {}).items(), *generated.items()]:
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or not Path(path).is_file() or build.sha(path) != digest:
            errors.append("byte pin differs: " + path)
    if any(row.get("returncode") != 0 or not Path(row.get("log", "")).is_file()
            for row in manifest.get("commands", [])):
        errors.append("build receipt differs")

    marker = manifest.get("trial_marker", "")
    image = (package / "probe.bin").read_bytes()
    if image.count(marker.encode()) != 1 or "NO_QUEUE NO_BME NO_DMA" not in marker:
        errors.append("unique inert marker differs")
    provider = (package / "overlay/BCM2712GEMDMABatch.cpp").read_text()
    transport = (package / "overlay/BCM2712RP1GEMIdentifyTransport.inc").read_text()
    progress = (package / "overlay/BCM2712PCIeIDTrialProgress.inc").read_text()
    for token in ("BCM2712GEMDMAMemory::prepare", "observeCPUOwnedLayout",
            "RPI5_GEM_FULL_PROVIDER_MAPPING_PAGES", "RPI5_GEM_FULL_PROVIDER_PACKET_SPANS"):
        if token not in provider + transport + progress:
            errors.append("full-provider caller token absent: " + token)
    for token in ("readFullProviderQuiescence", "FULL_QUIESCE_BEFORE", "FULL_PAGE INDEX=",
            "FULL_SPAN INDEX=", "observePreparedFullProvider"):
        if token not in transport + progress:
            errors.append("board evidence transport absent: " + token)
    reachable = transport + progress[progress.index('extern "C" void rpi5_pcie_id_trial_start(void)'):]
    forbidden = ("stageCPUOwned", "rpi5_gem_queue_admission_run", "setBusMasterEnable",
        "publishQueue", "submitPacket", "enableIRQ", "activateDMA")
    if any(token in reachable for token in forbidden):
        errors.append("activation call appears in observation-only path")
    symbols = (package / "kernel-symbols.log").read_text()
    for token in ("_ZN19BCM2712GEMDMAMemory7prepareEv",
            "_ZN19BCM2712GEMDMAMemory7qualify",
            "_ZNK19BCM2712GEMDMAMemory21observeCPUOwnedLayout"):
        if token not in symbols:
            errors.append("linked full-provider symbol absent: " + token)
    if "_rpi5_gem_queue_admission_run" in symbols:
        errors.append("queue admission object linked prematurely")
    if errors:
        raise ValueError("; ".join(errors))
    return {"status": "pass", "package": str(package),
        "manifest_sha256": expected_manifest_sha256,
        "kernel_sha256": manifest["kernel_sha256"], "image_sha256": manifest["image_sha256"],
        "detailed_evidence_records": 146, "software_qualified": True,
        "hardware_executed": False, "staged": False, "bme": False,
        "queues": False, "dma": False, "irq": False, "packets": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = check(args.package, args.manifest_sha256)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.write_text(encoded)
    print(encoded, end="")
