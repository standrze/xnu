#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the physmap-enabled, CPU-owned GEM ring successor; offline only.

The package retains the qualified ring-only v7 behavior and composes it with
the corrected v10 page-granular physmap implementation.  It allocates and
validates only two CPU-owned descriptor rings.  Queue publication, bus
mastering, IRQ/DMA activation, packet memory, packet submission and TX remain
absent.  This program never stages media or touches hardware.
"""
import argparse
import json
from pathlib import Path
import tempfile

from tools.rpi5 import build_gem_dma_batch_trial as composer
from tools.rpi5 import build_gem_cpu_ring_retry_trial as ring
from tools.rpi5 import gem_cpu_ring_retry_profile as retry

ROOT = composer.ROOT
PROFILE = "bcm2712-gem-physmap-cpu-owned-rings-v1"
RING_PARENT = ROOT / "build/rpi5/gem-cpu-ring-retry-trial-20261014-v7/manifest.json"
RING_PARENT_SHA = "532968eb3df2fcd6fb8f5dc3addfd11ddd2d1442c66b2ffc7f6de9bf5b744b64"
PHYSMAP_PARENT = ROOT / "build/rpi5/gem-physmap-mapping-verification-20261014-v10/manifest.json"
PHYSMAP_PARENT_SHA = "a73188d0234348025b151bc66ee7f5cb7763efd867871d23a4c5379eba7df141"
GATE = ROOT / "build/rpi5/gem-physmap-alias-gate-20261014-v7"
GATE_MANIFEST_SHA = "4e9b80ae101ab5201a5faf7e80c29773600c6c3b0604bd854af2abceb3f1907c"
CANONICAL = ROOT / "build/rpi5/gem-physmap-canonical-build-20261014-v2/qualification.json"
CANONICAL_SHA = "260ddf8001fe48fbdc014d86209db7d779c7db5f90480574fa32205dcbb37b30"
DISPLAY_PMAP = ROOT / "build/rpi5/display-xnu-console-5cd94fg_/pmap.c"
DISPLAY_PMAP_SHA = "13c6b9b2bfcfb29dcf3fbb130c8bbc546abfb8a6bf4cf8410e196eebcd79b16f"

_ORIGINAL_SOURCES = composer.sources
_ORIGINAL_PARENTS = composer.parents
_ORIGINAL_CORE_SOURCES = composer.core_sources
_ORIGINAL_DERIVED_SOURCES = composer.derived_sources
_ORIGINAL_KERNEL_OBJECTS = composer.kernel_objects
_ORIGINAL_PLAN = composer.plan
_INTENTIONAL_VM_SOURCE_DELTA = {
    str(ROOT / "makedefs/MakeInc.def"),
    str(ROOT / "osfmk/arm/pmap/pmap.c"),
    str(ROOT / "osfmk/arm64/arm_vm_init.c"),
    str(ROOT / "osfmk/arm64/loose_ends.c"),
    str(ROOT / "osfmk/arm64/proc_reg.h"),
}


class _Profile:
    derive = staticmethod(retry.derive)
    sources = staticmethod(retry.sources)
    marker = staticmethod(retry.trial.marker)
    loader = staticmethod(retry.trial.loader)
    psci = staticmethod(retry.trial.psci)
    BOOTARGS = retry.trial.BOOTARGS


def sha(path):
    return composer.sha(path)


def sources():
    own = [Path(__file__).resolve(),
        ROOT / "tools/rpi5/check_gem_cpu_ring_physmap_trial.py",
        ROOT / "tools/rpi5/tests/test_gem_cpu_ring_physmap_trial.py",
        RING_PARENT, PHYSMAP_PARENT, GATE / "manifest.json", CANONICAL,
        DISPLAY_PMAP, ROOT / "makedefs/MakeInc.def",
        ROOT / "osfmk/arm64/arm_vm_init.c", ROOT / "osfmk/arm64/loose_ends.c",
        ROOT / "osfmk/arm64/rpi5_gem_physmap_accounting.h",
        ROOT / "osfmk/arm64/rpi5_gem_physmap_bounds.h"]
    return list(dict.fromkeys([*_ORIGINAL_SOURCES(), *retry.sources(), *own]))


def parents():
    result = _ORIGINAL_PARENTS()
    for manifest in result:
        for table in ("inputs_sha256", "actual_headers_sha256"):
            for path in list(manifest.get(table, {})):
                if path in _INTENTIONAL_VM_SOURCE_DELTA:
                    manifest[table][path] = sha(path)
    return result


def core_sources():
    result = []
    for path in _ORIGINAL_CORE_SOURCES():
        result.append(ROOT / "iokit/Kernel/rpi5_gem_ring_only_batch.c"
            if path.name == "rpi5_gem_ring_batch.c" else path)
    result.append(ROOT / "iokit/Kernel/rpi5_gem_ram_window.c")
    return result


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
    matches = [row for row in manifest["commands"]
        if row["unit"] == unit and row["mode"] == "enabled"]
    if len(matches) != 1:
        raise ValueError("exact enabled arm compile command absent")
    args = list(matches[0]["command"])
    originals = {"arm_vm_init": ROOT / "osfmk/arm64/arm_vm_init.c",
        "pmap": ROOT / "osfmk/arm/pmap/pmap.c",
        "loose_ends": ROOT / "osfmk/arm64/loose_ends.c"}
    original = str(originals[unit])
    if (args.count(original) != 1 or args.count("-o") != 1 or
            "-DRPI5_GEM_PAGE_GRANULAR_PHYSMAP=1" not in args):
        raise ValueError("enabled arm compile command changed")
    args[args.index(original)] = str(source)
    args[args.index("-o") + 1] = str(output / object_name)
    args.insert(1, "-Wno-unused-but-set-variable")
    return args, matches[0]["cwd"]


def plan(output, tag):
    rows, scans = _ORIGINAL_PLAN(output, tag)
    index = next(i for i, row in enumerate(rows) if row[0] == "kernel-link")
    arm_args, arm_cwd = _vm_command(output, "arm_vm_init",
        ROOT / "osfmk/arm64/arm_vm_init.c", "arm_vm_init-enabled.o")
    pmap_args, pmap_cwd = _vm_command(output, "pmap", output / "pmap.c", "pmap-enabled.o")
    loose_args, loose_cwd = _vm_command(output, "loose_ends",
        ROOT / "osfmk/arm64/loose_ends.c", "loose_ends-enabled.o")
    rows[index:index] = [
        ("physmap-arm-object", list(map(str, arm_args)), arm_cwd),
        ("physmap-pmap-object", list(map(str, pmap_args)), pmap_cwd),
        ("physmap-loose-ends-object", list(map(str, loose_args)), loose_cwd),
        ("physmap-arm-disassembly", list(map(str,
            ["xcrun", "llvm-objdump", "-dr", output / "arm_vm_init-enabled.o"])), str(ROOT)),
        ("physmap-pmap-disassembly", list(map(str,
            ["xcrun", "llvm-objdump", "-dr", output / "pmap-enabled.o"])), str(ROOT)),
        ("physmap-loose-ends-disassembly", list(map(str,
            ["xcrun", "llvm-objdump", "-dr", output / "loose_ends-enabled.o"])), str(ROOT)),
    ]
    return rows, scans


def configure():
    composer.PROFILE = PROFILE
    composer.profile = _Profile
    composer.sources = sources
    composer.parents = parents
    composer.core_sources = core_sources
    composer.derived_sources = derived_sources
    composer.kernel_objects = kernel_objects
    composer.plan = plan
    return composer


def build(output=None):
    pins = ((RING_PARENT, RING_PARENT_SHA), (PHYSMAP_PARENT, PHYSMAP_PARENT_SHA),
        (GATE / "manifest.json", GATE_MANIFEST_SHA), (CANONICAL, CANONICAL_SHA),
        (DISPLAY_PMAP, DISPLAY_PMAP_SHA))
    if any(sha(path) != digest for path, digest in pins):
        raise ValueError("exact ring/physmap composition foundation changed")
    output = Path(output).resolve() if output else Path(tempfile.mkdtemp(
        prefix="gem-cpu-ring-physmap-trial-", dir=ROOT / "build/rpi5"))
    output, manifest = configure().build(output)
    manifest.update(profile=PROFILE, ring_parent_manifest=str(RING_PARENT),
        ring_parent_manifest_sha256=RING_PARENT_SHA,
        physmap_parent_manifest=str(PHYSMAP_PARENT),
        physmap_parent_manifest_sha256=PHYSMAP_PARENT_SHA,
        physmap_gate_manifest=str(GATE / "manifest.json"),
        physmap_gate_manifest_sha256=GATE_MANIFEST_SHA,
        canonical_build_qualification=str(CANONICAL),
        canonical_build_qualification_sha256=CANONICAL_SHA,
        build_opt_in="RPI5_GEM_PAGE_GRANULAR_PHYSMAP=1",
        allocation_bytes=0x8000, descriptor_pages=2, packet_spans=0,
        preparation_steps=17, preferred_ram_route_only=True,
        page_granular_physmap=True, cpu_ring_structure_validation=True,
        cpu_owned_descriptors_only=True, queue_publication=False,
        bme_enable=False, dma_activation=False, irq_activation=False,
        packet_mapping=False, packet_submission=False, tx_enable=False,
        hardware_executed=False, staged=False, maximum_table_pages=259,
        maximum_table_bytes=259 * 0x4000, preallocated_upper_pages=1,
        generated_sha256={str(path): sha(path) for path in output.rglob("*")
            if path.is_file() and path.name != "manifest.json"})
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return output, manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    package, manifest = build(parser.parse_args().output_dir)
    print(json.dumps({"package": str(package),
        "manifest_sha256": sha(package / "manifest.json"),
        "kernel_sha256": manifest["kernel_sha256"],
        "image_sha256": manifest["image_sha256"]}, sort_keys=True))
