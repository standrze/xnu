#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the discard-only page-granular GEM mapping verification image."""
import argparse, json, tempfile
from pathlib import Path
from tools.rpi5 import build_gem_dma_batch_trial as composer
from tools.rpi5 import build_gem_mapping_predicate_trial as lineage
from tools.rpi5 import gem_physmap_mapping_verification_profile as profile

ROOT = composer.ROOT
PROFILE = "bcm2712-gem-page-granular-mapping-verification-v1"
GATE = ROOT / "build/rpi5/gem-physmap-alias-gate-20261014-v7"
GATE_MANIFEST_SHA = "4e9b80ae101ab5201a5faf7e80c29773600c6c3b0604bd854af2abceb3f1907c"
CANONICAL = ROOT / "build/rpi5/gem-physmap-canonical-build-20261014-v2/qualification.json"
CANONICAL_SHA = "260ddf8001fe48fbdc014d86209db7d779c7db5f90480574fa32205dcbb37b30"
DISPLAY_PMAP = ROOT / "build/rpi5/display-xnu-console-5cd94fg_/pmap.c"
DISPLAY_PMAP_SHA = "13c6b9b2bfcfb29dcf3fbb130c8bbc546abfb8a6bf4cf8410e196eebcd79b16f"
_ORIGINAL_SOURCES = composer.sources
_ORIGINAL_DERIVED_SOURCES = composer.derived_sources
_ORIGINAL_PLAN = composer.plan
_ORIGINAL_KERNEL_OBJECTS = composer.kernel_objects
_ORIGINAL_PARENTS = composer.parents
_INTENTIONAL_VM_SOURCE_DELTA = {
    str(ROOT / "makedefs/MakeInc.def"),
    str(ROOT / "osfmk/arm/pmap/pmap.c"),
    str(ROOT / "osfmk/arm64/arm_vm_init.c"),
    str(ROOT / "osfmk/arm64/loose_ends.c"),
    str(ROOT / "osfmk/arm64/proc_reg.h"),
}


class _Profile:
    derive = staticmethod(profile.derive)
    sources = staticmethod(profile.sources)
    marker = staticmethod(lineage.inherited.retry.trial.marker)
    loader = staticmethod(lineage.inherited.retry.trial.loader)
    psci = staticmethod(lineage.inherited.retry.trial.psci)
    BOOTARGS = lineage.inherited.retry.trial.BOOTARGS


def sha(path):
    return composer.sha(path)


def sources():
    own = [Path(__file__).resolve(), ROOT / "tools/rpi5/check_gem_physmap_mapping_verification.py",
        ROOT / "tools/rpi5/tests/test_gem_physmap_mapping_verification.py",
        ROOT / "makedefs/MakeInc.def", ROOT / "osfmk/arm64/arm_vm_init.c",
        ROOT / "osfmk/arm64/loose_ends.c", ROOT / "osfmk/arm64/rpi5_gem_physmap_accounting.h",
        ROOT / "osfmk/arm64/rpi5_gem_physmap_bounds.h",
        ROOT / "tools/rpi5/qualify_gem_physmap_canonical_build.py",
        GATE / "manifest.json", CANONICAL, DISPLAY_PMAP]
    return list(dict.fromkeys([*_ORIGINAL_SOURCES(), *profile.sources(), *own]))


def parents():
    parents = _ORIGINAL_PARENTS()
    # These source bytes are intentionally superseded and their corresponding
    # inherited objects are replaced below.  All other immutable parent pins
    # remain byte-exact.
    for manifest in parents:
        for table in ("inputs_sha256", "actual_headers_sha256"):
            for path in list(manifest.get(table, {})):
                if path in _INTENTIONAL_VM_SOURCE_DELTA:
                    manifest[table][path] = sha(path)
    return parents


def derived_sources():
    result = _ORIGINAL_DERIVED_SOURCES()
    result["pmap.c"] = DISPLAY_PMAP.read_bytes()
    return result


def kernel_objects(output):
    result, replacements, extras, added = _ORIGINAL_KERNEL_OBJECTS(output)
    found = {}
    for index, path in enumerate(result):
        if Path(path).name in ("pmap.o", "arm_vm_init.o", "loose_ends.o"):
            if Path(path).name in found:
                raise ValueError("ambiguous VM object owner")
            found[Path(path).name] = (index, path)
    if set(found) != {"pmap.o", "arm_vm_init.o", "loose_ends.o"}:
        raise ValueError("exact VM object owners absent")
    for name, replacement in (("pmap.o", output / "pmap-enabled.o"),
                              ("arm_vm_init.o", output / "arm_vm_init-enabled.o"),
                              ("loose_ends.o", output / "loose_ends-enabled.o")):
        index, old = found[name]
        result[index] = str(replacement)
        replacements[old] = str(replacement)
    return result, replacements, extras, added


def _vm_command(output, unit, source, object_name):
    manifest = json.loads((GATE / "manifest.json").read_text())
    matches = [r for r in manifest["commands"] if r["unit"] == unit and r["mode"] == "enabled"]
    if len(matches) != 1:
        raise ValueError("exact enabled arm compile command absent")
    args = list(matches[0]["command"])
    originals = {"arm_vm_init": ROOT / "osfmk/arm64/arm_vm_init.c",
        "pmap": ROOT / "osfmk/arm/pmap/pmap.c", "loose_ends": ROOT / "osfmk/arm64/loose_ends.c"}
    original = str(originals[unit])
    if args.count(original) != 1 or args.count("-o") != 1 or "-DRPI5_GEM_PAGE_GRANULAR_PHYSMAP=1" not in args:
        raise ValueError("enabled arm compile command changed")
    args[args.index(original)] = str(source)
    args[args.index("-o") + 1] = str(output / object_name)
    args.insert(1, "-Wno-unused-but-set-variable")
    return args, matches[0]["cwd"]


def plan(output, tag):
    rows, scans = _ORIGINAL_PLAN(output, tag)
    index = next(i for i, row in enumerate(rows) if row[0] == "kernel-link")
    arm_args, arm_cwd = _vm_command(output, "arm_vm_init", ROOT / "osfmk/arm64/arm_vm_init.c", "arm_vm_init-enabled.o")
    pmap_args, pmap_cwd = _vm_command(output, "pmap", output / "pmap.c", "pmap-enabled.o")
    loose_args, loose_cwd = _vm_command(output, "loose_ends", ROOT / "osfmk/arm64/loose_ends.c", "loose_ends-enabled.o")
    rows[index:index] = [
        ("physmap-arm-object", list(map(str, arm_args)), arm_cwd),
        ("physmap-pmap-object", list(map(str, pmap_args)), pmap_cwd),
        ("physmap-loose-ends-object", list(map(str, loose_args)), loose_cwd),
        ("physmap-arm-disassembly", list(map(str, ["xcrun", "llvm-objdump", "-dr", output / "arm_vm_init-enabled.o"])), str(ROOT)),
        ("physmap-pmap-disassembly", list(map(str, ["xcrun", "llvm-objdump", "-dr", output / "pmap-enabled.o"])), str(ROOT)),
        ("physmap-loose-ends-disassembly", list(map(str, ["xcrun", "llvm-objdump", "-dr", output / "loose_ends-enabled.o"])), str(ROOT)),
    ]
    return rows, scans


def configure():
    lineage.configure()
    composer.PROFILE = PROFILE
    composer.profile = _Profile
    composer.sources = sources
    composer.core_sources = lineage.inherited.core_sources
    composer.derived_sources = derived_sources
    composer.kernel_objects = kernel_objects
    composer.plan = plan
    composer.parents = parents
    return composer


def build(output=None):
    if (sha(GATE / "manifest.json") != GATE_MANIFEST_SHA or sha(CANONICAL) != CANONICAL_SHA or
            sha(DISPLAY_PMAP) != DISPLAY_PMAP_SHA):
        raise ValueError("exact coupled physmap gate changed")
    output = Path(output).resolve() if output else Path(tempfile.mkdtemp(
        prefix="gem-physmap-mapping-verification-", dir=ROOT / "build/rpi5"))
    base = configure()
    output, manifest = base.build(output)
    manifest.update(profile=PROFILE, parent_mapping_profile=lineage.PROFILE,
        physmap_gate_manifest=str(GATE / "manifest.json"), physmap_gate_manifest_sha256=GATE_MANIFEST_SHA,
        canonical_build_qualification=str(CANONICAL), canonical_build_qualification_sha256=CANONICAL_SHA,
        display_pmap_source_sha256=DISPLAY_PMAP_SHA, build_opt_in="RPI5_GEM_PAGE_GRANULAR_PHYSMAP=1",
        verification_only=True, discard_before_route=True, mapping_rows=4,
        descriptor_stores=0, route_calls=0, queue_publication=False, bme_enable=False,
        dma_activation=False, irq_activation=False, packet_mapping=False,
        hardware_executed=False, staged=False, maximum_table_pages=259,
        maximum_table_bytes=259 * 0x4000, preallocated_upper_pages=1,
        generated_sha256={str(p): sha(p) for p in output.rglob("*") if p.is_file() and p.name != "manifest.json"})
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return output, manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    out, manifest = build(parser.parse_args().output_dir)
    print(json.dumps({"package": str(out), "manifest_sha256": sha(out / "manifest.json"),
        "kernel_sha256": manifest["kernel_sha256"], "image_sha256": manifest["image_sha256"]}, sort_keys=True))
