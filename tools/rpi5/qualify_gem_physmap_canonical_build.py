#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Seal a full XNU BCM2712 opt-in build and its three affected VM objects."""
import argparse, hashlib, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLAG = "RPI5_GEM_PAGE_GRANULAR_PHYSMAP=1"
UNITS = ("pmap.c", "arm_vm_init.c", "loose_ends.c")
MAXIMUM_TABLE_PAGES = 259
MAXIMUM_PHYSMAP_HIERARCHY_PAGES = 258
PREALLOCATED_UPPER_PAGES = 1
PAGE_BYTES = 0x4000


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def qualify(build_manifest, output):
    build_manifest = Path(build_manifest).resolve()
    report = json.loads(build_manifest.read_text())
    if report.get("exit_code") != 0 or report.get("profile") != "xcode27":
        raise ValueError("successful full Xcode27 BCM2712 build required")
    if not report.get("source_unchanged_during_build"):
        raise ValueError("source changed during full build")
    command = report.get("command", [])
    if "TARGET_CONFIGS=DEVELOPMENT ARM64 BCM2712" not in command or command[-1:] != ["all"]:
        raise ValueError("full BCM2712 DEVELOPMENT make link required")
    root = Path(report["output_root"])
    objroot = root / "obj/DEVELOPMENT_ARM64_BCM2712"
    database = objroot / "compile_commands.json"
    kernel = objroot / "kernel.development.bcm2712"
    if sha(kernel) != report["kernel_artifact"]["sha256"]:
        raise ValueError("linked kernel differs from build manifest")
    rows = json.loads(database.read_text())
    objects = {}
    compiles = {}
    for name in UNITS:
        matches = [row for row in rows if Path(row["file"]).name == name]
        if len(matches) != 1 or FLAG not in matches[0].get("arguments", []):
            raise ValueError("canonical make flag did not reach " + name)
        obj = objroot / "osfmk/DEVELOPMENT" / (Path(name).stem + ".o")
        if not obj.is_file():
            raise ValueError("canonical object absent: " + name)
        objects[str(obj)] = sha(obj)
        compiles[name] = matches[0]
    symbols = subprocess.run(["xcrun", "nm", str(kernel)], cwd=ROOT,
        capture_output=True, text=True, timeout=60, check=True).stdout
    for symbol in ("_rpi5_gem_physmap_accounting", "_rpi5_gem_physmap_stats", "_pmap_update_cache_attributes_locked"):
        if symbol not in symbols:
            raise ValueError("linked opt-in symbol absent: " + symbol)
    disassembly = {}
    for name in UNITS:
        obj = objroot / "osfmk/DEVELOPMENT" / (Path(name).stem + ".o")
        run = subprocess.run(["xcrun", "llvm-objdump", "-dr", str(obj)], cwd=ROOT,
            capture_output=True, timeout=90, check=True)
        disassembly[name] = hashlib.sha256(run.stdout).hexdigest()
        if name == "pmap.c" and b"_phystokv" not in run.stdout:
            raise ValueError("canonical pmap lacks physmap update path")
        if name == "loose_ends.c" and b"_phystokv_range" not in run.stdout:
            raise ValueError("canonical loose-ends physmap path absent")
        if name == "arm_vm_init.c" and b"_rpi5_gem_physmap_stats" not in run.stdout:
            raise ValueError("canonical bootstrap accounting absent")
    result = {
        "profile": "bcm2712-gem-physmap-canonical-build-qualification-v1",
        "hardware_executed": False,
        "media_staged": False,
        "build_manifest": str(build_manifest),
        "build_manifest_sha256": sha(build_manifest),
        "compile_commands": str(database),
        "compile_commands_sha256": sha(database),
        "kernel": str(kernel),
        "kernel_sha256": sha(kernel),
        "objects_sha256": objects,
        "disassembly_sha256": disassembly,
        "flag": FLAG,
        "affected_units": list(UNITS),
        "predicted_maximum_table_pages": MAXIMUM_TABLE_PAGES,
        "predicted_maximum_table_bytes": MAXIMUM_TABLE_PAGES * PAGE_BYTES,
        "predicted_maximum_physmap_hierarchy_pages": MAXIMUM_PHYSMAP_HIERARCHY_PAGES,
        "preallocated_upper_pages": PREALLOCATED_UPPER_PAGES,
        "measured_delta_components": ["physmap_l3_leaf_pages", "direct_kva_partial_edge_pages"],
        "actual_table_delta_source": "rpi5_gem_physmap_accounting runtime START/END/BYTES/PAGES",
        "actual_table_delta": None,
        "actual_delta_requires_board_capture": True,
        "linked_symbols_verified": True,
        "source_unchanged_during_build": True,
    }
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("distinct qualification output required")
    output.mkdir()
    target = output / "qualification.json"
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = qualify(args.build_manifest, args.output)
    print(json.dumps({"qualification": str(target), "sha256": sha(target)}, sort_keys=True))
