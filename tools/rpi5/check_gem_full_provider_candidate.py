#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Strict offline checker for the default-off full retained GEM provider."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.rpi5 import build_gem_full_provider_candidate as build

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(package):
    package = package.resolve()
    if package.parent != ROOT / "build/rpi5" or not package.is_dir():
        raise ValueError("exact build/rpi5 package required")
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    errors = []
    exact = {
        "profile": build.PROFILE,
        "provider_bytes": 0x48000,
        "ring_pages": 2,
        "ring_page_bytes": 0x4000,
        "packet_spans": 128,
        "packet_bytes": 0x800,
        "packet_mapped_bytes": 0x40000,
        "mapping_pages": 18,
        "ordered_page_proof_records": 18,
        "retained_translation_proofs": 18,
        "static_translation_proofs": 18,
        "normal_nc_page_bitmap_required": 0x3ffff,
        "packet_spans_cpu_owned": 128,
        "retained_descriptor": True,
        "retained_prepared_dma_command": True,
        "static_physmap_checked": True,
        "default_off": True,
        "boot_caller_added": False,
        "constructor_added": False,
        "loader_created": False,
        "staged": False,
        "hardware_executed": False,
        "dma_enabled": False,
        "irq_enabled": False,
        "packets": False,
    }
    for key, expected in exact.items():
        if manifest.get(key) != expected:
            errors.append(key + " differs")
    activation = manifest.get("activation", {})
    if set(activation) != {
        "boot_caller", "bme", "gem_queue_registers", "gem_rx_tx",
        "dma_ownership", "interrupts", "packets", "hardware_executed", "staged"
    } or any(activation.values()):
        errors.append("activation boundary differs")
    source_manifest = manifest.get("source_manifest", {})
    if source_manifest.get("profile") != build.PROFILE:
        errors.append("source manifest profile differs")
    rows = source_manifest.get("sources", [])
    source_hashes = {row.get("path"): row.get("sha256") for row in rows}
    if set(source_hashes) != set(build.SOURCES[:-1]):
        errors.append("source manifest inventory differs")
    else:
        for relative, digest in source_hashes.items():
            path = ROOT / relative
            if not path.is_file() or sha(path) != digest:
                errors.append("source differs: " + relative)
    generated = manifest.get("generated_sha256", {})
    for name, digest in generated.items():
        path = Path(name)
        if path.parent != package or not path.is_file() or sha(path) != digest:
            errors.append("generated artifact differs: " + name)
    kernel = Path(manifest.get("kernel", ""))
    if kernel.parent != package or not kernel.is_file() or sha(kernel) != manifest.get("kernel_sha256"):
        errors.append("linked kernel differs")
    tests = manifest.get("focused_tests", {})
    if tests.get("tests") != 4 or tests.get("result") != "pass" or tests.get("a76_object") is not True:
        errors.append("focused test record differs")
    if len(manifest.get("remaining_board_prerequisites", [])) != 4:
        errors.append("remaining board prerequisites differ")
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "profile": "rpi5-gem-full-provider-offline-qualification-v5",
        "package": str(package),
        "manifest_sha256": sha(manifest_path),
        "kernel_sha256": manifest["kernel_sha256"],
        "source_manifest_sha256": sha(ROOT / "tools/rpi5/gem_full_provider_sources.json"),
        "provider_bytes": 0x48000,
        "ring_pages": 2,
        "packet_spans": 128,
        "packet_spans_cpu_owned": 128,
        "mapping_pages_normal_nc": 18,
        "ordered_page_proof_records": 18,
        "software_qualified": True,
        "board_qualified": False,
        "activation": activation,
        "claim": "linked default-off provider and host/A76 semantics only; no hardware activation",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = check(args.package)
    encoded = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded)
    print(encoded, end="")
