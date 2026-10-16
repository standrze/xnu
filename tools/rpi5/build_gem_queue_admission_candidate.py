#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the default-off queue-zero admission object and host qualification.

This does not compose a kernel, stage media, touch hardware, toggle BME, enable
DMA/IRQs, or publish packets.  Physical use remains blocked on the separate
0x48000 Apple mapping provider and its 128 packet-span proof.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PROFILE = "rpi5-gem-queue-admission-default-off-v2"
CORE = ROOT / "iokit/Kernel/rpi5_gem_queue_admission.c"
HEADER = ROOT / "iokit/Kernel/rpi5_gem_queue_admission.h"
HOST = ROOT / "tools/rpi5/tests/gem_queue_admission_host.c"
METADATA = ROOT / "tools/rpi5/gem_queue_admission_sources.json"
FULL_PROVIDER_MANIFEST = ROOT / "build/rpi5/gem-full-provider-trial-20261014-v13/manifest.json"
FULL_PROVIDER_MANIFEST_SHA256 = "c91ed69c129103004ad92f2aa74424c8730203ea42040d697123ced46e88d402"
FULL_PROVIDER_CAPTURE_STATE = ROOT / "build/rpi5/gem-full-provider-trial-capture-20261014-v12/state.json"
FULL_PROVIDER_CAPTURE_STATE_SHA256 = "d1da655143c760c83f13326ea74889b88ca7ec768275265a6a2d67c7f96eeab8"
FULL_PROVIDER_PARSED = ROOT / "build/rpi5/gem-full-provider-trial-capture-20261014-v12/parsed.json"
FULL_PROVIDER_PARSED_SHA256 = "47646e3b2eb58cb50c71eceb546a3a7b1fd36e1482307f50f2b1ef209061514f"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_paths():
    return [
        Path(__file__).resolve(),
        ROOT / "tools/rpi5/check_gem_queue_admission_candidate.py",
        ROOT / "tools/rpi5/tests/test_gem_queue_admission.py",
        ROOT / "tools/rpi5/tests/test_gem_queue_admission_package.py",
        CORE,
        HEADER,
        HOST,
        METADATA,
        FULL_PROVIDER_MANIFEST,
        FULL_PROVIDER_CAPTURE_STATE,
        FULL_PROVIDER_PARSED,
        ROOT / "iokit/Kernel/rpi5_gem_ring_stage.h",
        ROOT / "iokit/Kernel/rpi5_gem_dma.h",
    ]


def build(output):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / "build/rpi5"):
        raise ValueError("Distinct build/rpi5 package required")
    output.mkdir(exist_ok=False)
    evidence = (
        (FULL_PROVIDER_MANIFEST, FULL_PROVIDER_MANIFEST_SHA256),
        (FULL_PROVIDER_CAPTURE_STATE, FULL_PROVIDER_CAPTURE_STATE_SHA256),
        (FULL_PROVIDER_PARSED, FULL_PROVIDER_PARSED_SHA256),
    )
    for path, digest in evidence:
        if not path.is_file() or sha256(path) != digest:
            raise ValueError("Full-provider board prerequisite differs: " + str(path))
    captured = json.loads(FULL_PROVIDER_CAPTURE_STATE.read_text())
    parsed = json.loads(FULL_PROVIDER_PARSED.read_text())
    if captured.get("status") != "captured" or captured.get("transmitted_bytes") != 0 or \
            not captured.get("normal_nvme_return") or parsed != {
                "bme": False, "detailed_evidence_records": 146, "dma": False,
                "gem_imr": "3fffffff", "interrupts_masked": True, "irq": False,
                "packet_span_records": 128, "packets_submitted": False,
                "page_records": 18, "provider_bytes": 0x48000,
                "queues_changed": False, "status": "pass"}:
        raise ValueError("Full-provider board prerequisite did not pass exactly")
    metadata = json.loads(METADATA.read_text())
    for row in metadata["sources"]:
        path = ROOT / row["path"]
        if path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
            raise ValueError("Primary source pin differs: " + str(path))
    inputs = {str(path): sha256(path) for path in source_paths()}
    commands = []

    def run(command, label, timeout=60):
        command = [str(item) for item in command]
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, timeout=timeout
        )
        log = output / (label + ".log")
        log.write_bytes(result.stdout + result.stderr)
        commands.append({
            "label": label,
            "command": command,
            "cwd": str(ROOT),
            "returncode": result.returncode,
            "log": str(log),
            "log_sha256": sha256(log),
        })
        if result.returncode != 0 or b"warning:" in result.stderr:
            raise ValueError("Qualification command failed: " + str(log))
        return result.stdout

    obj = output / "rpi5_gem_queue_admission.o"
    dep = output / "rpi5_gem_queue_admission.d"
    run([
        "xcrun", "clang", "--target=aarch64-none-elf", "-mcpu=cortex-a76",
        "-mstrict-align", "-mgeneral-regs-only", "-ffreestanding",
        "-fno-builtin", "-fno-stack-protector", "-std=c11", "-O2",
        "-Wall", "-Wextra", "-Werror", "-I", CORE.parent, "-c", "-MD",
        "-MF", dep, CORE, "-o", obj,
    ], "target-compile")
    undefined = run(
        ["xcrun", "llvm-nm", "--undefined-only", obj], "target-undefined"
    )
    if undefined.strip():
        raise ValueError("Target object gained undefined symbols")
    run(["xcrun", "llvm-objdump", "-d", obj], "target-disassembly")
    executable = output / "gem_queue_admission_host"
    run([
        "xcrun", "clang", "-std=c11", "-O1", "-g", "-Wall", "-Wextra",
        "-Werror", "-fsanitize=address,undefined", "-I", CORE.parent, CORE,
        HOST, "-o", executable,
    ], "host-compile")
    host_output = run([executable], "host-run")
    expected = (
        b"GEM_QUEUE_ADMISSION_PASS DEFAULT_OFF BME0 RE0 TE0 IRQ0 "
        b"DMA0 PACKETS0\n"
    )
    if host_output != expected:
        raise ValueError("Host qualification output differs")
    for path, digest in inputs.items():
        if sha256(path) != digest:
            raise ValueError("Input changed during build: " + path)
    manifest = {
        "profile": PROFILE,
        "inputs_sha256": inputs,
        "commands": commands,
        "object": str(obj),
        "object_sha256": sha256(obj),
        "object_bytes": obj.stat().st_size,
        "software_qualified": True,
        "default_off": True,
        "production_wired": False,
        "kernel_composed": False,
        "hardware_executed": False,
        "staged": False,
        "queue_zero_only": True,
        "queue_registers_written_on_hardware": False,
        "bus_master_enabled": False,
        "gem_rx_enabled": False,
        "gem_tx_enabled": False,
        "interrupts_enabled": False,
        "dma_ownership_transfers": False,
        "packets": False,
        "interface_registered": False,
        "provider_bytes_required": 0x48000,
        "ring_pages_required": 2,
        "ring_page_bytes": 0x4000,
        "packet_spans_required": 128,
        "packet_bytes_required": 2048,
        "packet_mapping_bytes_required": 0x40000,
        "physical_prerequisites_satisfied": True,
        "full_provider_manifest": str(FULL_PROVIDER_MANIFEST),
        "full_provider_manifest_sha256": FULL_PROVIDER_MANIFEST_SHA256,
        "full_provider_capture_state": str(FULL_PROVIDER_CAPTURE_STATE),
        "full_provider_capture_state_sha256": FULL_PROVIDER_CAPTURE_STATE_SHA256,
        "full_provider_parsed": str(FULL_PROVIDER_PARSED),
        "full_provider_parsed_sha256": FULL_PROVIDER_PARSED_SHA256,
        "next_gate": (
            "Compose this core with the exact passing full provider and live "
            "catalog owner, then run one queue-0 save/write/readback/reverse-"
            "restore trial with BME, NCR and DMA remaining off."
        ),
    }
    manifest["generated_sha256"] = {
        str(path): sha256(path)
        for path in output.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    result = build(arguments.output)
    print(json.dumps({
        "package": str(Path(arguments.output).resolve()),
        "manifest_sha256": sha256(Path(arguments.output) / "manifest.json"),
        "object_sha256": result["object_sha256"],
    }, sort_keys=True))
