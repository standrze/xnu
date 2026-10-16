# SPDX-License-Identifier: BSD-2-Clause
"""Read-only, bounded inventory of the Pi kernel's thin Mach-O loader inputs.

Structural success is not proof that a loader applies relocations correctly or
that instructions execute on Cortex-A76. Unknown load commands fail closed.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct


def inspect(data):
    def check(condition, message):
        if not condition:
            raise ValueError(message)

    def span(offset, size):
        check(0 <= offset <= len(data) and 0 <= size <= len(data) - offset,
              "file range out of bounds")

    def unpack(fmt, offset):
        span(offset, struct.calcsize(fmt))
        return struct.unpack_from(fmt, data, offset)

    magic, cpu, subtype, kind, ncmds, cmdbytes, flags, reserved = unpack("<8I", 0)
    check((magic, cpu, subtype, kind) == (0xfeedfacf, 0x100000c, 0, 2),
          "expected thin little-endian ARM64/ALL MH_EXECUTE")
    check(reserved == 0, "nonzero reserved header")
    span(32, cmdbytes)
    check(ncmds <= cmdbytes // 8, "impossible command count")
    pos, end = 32, 32 + cmdbytes
    segments, commands, entries, linkdata = [], [], [], []
    symtab = dysymtab = None
    singleton = set()
    for _ in range(ncmds):
        check(pos + 8 <= end, "truncated command header")
        cmd, size = unpack("<2I", pos)
        check(size >= 8 and size % 8 == 0 and size <= end - pos, "invalid command size")
        check(cmd in {0x19, 2, 0xb, 0x1b, 0x32, 0x2a, 5, 0x1e, 0x26},
              f"unsupported load command {cmd:#x}")
        if cmd != 0x19:
            check(cmd not in singleton, "duplicate singleton command")
            singleton.add(cmd)
        commands.append({"command": hex(cmd), "size": size})
        if cmd == 0x19:
            check(size >= 72, "short segment command")
            name, va, vs, off, fs, maxp, initp, ns, sf = unpack("<16s4Q4I", pos + 8)
            check(size == 72 + ns * 80, "invalid section count")
            span(off, fs)
            check(fs <= vs and va + vs <= 1 << 64, "invalid segment extent")
            check(not (initp & ~maxp) and not (maxp & ~7), "invalid protections")
            name = name.split(b"\0", 1)[0].decode("ascii")
            check(not any(s["name"] == name for s in segments), "duplicate segment")
            sections = []
            for i in range(ns):
                sn, sg, addr, length, so, align, ro, nr, fl, _, _, _ = unpack("<16s16s2Q8I", pos + 72 + i * 80)
                check(sg.split(b"\0", 1)[0].decode("ascii") == name, "section segment mismatch")
                check(va <= addr <= va + vs and length <= va + vs - addr, "section outside VM segment")
                check(align < 64 and addr % (1 << align) == 0, "invalid section alignment")
                if (fl & 255) not in {1, 12, 18}:  # zero-fill section kinds
                    check(off <= so <= off + fs and length <= off + fs - so, "section outside file segment")
                span(ro, nr * 8)
                sections.append({"name": sn.split(b"\0", 1)[0].decode("ascii"), "address": addr,
                                 "size": length, "relocations": nr})
            segments.append({"name": name, "vmaddr": va, "vmsize": vs, "fileoff": off,
                             "filesize": fs, "zero_fill": vs - fs, "initprot": initp, "sections": sections})
        elif cmd == 2:
            check(size == 24, "bad symbol command")
            symtab = unpack("<4I", pos + 8)
            span(symtab[0], symtab[1] * 16)
            span(symtab[2], symtab[3])
        elif cmd == 0xb:
            check(size == 80, "bad dynamic symbol command")
            dysymtab = unpack("<18I", pos + 8)
        elif cmd == 5:
            check(size == 288, "unsupported thread command")
            check(unpack("<2I", pos + 8) == (6, 68), "unsupported ARM thread state")
            entries.append(unpack("<Q", pos + 16 + 32 * 8)[0])
        elif cmd in {0x1e, 0x26}:
            check(size == 16, "bad linkedit data command")
            offset, length = unpack("<2I", pos + 8)
            span(offset, length)
            linkdata.append({"command": hex(cmd), "offset": offset, "size": length})
        elif cmd == 0x32:
            check(size >= 24, "short build version")
            check(size == 24 + unpack("<I", pos + 20)[0] * 8, "bad build tool count")
        else:
            check(size == {0x1b: 24, 0x2a: 16}[cmd], "bad metadata command")
        pos += size
    check(pos == end, "load command size mismatch")
    check(segments and len(entries) == 1, "missing segments or unique entry")
    for key, length in (("vmaddr", "vmsize"), ("fileoff", "filesize")):
        extents = sorted((s[key], s[key] + s[length]) for s in segments if s[length])
        check(all(a[1] <= b[0] for a, b in zip(extents, extents[1:])), "overlapping segments")
    check(any(s["initprot"] & 4 and s["vmaddr"] <= entries[0] and
              entries[0] + 4 <= s["vmaddr"] + s["filesize"]
              for s in segments), "entry instruction not fully file-backed and executable")
    check(symtab is not None and dysymtab is not None, "missing symbol tables")
    for start, count in zip(dysymtab[:6:2], dysymtab[1:6:2]):
        check(start <= symtab[1] and count <= symtab[1] - start, "symbol index out of bounds")
    check(dysymtab[5] == 0, "undefined dynamic symbols")
    for i in range(symtab[1]):
        string, typ, sect, desc, value = unpack("<IBBHQ", symtab[0] + i * 16)
        check(string < symtab[3], "symbol string out of bounds")
        check(data.find(b"\0", symtab[2] + string, symtab[2] + symtab[3]) != -1, "unterminated symbol")
        check(typ & 0xe0 or (typ & 0x0e) != 0, "undefined symbol")
    check(not any(dysymtab[6:14]), "unsupported auxiliary dynamic symbol tables")
    check(dysymtab[15] == 0, "external relocations require provider resolution")
    offset, count = dysymtab[16:18]
    span(offset, count * 8)
    relocations = Counter()
    relocation_sites = set()
    destinations = Counter()
    # ARM64 local relocation addresses are relative to the first segment.
    # This matches OSKext::slidePrelinkedExecutable; it is not a claim that
    # that kext routine rebases the main kernel at startup.
    relocation_base = segments[0]["vmaddr"]
    for i in range(count):
        address, bits = unpack("<2I", offset + i * 8)
        check(not address & 0x80000000, "unsupported scattered relocation")
        check(not bits & (1 << 27), "external local relocation")
        check(bits >> 24 == 6, "unsupported local relocation encoding")
        site = relocation_base + address
        check(site not in relocation_sites, "duplicate relocation site")
        relocation_sites.add(site)
        owners = [s for s in segments if s["vmaddr"] <= site and
                  site + 8 <= s["vmaddr"] + s["filesize"]]
        check(len(owners) == 1, "relocation site not file-backed")
        owner = owners[0]
        pointer = unpack("<Q", owner["fileoff"] + site - owner["vmaddr"])[0]
        targets = [s["name"] for s in segments if s["vmaddr"] <= pointer < s["vmaddr"] + s["vmsize"]]
        destinations[targets[0] if targets else "outside_nonempty_segments"] += 1
        relocations[f"type={(bits >> 28)},pcrel={(bits >> 24) & 1},width={1 << ((bits >> 25) & 3)}"] += 1
    base = min(s["vmaddr"] for s in segments if s["vmsize"])
    return {"sha256": hashlib.sha256(data).hexdigest(), "entry": entries[0], "flags": flags,
            "segments": segments, "commands": commands, "linkedit_data": linkdata,
            "local_relocations": dict(relocations), "virtual_base": base,
            "relocation_base": relocation_base, "relocation_pointer_destinations": dict(destinations),
            "physical_base_mod_32MiB": base % (32 * 1024 * 1024),
            "scope": "structural inventory only; relocation semantics, ISA and runtime loader remain unverified"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(args.kernel.read_bytes()), indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, f"Mach-O audit failed: {error}\n")
