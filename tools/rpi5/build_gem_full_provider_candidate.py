#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the default-off full GEM provider; never stage or touch hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.rpi5 import build_gem_dma_memory_kernel as parent

ROOT = Path(__file__).resolve().parents[2]
PROFILE = "bcm2712-gem-full-retained-provider-default-off-v7"
BASE = ROOT / "build/rpi5/gem-dma-rings-20261014-v2"
BASE_MANIFEST_SHA256 = "01f55192a03dd5e0292d41f75b96aa861e40829b4e3ebf92871dc2aaba72eb82"
SOURCES = (
    "iokit/Kernel/BCM2712GEMDMAMemory.h",
    "iokit/Kernel/BCM2712GEMDMAMemory.cpp",
    "tools/rpi5/tests/gem_dma_memory_host.cpp",
    "tools/rpi5/tests/test_gem_dma_memory.py",
    "tools/rpi5/build_gem_dma_memory_kernel.py",
    "tools/rpi5/gem_dma_memory_sources.json",
    "tools/rpi5/build_gem_full_provider_candidate.py",
    "tools/rpi5/check_gem_full_provider_candidate.py",
    "tools/rpi5/tests/test_gem_full_provider_candidate.py",
    "tools/rpi5/gem_full_provider_sources.json",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(output):
    output = output.resolve()
    if output.parent != ROOT / "build/rpi5" or output.exists():
        raise ValueError("new distinct build/rpi5 directory required")
    source_manifest = json.loads((ROOT / "tools/rpi5/gem_full_provider_sources.json").read_text())
    if source_manifest.get("profile") != PROFILE:
        raise ValueError("exact full-provider source manifest required")
    expected = {row["path"]: row["sha256"] for row in source_manifest["sources"]}
    if set(expected) != set(SOURCES[:-1]):
        raise ValueError("source manifest inventory differs")
    for relative, digest in expected.items():
        if sha(ROOT / relative) != digest:
            raise ValueError("source hash differs: " + relative)

    base_manifest_path = BASE / "manifest.json"
    if sha(base_manifest_path) != BASE_MANIFEST_SHA256:
        raise ValueError("exact linked default-off Apple provider parent required")
    base = json.loads(base_manifest_path.read_text())
    output.mkdir()
    commands = []

    def run(command, log_name, cwd=ROOT):
        command = list(map(str, command))
        completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=300)
        log = output / log_name
        log.write_text(completed.stdout + completed.stderr)
        row = {"command": command, "cwd": str(cwd), "log": str(log),
               "returncode": completed.returncode}
        commands.append(row)
        if completed.returncode:
            raise ValueError("failed command: " + log_name)
        return row

    provider_object = output / "BCM2712GEMDMAMemory.cpp.o"
    compile_row = next(row for row in base["commands"]
        if row["log"].endswith("dma-rings-compile.log"))
    compile_command = list(compile_row["command"])
    old_object = BASE / "dma-rings.o"
    old_source = BASE / "overlay/BCM2712GEMDMARings.cpp"
    replacements = {
        str(old_object): str(provider_object),
        str(BASE / "dma-rings.d"): str(output / "BCM2712GEMDMAMemory.cpp.d"),
        str(old_source): str(ROOT / "iokit/Kernel/BCM2712GEMDMAMemory.cpp"),
    }
    compile_command = [replacements.get(value, value) for value in compile_command]
    compile_cwd = Path(compile_row["cwd"])
    run(compile_command, "provider-compile.log", compile_cwd)

    assembly_row = next(row for row in base["commands"]
        if row["log"].endswith("dma-rings-assembly.log"))
    assembly_command = list(assembly_row["command"])
    old_assembly = str(BASE / "dma-rings.s")
    assembly = output / "BCM2712GEMDMAMemory.cpp.s"
    assembly_replacements = {old_assembly: str(assembly), str(old_source):
        str(ROOT / "iokit/Kernel/BCM2712GEMDMAMemory.cpp")}
    if any(assembly_command.count(value) != 1 for value in assembly_replacements):
        raise ValueError("exact parent provider assembly command required")
    assembly_command = [assembly_replacements.get(value, value) for value in assembly_command]
    run(assembly_command, "provider-assembly.log", compile_cwd)

    old_filelist = BASE / "kernel.filelist"
    filelist_lines = old_filelist.read_text().splitlines()
    if str(provider_object) in filelist_lines or len(filelist_lines) != len(set(filelist_lines)):
        raise ValueError("parent filelist is not append-only compatible")
    filelist = output / "kernel.filelist"
    filelist.write_text("\n".join([*filelist_lines, str(provider_object)]) + "\n")

    link_row = next(row for row in base["commands"] if row["log"].endswith("/kernel-link.log"))
    old_unstripped = BASE / "kernel.unstripped"
    unstripped = output / "kernel.unstripped"
    old_map = BASE / "kernel.map"
    kernel_map = output / "kernel.map"
    link_replacements = {
        str(old_filelist): str(filelist),
        str(old_unstripped): str(unstripped),
        "-Wl,-map," + str(old_map): "-Wl,-map," + str(kernel_map),
    }
    if any(link_row["command"].count(value) != 1 for value in link_replacements):
        raise ValueError("exact parent link paths required")
    run([link_replacements.get(value, value) for value in link_row["command"]], "link.log")
    kernel = output / "kernel.full-provider"
    run(["xcrun", "strip", "-S", unstripped, "-o", kernel], "strip.log")
    symbols = subprocess.check_output(["xcrun", "nm", "-nm", kernel], text=True)
    (output / "kernel.symbols").write_text(symbols)
    unresolved = subprocess.check_output(["xcrun", "nm", "-ju", kernel], text=True).strip()
    if unresolved:
        raise ValueError("linked full provider has unresolved imports")

    result = dict(base)
    result.update({
        "parent_manifest": str(base_manifest_path),
        "parent_manifest_sha256": BASE_MANIFEST_SHA256,
        "default_off": True,
        "boot_caller_added": False,
        "constructor_added": False,
        "loader_created": False,
        "hardware_executed": False,
        "staged": False,
        "dma_enabled": False,
        "irq_enabled": False,
        "packets": False,
        "kernel": str(kernel),
        "kernel_sha256": sha(kernel),
        "kernel_bytes": kernel.stat().st_size,
        "added_objects": [*base["added_objects"], str(provider_object)],
        "commands": commands,
    })
    test = subprocess.run(
        ["python3", "-m", "unittest", "tools.rpi5.tests.test_gem_dma_memory"],
        cwd=ROOT, capture_output=True, text=True, timeout=180)
    if test.returncode != 0 or "Ran 4 tests" not in test.stderr or "OK" not in test.stderr:
        raise ValueError("provider host/A76 tests failed: " + test.stdout + test.stderr)
    (output / "focused-tests.log").write_text(test.stdout + test.stderr)

    symbols = (output / "kernel.symbols").read_text()
    if "observeCPUOwnedLayout" not in symbols:
        raise ValueError("full-provider observation method absent from linked kernel")
    assembly = (output / "BCM2712GEMDMAMemory.cpp.s").read_text()
    for token in ("s1e1r", "s1e1w", "PAR_EL1"):
        if token not in assembly:
            raise ValueError("A76 page proof missing: " + token)
    provider = (ROOT / SOURCES[1]).read_text()
    header = (ROOT / SOURCES[0]).read_text()
    for forbidden in ("write32(", "COMMAND.BME", "GEM_NCR", "GEM_RBQP", "GEM_TBQP"):
        if forbidden in provider:
            raise ValueError("hardware activation entered provider: " + forbidden)
    if "no constructor registration" not in header or "observeCPUOwnedLayout" not in header:
        raise ValueError("default-off provider boundary differs")

    result.update({
        "profile": PROFILE,
        "source_manifest": source_manifest,
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
        "focused_tests": {
            "command": "python3 -m unittest tools.rpi5.tests.test_gem_dma_memory",
            "tests": 4,
            "host_sanitizers": ["address", "undefined"],
            "a76_object": True,
            "result": "pass",
        },
        "activation": {
            "boot_caller": False,
            "bme": False,
            "gem_queue_registers": False,
            "gem_rx_tx": False,
            "dma_ownership": False,
            "interrupts": False,
            "packets": False,
            "hardware_executed": False,
            "staged": False,
        },
        "remaining_board_prerequisites": [
            "same-boot owner binds the retained provider to fresh released-window and GEM capability evidence",
            "board proves all 18 retained and static physmap pages Normal-NC before queue admission",
            "board proves all 128 packet spans remain CPU-owned and descriptors remain unchanged",
            "queue-zero register write/readback/reverse-restore trial runs separately with BME, RE/TE and IRQs disabled",
        ],
    })
    generated = {}
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "manifest.json":
            generated[str(path)] = sha(path)
    result["generated_sha256"] = generated
    (output / "manifest.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    manifest = build(parser.parse_args().output_dir)
    print(json.dumps({
        "profile": manifest["profile"],
        "kernel_sha256": manifest["kernel_sha256"],
        "provider_bytes": manifest["provider_bytes"],
        "packet_spans": manifest["packet_spans"],
        "hardware_executed": manifest["activation"]["hardware_executed"],
    }, sort_keys=True))
