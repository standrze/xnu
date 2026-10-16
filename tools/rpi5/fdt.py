# SPDX-License-Identifier: BSD-2-Clause
"""Bounded DTB structure reader; leaves property bytes untranslated.

Format reference: Devicetree Specification, chapter 5 (version 17).
This is host tooling, not the eventual freestanding loader parser.
"""
import struct


def available_memory(tree, *, additional_reserved):
    """Subtract known reservations. Caller must include DTB/live firmware data.

    Static reusable regions remain excluded until ownership protocols exist.
    Dynamic reservations and IOMMU bindings stop this initial implementation.
    """
    ram = memory_ranges(tree)
    root = tree["root"]
    excluded = list(tree["reservations"]) + list(additional_reserved)
    containers = [n for n in root["children"] if n["name"].split("@", 1)[0] == "reserved-memory"]
    if len(containers) > 1:
        raise ValueError("multiple reserved-memory containers")
    for container in containers:
        props = container["properties"]
        if props.get("status", b"okay\0") not in (b"okay\0", b"ok\0"):
            raise ValueError("unsupported reserved-memory container status")
        if props.get("ranges") != b"" or any(props.get(k) != root["properties"].get(k)
                                                for k in ("#address-cells", "#size-cells")):
            raise ValueError("reserved-memory requires matching cells and empty ranges")
        for child in container["children"]:
            p = child["properties"]
            if p.get("status") == b"disabled\0":
                continue
            if p.get("status", b"okay\0") not in (b"okay\0", b"ok\0"):
                raise ValueError("unsupported reservation status")
            if child["children"] or "iommu-addresses" in p or "reg" not in p:
                raise ValueError("dynamic/nested/IOMMU reservation requires implementation")
            if "no-map" in p and "reusable" in p:
                raise ValueError("conflicting reservation attributes")
            for flag in ("no-map", "reusable"):
                if flag in p and p[flag] != b"":
                    raise ValueError("reservation flag must be empty")
            # Reuse the exact root-cell tuple decoder, not Apple native-endian rules.
            temporary = {"root": {"properties": root["properties"], "children": [
                {"name": "memory", "properties": {"device_type": b"memory\0", "reg": p["reg"]}}]}}
            excluded.extend(memory_ranges(temporary))
    for pair in excluded:
        if len(pair) != 2 or any(type(v) is not int for v in pair) or not 0 <= pair[0] < pair[1] <= 1 << 40:
            raise ValueError("invalid physical reservation")
    merged = []
    for start, end in sorted(excluded):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    available = []
    for start, end in ram:
        cursor = start
        for low, high in merged:
            if high <= cursor or low >= end:
                continue
            if low > cursor:
                available.append((cursor, low))
            cursor = max(cursor, min(high, end))
        if cursor < end:
            available.append((cursor, end))
    return {"ram": ram, "reserved": merged, "available": available}


def memory_ranges(tree):
    """Decode root-level RAM ranges; not a usable-memory allocator.

    Reservations (including reserved-memory children) must be removed separately.
    Unsupported cell layouts and ambiguous memory nodes fail closed.
    """
    root = tree["root"]
    def cells(name):
        raw = root["properties"].get(name)
        if not isinstance(raw, bytes) or len(raw) != 4:
            raise ValueError("explicit root cell counts required")
        count = int.from_bytes(raw, "big")
        if count not in (1, 2):
            raise ValueError("unsupported root cell width")
        return count
    ac, sc = cells("#address-cells"), cells("#size-cells")
    stride = (ac + sc) * 4
    ranges = []
    for node in root["children"]:
        props = node["properties"]
        if node["name"].split("@", 1)[0] != "memory" and props.get("device_type") != b"memory\0":
            continue
        if props.get("device_type") != b"memory\0":
            raise ValueError("memory node missing device_type")
        status = props.get("status", b"okay\0")
        if status == b"disabled\0":
            continue
        if status not in (b"ok\0", b"okay\0"):
            raise ValueError("unsupported memory status")
        raw = props.get("reg", b"")
        if not raw or len(raw) % stride:
            raise ValueError("invalid memory reg length")
        for offset in range(0, len(raw), stride):
            address = int.from_bytes(raw[offset:offset + ac * 4], "big")
            size = int.from_bytes(raw[offset + ac * 4:offset + stride], "big")
            if size == 0 or address + size > 1 << 40:
                raise ValueError("memory range outside Pi 40-bit profile")
            ranges.append((address, address + size))
    ranges.sort()
    if not ranges or any(a[1] > b[0] for a, b in zip(ranges, ranges[1:])):
        raise ValueError("missing or overlapping RAM ranges")
    return ranges


def parse(data):
    def check(ok, message):
        if not ok:
            raise ValueError(message)

    check(isinstance(data, bytes) and 40 <= len(data) <= 16 * 1024 * 1024, "invalid DTB size")
    magic, total, so, strings, ro, version, compat, bootcpu, ns, sz = struct.unpack_from(">10I", data)
    check(magic == 0xd00dfeed and 40 <= total <= len(data), "invalid DTB header")
    check(version >= 17 and compat <= 17 and compat <= version, "unsupported DTB version")
    check(ro >= 40 and ro % 8 == 0 and so % 4 == 0, "unaligned DTB blocks")
    check(40 <= so <= total and sz <= total - so and 40 <= strings <= total and ns <= total - strings, "block outside DTB")
    reserved, pos = [], ro
    while True:
        check(pos + 16 <= total, "unterminated reservation map")
        address, size = struct.unpack_from(">QQ", data, pos)
        pos += 16
        if address == size == 0:
            break
        check(size > 0 and address + size <= 1 << 64, "invalid reservation")
        reserved.append((address, address + size))
    spans = sorted([(0, 40), (ro, pos), (so, so + sz), (strings, strings + ns)])
    check(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), "overlapping DTB blocks")
    ordered = sorted(reserved)
    check(all(a[1] <= b[0] for a, b in zip(ordered, ordered[1:])), "overlapping reservations")
    end = so + sz
    pos = so
    root, stack = None, []

    def cstring(offset, stop):
        nul = data.find(b"\0", offset, stop)
        check(nul >= offset, "unterminated DTB string")
        return data[offset:nul].decode("ascii"), nul + 1

    while pos < end:
        check(pos + 4 <= end, "truncated DTB token")
        token, = struct.unpack_from(">I", data, pos)
        pos += 4
        if token == 1:
            name, cursor = cstring(pos, end)
            pos = (cursor + 3) & ~3
            check(pos <= end and not any(data[cursor:pos]), "invalid node padding")
            check(len(stack) < 64 and "/" not in name, "invalid node depth/name")
            node = {"name": name, "properties": {}, "children": []}
            if stack:
                check(name and all(c["name"] != name for c in stack[-1]["children"]), "duplicate/empty child name")
                stack[-1]["children"].append(node)
            else:
                check(root is None and name == "", "invalid DTB root")
                root = node
            stack.append(node)
        elif token == 2:
            check(bool(stack), "unbalanced end node")
            stack.pop()
        elif token == 3:
            check(stack and not stack[-1]["children"] and pos + 8 <= end, "misplaced/truncated property")
            length, offset = struct.unpack_from(">II", data, pos)
            pos += 8
            check(offset < ns and length <= end - pos, "property out of bounds")
            name, _ = cstring(strings + offset, strings + ns)
            check(name and name not in stack[-1]["properties"], "duplicate/empty property name")
            stack[-1]["properties"][name] = data[pos:pos + length]
            cursor = pos + length
            pos = (cursor + 3) & ~3
            # Pi firmware leaves nonzero property padding; it is not data.
            check(pos <= end, "invalid property padding")
        elif token == 4:
            continue
        elif token == 9:
            check(root is not None and not stack and pos == end, "premature/trailing FDT_END")
            return {"root": root, "reservations": reserved, "boot_cpuid_phys": bootcpu, "total_size": total}
        else:
            raise ValueError("unknown DTB token")
    raise ValueError("missing FDT_END")
