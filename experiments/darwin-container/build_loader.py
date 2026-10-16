#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the source EFI loader. Console-only is an explicit hardware diagnostic."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "loader/vz"


def run(command):
    subprocess.run([str(x) for x in command], check=True)


def kernel_metadata(data):
    """Bound framing and placement on the host; guest revalidates all Mach-O data."""
    if len(data) < 32 or len(data) > 30 * 1024 * 1024:
        raise ValueError("kernel must be a bounded thin ARM64 executable")
    magic, cpu, subtype, filetype, count, command_bytes, flags, _ = struct.unpack_from("<8I", data)
    if (magic, cpu, subtype, filetype) != (0xFEEDFACF, 0x100000C, 0, 2):
        raise ValueError("expected ARM64/ALL MH_EXECUTE")
    if not flags & 1 or flags & 0x80000000 or count > 4096 or command_bytes > len(data) - 32:
        raise ValueError("unsupported Mach-O flags or command envelope")
    cursor = 32
    end = cursor + command_bytes
    segments = []
    relocations = 0
    for _ in range(count):
        if cursor + 8 > end:
            raise ValueError("truncated Mach-O load command")
        command, size = struct.unpack_from("<II", data, cursor)
        if size < 8 or size % 8 or size > end - cursor:
            raise ValueError("invalid Mach-O load command length")
        if command == 0x19:
            if size < 72:
                raise ValueError("short segment command")
            vm, span, offset, length = struct.unpack_from("<4Q", data, cursor + 24)
            if span and (vm < 0xFFFFFE0007004000 or vm % 0x4000 or vm + span > 1 << 64):
                raise ValueError("unsupported kernel segment placement")
            if length > span or offset > len(data) or length > len(data) - offset:
                raise ValueError("kernel segment outside source image")
            if span:
                segments.append((vm, span, offset, length))
        elif command == 0xB:
            if size < 80:
                raise ValueError("short dynamic-symbol command")
            relocations = struct.unpack_from("<I", data, cursor + 76)[0]
        cursor += size
    if cursor != end or not segments or len(segments) > 32 or relocations > 0x100000:
        raise ValueError("unsupported segment/relocation envelope")
    if not any(vm == 0xFFFFFE0007004000 and offset == 0 and length >= end
               for vm, _, offset, length in segments):
        raise ValueError("kernel does not have the expected file-backed header/link address")
    memory_size = max(vm + span for vm, span, _, _ in segments) - 0xFFFFFE0007004000
    if memory_size > 200 * 1024 * 1024:
        raise ValueError("kernel cannot fit the minimum retained-memory profile")
    return {"bytes": len(data), "linkedHeaderVA": "0xfffffe0007004000",
            "materializedBytes": (memory_size + 0x3FFF) & ~0x3FFF, "localRelocations": relocations}


def assembly_path(path):
    value = str(path)
    if any(ord(character) < 32 for character in value):
        raise ValueError("control character in input path")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--console-only", action="store_true")
    mode.add_argument("--kernel", type=Path, help="source-built VZGENERIC ARM64 kernel")
    parser.add_argument("--ramroot", type=Path, help="source-built, 16-KiB-aligned RAM root")
    parser.add_argument("--image-tool", type=Path, required=True)
    parser.add_argument("--storage", action="store_true", help="Distinct writable virtio-block/HFS guest profile")
    parser.add_argument("--network", action="store_true", help="Distinct VM-only VirtIO Ethernet profile")
    args = parser.parse_args()
    if bool(args.ramroot) == bool(args.console_only):
        parser.error("--ramroot is required with --kernel, and forbidden with --console-only")
    output = Path(tempfile.mkdtemp(prefix="darwin-vz-loader-", dir="/private/tmp"))
    clang = subprocess.check_output(["xcrun", "--find", "clang"], text=True).strip()
    zig = ROOT / "build/rpi5/zig-aarch64-macos-0.16.0/zig"
    objects = []
    sources = [SOURCES / "boot.c", SOURCES / "virtio_console.c", SOURCES / "transition.S"]
    headers = [SOURCES / "efi.h", SOURCES / "virtio_console.h"]
    if args.storage:
        if args.console_only:
            parser.error("--storage requires a kernel and RAM root")
        sources.append(SOURCES / "virtio_block.c")
        headers.append(SOURCES / "virtio_block.h")
    if args.network:
        if args.console_only:
            parser.error("--network requires a kernel and RAM root")
        sources.append(SOURCES / "virtio_net.c")
        headers.append(SOURCES / "virtio_net.h")
    input_metadata = None
    seed_path = None
    if not args.console_only:
        kernel_path, root_path = args.kernel.resolve(), args.ramroot.resolve()
        if not kernel_path.is_file() or not root_path.is_file():
            raise ValueError("kernel and ramroot must be existing regular files")
        kernel = kernel_path.read_bytes()
        root = root_path.read_bytes()
        input_metadata = kernel_metadata(kernel)
        if not root or len(root) % 0x4000 or len(root) > 8 * 1024 * 1024:
            raise ValueError("RAM root must be nonempty, 16-KiB aligned, and no larger than 8 MiB")
        if kernel[:4] != root[:4] or b"RPI5RFS1" not in root:
            raise ValueError("RAM root lacks the expected Mach-O PID1/RPI5RFS1 container")
        if len(kernel) + len(root) > 31 * 1024 * 1024:
            raise ValueError("embedded payload exceeds the 32-MiB EFI packaging limit")
        (output / "kernel.macho").write_bytes(kernel)
        (output / "ramroot.bin").write_bytes(root)
        seed_path = output / "boot-seed.bin"
        with seed_path.open("xb") as seed_file:
            os.fchmod(seed_file.fileno(), 0o600)
            seed_file.write(os.urandom(256))
        assembly = output / "payload.S"
        assembly.write_text(
            '.section .rdata,"dr"\n.balign 16\n.globl vz_kernel_start\nvz_kernel_start:\n'
            f'.incbin "{assembly_path(output / "kernel.macho")}"\n'
            '.globl vz_kernel_end\nvz_kernel_end:\n.balign 16\n.globl vz_ramroot_start\nvz_ramroot_start:\n'
            f'.incbin "{assembly_path(output / "ramroot.bin")}"\n'
            '.globl vz_ramroot_end\nvz_ramroot_end:\n.section .data,"dw"\n.balign 16\n'
            '.globl vz_boot_seed\nvz_boot_seed:\n'
            f'.incbin "{assembly_path(seed_path)}"\n.globl vz_boot_seed_end\nvz_boot_seed_end:\n')
        sources += [ROOT / "loader/rpi5/macho.c", ROOT / "loader/rpi5/boot_args.c",
                    ROOT / "loader/rpi5/apple_dt.c", assembly]
        headers += [ROOT / "loader/rpi5/macho.h", ROOT / "loader/rpi5/boot_args.h",
                    ROOT / "loader/rpi5/apple_dt.h"]
        input_metadata.update({"kernelSource": str(kernel_path), "ramrootSource": str(root_path),
                               "kernelSHA256": hashlib.sha256(kernel).hexdigest(),
                               "ramrootSHA256": hashlib.sha256(root).hexdigest(),
                               "ramrootBytes": len(root), "seedSource": "fresh os.urandom(256), never logged"})
    for source in sources:
        obj = output / (source.stem + ".obj")
        run([clang, "--target=aarch64-pc-windows-msvc", "-ffreestanding", "-fno-builtin",
             "-fno-stack-protector", "-mno-stack-arg-probe", "-mgeneral-regs-only", "-O2", "-Wall", "-Wextra", "-Werror",
             f"-DVZ_CONSOLE_ONLY={int(args.console_only)}", f"-DVZ_WRITABLE_STORAGE={int(args.storage)}",
             f"-DVZ_NETWORK={int(args.network)}",
             "-c", source, "-o", obj])
        objects.append(obj)
    payload = output / "BOOTAA64.EFI"
    run([zig, "lld-link", "/subsystem:efi_application", "/entry:efi_main", "/nodefaultlib",
         "/machine:arm64", "/fixed:no", "/dynamicbase", "/out:" + str(payload), *objects])
    if seed_path:
        seed = seed_path.read_bytes()
        payload_bytes = payload.read_bytes()
        seed_offset = payload_bytes.find(seed)
        if seed_offset < 0 or payload_bytes.find(seed, seed_offset + 1) >= 0:
            raise ValueError("boot seed does not occupy one unique payload slot")
        seed_path.unlink()  # The fresh seed remains only inside the private EFI payload.
    run([args.image_tool.resolve(), payload, output / "efi.img"])
    manifest = {
        "mode": "console-only-not-xnu" if args.console_only else "xnu-handoff-not-yet-boot-verified",
        "directory": str(output), "payload": str(payload),
        "writableStorageProfile": args.storage,
        "networkProfile": args.network,
        "bootDisk": str(output / "efi.img"),
        "sources": {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else p.name:
                    hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sources + headers + [Path(__file__).resolve()]},
        "payloadSHA256": hashlib.sha256(payload.read_bytes()).hexdigest(),
    }
    if input_metadata:
        manifest["inputs"] = input_metadata
        disk = (output / "efi.img").read_bytes()
        payload_offset = disk.find(payload_bytes)
        if payload_offset < 0 or disk.find(payload_bytes, payload_offset + 1) >= 0:
            raise ValueError("EFI payload must occupy one contiguous disk extent")
        manifest["bootEntropySlot"] = {"payloadOffset": seed_offset,
            "diskOffset": payload_offset + seed_offset, "bytes": 256,
            "policy": "replace with fresh host entropy before each workspace boot"}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
