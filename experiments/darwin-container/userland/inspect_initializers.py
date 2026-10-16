# SPDX-License-Identifier: BSD-2-Clause
"""Inspect linked static Mach-O constructor pointers, without executing them."""
import struct

from prepare_pid1 import inspect


def inspect_initializers(data, expected):
    inspect(data)
    offset = 32
    sections, mappings = [], []
    symtab = None
    for _ in range(struct.unpack_from("<I", data, 16)[0]):
        command, size = struct.unpack_from("<II", data, offset)
        if command == 0x19:
            vmaddr, _, fileoff, filesize = struct.unpack_from("<4Q", data, offset + 24)
            protection = struct.unpack_from("<I", data, offset + 60)[0]
            mappings.append((vmaddr, filesize, protection))
            count = struct.unpack_from("<I", data, offset + 64)[0]
            for index in range(count):
                name, segment, address, length, start = struct.unpack_from("<16s16sQQI", data, offset + 72 + 80 * index)
                if name.rstrip(b"\0") == b"__mod_init_func":
                    if segment.rstrip(b"\0") != b"__DATA" or length != 8 * len(expected):
                        raise ValueError("unexpected static initializer section")
                    if start < fileoff or start + length > fileoff + filesize or address != vmaddr + start - fileoff:
                        raise ValueError("initializer section outside file-backed segment")
                    sections.append(struct.unpack_from("<" + "Q" * len(expected), data, start))
        elif command == 2:
            symtab = struct.unpack_from("<4I", data, offset + 8)
        offset += size
    if len(sections) != 1 or symtab is None:
        raise ValueError("missing unique initializer section or symbol table")
    symoff, count, stroff, strsize = symtab
    symbols = {}
    for index in range(count):
        name_offset, kind, _, _, address = struct.unpack_from("<IBBHQ", data, symoff + 16 * index)
        end = data.find(b"\0", stroff + name_offset, stroff + strsize)
        if end < 0:
            raise ValueError("unterminated symbol")
        name = data[stroff + name_offset:end].decode("ascii")
        if name in expected:
            if name in symbols or kind & 0xE != 0xE:
                raise ValueError("duplicate or non-section initializer symbol")
            symbols[name] = address
    pointers = sections[0]
    if set(symbols) != set(expected) or len(set(pointers)) != len(expected) or set(pointers) != set(symbols.values()):
        raise ValueError("initializer pointers do not match original module constructors")
    for pointer in pointers:
        if not any(start <= pointer < start + length and protection & 4 for start, length, protection in mappings):
            raise ValueError("initializer pointer is not executable and file backed")
    return {"count": len(pointers), "original_constructor_addresses": symbols,
            "scope": "linked pointer/section inspection; actual constructor execution requires guest evidence"}
