#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Fresh BL33 build, diagnostic by default. Placement is never board-approved here."""
import argparse
import re
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from payload_container import encode as encode_container
from audit_macho import inspect as inspect_kernel
from ramroot import inspect_init as inspect_pid1

ROOT = Path(__file__).resolve().parents[2]


def inspect(data, raw, base):
    def unpack(fmt, offset):
        if offset < 0 or offset + struct.calcsize(fmt) > len(data):
            raise ValueError("truncated ELF")
        return struct.unpack_from(fmt, data, offset)

    if data[:7] != b"\x7fELF\x02\x01\x01":
        raise ValueError("expected little-endian ELF64")
    kind, machine, version, entry, phoff, shoff, flags, ehsize, phsize, phnum, shsize, shnum, names = unpack("<HHIQQQIHHHHHH", 16)
    if (kind, machine, version, ehsize, phsize, shsize) != (2, 183, 1, 64, 56, 64) or entry != base:
        raise ValueError("unexpected executable ABI or entry")
    loads = []
    for i in range(phnum):
        typ, perms, off, va, pa, size, memory, align = unpack("<IIQQQQQQ", phoff + i * phsize)
        if typ in (2, 3):
            raise ValueError("dynamic executable forbidden")
        if typ != 1:
            continue
        if not memory or size > memory or off + size > len(data) or va != pa or pa < base or pa + memory > 1 << 40 or perms & 3 == 3:
            raise ValueError("invalid LOAD extent/protection")
        if size and (pa - base + size > len(raw) or raw[pa-base:pa-base+size] != data[off:off+size]):
            raise ValueError("raw binary differs from ELF")
        loads.append(dict(address=pa, file_size=size, memory_size=memory, flags=perms))
    loads.sort(key=lambda x: x["address"])
    if not loads or not any(x["flags"] & 1 and x["address"] <= entry < x["address"] + x["file_size"] for x in loads):
        raise ValueError("entry is not file-backed executable memory")
    for a, b in zip(loads, loads[1:]):
        if a["address"] + a["memory_size"] > b["address"]:
            raise ValueError("overlapping LOAD extents")
    if len(raw) != max(x["address"] + x["file_size"] for x in loads if x["file_size"]) - base:
        raise ValueError("unexpected raw extent")
    symbols = False
    for i in range(shnum):
        _, typ, _, _, off, size, _, _, _, entsize = unpack("<IIQQQQIIQQ", shoff + i * shsize)
        if off + size > len(data) and typ != 8:
            raise ValueError("section outside ELF")
        if typ in (4, 9) and size:
            raise ValueError("remaining relocations")
        if typ == 2:
            symbols = True
            if entsize != 24 or size % 24:
                raise ValueError("invalid symbol table")
            for pos in range(off + 24, off + size, 24):
                _, _, _, section, _, _ = unpack("<IBBHQQ", pos)
                if section == 0:
                    raise ValueError("undefined symbol")
    if not symbols:
        raise ValueError("missing audit symbol table")
    return dict(entry=entry, loads=loads, board_placement_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--load-address", type=lambda x: int(x, 0), required=True)
    parser.add_argument("--kernel", type=Path, help="Embed a host-audited kernel; diagnostic only unless --transfer is supplied")
    parser.add_argument("--init", type=Path,
                        help="Embed a validated 16 KiB-padded static arm64 RAMDisk image; requires --kernel")
    parser.add_argument("--transfer", action="store_true",
                        help="Opt in to XNU entry after probes and seed commit, with a 15-second recovery watchdog")
    parser.add_argument("--serial-terminal", action="store_true",
                        help="Use serial=3 for an opt-in interactive PID 1 trial; never a Gate 3 qualification image")
    parser.add_argument("--gate4-storage", action="store_true",
                        help="With --serial-terminal, validate SD slot binding, snapshot registers and publish SD DT/MMIO; no card commands")
    parser.add_argument("--gate5-pcie-topology", action="store_true",
                        help="Opt-in runtime PCIe/RP1 FDT declaration log only; no PCIe access; excludes storage trials")
    parser.add_argument("--gate4-sd-readonly", action="store_true",
                        help="With --gate4-storage, opt in to the kernel's SD power/pin handoff and read-only PIO driver; no data writes")
    parser.add_argument("--gate4-hfs-readonly", action="store_true",
                        help="With --gate4-sd-readonly, enable separately gated built-in HFS registration; no automatic mount or writes")
    parser.add_argument("--gate4-hfs-write-trial", action="store_true",
                        help="Distinct bounded-write HFS image; requires storage/serial recovery and excludes read-only flags")
    parser.add_argument("--gate3-register-cpus", action="store_true",
                        help="Opt in to BCM2712 CPU-object registration only; does not start secondary cores")
    parser.add_argument("--gate3-register-boot-cpu", action="store_true",
                        help="Opt in to boot-CPU registration only for lifecycle fault isolation")
    parser.add_argument("--gate3-cpu-on-1", action="store_true",
                        help="Opt in to a watchdog-backed PSCI CPU_ON trial for CPU 1")
    parser.add_argument("--gate3-cpu-on-all", action="store_true",
                        help="Opt in to a watchdog-backed PSCI CPU_ON trial for CPUs 1-3")
    parser.add_argument("--gate3-tlb-trial", action="store_true",
                        help="With --gate3-cpu-on-all, test broadcast kernel-VA invalidation")
    parser.add_argument("--gate3-user-tlb-trial", action="store_true",
                        help="With --gate3-cpu-on-all, test cross-core user-ASID invalidation")
    parser.add_argument("--gate3-concurrency-trial", action="store_true",
                        help="With --gate3-cpu-on-all, test four pinned concurrent kernel workers")
    parser.add_argument("--gate3-xnupost-inventory", action="store_true",
                        help="With --gate3-cpu-on-all, list compiled XNUPOST tests without running them")
    parser.add_argument("--gate3-xnupost-index", type=int, default=0,
                        help="With --gate3-cpu-on-all, run only this XNUPOST table index")
    parser.add_argument("--gate3-xnupost-config", default="",
                        help="With --gate3-cpu-on-all, run exact XNUPOST ranges (e.g. 16_16,23_24)")
    parser.add_argument("--gate3-qualification-config", default="",
                        help="With --gate3-cpu-on-all, sequential XNUPOST/concurrency/TLB then eight-hour soak")
    parser.add_argument("--gate3-soak-seconds", type=int, default=0,
                        help="With --gate3-cpu-on-all, watchdog-backed SMP soak for 60-28800 seconds")
    args = parser.parse_args()
    if args.gate5_pcie_topology and any((args.gate4_storage, args.gate4_sd_readonly,
                                       args.gate4_hfs_readonly, args.gate4_hfs_write_trial)):
        parser.error("--gate5-pcie-topology must remain separate from storage trials")
    if args.gate4_hfs_write_trial and (not args.gate4_storage or args.gate4_sd_readonly or args.gate4_hfs_readonly):
        parser.error("--gate4-hfs-write-trial requires --gate4-storage and excludes read-only flags")
    if args.gate4_hfs_readonly and not args.gate4_sd_readonly:
        parser.error("--gate4-hfs-readonly requires --gate4-sd-readonly and its separate recovery image")
    if args.gate4_sd_readonly and not args.gate4_storage:
        parser.error("--gate4-sd-readonly requires --gate4-storage and its separate serial recovery image")
    if args.gate4_storage and not args.serial_terminal:
        parser.error("--gate4-storage requires the separate --serial-terminal recovery image")
    if args.transfer and not args.kernel:
        parser.error("--transfer requires --kernel")
    if args.init and not args.kernel:
        parser.error("--init requires --kernel")
    if args.serial_terminal and not (args.transfer and args.kernel and args.init and args.gate3_cpu_on_all):
        parser.error("--serial-terminal requires --transfer, --kernel, --init and --gate3-cpu-on-all")
    if args.serial_terminal and any((args.gate3_register_cpus, args.gate3_register_boot_cpu,
                                     args.gate3_cpu_on_1, args.gate3_tlb_trial,
                                     args.gate3_user_tlb_trial, args.gate3_concurrency_trial,
                                     args.gate3_xnupost_inventory, args.gate3_xnupost_index,
                                     args.gate3_xnupost_config, args.gate3_qualification_config,
                                     args.gate3_soak_seconds)):
        parser.error("--serial-terminal cannot be combined with Gate 3 qualification or trial modes")
    if args.gate3_register_cpus and not (args.transfer and args.kernel and args.init):
        parser.error("--gate3-register-cpus requires --transfer, --kernel and --init")
    if args.gate3_register_boot_cpu and not (args.transfer and args.kernel and args.init):
        parser.error("--gate3-register-boot-cpu requires --transfer, --kernel and --init")
    if args.gate3_cpu_on_1 and not (args.transfer and args.kernel and args.init):
        parser.error("--gate3-cpu-on-1 requires --transfer, --kernel and --init")
    if args.gate3_cpu_on_all and not (args.transfer and args.kernel and args.init):
        parser.error("--gate3-cpu-on-all requires --transfer, --kernel and --init")
    if args.gate3_tlb_trial and not args.gate3_cpu_on_all:
        parser.error("--gate3-tlb-trial requires --gate3-cpu-on-all")
    if args.gate3_user_tlb_trial and not args.gate3_cpu_on_all:
        parser.error("--gate3-user-tlb-trial requires --gate3-cpu-on-all")
    if args.gate3_concurrency_trial and not args.gate3_cpu_on_all:
        parser.error("--gate3-concurrency-trial requires --gate3-cpu-on-all")
    if (args.gate3_xnupost_inventory or args.gate3_xnupost_index or
            args.gate3_xnupost_config or args.gate3_qualification_config) and not args.gate3_cpu_on_all:
        parser.error("Gate 3 XNUPOST modes require --gate3-cpu-on-all")
    if args.gate3_xnupost_index < 0 or args.gate3_xnupost_index > 9999:
        parser.error("--gate3-xnupost-index must be between 0 and 9999")
    for selected_config in (args.gate3_xnupost_config, args.gate3_qualification_config):
        if not selected_config:
            continue
        ranges = selected_config.split(",")
        previous_end = 0
        if len(selected_config) > 128:
            parser.error("Gate 3 XNUPOST/qualification config exceeds 128 characters")
        for item in ranges:
            if not re.fullmatch(r"[0-9]{1,4}_[0-9]{1,4}", item):
                parser.error("Gate 3 XNUPOST/qualification config requires exact ranges 1_1,...,9999_9999")
            start, end = map(int, item.split("_"))
            if not previous_end < start <= end <= 9999:
                parser.error("Gate 3 XNUPOST/qualification ranges must be ascending and non-overlapping")
            previous_end = end
    if args.gate3_soak_seconds and not args.gate3_cpu_on_all:
        parser.error("--gate3-soak-seconds requires --gate3-cpu-on-all")
    if args.gate3_soak_seconds < 0 or (args.gate3_soak_seconds and
            not 60 <= args.gate3_soak_seconds <= 28800):
        parser.error("--gate3-soak-seconds must be between 60 and 28800")
    if sum((args.gate3_tlb_trial, args.gate3_user_tlb_trial,
            args.gate3_concurrency_trial,
            args.gate3_xnupost_inventory,
            args.gate3_xnupost_index != 0, bool(args.gate3_xnupost_config),
            args.gate3_soak_seconds != 0, bool(args.gate3_qualification_config))) > 1:
        parser.error("Gate 3 TLB/user-TLB/concurrency/XNUPOST/soak/qualification modes are mutually exclusive")
    if sum((args.gate3_register_cpus, args.gate3_register_boot_cpu,
            args.gate3_cpu_on_1, args.gate3_cpu_on_all)) > 1:
        parser.error("Gate 3 CPU modes are mutually exclusive")
    if args.load_address <= 0 or args.load_address >= 1 << 40 or args.load_address & 0xffff:
        parser.error("load address must be positive, 64 KiB aligned and below 40 bits")
    output = ROOT / "build/rpi5"
    output.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="bl33-probe-", dir=output))
    commands = []
    def execute(command):
        commands.append([str(x) for x in command])
        subprocess.run(commands[-1], check=True, cwd=ROOT)
    sources = [ROOT / "loader/rpi5" / name for name in ("probe_entry.S", "probe_main.c", "uart.c", "psci.S", "irq_entry.S", "fdt.c", "ranges.c", "reservations.c", "macho.c", "bootstrap.c", "boot_args.c", "memory.S")]
    objects = []
    sources.append(ROOT / "loader/rpi5/apple_dt.c")
    sources.append(ROOT / "loader/rpi5/boot_seed.c")
    sources.append(ROOT / "loader/rpi5/seed_tree.c")
    sources.append(ROOT / "loader/rpi5/cpu_tree.c")
    sources.append(ROOT / "loader/rpi5/serial_tree.c")
    sources.append(ROOT / "loader/rpi5/board_tree.c")
    sources.append(ROOT / "loader/rpi5/tree_handoff.c")
    sources.append(ROOT / "loader/rpi5/memory_type.c")
    sources.append(ROOT / "loader/rpi5/fdt_reg.c")
    if args.gate5_pcie_topology:
        sources += [ROOT / "loader/rpi5/pcie_fdt.c", ROOT / "loader/rpi5/pcie_topology.c"]
    sources.append(ROOT / "loader/rpi5/handoff.c")
    sources.append(ROOT / "loader/rpi5/boot_data.c")
    sources.append(ROOT / "loader/rpi5/transfer.S")
    bearssl = ROOT / "build/rpi5/bearssl-candidate"
    if subprocess.check_output(["git", "-C", str(bearssl), "rev-parse", "HEAD"], text=True).strip() != "7bea48e5e850ab4cafbe68d3765cdaba13a86d6f" or subprocess.check_output(["git", "-C", str(bearssl), "status", "--porcelain", "--untracked-files=all"], text=True).strip():
        raise ValueError("SHA-256 requires the unmodified pinned BearSSL candidate")
    sources.append(ROOT / "loader/rpi5/hash.c")
    sources.append(ROOT / "loader/rpi5/firmware_seed.c")
    sources.append(ROOT / "loader/rpi5/firmware_seed_fdt.c")
    sources.append(ROOT / "loader/rpi5/firmware_seed_tree.c")
    sources.append(ROOT / "loader/rpi5/firmware_seed_stack.S")
    sources.append(ROOT / "loader/rpi5/container.c")
    sources.extend(bearssl / "src" / unit for unit in ("hash/sha2small.c", "codec/dec32be.c", "codec/enc32be.c", "mac/hmac.c", "kdf/hkdf.c"))
    payload_inputs = []
    kernel_report = None
    init_report = None
    relocation_capacity = 2
    if args.kernel:
        kernel_bytes = args.kernel.read_bytes()
        kernel_report = inspect_kernel(kernel_bytes)
        relocation_count = sum(kernel_report["local_relocations"].values())
        relocation_capacity = 1 << max(1, (2 * relocation_count - 1).bit_length())
        if relocation_capacity > 1 << 20:
            raise ValueError("embedded kernel relocation scratch exceeds 4 MiB profile")
        payload = run / "payload.bin"
        init_bytes = None
        if args.init:
            init_bytes = args.init.read_bytes()
            if not init_bytes or len(init_bytes) % 16384:
                raise ValueError("init image must be nonempty and 16 KiB padded")
            init_report = inspect_pid1(init_bytes)
        payload.write_bytes(encode_container(kernel_bytes, init_bytes))
        assembly = run / "payload.S"
        assembly.write_text('.section .payload,"a"\n.balign 64\n.incbin "' + str(payload) + '"\n')
        sources.append(assembly)
        payload_inputs = [payload, ROOT / "tools/rpi5/payload_container.py", ROOT / "tools/rpi5/audit_macho.py"]
    for source in sources:
        obj = run / (source.stem + ".o")
        stack_flags = ["-fstack-usage"] if source.suffix == ".c" else []
        if source.name == "probe_main.c":
            stack_flags.append("-DRPI5_RELOCATION_CAPACITY=" + str(relocation_capacity))
            stack_flags.append("-DRPI5_XNU_TRANSFER=" + str(int(args.transfer)))
            stack_flags.append("-DRPI5_SERIAL_TERMINAL=" + str(int(args.serial_terminal)))
            stack_flags.append("-DRPI5_GATE4_STORAGE=" + str(int(args.gate4_storage)))
            stack_flags.append("-DRPI5_GATE5_PCIE_TOPOLOGY=" + str(int(args.gate5_pcie_topology)))
            stack_flags.append("-DRPI5_GATE4_SD_READONLY=" + str(int(args.gate4_sd_readonly)))
            stack_flags.append("-DRPI5_GATE4_HFS_READONLY=" + str(int(args.gate4_hfs_readonly)))
            stack_flags.append("-DRPI5_GATE4_HFS_WRITE_TRIAL=" + str(int(args.gate4_hfs_write_trial)))
            stack_flags.append("-DRPI5_GATE3_REGISTER_CPUS=" + str(int(args.gate3_register_cpus)))
            stack_flags.append("-DRPI5_GATE3_REGISTER_BOOT_CPU=" + str(int(args.gate3_register_boot_cpu)))
            stack_flags.append("-DRPI5_GATE3_CPU_ON_1=" + str(int(args.gate3_cpu_on_1)))
            stack_flags.append("-DRPI5_GATE3_CPU_ON_ALL=" + str(int(args.gate3_cpu_on_all)))
            stack_flags.append("-DRPI5_GATE3_TLB_TRIAL=" + str(int(args.gate3_tlb_trial)))
            stack_flags.append("-DRPI5_GATE3_USER_TLB_TRIAL=" + str(int(args.gate3_user_tlb_trial)))
            stack_flags.append("-DRPI5_GATE3_CONCURRENCY_TRIAL=" + str(int(args.gate3_concurrency_trial)))
            stack_flags.append("-DRPI5_GATE3_XNUPOST_INVENTORY=" + str(int(args.gate3_xnupost_inventory)))
            stack_flags.append("-DRPI5_GATE3_XNUPOST_INDEX=" + str(args.gate3_xnupost_index))
            stack_flags.append('-DRPI5_GATE3_XNUPOST_CONFIG="' + args.gate3_xnupost_config + '"')
            stack_flags.append("-DRPI5_GATE3_XNUPOST_CONFIG_ENABLED=" +
                               str(int(bool(args.gate3_xnupost_config))))
            stack_flags.append('-DRPI5_GATE3_QUALIFICATION_CONFIG="' +
                               args.gate3_qualification_config + '"')
            stack_flags.append("-DRPI5_GATE3_QUALIFICATION_CONFIG_ENABLED=" +
                               str(int(bool(args.gate3_qualification_config))))
            stack_flags.append("-DRPI5_GATE3_SOAK_SECONDS=" + str(args.gate3_soak_seconds))
        stack_flags += ["-I" + str(ROOT / "loader/rpi5/freestanding"), "-I" + str(bearssl / "inc"), "-I" + str(bearssl / "src")]
        # MMU-off accesses cannot rely on Normal-memory unaligned semantics.
        # In particular, FDT properties are only four-byte aligned: prevent
        # combining byte decodes into unaligned 64-bit loads.
        execute(["xcrun", "clang", "--target=aarch64-none-elf", "-mcpu=cortex-a76", "-mstrict-align", "-ffreestanding", "-fno-stack-protector", "-mgeneral-regs-only", "-O2", "-Wall", "-Wextra", "-Werror", *stack_flags, "-c", source, "-o", obj])
        objects.append(obj)
    elf, binary = run / "probe.elf", run / "probe.bin"
    execute([ROOT / "tools/rpi5/tfa-lld", "--defsym=LOADER_BASE=" + hex(args.load_address), "-T", ROOT / "loader/rpi5/probe.ld", *objects, "-o", elf])
    execute([ROOT / "tools/rpi5/tfa-objcopy", "-O", "binary", elf, binary])
    report = inspect(elf.read_bytes(), binary.read_bytes(), args.load_address)
    report["embedded_kernel"] = kernel_report
    report["embedded_init"] = init_report
    report["xnu_transfer_enabled"] = args.transfer
    report["serial_terminal"] = args.serial_terminal
    report["gate4_storage_binding_snapshot"] = args.gate4_storage
    report["gate5_pcie_topology"] = args.gate5_pcie_topology
    report["gate5_pcie_mmio_enabled"] = False
    report["gate4_sd_readonly"] = args.gate4_sd_readonly
    report["gate4_hfs_readonly"] = args.gate4_hfs_readonly
    report["gate4_hfs_write_trial"] = args.gate4_hfs_write_trial
    report["gate3_register_cpus"] = args.gate3_register_cpus
    report["gate3_register_boot_cpu"] = args.gate3_register_boot_cpu
    report["gate3_cpu_on_1"] = args.gate3_cpu_on_1
    report["gate3_cpu_on_all"] = args.gate3_cpu_on_all
    report["gate3_tlb_trial"] = args.gate3_tlb_trial
    report["gate3_user_tlb_trial"] = args.gate3_user_tlb_trial
    report["gate3_concurrency_trial"] = args.gate3_concurrency_trial
    report["gate3_xnupost_inventory"] = args.gate3_xnupost_inventory
    report["gate3_xnupost_index"] = args.gate3_xnupost_index
    report["gate3_xnupost_config"] = args.gate3_xnupost_config
    report["gate3_qualification_config"] = args.gate3_qualification_config
    report["gate3_soak_seconds"] = args.gate3_soak_seconds
    report["transfer_watchdog_policy"] = "15-second full-reset observation window" if args.transfer else None
    report["relocation_scratch_bytes"] = relocation_capacity * 4
    if args.kernel:
        payload_bytes = payload.read_bytes()
        raw = binary.read_bytes()
        payload_offset = raw.find(payload_bytes)
        if payload_offset < 0 or raw.find(payload_bytes, payload_offset + 1) >= 0 or (args.load_address + payload_offset) & 63:
            raise ValueError("embedded container absent, duplicated or misaligned in raw image")
        report["payload_physical_range"] = [args.load_address + payload_offset, args.load_address + payload_offset + len(payload_bytes)]
    stack_files = [run / (source.stem + ".su") for source in sources if source.suffix == ".c"]
    stack_frames = []
    for stack_file in stack_files:
        for line in stack_file.read_text().splitlines():
            location, size, kind = line.split("\t")
            frame = int(size)
            if kind != "static" or frame >= 0x4000:
                raise ValueError(f"unsupported stack frame: {line}")
            stack_frames.append({"location": location, "bytes": frame, "kind": kind})
    report["stack_frames"] = sorted(stack_frames, key=lambda row: row["bytes"], reverse=True)
    if args.gate5_pcie_topology:
        from pcie_stack import check as check_pcie_stack
        report["gate5_pcie_topology_stack_budget"] = check_pcie_stack(stack_frames)
    if args.gate4_storage:
        from tree_stack import check_gate4_binding
        report["gate4_binding_stack_budget"] = check_gate4_binding(stack_frames)
    # Conservative sum of every emitted frame in the nonrecursive seed/crypto
    # units. Sequential alternatives are deliberately counted together.
    seed_units = {"firmware_seed.c", "hkdf.c", "hmac.c", "sha2small.c", "dec32be.c", "enc32be.c"}
    seed_frames = [r for r in stack_frames if Path(r['location'].split(':')[0]).name in seed_units]
    if {Path(r['location'].split(':')[0]).name for r in seed_frames} != seed_units:
        raise ValueError('missing isolated seed stack evidence')
    seed_bound = sum(r['bytes'] for r in seed_frames)
    if seed_bound + 512 >= 0x4000:
        raise ValueError('isolated seed stack budget exceeded')
    report['isolated_seed_stack_budget'] = {'conservative_bytes':seed_bound,
        'stack_bytes':0x4000,'required_margin':512,
        'scope':'Nonrecursive pinned seed/HKDF/HMAC/SHA256 units; bytewise assembly memcpy/memset use no stack'}
    from tree_stack import check as check_tree_stack, check_runtime_plan
    depth = re.search(r'^#define RPI5_ADT_MAX_DEPTH ([0-9]+)$',
                      (ROOT / 'loader/rpi5/apple_dt.h').read_text(), re.M)
    if not depth:
        raise ValueError('Apple tree depth declaration missing')
    report['tree_stack_budget'] = check_tree_stack(stack_frames,int(depth[1]))
    report['runtime_plan_stack_budget'] = check_runtime_plan(stack_frames,int(depth[1]))
    report["stack_scope"] = "Compiler C frames only; call-chain sums, recursion and assembly IRQ frames require separate review."
    inputs = sources + [ROOT / "loader/rpi5/boot_args.h", ROOT / "loader/rpi5/bootstrap.h", ROOT / "loader/rpi5/macho.h", ROOT / "loader/rpi5/ranges.h", ROOT / "loader/rpi5/fdt.h", ROOT / "loader/rpi5/uart.h", ROOT / "loader/rpi5/probe.ld", Path(__file__).resolve(), ROOT / "tools/rpi5/loader-toolchain.lock.json", ROOT / "tools/rpi5/tfa-lld", ROOT / "tools/rpi5/tfa-objcopy"]
    inputs.append(ROOT / "loader/rpi5/apple_dt.h")
    inputs.append(ROOT / "loader/rpi5/boot_seed.h")
    inputs.append(ROOT / "loader/rpi5/seed_tree.h")
    inputs.append(ROOT / "loader/rpi5/cpu_tree.h")
    inputs.append(ROOT / "loader/rpi5/serial_tree.h")
    inputs.append(ROOT / "loader/rpi5/board_tree.h")
    inputs.append(ROOT / "loader/rpi5/tree_handoff.h")
    inputs.append(ROOT / "loader/rpi5/memory_type.h")
    inputs.append(ROOT / "tools/rpi5/tree_stack.py")
    inputs.append(ROOT / "loader/rpi5/handoff.h")
    if args.gate5_pcie_topology:
        inputs += [ROOT / "loader/rpi5/pcie_fdt.h", ROOT / "loader/rpi5/pcie_topology.h",
                   ROOT / "tools/rpi5/pcie_stack.py"]
    inputs.extend([ROOT / "loader/rpi5/boot_data.h", ROOT / "loader/rpi5/transfer.h"])
    inputs.append(ROOT / "loader/rpi5/container.h")
    inputs.extend([ROOT / "loader/rpi5/hash.h", ROOT / "loader/rpi5/freestanding/string.h", bearssl / "LICENSE.txt", bearssl / "src/inner.h", bearssl / "src/config.h"])
    inputs.extend(sorted((bearssl / "inc").glob("*.h")))
    inputs.extend(stack_files)
    inputs.extend(payload_inputs)
    report.update(commands=commands, compiler=subprocess.check_output(["xcrun", "clang", "--version"], text=True), linker=subprocess.check_output([str(ROOT / "tools/rpi5/tfa-lld"), "--version"], text=True), sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs + [elf, binary]})
    (run / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(run)


if __name__ == "__main__":
    main()
