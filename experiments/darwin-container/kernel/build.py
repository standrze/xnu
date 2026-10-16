#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Snapshot the dirty source port and build a distinct, isolated VZGENERIC XNU.

All generated files remain beneath this experiment's kernel/build directory.
No root source, physical Pi build output, SDK, or provider object is modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE_TREES = (
    "bsd", "config", "EXTERNAL_HEADERS", "iokit", "libkern", "libsa", "libkdd",
    "libsyscall", "makedefs", "osfmk", "pexpert", "san", "security", "SETUP", "tools/lldbmacros",
)
SOURCE_FILES = ("Makefile", "APPLE_LICENSE")
# These are portable source-only provider, ABI, memory and missing-Apple-service
# fallbacks. Hardware startup, CPU handoff, interrupts and platform personality
# are intentionally NOT widened by this list.
PORTABLE_GUARDS = (
    "bsd/kern/decmpfs.c", "bsd/kern/kern_exec.c", "bsd/kern/kern_mib.c",
    "bsd/kern/kern_trustcache.c", "bsd/miscfs/mockfs/mockfs_paging_policy.h",
    "bsd/net/necp_client.c", "bsd/nfs/gss/gss_krb5_mech.c", "bsd/sys/trust_caches.h",
    "bsd/uxkern/ux_exception.c", "bsd/vm/vm_unix.c", "iokit/Kernel/IOService.cpp",
    "iokit/Kernel/IOStartIOKit.cpp", "iokit/bsddev/IOKitBSDInit.cpp",
    "libkern/amfi/amfi.c", "libkern/c++/OSKext.cpp", "libkern/crypto/corecrypto_aesxts.c",
    "libkern/crypto/register_crypto.c", "libkern/libkern/amfi/amfi.h",
    "osfmk/arm/commpage/commpage.c", "osfmk/arm/machine_routines.h",
    "osfmk/arm/pmap/pmap.c", "osfmk/arm/pmap/pmap.h", "osfmk/kern/debug.c",
    "osfmk/kern/kalloc.c", "osfmk/kern/startup.c", "osfmk/kern/zalloc.c",
    "osfmk/mach/arm/vm_param.h", "osfmk/prng/prng_random.c", "osfmk/vm/pmap_cs.h",
)
BCM = "defined(ARM64_BOARD_CONFIG_BCM2712)"
PORTABLE = "(defined(ARM64_BOARD_CONFIG_BCM2712) || defined(ARM64_BOARD_CONFIG_VZGENERIC))"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n")


def replace(path: Path, old: str, new: str, *, count: int | None = 1) -> None:
    text = path.read_text()
    observed = text.count(old)
    if not observed or (count is not None and observed != count):
        raise ValueError(f"source drift in {path}: expected {count} occurrences of {old!r}, got {observed}")
    path.write_text(text.replace(old, new))


def snapshot(destination: Path) -> dict[str, str]:
    copied = {}
    for name in SOURCE_TREES:
        origin = ROOT / name
        for path in sorted(origin.rglob("*")):
            if not path.is_file() or path.is_symlink() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(ROOT)
            output = destination / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            before = digest(path)
            shutil.copy2(path, output)
            if before != digest(output) or before != digest(path):
                raise ValueError(f"source changed during copy: {relative}")
            copied[str(relative)] = before
    extras = (*SOURCE_FILES, "tools/Makefile", "tools/rpi5/export_policy.py", "tools/rpi5/LICENSE", "tools/vm_sanitize_enforcement.py",
              "tools/xcrun_cache.sh", "loader/vz/virtio_console.c", "loader/vz/virtio_console.h")
    for name in extras:
        source = ROOT / name
        output = destination / name
        output.parent.mkdir(parents=True, exist_ok=True)
        before = digest(source)
        shutil.copy2(source, output)
        if before != digest(output) or before != digest(source):
            raise ValueError(f"source changed during copy: {name}")
        copied[name] = before
    # The physical project can keep working. If it changed our inputs while the
    # snapshot was assembled, abort instead of calling a mixed revision frozen.
    for name, expected in copied.items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"source changed while snapshot was assembled: {name}")
    return copied


def apply_overlay(source: Path) -> None:
    for name in PORTABLE_GUARDS:
        replace(source / name, BCM, PORTABLE, count=None)
    for name in ("makedefs/MakeInc.def", "makedefs/MakeInc.kernel", "config/Makefile"):
        replace(source / name, "ifeq ($(CURRENT_MACHINE_CONFIG),BCM2712)",
                "ifneq ($(filter $(CURRENT_MACHINE_CONFIG),BCM2712 VZGENERIC),)", count=None)
    make = source / "makedefs/MakeInc.def"
    replace(make, "VMAPPLE BCM2712\n", "VMAPPLE BCM2712 VZGENERIC\n")
    replace(make, "SOURCE_ONLY_MACHINE_CONFIGS := BCM2712", "SOURCE_ONLY_MACHINE_CONFIGS := BCM2712 VZGENERIC")
    anchor = "MACHINE_FLAGS_ARM64_BCM2712 = -DARM64_BOARD_CONFIG_BCM2712              -mcpu=cortex-a76"
    replace(make, anchor, anchor + "\nMACHINE_FLAGS_ARM64_VZGENERIC = -DARM64_BOARD_CONFIG_VZGENERIC -march=armv8.1-a")
    for flag in ("PTHREAD_PROVIDER", "CRYPTO_STARTUP"):
        old = f"MACHINE_FLAGS_ARM64_BCM2712 += -DRPI5_{flag}=1"
        replace(make, old, old + f"\nMACHINE_FLAGS_ARM64_VZGENERIC += -DRPI5_{flag}=1")
    replace(source / "tools/rpi5/export_policy.py", 'if not boolean("CONFIG_RPI5_BRINGUP") or not boolean("DEVELOPMENT"):',
            'if not (boolean("CONFIG_RPI5_BRINGUP") or boolean("CONFIG_VZGENERIC_BRINGUP")) or not boolean("DEVELOPMENT"):')
    replace(source / "pexpert/pexpert/arm64/board_config.h", "#ifdef ARM64_BOARD_CONFIG_BCM2712",
            "#ifdef ARM64_BOARD_CONFIG_VZGENERIC\n#include <pexpert/arm64/VZGENERIC.h>\n#endif\n#ifdef ARM64_BOARD_CONFIG_BCM2712")
    replace(source / "pexpert/pexpert/arm64/Makefile", "\tBCM2712.h \\", "\tBCM2712.h \\\n\tVZGENERIC.h \\")
    # Select only shared low-level source closure, not Pi PSCI/SMP/soak files.
    file_list = source / "osfmk/conf/files.arm64"
    additions = [line.replace("config_rpi5_bringup", "config_vzgeneric_bringup")
                 for line in file_list.read_text().splitlines()
                 if "optional config_rpi5_bringup" in line and "/rpi5_" not in line]
    with file_list.open("a") as output:
        output.write("\n# Isolated generic VZ legacy ARM bootstrap.\n" + "\n".join(additions) + "\n")
        output.write("osfmk/arm64/vz_stack_probe.s optional config_vzgeneric_bringup\n")
    # The DEVELOPMENT panic-test sysctl otherwise refers unconditionally to
    # two functions that live only in CONFIG_XNUPOST's platform_tests.c.
    replace(source / "bsd/kern/kern_sysctl.c", "#if __arm64__ && (DEVELOPMENT || DEBUG)",
            "#if __arm64__ && (DEVELOPMENT || DEBUG) && CONFIG_XNUPOST")
    replace(source / "pexpert/conf/files.arm64", "pexpert/arm/pe_fiq.c                   standard",
            "pexpert/arm/pe_vzgeneric.c             standard\npexpert/arm/virtio_console.c           standard")
    with (source / "iokit/conf/files").open("a") as output:
        output.write("\niokit/Kernel/VZGenericPlatformExpert.cpp optional iokitcpp\n")
    # Portable ISA/cache fallback; do not enable VMAPPLE's private PAC/CTRR ABI.
    replace(source / "osfmk/arm64/proc_reg.h", "defined (ARM64_BOARD_CONFIG_BCM2712)", PORTABLE)
    replace(source / "osfmk/arm64/proc_reg.h", "#if __ARM_42BIT_PA_SPACE__\n#define TCR_IPS_VALUE",
            "#if defined(ARM64_BOARD_CONFIG_VZGENERIC)\n#define TCR_IPS_VALUE TCR_IPS_36BITS\n#elif __ARM_42BIT_PA_SPACE__\n#define TCR_IPS_VALUE")
    # Pi markers and UART page tables stay disabled. Only absence of Apple
    # tunables and the architecturally required SIMD ISB are shared.
    replace(source / "osfmk/arm64/start.s", "#if !" + BCM, "#if !" + PORTABLE, count=None)
    replace(source / "osfmk/arm64/start.s", "#if " + BCM + "\n\t/* Synchronize FP/SIMD", "#if " + PORTABLE + "\n\t/* Synchronize FP/SIMD")
    arm_init = source / "osfmk/arm/arm_init.c"
    replace(arm_init, "#if " + BCM, "#if " + PORTABLE, count=None)
    # Leave the pre-/post-VM Pi UART blocks Pi-only.
    replace(arm_init, "#if " + PORTABLE + "\n#include <arm64/rpi5_boot_uart.h>", "#if " + BCM + "\n#include <arm64/rpi5_boot_uart.h>")
    replace(arm_init, "#if " + PORTABLE + "\n\t/* Use the normal post-VM I/O allocator", "#if " + BCM + "\n\t/* Use the normal post-VM I/O allocator")
    replace(arm_init, 'SecureDTGetProperty(chosen, "rpi5-memory-map",', 'SecureDTGetProperty(chosen, "vz-memory-map",')
    replace(source / "osfmk/arm64/arm_vm_init.c", "#if !" + BCM, "#if !" + PORTABLE, count=None)
    # VZ runs one homogeneous CPU. Keep generic topology and timer startup.
    replace(source / "osfmk/arm64/machine_routines.c", BCM, PORTABLE, count=None)
    replace(source / "iokit/Kernel/IOCPU.cpp", "#if " + BCM + " && DEVELOPMENT",
            "#if defined(ARM64_BOARD_CONFIG_VZGENERIC) && DEVELOPMENT\n\treturn false;\n#elif " + BCM + " && DEVELOPMENT")
    table = source / "iokit/KernelConfigTables.cpp"
    replace(table, '    "("\n', '    "("\n#if defined(ARM64_BOARD_CONFIG_VZGENERIC)\n'
            '    " { IOClass=VZGenericPlatformExpert; IOProviderClass=IOPlatformExpertDevice;"\n'
            '    " IONameMatch=device-tree; IOProbeScore=1000:32; },"\n#endif\n')
    prototypes = source / "pexpert/pexpert/arm/protos.h"
    replace(prototypes, "void pe_init_fiq(void);", "void pe_init_fiq(void);\n#if defined(ARM64_BOARD_CONFIG_VZGENERIC)\n"
            "uint32_t pe_vz_irq_acknowledge(void);\nvoid pe_vz_irq_complete(uint32_t);\n"
            "void pe_vz_send_self_sgi(void);\nint pe_vz_halt_restart(unsigned int);\n#endif")
    sleh = source / "osfmk/arm64/sleh.c"
    replace(sleh, "#if " + BCM + " && !defined(HAS_IPI)", "#if " + PORTABLE + " && !defined(HAS_IPI)")
    replace(sleh, "#elif USE_APPLEARMSMP\n\tPE_handle_ext_interrupt();",
            "#elif defined(ARM64_BOARD_CONFIG_VZGENERIC)\n"
            "\tuint32_t iar = pe_vz_irq_acknowledge();\n"
            "\tif (iar == 27U) {\n"
            "\t\tif (!ml_get_timer_pending()) panic(\"VZGENERIC: timer IRQ without pending timer\");\n"
            "\t\tcdp->cpu_decrementer = -1;\n"
            "\t\tml_interrupt_masked_debug_start(rtclock_intr, DBG_INTR_TYPE_TIMER);\n"
            "\t\trtclock_intr(TRUE);\n\t\tml_interrupt_masked_debug_end();\n"
            "\t\tpe_vz_irq_complete(iar);\n"
            "\t} else if (iar == 1U) {\n\t\tpe_vz_irq_complete(iar);\n\t\tcpu_signal_handler();\n"
            "\t} else if (iar < 1020U || iar > 1023U) {\n"
            "\t\tpanic(\"VZGENERIC: unexpected IRQ %u\", iar);\n\t}\n"
            "#elif USE_APPLEARMSMP\n\tPE_handle_ext_interrupt();")
    serial = source / "pexpert/arm/pe_serial.c"
    replace(serial, "static const struct {\n\tconst char *const compatible;",
            '#include "vz_serial.inc"\n\nstatic const struct {\n\tconst char *const compatible;')
    replace(serial, "} driver_setup_functions[] = {", '} driver_setup_functions[] = {\n\t{ .compatible = "virtio,pci-console", .setup = vz_serial_setup },')
    # Copy transport implementation verbatim; maintain its provenance hash.
    for name in ("virtio_console.h", "virtio_console.c"):
        shutil.copy2(source / "loader/vz" / name, source / "pexpert/arm" / name)
    for path in sorted((HERE / "overlay").rglob("*")):
        if path.is_file():
            output = source / path.relative_to(HERE / "overlay")
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, output)
    apply_early_trace(source)
    apply_early_trace_stage2(source)
    apply_early_trace_stage3(source)
    apply_physmap_alignment_fix(source)
    apply_timer_irq_fix(source)
    # Only this isolated VM snapshot changes; preserve qualified kernels and
    # the shared physical-platform source. native_rand is 192, not 256 bytes.
    replace(source / "osfmk/prng/prng_random.c",
            "cc_clear(BOOTLOADER_ENTROPY_REQUEST_SIZE, native_rand);",
            "cc_clear(sizeof(native_rand), native_rand);")


def apply_timer_irq_fix(source: Path) -> None:
    """Install the testable VZ dispatcher, including stale level-timer handling."""
    path = source / "osfmk/arm64/sleh.c"
    replacement = '#include "vz_irq.inc"\n'
    if replacement in path.read_text():
        return
    old = ("\tuint32_t iar = pe_vz_irq_acknowledge();\n"
           "\tif (iar == 27U) {\n"
           "\t\tif (!ml_get_timer_pending()) panic(\"VZGENERIC: timer IRQ without pending timer\");\n"
           "\t\tcdp->cpu_decrementer = -1;\n"
           "\t\tml_interrupt_masked_debug_start(rtclock_intr, DBG_INTR_TYPE_TIMER);\n"
           "\t\trtclock_intr(TRUE);\n\t\tml_interrupt_masked_debug_end();\n"
           "\t\tpe_vz_irq_complete(iar);\n"
           "\t} else if (iar == 1U) {\n\t\tpe_vz_irq_complete(iar);\n\t\tcpu_signal_handler();\n"
           "\t} else if (iar < 1020U || iar > 1023U) {\n"
           "\t\tpanic(\"VZGENERIC: unexpected IRQ %u\", iar);\n\t}\n")
    replace(path, old, replacement)


def apply_early_trace(source: Path) -> None:
    """Add diagnostic checkpoints without changing Pi startup or MMIO maps."""
    startup = source / "osfmk/arm64/start.s"
    if '#include "vz_early_trace.inc"' in startup.read_text():
        return
    replace(startup, "\t.globl EXT(_start)\n", '#include "vz_early_trace.inc"\n\n\t.globl EXT(_start)\n')
    replace(startup, "LEXT(start_first_cpu)\n", "LEXT(start_first_cpu)\n"
            "#if defined(ARM64_BOARD_CONFIG_VZGENERIC)\n"
            "\tmov x27, x2\n\tmsr DAIFSet, #(DAIFSC_ALL)\n"
            "\tadrp x9, L_vz_early_vectors@page\n\tadd x9, x9, L_vz_early_vectors@pageoff\n"
            "\tmsr VBAR_EL1, x9\n\tisb\n\tvz_early_mark 88 // X: before OSLAR\n#endif\n")
    # Replace the first-CPU low-vector address only; our ESR dumper deliberately
    # parks after an exception rather than attempting recovery.
    text = startup.read_text()
    prefix, body = text.split("LEXT(start_first_cpu)\n", 1)
    body = body.replace("\tadrp\tx0, EXT(LowExceptionVectorBase)@page\n"
                        "\tadd\t\tx0, x0, EXT(LowExceptionVectorBase)@pageoff\n",
                        "#if defined(ARM64_BOARD_CONFIG_VZGENERIC)\n"
                        "\tadrp x0, L_vz_early_vectors@page\n\tadd x0, x0, L_vz_early_vectors@pageoff\n"
                        "#else\n\tadrp\tx0, EXT(LowExceptionVectorBase)@page\n"
                        "\tadd\t\tx0, x0, EXT(LowExceptionVectorBase)@pageoff\n#endif\n", 1)
    startup.write_text(prefix + "LEXT(start_first_cpu)\n" + body)
    for byte, label in ((68, "debug unlock and DAIF complete"), (65, "boot arguments read"),
                        (90, "bootstrap tables cleared"), (80, "bootstrap mappings populated"),
                        (77, "final pre-MMU checkpoint, physical UART still valid")):
        old = f"\trpi5_pre_mmu_mark {byte} // {chr(byte)}: {label}\n#endif"
        replace(startup, old, old + f"\n#if defined(ARM64_BOARD_CONFIG_VZGENERIC)\n\tvz_early_mark {byte}\n#endif")


def apply_early_trace_stage2(source: Path) -> None:
    startup = source / "osfmk/arm64/start.s"
    if "\tvz_early_map_io\n" in startup.read_text():
        return
    replace(startup, "\tmov x27, x2\n\tmsr DAIFSet, #(DAIFSC_ALL)\n",
            "\tmov x27, x2\n\tmsr DAIFSet, #(DAIFSC_ALL)\n"
            "\tadrp x9, EXT(vz_early_console_pa)@page\n"
            "\tadd x9, x9, EXT(vz_early_console_pa)@pageoff\n\tstr x27, [x9]\n")
    replace(startup, "\tvz_early_mark 80\n", "\tvz_early_map_io\n\tvz_early_mark 80\n")
    normal_vector = "\tadrp\tx0, EXT(ExceptionVectorsBase)@page\t\t\t// Load exception vectors base address\n" \
        "\tadd\t\tx0, x0, EXT(ExceptionVectorsBase)@pageoff\n" \
        "\tadd\t\tx0, x0, x22\t\t\t\t\t\t\t\t\t// Convert exception vector address to KVA\n" \
        "\tsub\t\tx0, x0, x23\n"
    replace(startup, normal_vector, "#if defined(ARM64_BOARD_CONFIG_VZGENERIC)\n"
            "\tadrp x0, L_vz_early_vectors@page\n\tadd x0, x0, L_vz_early_vectors@pageoff\n"
            "#else\n" + normal_vector + "#endif\n")
    replace(startup, "\tMSR_SCTLR_EL1_X0\n\tisb\t\tsy\n",
            "\tMSR_SCTLR_EL1_X0\n\tisb\t\tsy\n#if defined(ARM64_BOARD_CONFIG_VZGENERIC)\n"
            "\tvz_early_mark 86 // V: execution after SCTLR/ISB\n#endif\n")
    old = "\trpi5_pre_mmu_mark 67 // C: cold assembly initialization complete\n#endif"
    replace(startup, old, old + "\n#if defined(ARM64_BOARD_CONFIG_VZGENERIC)\n\tvz_early_mark 67\n#endif")
    arm_init = source / "osfmk/arm/arm_init.c"
    replace(arm_init, "#else\n#define RPI5_BOOT_MARK(stage) ((void)0)",
            "#elif defined(ARM64_BOARD_CONFIG_VZGENERIC)\n"
            "extern void vz_early_c_mark(unsigned int stage);\nextern void vz_early_trace_end(void);\n"
            "#define RPI5_BOOT_MARK(stage) vz_early_c_mark(stage)\n"
            "#else\n#define RPI5_BOOT_MARK(stage) ((void)0)")
    replace(arm_init, "\tarm_vm_init(xmaxmem, args);",
            "#if defined(ARM64_BOARD_CONFIG_VZGENERIC)\n\tvz_early_trace_end();\n#endif\n"
            "\tarm_vm_init(xmaxmem, args);")


def apply_early_trace_stage3(source: Path) -> None:
    vm_init = source / "osfmk/arm64/arm_vm_init.c"
    if "extern void vz_early_c_mark" in vm_init.read_text():
        return
    replace(vm_init, "#else\n#define RPI5_VM_MARK(stage) ((void)0)",
            "#elif defined(ARM64_BOARD_CONFIG_VZGENERIC)\n"
            "extern void vz_early_c_mark(unsigned int stage);\nextern void vz_early_trace_end(void);\n"
            "/* The old low RAM and BAR mappings exist only through checkpoint j. */\n"
            "#define RPI5_VM_MARK(stage) do { if ((stage) <= 'j') vz_early_c_mark(stage); } while (0)\n"
            "#else\n#define RPI5_VM_MARK(stage) ((void)0)")
    replace(vm_init, "#else\n\tset_mmu_ttb(invalid_ttep & TTBR_BADDR_MASK);",
            "#else\n#if defined(ARM64_BOARD_CONFIG_VZGENERIC)\n\tvz_early_trace_end();\n#endif\n"
            "\tset_mmu_ttb(invalid_ttep & TTBR_BADDR_MASK);")
    arm_init = source / "osfmk/arm/arm_init.c"
    replace(arm_init, "#if defined(ARM64_BOARD_CONFIG_VZGENERIC)\n\tvz_early_trace_end();\n#endif\n"
            "\tarm_vm_init(xmaxmem, args);", "\tarm_vm_init(xmaxmem, args);")
    replace(arm_init, "#else\n#define RPI5_POST_VM_MARK(stage) ((void)0)",
            "#elif defined(ARM64_BOARD_CONFIG_VZGENERIC)\n"
            "\textern void vz_post_vm_mark(unsigned int stage);\n"
            "#define RPI5_POST_VM_MARK(stage) vz_post_vm_mark(stage)\n"
            "#else\n#define RPI5_POST_VM_MARK(stage) ((void)0)")


def apply_physmap_alignment_fix(source: Path) -> None:
    """Reserve virtual headroom for block-congruent physical-aperture holes."""
    vm_init = source / "osfmk/arm64/arm_vm_init.c"
    if "vz_physmap_alignment_slack" in vm_init.read_text():
        return
    old = "\tunsigned long physmap_l1_entries = ((real_phys_size + ARM64_PHYSMAP_SLIDE_RANGE) >> ARM_TT_L1_SHIFT) + 1;"
    replace(vm_init, old,
            "#if defined(ARM64_BOARD_CONFIG_VZGENERIC)\n"
            "\t/* Block-congruent mappings may add one alignment hole per PTOV\n"
            "\t * entry. Reserve VA only; never enlarge managed physical RAM.\n"
            "\t * This mirrors the non-ARM_LARGE_MEMORY reservation below. */\n"
            "\tconst uint64_t vz_physmap_alignment_slack = PTOV_TABLE_SIZE * ARM_TT_TWIG_SIZE;\n"
            "\tif (real_phys_size > UINT64_MAX - ARM64_PHYSMAP_SLIDE_RANGE - vz_physmap_alignment_slack) {\n"
            "\t\tpanic(\"VZGENERIC: physical aperture reservation overflow\");\n\t}\n"
            "\tunsigned long physmap_l1_entries = ((real_phys_size + ARM64_PHYSMAP_SLIDE_RANGE +\n"
            "\t    vz_physmap_alignment_slack) >> ARM_TT_L1_SHIFT) + 1;\n"
            "#else\n" + old + "\n#endif")
    old = "\t/* For large memory systems with no PPL such as virtual machines */\n"
    old += "\tstatic_memory_end = phystokv(args->topOfKernelData);\n\tphysmap_end = physmap_base + real_phys_size;"
    replace(vm_init, old, old + "\n#if defined(ARM64_BOARD_CONFIG_VZGENERIC)\n"
            "\tphysmap_end += vz_physmap_alignment_slack;\n"
            "\tassert(physmap_end <= VM_MIN_KERNEL_ADDRESS);\n#endif")


def apply_storage(source: Path) -> None:
    """Opt-in VM filesystem/profile only. Never widen physical Pi transport."""
    config = source / "config/MASTER.arm64.vzgeneric"
    if "config_fse fs_compression ]" not in config.read_text():
        replace(config, "devfs mockfs fifo namedstreams config_fse ]",
                "devfs mockfs fifo namedstreams config_fse fs_compression ]")
    make = source / "makedefs/MakeInc.def"
    if "-DVZ_STORAGE_PROVIDER=1" not in make.read_text():
        replace(make, "MACHINE_FLAGS_ARM64_VZGENERIC = -DARM64_BOARD_CONFIG_VZGENERIC -march=armv8.1-a",
                "MACHINE_FLAGS_ARM64_VZGENERIC = -DARM64_BOARD_CONFIG_VZGENERIC -march=armv8.1-a -DVZ_STORAGE_PROVIDER=1")
    table = source / "iokit/KernelConfigTables.cpp"
    anchor = '    " IONameMatch=device-tree; IOProbeScore=1000:32; },"'
    # Migrate only our first diagnostic table, leaving Pi personalities intact.
    legacy = ("VZBlockStorage", "IOBlockStorageDriver", "IOMediaBSDClient",
              "com_apple_filesystems_hfs_encodings", "com_apple_filesystems_hfs")
    text = table.read_text()
    text = "\n".join(line for line in text.splitlines()
                     if not any(line.startswith(f'    " {{ IOClass={name};') for name in legacy)) + "\n"
    table.write_text(text)
    if '#include "VZStoragePersonalities.inc"' not in text:
        replace(table, anchor, anchor + '\n#if VZ_STORAGE_PROVIDER\n#include "VZStoragePersonalities.inc"\n#endif')
    # A CREATE lookup still traverses read-only ancestors before crossing /data.
    # Reject mutation only at the final component, not at an existing ancestor.
    lookup = source / "bsd/miscfs/mockfs/mockfs_vnops.c"
    old = "if (op != LOOKUP) { return EROFS; }"
    if old in lookup.read_text():
        replace(lookup, old, "if (op != LOOKUP && (cnp->cn_flags & ISLASTCN)) { return EROFS; }")


def apply_network(source: Path) -> None:
    """Distinct opt-in Ethernet profile; no physical Pi source changes."""
    config = source / "config/MASTER.arm64.vzgeneric"
    network = "NETWORK_BASE = [ inet ether bpfilter necp traffic_mgt ]"
    if network not in config.read_text():
        previous = "NETWORK_BASE = [ inet ether necp traffic_mgt ]"
        if previous not in config.read_text():
            previous = "NETWORK_BASE = [ inet necp traffic_mgt ]"
        replace(config, previous, network)
    make = source / "makedefs/MakeInc.def"
    flag = "MACHINE_FLAGS_ARM64_VZGENERIC += -DVZ_NETWORK_PROVIDER=1"
    if flag not in make.read_text():
        anchor = next(line for line in make.read_text().splitlines()
                      if line.startswith("MACHINE_FLAGS_ARM64_VZGENERIC = "))
        replace(make, anchor, anchor + "\n" + flag)
    for relative, line in (
        ("iokit/conf/files", "iokit/Kernel/VZVirtioNetwork.cpp optional iokitcpp"),
        ("pexpert/conf/files.arm64", "pexpert/arm/virtio_net.c standard"),
    ):
        path = source / relative
        if line not in path.read_text():
            with path.open("a") as output:
                output.write("\n" + line + "\n")
    for name in ("virtio_net.c", "virtio_net.h"):
        origin = source / "loader/vz" / name
        if not origin.is_file():
            # Explicit overlay refresh on this experimental snapshot only.
            origin.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "loader/vz" / name, origin)
        shutil.copy2(origin, source / "pexpert/arm" / name)
    shutil.copy2(source / "loader/vz/virtio_net.h", source / "iokit/Kernel/virtio_net.h")


def attach_storage(record: dict, manifest: Path, run: Path) -> None:
    if not record.get("storage_profile"):
        raise ValueError("storage provider requires a distinct --storage snapshot")
    evidence = json.loads(manifest.read_text())
    if not evidence.get("all_compiled") or evidence.get("link", {}).get("returncode") != 0:
        raise ValueError("storage provider lacks compile/link evidence")
    obj = Path(evidence["object"])
    if digest(obj) != evidence["object_sha256"]:
        raise ValueError("storage provider hash changed")
    destination = run / "storage-provider"
    destination.mkdir(exist_ok=True)
    copied = destination / "vz-storage-provider.o"
    shutil.copy2(obj, copied)
    shutil.copy2(manifest, destination / "manifest.json")
    record["storage_provider"] = {"manifest": str(manifest), "manifest_sha256": digest(manifest),
        "object": str(copied), "object_sha256": digest(copied)}
    record["command"] = [item for item in record["command"] if not item.startswith("RPI5_STORAGE_PROVIDER_OBJECT=")]
    record["command"].insert(-1, f"RPI5_STORAGE_PROVIDER_OBJECT={copied}")


def provider_inputs(manifest: dict, output: Path) -> dict:
    result = {}
    for name in ("crypto_candidate", "pthread_provider"):
        entry = manifest[name]
        if not entry or not entry.get("object_sha256") or not entry.get("manifest_sha256"):
            raise ValueError(f"missing immutable provider evidence: {name}")
        for field in ("object", "manifest"):
            path = Path(entry[field])
            if digest(path) != entry[field + "_sha256"]:
                raise ValueError(f"provider hash mismatch: {path}")
        destination = output / name
        destination.mkdir()
        obj = destination / Path(entry["object"]).name
        shutil.copy2(entry["object"], obj)
        shutil.copy2(entry["manifest"], destination / "manifest.json")
        result[name] = {**entry, "copied_object": str(obj)}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "build/rpi5-xcode27/run-obi6gw3d/manifest.json")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--resume", type=Path, help="Rebuild an existing isolated snapshot without changing it")
    parser.add_argument("--sync-overlay", action="store_true", help="On resume, copy the current maintained overlays into the isolated snapshot")
    parser.add_argument("--refresh-transport", action="store_true", help="On resume, copy and hash the current shared virtio transport")
    parser.add_argument("--keep-going", action="store_true", help="Continue independent compilation after a file fails")
    parser.add_argument("--refresh-build-support", action="store_true", help="On resume, fill the debugger packaging support closure")
    parser.add_argument("--storage", action="store_true", help="Prepare a distinct virtio-block/Apple HFS+ kernel profile")
    parser.add_argument("--network", action="store_true", help="Prepare a distinct VM-only VirtIO Ethernet/XNU ifnet profile")
    parser.add_argument("--ramroot-max-nodes", type=int, choices=(32, 96), default=32,
                        help="VM-only read-only root capacity; 96 for broader source-built userland")
    parser.add_argument("--storage-provider", type=Path, help="Verified manifest from build_storage.py")
    parser.add_argument("--provider-snapshot", type=Path, help="Reuse verified provider copies from a completed isolated VZ build")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 16:
        parser.error("jobs must be 1..16")
    build_root = HERE / "build"
    build_root.mkdir(exist_ok=True)
    if args.resume:
        run = args.resume.resolve()
        if run.parent != build_root.resolve() or not (run / "manifest.json").is_file():
            parser.error("resume must name a recorded direct child of kernel/build")
        record = json.loads((run / "manifest.json").read_text())
        if args.ramroot_max_nodes != 32 and args.ramroot_max_nodes != record.get("ramroot_max_nodes", 32):
            parser.error("cannot change RAM-root profile on resume")
        source = run / "source"
        command = record["command"]
        if args.sync_overlay:
            for path in sorted((HERE / "overlay").rglob("*")):
                if path.is_file():
                    output = source / path.relative_to(HERE / "overlay")
                    output.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, output)
            apply_early_trace(source)
            apply_early_trace_stage2(source)
            apply_early_trace_stage3(source)
            apply_physmap_alignment_fix(source)
            apply_timer_irq_fix(source)
            if record.get("storage_profile"):
                apply_storage(source)
            if record.get("network_profile"):
                apply_network(source)
            record["overlay_sha256"] = {str(p.relative_to(HERE)): digest(p)
                for p in sorted((HERE / "overlay").rglob("*")) if p.is_file()}
            record["build_script_sha256"] = digest(Path(__file__))
            write_json(run / "manifest.json", record)
        if args.refresh_transport:
            refreshed = {}
            names = ("virtio_console.c", "virtio_console.h")
            if record.get("network_profile"):
                names += ("virtio_net.c", "virtio_net.h")
            for name in names:
                origin = ROOT / "loader/vz" / name
                expected = digest(origin)
                for output in (source / "loader/vz" / name, source / "pexpert/arm" / name):
                    shutil.copy2(origin, output)
                    if digest(output) != expected:
                        raise ValueError("transport changed during refresh")
                refreshed[name] = expected
            if record.get("network_profile"):
                shutil.copy2(source / "loader/vz/virtio_net.h", source / "iokit/Kernel/virtio_net.h")
            record["refreshed_transport_sha256"] = refreshed
            write_json(run / "manifest.json", record)
        if args.refresh_build_support:
            support = [ROOT / "tools/Makefile", ROOT / "tools/rpi5/LICENSE"]
            support += [p for p in (ROOT / "tools/lldbmacros").rglob("*") if p.is_file()]
            refreshed = {}
            for origin in support:
                relative = origin.relative_to(ROOT)
                output = source / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                expected = digest(origin)
                shutil.copy2(origin, output)
                if digest(output) != expected:
                    raise ValueError("build support changed during refresh")
                refreshed[str(relative)] = expected
            record["refreshed_build_support_sha256"] = refreshed
            write_json(run / "manifest.json", record)
    else:
        manifest = json.loads(args.manifest.read_text())
        if manifest.get("exit_code") != 0 or not manifest["crypto_candidate"]["startup_enabled"]:
            raise ValueError("the reference build must have succeeded with provider startup")
        run = Path(tempfile.mkdtemp(prefix="vzgeneric-", dir=build_root))
        source = run / "source"
        source.mkdir()
        original = snapshot(source)
        if args.network:
            for name in ("virtio_net.c", "virtio_net.h"):
                origin = ROOT / "loader/vz" / name
                output = source / "loader/vz" / name
                expected = digest(origin)
                shutil.copy2(origin, output)
                if digest(origin) != expected or digest(output) != expected:
                    raise ValueError("network transport changed during snapshot")
                original[str(origin.relative_to(ROOT))] = expected
        write_json(run / "source-snapshot.json", original)
        if args.provider_snapshot:
            frozen_path = args.provider_snapshot.resolve()
            frozen = json.loads(frozen_path.read_text())
            if frozen.get("exit_code") != 0:
                raise ValueError("provider snapshot must be a completed kernel build")
            for name in ("crypto_candidate", "pthread_provider"):
                entry = frozen["providers"][name]
                manifest[name] = {**entry, "object": entry["copied_object"],
                                  "manifest": str(Path(entry["copied_object"]).parent / "manifest.json")}
        providers = provider_inputs(manifest, run)
        apply_overlay(source)
        if args.ramroot_max_nodes != 32:
            replace(source / "bsd/miscfs/mockfs/rpi5_ramroot_format.h",
                    "#define RPI5_RFS_NODES 32u", f"#define RPI5_RFS_NODES {args.ramroot_max_nodes}u")
        if args.storage:
            apply_storage(source)
        if args.network:
            apply_network(source)
        original_args = dict(value.split("=", 1) for value in manifest["command"] if "=" in value)
        retained = ("SDKROOT", "SDKROOT_RESOLVED", "SDKVERSION", "PLATFORM", "PLATFORMPATH",
                    "HOST_SDKROOT", "RC_DARWIN_KERNEL_VERSION", "RPI5_EXPLORATORY_TOOLCHAIN")
        command = ["make", f"-j{args.jobs}", f"MAKEJOBS=--jobs={args.jobs}"]
        command += [f"{key}={original_args[key]}" for key in retained]
        command += ["TARGET_CONFIGS=DEVELOPMENT ARM64 VZGENERIC", "KDKROOT=", "BUILD_LTO=0", "DO_CTFMERGE=0",
                    "RPI5_REPRODUCIBLE=0", "RPI5_CRYPTO_STARTUP=1",
                    f"RPI5_CRYPTO_CANDIDATE_OBJECT={providers['crypto_candidate']['copied_object']}",
                    f"RPI5_PTHREAD_PROVIDER_OBJECT={providers['pthread_provider']['copied_object']}",
                    f"OBJROOT={run / 'obj'}", f"DSTROOT={run / 'dst'}", f"SYMROOT={run / 'sym'}", "all"]
        record = {"started_utc": datetime.now(timezone.utc).isoformat(), "scope": "isolated VZGENERIC DEVELOPMENT; no hardware validation claim",
                  "source_root": str(ROOT), "source_snapshot": str(run / "source-snapshot.json"),
                  "source_snapshot_sha256": digest(run / "source-snapshot.json"),
                  "reference_manifest": str(args.manifest), "reference_manifest_sha256": digest(args.manifest),
                  "providers": providers, "command": command, "run": str(run), "exit_code": None,
                  "overlay_sha256": {str(p.relative_to(HERE)): digest(p) for p in sorted((HERE / "overlay").rglob("*")) if p.is_file()},
                  "build_script_sha256": digest(Path(__file__)), "storage_profile": args.storage,
                  "network_profile": args.network, "ramroot_max_nodes": args.ramroot_max_nodes}
        write_json(run / "manifest.json", record)
    if args.storage_provider:
        attach_storage(record, args.storage_provider.resolve(), run)
        command = record["command"]
        write_json(run / "manifest.json", record)
    print(f"RUN={run}", flush=True)
    if args.prepare_only:
        print("Snapshot prepared; compilation not run.", flush=True)
        return 0
    command = [item for item in command if item != "-k"]
    if args.keep_going:
        command.insert(1, "-k")
    record["command"] = command
    record["effective_source_sha256"] = {str(p.relative_to(source)): digest(p)
        for p in sorted(source.rglob("*")) if p.is_file() and not p.is_symlink()}
    write_json(run / "manifest.json", record)
    env = {key: value for key, value in os.environ.items() if not
           (key.startswith(("RPI5_", "MAKE", "SDK", "OBJROOT", "DSTROOT", "SYMROOT", "SRCROOT", "VERSDIR", "CURRENT_", "TARGET_CONFIG")))}
    with (run / "build.log").open("a") as log:
        outcome = subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT)
    record["exit_code"] = outcome.returncode
    record["finished_utc"] = datetime.now(timezone.utc).isoformat()
    kernels = [p for p in (run / "obj").rglob("kernel.development.vzgeneric") if ".dSYM" not in str(p)]
    record["kernels"] = [{"path": str(p), "sha256": digest(p)} for p in kernels]
    write_json(run / "manifest.json", record)
    print(f"EXIT={outcome.returncode} LOG={run / 'build.log'}", flush=True)
    return outcome.returncode


if __name__ == "__main__":
    raise SystemExit(main())
