#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only checker for the default-off queue-zero admission candidate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.rpi5 import build_gem_queue_admission_candidate as builder


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(package, expected_manifest_sha256):
    package = Path(package).resolve()
    manifest_path = package / "manifest.json"
    if not package.is_relative_to(builder.ROOT / "build/rpi5"):
        raise ValueError("Distinct build/rpi5 package required")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256):
        raise ValueError("Exact manifest pin required")
    if sha256(manifest_path) != expected_manifest_sha256:
        raise ValueError("Manifest pin differs")
    manifest = json.loads(manifest_path.read_text())
    if manifest["profile"] != builder.PROFILE:
        raise ValueError("Profile differs")
    expected_inputs = {str(path): sha256(path) for path in builder.source_paths()}
    if manifest["inputs_sha256"] != expected_inputs:
        raise ValueError("Complete source closure differs")
    actual_generated = {
        str(path): sha256(path)
        for path in package.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if manifest["generated_sha256"] != actual_generated:
        raise ValueError("Generated closure differs")
    for row in manifest["commands"]:
        if row["returncode"] != 0 or row["cwd"] != str(builder.ROOT):
            raise ValueError("Command completion differs")
        if row["log_sha256"] != sha256(row["log"]):
            raise ValueError("Command log differs")
    labels = [row["label"] for row in manifest["commands"]]
    if labels != [
        "target-compile", "target-undefined", "target-disassembly",
        "host-compile", "host-run",
    ]:
        raise ValueError("Qualification recipe differs")
    obj = package / "rpi5_gem_queue_admission.o"
    if manifest["object"] != str(obj) or \
            manifest["object_sha256"] != sha256(obj) or \
            manifest["object_bytes"] != obj.stat().st_size:
        raise ValueError("Exact target object differs")
    if (package / "target-undefined.log").read_bytes() != b"":
        raise ValueError("Target object has unresolved symbols")
    if (package / "host-run.log").read_text() != (
        "GEM_QUEUE_ADMISSION_PASS DEFAULT_OFF BME0 RE0 TE0 IRQ0 "
        "DMA0 PACKETS0\n"
    ):
        raise ValueError("Host result differs")
    true_fields = (
        "software_qualified", "default_off", "queue_zero_only",
        "physical_prerequisites_satisfied",
    )
    false_fields = (
        "production_wired", "kernel_composed", "hardware_executed", "staged",
        "queue_registers_written_on_hardware", "bus_master_enabled",
        "gem_rx_enabled", "gem_tx_enabled", "interrupts_enabled",
        "dma_ownership_transfers", "packets", "interface_registered",
    )
    if not all(manifest[field] is True for field in true_fields) or \
            not all(manifest[field] is False for field in false_fields):
        raise ValueError("Authority boundary differs")
    if (
        manifest["provider_bytes_required"] != 0x48000 or
        manifest["ring_pages_required"] != 2 or
        manifest["ring_page_bytes"] != 0x4000 or
        manifest["packet_spans_required"] != 128 or
        manifest["packet_bytes_required"] != 2048 or
        manifest["packet_mapping_bytes_required"] != 0x40000
    ):
        raise ValueError("Full provider prerequisite differs")
    evidence = {
        "full_provider_manifest": (builder.FULL_PROVIDER_MANIFEST,
            builder.FULL_PROVIDER_MANIFEST_SHA256),
        "full_provider_capture_state": (builder.FULL_PROVIDER_CAPTURE_STATE,
            builder.FULL_PROVIDER_CAPTURE_STATE_SHA256),
        "full_provider_parsed": (builder.FULL_PROVIDER_PARSED,
            builder.FULL_PROVIDER_PARSED_SHA256),
    }
    for key, (path, digest) in evidence.items():
        if manifest.get(key) != str(path) or \
                manifest.get(key + "_sha256") != digest or sha256(path) != digest:
            raise ValueError("Full-provider evidence binding differs")
    source = builder.CORE.read_text() + builder.HEADER.read_text()
    if "SET_BME" in source or "set_bus_master" in source:
        raise ValueError("BME operation entered candidate")
    users = []
    for top in ("bsd", "iokit", "libkern", "osfmk", "pexpert", "security"):
        for path in (builder.ROOT / top).rglob("*"):
            if not path.is_file() or path in (builder.CORE, builder.HEADER):
                continue
            if path.suffix in (".c", ".cpp", ".h", ".inc") and \
                    "rpi5_gem_queue_admission.h" in path.read_text(errors="ignore"):
                users.append(str(path.relative_to(builder.ROOT)))
    if users:
        raise ValueError("Candidate is production-wired: " + ",".join(users))
    return {
        "profile": builder.PROFILE,
        "package": str(package),
        "manifest_sha256": expected_manifest_sha256,
        "object_sha256": manifest["object_sha256"],
        "result": "SOFTWARE_QUALIFIED_DEFAULT_OFF",
        "bme": False,
        "dma": False,
        "irq": False,
        "packets": False,
        "physical_prerequisites_satisfied": True,
        "next_gate": manifest["next_gate"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--expected-manifest-sha256", required=True)
    arguments = parser.parse_args()
    print(json.dumps(
        check(arguments.package, arguments.expected_manifest_sha256),
        indent=2, sort_keys=True,
    ))
