# SPDX-License-Identifier: BSD-2-Clause
"""Validate a static thin arm64 PID 1 Mach-O and make a 16 KiB RAMDisk image.

The result is a raw executable followed only by zero padding. It is not a
filesystem, a signature, or proof that XNU can execute the binary.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct

PAGE_SIZE = 16384
MAX_SIZE = 64 * 1024 * 1024
MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
MH_EXECUTE = 2
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 2
LC_DYSYMTAB = 0xB
LC_UNIXTHREAD = 5

# These commands carry no runtime loader/import/signature dependency.
PASSIVE_COMMANDS = {0x1B, 0x26, 0x29, 0x2A, 0x32}
ALLOWED_COMMANDS = PASSIVE_COMMANDS | {LC_SEGMENT_64, LC_SYMTAB, LC_DYSYMTAB, LC_UNIXTHREAD}

PROCESS_LITERALS = {
    "_process_cmd": b"process",
    "_process_path": b"/sbin/launchd",
    "_process_arg": b"--process-child",
    "_process_tag": b"RPI5_EXEC_ARG",
    "_newline": b"\n",
    "_crlf": b"\r\n",
}


def inspect(data: bytes) -> dict:
    if len(data) < 32 or len(data) > MAX_SIZE:
        raise ValueError("Mach-O size outside supported range")
    magic, cpu, subtype, filetype, ncmds, sizeofcmds, flags, reserved = struct.unpack_from("<8I", data)
    if magic != MAGIC_64 or cpu != CPU_TYPE_ARM64 or filetype != MH_EXECUTE:
        raise ValueError("expected thin little-endian arm64 MH_EXECUTE")
    if subtype & 0xFF not in (0, 1):
        raise ValueError("unsupported arm64 CPU subtype")
    if reserved or not ncmds or ncmds > 4096 or sizeofcmds > len(data) - 32:
        raise ValueError("invalid Mach-O load-command envelope")
    if flags & 0x4:  # MH_DYLDLINK
        raise ValueError("dyld-linked executable is not static")

    offset, limit = 32, 32 + sizeofcmds
    segments = []
    symtab = None
    unixthread = None
    dysymtab_seen = False
    for _ in range(ncmds):
        if offset + 8 > limit:
            raise ValueError("truncated load command")
        cmd, size = struct.unpack_from("<II", data, offset)
        if size < 8 or size % 8 or offset + size > limit:
            raise ValueError("invalid load-command size")
        if cmd not in ALLOWED_COMMANDS:
            raise ValueError(f"unsupported or dynamic load command 0x{cmd:x}")
        if cmd == LC_SEGMENT_64:
            if size < 72:
                raise ValueError("truncated segment")
            name, vmaddr, vmsize, fileoff, filesize, maxprot, initprot, nsects, segflags = struct.unpack_from(
                "<16s4Q4I", data, offset + 8
            )
            if size != 72 + 80 * nsects or filesize > vmsize or fileoff + filesize > len(data):
                raise ValueError("invalid segment bounds")
            if vmsize and vmaddr + vmsize > 1 << 64:
                raise ValueError("segment address overflow")
            for index in range(nsects):
                section = offset + 72 + 80 * index
                reloff, nreloc = struct.unpack_from("<II", data, section + 56)
                if nreloc:
                    raise ValueError("unlinked section relocations present")
            segments.append((name.rstrip(b"\0").decode("ascii", "replace"), vmaddr, vmsize,
                             fileoff, filesize, initprot))
        elif cmd == LC_UNIXTHREAD:
            if unixthread is not None or size != 8 + 8 + 272:
                raise ValueError("expected one arm64 LC_UNIXTHREAD state")
            flavor, count = struct.unpack_from("<II", data, offset + 8)
            if (flavor, count) != (6, 68):
                raise ValueError("unexpected arm64 thread-state flavor/count")
            unixthread = struct.unpack_from("<Q", data, offset + 16 + 256)[0]
        elif cmd == LC_SYMTAB:
            if symtab is not None or size != 24:
                raise ValueError("invalid or duplicate symbol table")
            symtab = struct.unpack_from("<4I", data, offset + 8)
        elif cmd == LC_DYSYMTAB:
            if size != 80 or dysymtab_seen:
                raise ValueError("invalid or duplicate dynamic symbol table")
            dysymtab_seen = True
            fields = struct.unpack_from("<18I", data, offset + 8)
            if fields[5] or fields[13] or fields[15] or fields[17]:
                raise ValueError("undefined/indirect/external relocations present")
        offset += size
    if offset != limit or unixthread is None:
        raise ValueError("missing LC_UNIXTHREAD or command-size mismatch")
    if not segments or not any(name == "__TEXT" and fileoff == 0 and filesize >= limit and
                               (prot & 5) == 5 for name, _, _, fileoff, filesize, prot in segments):
        raise ValueError("missing executable __TEXT header mapping")
    if not any(vmaddr <= unixthread < vmaddr + vmsize and (prot & 4) for
               _, vmaddr, vmsize, _, _, prot in segments):
        raise ValueError("entry PC is not in executable segment")
    if symtab:
        symoff, nsyms, stroff, strsize = symtab
        if nsyms > (len(data) - symoff) // 16 or stroff + strsize > len(data):
            raise ValueError("symbol table out of bounds")
        for i in range(nsyms):
            strx, ntype, nsect, desc, value = struct.unpack_from("<IBBHQ", data, symoff + i * 16)
            if strx >= strsize or (ntype & 0xE) == 0:
                raise ValueError("undefined symbol or invalid symbol string index")
    return {"cpu_subtype": subtype, "entry_pc": unixthread, "mach_o_size": len(data),
            "ramdisk_size": (len(data) + PAGE_SIZE - 1) & ~(PAGE_SIZE - 1),
            "segments": len(segments), "sha256": hashlib.sha256(data).hexdigest()}


def inspect_process_literals(data: bytes, process_path: bytes = b"/sbin/launchd") -> dict:
    """Check the bytes addressed by linked symbols, not substring presence.

    Mach-O cstring coalescing can leave the desired word present in the file
    while its symbol/relocation addresses a preceding unterminated literal.
    This catches the physical process-dispatch failure from 2026-10-11.
    """
    inspect(data)
    offset = 32
    segments = []
    symtab = None
    for _ in range(struct.unpack_from("<I", data, 16)[0]):
        cmd, size = struct.unpack_from("<II", data, offset)
        if cmd == LC_SEGMENT_64:
            segments.append(struct.unpack_from("<4Q", data, offset + 24))
        elif cmd == LC_SYMTAB:
            symtab = struct.unpack_from("<4I", data, offset + 8)
        offset += size
    if symtab is None:
        raise ValueError("process literal validation requires linked symbols")
    symoff, nsyms, stroff, strsize = symtab
    symbols = {}
    for index in range(nsyms):
        strx, ntype, nsect, desc, value = struct.unpack_from("<IBBHQ", data, symoff + index * 16)
        end = data.find(b"\0", stroff + strx, stroff + strsize)
        if end < 0:
            raise ValueError("unterminated symbol name")
        name = data[stroff + strx:end].decode("ascii", "replace")
        if name in PROCESS_LITERALS:
            if name in symbols or (ntype & 0xE) != 0xE:
                raise ValueError(f"invalid or duplicate literal symbol {name}")
            symbols[name] = value
    result = {}
    for name, expected in (PROCESS_LITERALS | {"_process_path": process_path}).items():
        if name not in symbols:
            raise ValueError(f"missing process literal symbol {name}")
        address = symbols[name]
        matches = [(fileoff + address - vmaddr, filesize - (address - vmaddr))
                   for vmaddr, vmsize, fileoff, filesize in segments
                   if vmaddr <= address < vmaddr + filesize]
        if len(matches) != 1:
            raise ValueError(f"literal symbol {name} has no unique file mapping")
        fileoff, available = matches[0]
        literal = expected + b"\0"
        if available < len(literal) or data[fileoff:fileoff + len(literal)] != literal:
            raise ValueError(f"linked literal {name} does not address {expected!r}")
        result[name] = {"address": address, "value": expected.decode("ascii")}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_macho", type=Path)
    parser.add_argument("output_ramdisk", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.input_macho.resolve() == args.output_ramdisk.resolve():
        parser.error("input and output must differ")
    raw = args.input_macho.read_bytes()
    result = inspect(raw)
    image = raw + bytes(result["ramdisk_size"] - len(raw))
    args.output_ramdisk.write_bytes(image)
    result["ramdisk_sha256"] = hashlib.sha256(image).hexdigest()
    if args.manifest:
        args.manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
