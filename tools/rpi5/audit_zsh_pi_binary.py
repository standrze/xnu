#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only static trap/instruction inventory. Never qualifies Pi execution."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

try:
    from .prepare_pid1 import inspect as inspect_macho
    from .check_zsh_ramroot import checked_hash, read_bounded
except ImportError:
    from prepare_pid1 import inspect as inspect_macho
    from check_zsh_ramroot import checked_hash, read_bounded

ROOT = Path(__file__).resolve().parents[2]


def text_section(data):
    """Exactly one file-backed instruction section, within executable __TEXT."""
    inspect_macho(data)
    ncmds, sizeofcmds = struct.unpack_from("<II", data, 16)
    cursor, sections = 32, []
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, cursor)
        if size < 8 or cursor + size > 32 + sizeofcmds:
            raise ValueError("invalid Mach-O command span")
        if cmd == 0x19:
            if size < 72:
                raise ValueError("truncated segment")
            name = data[cursor + 8:cursor + 24].rstrip(b"\0")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, cursor + 24)
            maxprot, initprot, count = struct.unpack_from("<iiI", data, cursor + 56)
            if size != 72 + count * 80:
                raise ValueError("invalid section count")
            for index in range(count):
                pos = cursor + 72 + index * 80
                section = data[pos:pos + 16].rstrip(b"\0")
                segment = data[pos + 16:pos + 32].rstrip(b"\0")
                address, length, offset = struct.unpack_from("<QQI", data, pos + 32)
                flags = struct.unpack_from("<I", data, pos + 64)[0]
                if not flags & 0x80000400:  # PURE/SOME_INSTRUCTIONS
                    continue
                if (section != b"__text" or segment != name or name != b"__TEXT"
                        or initprot != 5 or maxprot != 5 or address % 4 or length % 4
                        or not length or offset < fileoff or offset + length > fileoff + filesize
                        or address < vmaddr or address + length > vmaddr + vmsize
                        or address - vmaddr != offset - fileoff
                        or offset + length > len(data) or (flags & 0xff) != 0):
                    raise ValueError("unsupported instruction section")
                sections.append((address, data[offset:offset + length]))
        cursor += size
    if cursor != 32 + sizeofcmds or len(sections) != 1:
        raise ValueError("need exactly one completely bounded instruction section")
    return sections[0]


def source_tables(bsd, mach):
    """Declaration inventory only: deliberately does not evaluate #if branches."""
    syscalls, traps = {}, {}
    for line in bsd.splitlines():
        match = re.match(r"^(\d+)\s+\S+\s+\S+\s+\{\s*[^{};]*?\b([A-Za-z_]\w*)\(", line)
        if match:
            syscalls.setdefault(int(match[1]), set()).add(match[2])
    for match in re.finditer(r"/\*\s*(\d+)\s*\*/\s*MACH_TRAP\(\s*(\w+)", mach):
        traps.setdefault(int(match[1]), set()).add(match[2])
    return syscalls, traps


def immediate_x16(word):
    # Only a single immediately preceding 64-bit MOVZ/MOVN to X16 is resolved.
    # MOVK chains, register-derived calls and cross-branch propagation stay unknown.
    op = word & 0xff80001f
    if op not in (0xd2800010, 0x92800010):
        return None
    value = ((word >> 5) & 0xffff) << (((word >> 21) & 3) * 16)
    if op == 0x92800010:
        value = (~value) & ((1 << 64) - 1)
    return value - (1 << 64) if value >> 63 else value


def inventory(code, base, listing, syscalls, traps):
    rows, symbol = [], None
    for line in listing.splitlines():
        label = re.fullmatch(r"([0-9a-fA-F]+) <(.+)>:", line)
        if label:
            symbol = label[2]
        match = re.fullmatch(r"([0-9a-fA-F]+):\s+(\S+)\s*(.*)", line)
        if match:
            rows.append((int(match[1], 16), match[2], match[3], symbol))
    if not code or len(code) % 4 or len(rows) != len(code) // 4:
        raise ValueError("disassembler did not cover every instruction word")
    counts, calls, system, unknown = Counter(), [], [], []
    for index, (address, mnemonic, operands, label) in enumerate(rows):
        if address != base + index * 4:
            raise ValueError("disassembly has a gap, duplicate or out-of-order address")
        counts[mnemonic] += 1
        word = struct.unpack_from("<I", code, index * 4)[0]
        is_svc = word & 0xffe0001f == 0xd4000001
        if is_svc != (mnemonic == "svc"):
            raise ValueError("raw SVC encoding disagrees with disassembler")
        if mnemonic in ("<unknown>", ".word", ".long", ".inst"):
            unknown.append(hex(address))
        if mnemonic in ("mrs", "msr", "sys", "dc", "ic"):
            system.append({"address": hex(address), "symbol": label,
                           "instruction": mnemonic + " " + operands})
        if not is_svc:
            continue
        number = None
        if index and rows[index - 1][3] == label:
            number = immediate_x16(struct.unpack_from("<I", code, (index - 1) * 4)[0])
        kind, declarations = "unresolved", []
        if number == 0x80000000:
            kind = "platform"
        elif number is not None and number < 0:
            kind, declarations = "mach", sorted(traps.get(-number, set()))
        elif number is not None:
            kind, declarations = "bsd", sorted(syscalls.get(number, set()))
        calls.append({"address": hex(address), "symbol": label,
                      "svc_immediate": (word >> 5) & 0xffff,
                      "immediately_preceding_x16": number, "kind": kind,
                      "current_source_declarations": declarations,
                      "runtime_argument_and_result_contract_proven": False})
    if not calls:
        raise ValueError("no trap sites inventoried")
    return {"text_address": hex(base), "text_bytes": len(code),
            "instruction_words": len(rows), "mnemonics": dict(sorted(counts.items())),
            "unknown_decode_addresses": unknown, "system_register_sites": system,
            "trap_sites": calls, "trap_count": len(calls),
            "unresolved_immediate_sites": sum(c["kind"] == "unresolved" for c in calls)}


def audit(zsh, expected):
    data = read_bounded(zsh)
    digest = checked_hash(data, expected, "zsh")
    base, code = text_section(data)
    source_paths = [ROOT / "bsd/kern/syscalls.master", ROOT / "osfmk/kern/syscall_sw.c"]
    source_bytes = [read_bounded(path) for path in source_paths]
    syscalls, traps = source_tables(*(item.decode() for item in source_bytes))
    command = ["xcrun", "llvm-objdump", "--disassemble", "--mcpu=cortex-a76",
               "--no-show-raw-insn", str(zsh)]
    completed = subprocess.run(command, capture_output=True, text=True, check=True, timeout=60)
    # Bind the inspected file to the disassembly input across the external tool.
    checked_hash(read_bounded(zsh), digest, "zsh after disassembly")
    for path, before in zip(source_paths, source_bytes):
        if read_bounded(path) != before:
            raise ValueError("source declaration table changed during audit")
    if completed.stderr.strip():
        raise ValueError("disassembler emitted diagnostics: " + completed.stderr[:500])
    result = inventory(code, base, completed.stdout, syscalls, traps)
    result.update({"schema_version": 1, "scope": "static decode/trap inventory only",
                   "zsh_sha256": digest, "disassembler_command": command,
                   "disassembly_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
                   "current_source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(b).hexdigest()
                                             for p, b in zip(source_paths, source_bytes)},
                   "source_tables_preprocessor_evaluated": False,
                   "source_tables_bound_to_installed_kernel": False,
                   "isa_compatibility_proven": False, "pi_executed": False,
                   "syscall_semantics_proven": False, "serial_actions": 0,
                   "sd_actions": 0, "reboots": 0,
                   "limitations": [
                       "Decoder CPU option is not architectural feature validation",
                       "Immediate setup is local evidence, not control-flow/call-path proof",
                       "Source declarations do not prove configured or installed providers",
                       "Startup/TSD, signals, VM, FP/SIMD and serial TTY need Pi acceptance",
                   ]})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zsh", type=Path, required=True)
    parser.add_argument("--zsh-sha256", required=True)
    parser.add_argument("--report", type=Path, help="New local report only; never overwrite")
    args = parser.parse_args()
    result = audit(args.zsh, args.zsh_sha256)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.report:
        with args.report.open("x") as output:
            output.write(encoded)
        print(json.dumps({"report": str(args.report), "trap_count": result["trap_count"],
                          "instruction_words": result["instruction_words"],
                          "unknown_decode_addresses": result["unknown_decode_addresses"],
                          "unresolved_immediate_sites": result["unresolved_immediate_sites"],
                          "pi_executed": False}, indent=2))
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
