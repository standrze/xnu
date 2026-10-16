#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the software-only BCM2712 GEM physmap-alias qualification gate.

This gate never builds or stages media.  It proves that the opt-in compiles as
one coupled change: page-granular physical-aperture construction plus XNU's
existing per-page physical-aperture cache-attribute update.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "build/rpi5/gem-mapping-predicate-capture-20261014/return.json"
SERIAL = EVIDENCE.parent / "serial.bin"
EVIDENCE_SHA = "79d461cb2d202c3735cca2f4bcf64ebc88b62fb4cb6088801f13d20e6e5bc084"
SERIAL_SHA = "5a756eddc8ac171bc2066b658044798fc5af3709546a92d01cedc61f2caf9be4"
COMPILE_DB = ROOT / "build/rpi5-xcode27/obj/DEVELOPMENT_ARM64_BCM2712/compile_commands.json"
FLAG = "RPI5_GEM_PAGE_GRANULAR_PHYSMAP"
SOURCES = {
    "pmap": ROOT / "osfmk/arm/pmap/pmap.c",
    "arm_vm_init": ROOT / "osfmk/arm64/arm_vm_init.c",
    "loose_ends": ROOT / "osfmk/arm64/loose_ends.c",
}
DIRECT_INPUTS = [
    ROOT / "makedefs/MakeInc.def",
    ROOT / "osfmk/arm64/proc_reg.h",
    ROOT / "iokit/Kernel/BCM2712GEMDMAMemory.cpp",
    ROOT / "tools/rpi5/gem_mapping_predicate_profile.py",
    EVIDENCE,
    SERIAL,
    COMPILE_DB,
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_coupling(makeinc=None, proc=None, arm=None):
    makeinc = makeinc if makeinc is not None else (ROOT / "makedefs/MakeInc.def").read_text()
    proc = proc if proc is not None else (ROOT / "osfmk/arm64/proc_reg.h").read_text()
    arm = arm if arm is not None else SOURCES["arm_vm_init"].read_text()
    errors = []
    make_block = "ifeq ($(RPI5_GEM_PAGE_GRANULAR_PHYSMAP),1)\nMACHINE_FLAGS_ARM64_BCM2712 += -DRPI5_GEM_PAGE_GRANULAR_PHYSMAP=1\nendif"
    if makeinc.count(make_block) != 1:
        errors.append("build flag is not an exact default-off BCM2712 opt-in")
    proc_guard = "defined(RPI5_GEM_PAGE_GRANULAR_PHYSMAP) && RPI5_GEM_PAGE_GRANULAR_PHYSMAP"
    if proc.count(proc_guard) != 1 or proc.count("#define __ARM_PTE_PHYSMAP__ 1") != 1:
        errors.append("pmap physical-aperture PTE update is not coupled to the opt-in")
    if arm.count(proc_guard) < 1:
        errors.append("page-granular physmap construction is not coupled to the opt-in")
    if arm.count("const unsigned physmap_granule = 0;") != 1:
        errors.append("enabled physmap does not force page granularity")
    if arm.count("AP_RWNA, physmap_granule") != 1 or arm.count("AP_RWNA,\n\t    physmap_granule") != 1:
        errors.append("both VM-returnable physical-aperture regions are not coupled")
    if errors:
        raise ValueError("; ".join(errors))


def evidence():
    if sha(EVIDENCE) != EVIDENCE_SHA or sha(SERIAL) != SERIAL_SHA:
        raise ValueError("exact accepted board evidence changed")
    report = json.loads(EVIDENCE.read_text())
    if not report.get("capture_valid") or not report.get("zero_serial_tx") or not report.get(
        "independent_normal_nvme_linux_return_verified"
    ):
        raise ValueError("board capture is not the accepted zero-TX returned trial")
    line = (b"RPI5XNU:PCIEID:DMA_MAP REASON=36 PAGE=0 ATTR=6 VA=2 PA=185532416 "
            b"PAR_R=18374686479857158912 PAR_W=18374686479857158912")
    if SERIAL.read_bytes().count(line) != 1:
        raise ValueError("exact static-physmap alias rejection is absent or ambiguous")
    return line.decode()


def compile_entry(entries, source):
    matches = [row for row in entries if Path(row["file"]).resolve() == source.resolve()]
    if len(matches) != 1:
        raise ValueError(f"expected one compile command for {source}, got {len(matches)}")
    return matches[0]


def compile_one(row, source, output, enabled):
    args = list(row["arguments"])
    if args.count("-o") != 1 or args.count(str(source)) != 1:
        raise ValueError("compile command owner changed")
    args[args.index("-o") + 1] = str(output)
    if enabled:
        args[1:1] = [f"-D{FLAG}=1"]
    run = subprocess.run(args, cwd=row["directory"], capture_output=True, timeout=180)
    log = output.with_suffix(".log")
    log.write_bytes(run.stdout + run.stderr)
    if run.returncode:
        raise ValueError(f"compile failed: {log}")
    return args, log


def disassemble(obj, symbol):
    run = subprocess.run(
        ["xcrun", "llvm-objdump", "-dr", f"--disassemble-symbols={symbol}", str(obj)],
        cwd=ROOT, capture_output=True, timeout=60,
    )
    marker = f"<{symbol}>:".encode()
    if run.returncode or marker not in run.stdout or len(run.stdout.splitlines()) < 8:
        raise ValueError(f"disassembly failed for {symbol}")
    return run.stdout


def build(output=None):
    evidence_line = evidence()
    validate_coupling()
    output = Path(output).resolve() if output else Path(tempfile.mkdtemp(
        prefix="gem-physmap-alias-gate-", dir=ROOT / "build/rpi5"))
    if output.parent != ROOT / "build/rpi5" or (output.exists() and any(output.iterdir())):
        raise ValueError("distinct empty build/rpi5 output required")
    output.mkdir(exist_ok=True)
    entries = json.loads(COMPILE_DB.read_text())
    commands = []
    # Clang constant-specializes arm_vm_physmap_init into its static helper, so
    # the granule delta is carried by arm_vm_physmap_slide rather than its caller.
    symbols = {"pmap": "_pmap_update_cache_attributes_locked", "arm_vm_init": "_arm_vm_physmap_slide",
               "loose_ends": "_bcopy_phys_internal"}
    artifacts = {}
    for name, source in SOURCES.items():
        row = compile_entry(entries, source)
        for enabled in (False, True):
            mode = "enabled" if enabled else "default"
            obj = output / f"{name}-{mode}.o"
            args, log = compile_one(row, source, obj, enabled)
            asm = output / f"{name}-{mode}.disassembly.txt"
            asm.write_bytes(disassemble(obj, symbols[name]))
            commands.append({"unit": name, "mode": mode, "command": args,
                "cwd": row["directory"], "log": str(log), "log_sha256": sha(log)})
            artifacts[str(obj)] = sha(obj)
            artifacts[str(asm)] = sha(asm)
        if (output / f"{name}-default.o").read_bytes() == (output / f"{name}-enabled.o").read_bytes():
            raise ValueError(f"{name} opt-in compiled identically to the default")
        default_asm = (output / f"{name}-default.disassembly.txt").read_text()
        enabled_asm = (output / f"{name}-enabled.disassembly.txt").read_text()
        if default_asm == enabled_asm:
            raise ValueError(f"{name} opt-in did not change the target function")
        if name == "pmap":
            for relocation in ("ARM64_RELOC_BRANCH26\t_phystokv", "ARM64_RELOC_BRANCH26\t_wimg_to_pte"):
                if relocation in default_asm or enabled_asm.count(relocation) != 1:
                    raise ValueError("physical-aperture cache rewrite was not added exactly once")
        elif name == "arm_vm_init":
            if "mov\tw6, #0x3" not in default_asm or "mov\tw6, wzr" not in enabled_asm:
                raise ValueError("physmap granule did not compile from block+hint to page-only")
        else:
            if (default_asm.count("ARM64_RELOC_BRANCH26\t_phystokv_range") != 2 or
                    enabled_asm.count("ARM64_RELOC_BRANCH26\t_phystokv_range") != 3 or
                    enabled_asm.count("ARM64_RELOC_BRANCH26\t_pmap_cache_attributes") != 2):
                raise ValueError("loose-ends physmap-copy policy did not follow the opt-in")
    inputs = {str(p): sha(p) for p in [*DIRECT_INPUTS, *SOURCES.values(), Path(__file__).resolve()]}
    manifest = {
        "profile": "bcm2712-gem-page-granular-physmap-alias-gate-v1",
        "hardware_executed": False,
        "media_staged": False,
        "default_enabled": False,
        "build_opt_in": f"RPI5_GEM_PAGE_GRANULAR_PHYSMAP=1 / -D{FLAG}=1",
        "accepted_board_failure": evidence_line,
        "safety_argument": [
            "The retained IOBufferMemoryDescriptor mapping already translates as Normal-NC to the exact PA.",
            "The rejected alias is XNU's static physical aperture, which remains a Normal-WB block mapping on the non-monitor BCM2712 build.",
            "The opt-in constructs VM-returnable physmap regions at page granularity and enables XNU's existing pmap cache-attribute update for the physical-aperture PTE.",
            "pmap_set_cache_attributes then updates the physmap PTE and every PV-tracked alias under the existing pvh lock and TLB synchronization.",
            "loose_ends.c is compiled with the same macro so physical copy/read/write paths consistently use the maintained physical aperture.",
            "Neither half is admitted independently; the provider's exact-PA and Normal-NC checks remain unchanged.",
        ],
        "limits": [
            "Software qualification only; a new zero-TX board trial must still prove PAR read/write Attr=0x44 for both retained and static aliases.",
            "Page-granular physmap consumes more page-table memory than block mappings.",
            "This does not enable BME, queues, DMA, IRQ, packet buffers, networking, or SSH.",
        ],
        "commands": commands,
        "inputs_sha256": inputs,
        "artifacts_sha256": artifacts,
    }
    path = output / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return output, manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    out, _ = build(parser.parse_args().output_dir)
    print(json.dumps({"package": str(out), "manifest_sha256": sha(out / "manifest.json")}, sort_keys=True))
