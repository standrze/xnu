#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compare native segment inventory with the stricter host kernel audit.

Host execution only. Success does not authorize native loading or prove boot.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
import struct
import tempfile

from audit_macho import inspect
from prepare_handoff import prepare
from payload_container import encode as encode_container

ROOT = Path(__file__).resolve().parents[2]


class Segment(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in ("vmaddr", "vmsize", "fileoff", "filesize")] + [
        ("maxprot", C.c_uint32), ("initprot", C.c_uint32), ("name", C.c_ubyte * 16)]


class Inventory(C.Structure):
    _fields_ = [("segment", Segment * 32), ("entry", C.c_uint64), ("count", C.c_uint32)]


class Placement(C.Structure):
    _fields_ = [("destination", C.c_uint64 * 32), ("header", C.c_uint64),
                ("end", C.c_uint64), ("entry", C.c_uint64), ("count", C.c_uint32)]


class Range(C.Structure):
    _fields_ = [("start", C.c_uint64), ("end", C.c_uint64)]


class Payload(C.Structure):
    _fields_ = [("offset",C.c_uint64),("length",C.c_uint64)]


class Container(C.Structure):
    _fields_ = [("kernel",Payload),("init",Payload),("count",C.c_uint32)]


class HandoffInput(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in ("header_pa", "phys_base", "mem_size", "mem_actual", "args_pa", "tree_pa")] + [("usable", Range), ("tree_length", C.c_uint32)]


class Mapping(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in ("physical_start", "physical_end", "virtual_start", "virtual_end", "entries")] + [("table_pages", C.c_uint32)]


class Handoff(C.Structure):
    _fields_ = [("kernel", Placement), ("mapping", Mapping), ("top", C.c_uint64),
                ("args_pa", C.c_uint64), ("args", C.c_ubyte * 1152)]


def entry_trampoline(data, host, symbols):
    """Check the pinned plain-ARM64 __start -> start_first_cpu entry ABI."""
    entry = host["entry"]
    if symbols.get("__start") != entry or "_start_first_cpu" not in symbols:
        raise ValueError("missing or mismatched XNU entry symbols")
    backed = [s for s in host["segments"] if s["initprot"] & 4 and
              s["vmaddr"] <= entry and entry+4 <= s["vmaddr"]+s["filesize"]]
    if len(backed) != 1:
        raise ValueError("entry instruction not uniquely file-backed")
    offset = backed[0]["fileoff"] + entry - backed[0]["vmaddr"]
    instruction = struct.unpack_from("<I", data, offset)[0]
    if instruction & 0xfc000000 != 0x14000000:
        raise ValueError("entry is not the reviewed direct B trampoline")
    immediate = instruction & 0x03ffffff
    if immediate & (1 << 25):
        immediate -= 1 << 26
    target = entry + immediate*4
    if target != symbols["_start_first_cpu"]:
        raise ValueError("entry trampoline target changed")
    return target


def compare(path, probe_build=None, post_cma_layout=False):
    if post_cma_layout and probe_build is None:
        raise ValueError('post-CMA geometry requires an actual probe build')
    data = path.read_bytes()
    host = inspect(data)
    candidate = None
    if probe_build is not None:
        from build_probe import inspect as inspect_probe
        manifest = json.loads((probe_build / 'manifest.json').read_text())
        raw = (probe_build / 'probe.bin').read_bytes()
        checked = inspect_probe((probe_build / 'probe.elf').read_bytes(), raw, manifest['entry'])
        # The probe may carry an optional raw PID1 RAM disk after the kernel.
        # Reconstruct the complete container from the recorded, host-validated
        # input rather than accepting a kernel substring in arbitrary bytes.
        init_input = manifest.get('embedded_init')
        init_bytes = None
        if init_input is not None:
            from prepare_pid1 import inspect as inspect_pid1
            payload_file = probe_build / 'payload.bin'
            payload = payload_file.read_bytes()
            if len(payload) < 192 or payload[:8] != b'RPI5XNU\0':
                raise ValueError('invalid probe payload envelope')
            kind, flags, offset, length, digest, reserved = struct.unpack_from('<IIQQ32sQ', payload, 128)
            if kind != 2 or flags or reserved or offset > len(payload) or length > len(payload)-offset:
                raise ValueError('invalid probe init payload record')
            init_bytes = payload[offset:offset+length]
            if hashlib.sha256(init_bytes).digest() != digest:
                raise ValueError('probe init payload digest mismatch')
            if inspect_pid1(init_bytes) != init_input:
                raise ValueError('probe init image differs from recorded validation')
        packed_image = encode_container(data, init_bytes)
        if raw.count(packed_image) != 1:
            raise ValueError('probe must contain exactly this kernel container')
        candidate = (min(x['address'] for x in checked['loads']),
                     max(x['address']+x['memory_size'] for x in checked['loads']))
    symbol_text = subprocess.check_output(["xcrun", "nm", "-n", str(path)], text=True)
    symbols_by_name = {}
    for line in symbol_text.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] in {"__start", "_start_first_cpu"}:
            if fields[2] in symbols_by_name:
                raise ValueError("duplicate XNU entry symbol")
            symbols_by_name[fields[2]] = int(fields[0], 16)
    trampoline_target = entry_trampoline(data, host, symbols_by_name)
    bearssl = ROOT / "build/rpi5/bearssl-candidate"
    if subprocess.check_output(["git","-C",str(bearssl),"rev-parse","HEAD"],text=True).strip() != "7bea48e5e850ab4cafbe68d3765cdaba13a86d6f" or subprocess.check_output(["git","-C",str(bearssl),"status","--porcelain","--untracked-files=all"],text=True).strip():
        raise ValueError("requires unmodified pinned BearSSL candidate")
    with tempfile.TemporaryDirectory(prefix="rpi5-macho-") as directory:
        library = Path(directory) / "macho.dylib"
        subprocess.run(["xcrun", "clang", "-dynamiclib", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-I"+str(bearssl/"inc"), "-I"+str(bearssl/"src"),
                        *[str(ROOT / "loader/rpi5" / name) for name in ("macho.c", "handoff.c", "ranges.c", "bootstrap.c", "boot_args.c", "container.c", "hash.c")],
                        *[str(bearssl/"src"/name) for name in ("hash/sha2small.c","codec/dec32be.c","codec/enc32be.c")], "-o", str(library)], check=True)
        loaded = C.CDLL(str(library))
        native = loaded.rpi5_macho_segments
        native.argtypes = [C.c_void_p, C.c_size_t, C.POINTER(Inventory)]
        native.restype = C.c_int
        packed = encode_container(data)
        container_buffer = C.create_string_buffer(packed)
        container = Container()
        parse = loaded.rpi5_container_parse
        parse.argtypes = [C.c_void_p,C.c_size_t,C.POINTER(Container)]
        parse.restype = C.c_int
        if parse(container_buffer,len(packed),C.byref(container)) or container.count!=1 or container.kernel.length!=len(data):
            raise ValueError("actual kernel container verification failed")
        buffer = C.cast(C.byref(container_buffer,container.kernel.offset),C.c_void_p)
        symbols = loaded.rpi5_macho_symbols
        symbols.argtypes = [C.c_void_p, C.c_size_t]
        symbols.restype = C.c_int
        if symbols(buffer, len(data)):
            raise ValueError("native symbol validator rejected host-audited image")
        relocation_count = sum(host["local_relocations"].values())
        capacity = 1 << max(1, (2 * relocation_count - 1).bit_length())
        scratch = (C.c_uint32 * capacity)()
        checked_count = C.c_uint32()
        relocations = loaded.rpi5_macho_relocations
        relocations.argtypes = [C.c_void_p, C.c_size_t, C.POINTER(C.c_uint32), C.c_size_t, C.POINTER(C.c_uint32)]
        relocations.restype = C.c_int
        if relocations(buffer, len(data), scratch, capacity, C.byref(checked_count)) or checked_count.value != relocation_count:
            raise ValueError("native relocation validation/count disagrees with host audit")
        # Mutate only temporary in-memory copies; never alter the kernel file.
        if relocation_count >= 2:
            pos = 32
            for _ in range(struct.unpack_from("<I", data, 16)[0]):
                command, length = struct.unpack_from("<II", data, pos)
                if command == 0xb:
                    relocation_offset = struct.unpack_from("<I", data, pos + 72)[0]
                    break
                pos += length
            for kind in ("duplicate", "bad_encoding"):
                malformed = bytearray(data)
                if kind == "duplicate":
                    malformed[relocation_offset + 8:relocation_offset + 16] = malformed[relocation_offset:relocation_offset + 8]
                else:
                    struct.pack_into("<I", malformed, relocation_offset + 4, 0)
                bad_buffer = C.create_string_buffer(bytes(malformed))
                checked_count.value = 0xdeadbeef
                if relocations(bad_buffer, len(data), scratch, capacity, C.byref(checked_count)) != -1 or checked_count.value != 0xdeadbeef:
                    raise ValueError(f"native relocation rejection/atomicity failed: {kind}")
        result = Inventory()
        if native(buffer, len(data), C.byref(result)):
            raise ValueError("native segment validator rejected host-audited image")
        if result.entry != host["entry"] or result.count != len(host["segments"]):
            raise ValueError("entry/count disagreement")
        for index, expected in enumerate(host["segments"]):
            actual = result.segment[index]
            for field in ("vmaddr", "vmsize", "fileoff", "filesize", "initprot"):
                if getattr(actual, field) != expected[field]:
                    raise ValueError(f"segment {index} {field} disagreement")
            if bytes(actual.name).split(b"\0", 1)[0].decode("ascii") != expected["name"]:
                raise ValueError(f"segment {index} name disagreement")
        place = loaded.rpi5_macho_placement
        place.argtypes = [C.c_void_p, C.c_size_t, C.c_uint64, C.c_uint64, C.c_uint64, C.POINTER(Placement)]
        place.restype = C.c_int
        layout = Placement()
        # Synthetic host-test interval, NOT an approved board placement.
        header, low, high, link = 0x3004000, 0x2000000, 0x28000000, 0xfffffe0007004000
        if place(buffer, len(data), header, low, high, C.byref(layout)):
            raise ValueError("native synthetic placement rejected")
        expected_end = header
        for index, segment in enumerate(host["segments"]):
            destination = header + segment["vmaddr"] - link if segment["vmsize"] else 0
            if layout.destination[index] != destination:
                raise ValueError("native destination disagreement")
            if segment["vmsize"]:
                expected_end = max(expected_end, destination + segment["vmsize"])
        if layout.end != (expected_end + 0x3fff) & ~0x3fff or layout.entry != header + host["entry"] - link:
            raise ValueError("native placement extent/entry disagreement")
        prior = bytes(layout)
        for bad_header, bad_low, bad_high in ((header+0x4000,low,high), (header,low,layout.end-1), (header,header+1,high)):
            if place(buffer, len(data), bad_header, bad_low, bad_high, C.byref(layout)) != -1 or bytes(layout) != prior:
                raise ValueError("native placement rejection/atomicity failed")
        used = layout.end - header
        handoff_input = HandoffInput(header,low,high-low,high,layout.end,layout.end+0x4000,Range(low,high),128)
        live = Range(low,low+0x40000)
        handoff = Handoff()
        plan = loaded.rpi5_handoff_plan
        plan.argtypes = [C.c_void_p,C.c_size_t,C.POINTER(HandoffInput),C.POINTER(Range),C.c_size_t,C.c_char_p,C.c_size_t,C.POINTER(Handoff)]
        plan.restype = C.c_int
        if plan(buffer,len(data),C.byref(handoff_input),C.byref(live),1,b"-v",2,C.byref(handoff)):
            raise ValueError("native combined handoff rejected synthetic placement")
        reference = prepare(data,header_pa=header,phys_base=low,mem_size=high-low,mem_size_actual=high,
            ram=(low,high),reserved=[],boot_args_pa=handoff_input.args_pa,device_tree_pa=handoff_input.tree_pa,
            device_tree_length=128,live_allocations={"probe":(live.start,live.end)},command_line="-v")
        if bytes(handoff.args)!=reference["boot_args"] or handoff.top!=reference["top_of_kernel_data"] or handoff.kernel.entry!=reference["entry_pa"]:
            raise ValueError("combined handoff disagrees with host reference")
        prior_handoff = bytes(handoff)
        live.end=header+1
        if plan(buffer,len(data),C.byref(handoff_input),C.byref(live),1,b"-v",2,C.byref(handoff))!=-1 or bytes(handoff)!=prior_handoff:
            raise ValueError("combined handoff accepted live/kernel overlap or mutated output")
        if candidate is not None:
            # Explicit geometry experiment, NOT discovered board RAM or FDT.
            candidate_header = 0x7004000 if post_cma_layout else header
            candidate_low = 0x6000000 if post_cma_layout else 0x2000000
            candidate_end = layout.end + candidate_header - header
            candidate_fdt = (0xb000000,0xb400000) if post_cma_layout else (0x8000000,0x8400000)
            ci = HandoffInput(candidate_header,candidate_low,0x10000000-candidate_low,0x200000000,
                candidate_end,candidate_end+0x4000,Range(candidate_low,0x10000000),0x10000)
            clive = (Range * 2)(Range(*candidate), Range(*candidate_fdt))
            ch = Handoff()
            if plan(buffer,len(data),C.byref(ci),clive,2,b"-v",2,C.byref(ch)):
                raise ValueError('native candidate geometry rejected')
            cp = prepare(data,header_pa=candidate_header,phys_base=ci.phys_base,
                mem_size=ci.mem_size,mem_size_actual=ci.mem_actual,
                ram=(ci.usable.start,ci.usable.end),reserved=[(0,0x4080000)] if post_cma_layout else [(0,0x80000)],
                boot_args_pa=ci.args_pa,device_tree_pa=ci.tree_pa,
                device_tree_length=ci.tree_length,
                live_allocations={'probe':candidate,'fdt_capacity':candidate_fdt},
                command_line='-v')
            if (bytes(ch.args)!=cp['boot_args'] or ch.top!=cp['top_of_kernel_data'] or
                ch.kernel.entry!=cp['entry_pa'] or
                [ch.mapping.physical_start,ch.mapping.physical_end]!=cp['mapping']['physical_mapping']):
                raise ValueError('native candidate geometry disagrees with Python')
        arena = C.create_string_buffer(b"\xa5" * (used + 64), used + 64)
        materialize = loaded.rpi5_macho_materialize
        materialize.argtypes = [C.c_void_p, C.c_size_t, C.c_void_p, C.c_size_t, C.c_uint64,
                               C.POINTER(C.c_uint32), C.c_size_t, C.POINTER(Placement)]
        materialize.restype = C.c_int
        if materialize(buffer, len(data), arena, used, header, scratch, capacity, C.byref(layout)):
            raise ValueError("native host-buffer materialization rejected")
        expected_bytes = bytearray(used)
        for segment in host["segments"]:
            if segment["filesize"]:
                start = segment["vmaddr"] - link
                expected_bytes[start:start+segment["filesize"]] = data[segment["fileoff"]:segment["fileoff"]+segment["filesize"]]
        if arena.raw[:used] != expected_bytes or arena.raw[used:] != b"\xa5" * 64:
            raise ValueError("native copy/zero-fill or trailing canary mismatch")
        before = arena.raw
        if materialize(buffer, len(data), arena, used-1, header, scratch, capacity, C.byref(layout)) != -1 or arena.raw != before:
            raise ValueError("undersized materialization modified destination")
        if materialize(buffer, len(data), buffer, used, header, scratch, capacity, C.byref(layout)) != -1:
            raise ValueError("overlapping source/destination accepted")
        for policy in ("kernel_collection", "threaded_fixups"):
            bad = bytearray(data)
            if policy == "kernel_collection":
                struct.pack_into("<I", bad, 24, struct.unpack_from("<I", bad, 24)[0] | 0x80000000)
            else:
                pos = 32
                found = False
                for _ in range(struct.unpack_from("<I", bad, 16)[0]):
                    command, length = struct.unpack_from("<II", bad, pos)
                    if command == 0x19:
                        for section in range(struct.unpack_from("<I", bad, pos+64)[0]):
                            section_pos = pos+72+section*80
                            if struct.unpack_from("<Q", bad, section_pos+40)[0]:
                                bad[section_pos:section_pos+16] = b"__thread_starts".ljust(16,b"\0")
                                found = True
                                break
                    if found:
                        break
                    pos += length
                if not found:
                    raise ValueError("no nonempty section for threaded-fixup rejection test")
            bad_buffer = C.create_string_buffer(bytes(bad))
            prior_layout = bytes(layout)
            if materialize(bad_buffer, len(data), arena, used, header, scratch, capacity, C.byref(layout)) != -1 or arena.raw != before or bytes(layout) != prior_layout:
                raise ValueError(f"unsupported policy mutated output: {policy}")
    return {"image": str(path.resolve()), "sha256": host["sha256"],
            "segments": result.count, "entry": hex(result.entry), "local_relocations": relocation_count,
            "materialized_bytes_host_buffer": used,
            "verified_container_bytes": len(packed),
            "entry_trampoline_target": hex(trampoline_target),
            "candidate_probe_extent": candidate,
            "candidate_layout": "post-CMA experiment" if post_cma_layout else "historical synthetic experiment",
            "candidate_scope": "synthetic RAM/FDT capacity; no ownership or board approval",
            "result": "native validation and host-buffer copy agree; not physical load or boot proof"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--probe-build", type=Path, help="Check experimental layout using this actual probe ELF/binary")
    parser.add_argument("--post-cma-layout", action="store_true", help="Test geometry above observed low CMA reservation; not ownership approval")
    args = parser.parse_args()
    print(json.dumps(compare(args.image, args.probe_build, args.post_cma_layout), indent=2))
