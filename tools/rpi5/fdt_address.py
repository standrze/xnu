# SPDX-License-Identifier: BSD-2-Clause
"""Translate simple-bus FDT reg extents; PCI address formats are unsupported."""


def reg_ranges(tree, path):
    if not isinstance(path, str) or not path.startswith("/") or path == "/":
        raise ValueError("exact absolute device path required")
    chain = [tree["root"]]
    for part in path[1:].split("/"):
        matches = [n for n in chain[-1]["children"] if n["name"] == part]
        if not part or len(matches) != 1:
            raise ValueError("missing/ambiguous device path")
        chain.append(matches[0])
    for node in chain:
        if node["properties"].get("status", b"okay\0") not in (b"ok\0", b"okay\0"):
            raise ValueError("device or ancestor is unavailable")

    def width(node, key):
        raw = node["properties"].get(key)
        if not isinstance(raw, bytes) or len(raw) != 4 or int.from_bytes(raw, "big") not in (1, 2):
            raise ValueError("unsupported or missing bus cell width")
        return int.from_bytes(raw, "big") * 4

    def tuples(raw, widths):
        if not isinstance(raw, bytes) or len(raw) % sum(widths):
            raise ValueError("malformed bus tuples")
        result = []
        for pos in range(0, len(raw), sum(widths)):
            row = []
            for count in widths:
                row.append(int.from_bytes(raw[pos:pos + count], "big"))
                pos += count
            result.append(row)
        return result

    ac, sc = width(chain[-2], "#address-cells"), width(chain[-2], "#size-cells")
    extents = tuples(chain[-1]["properties"].get("reg"), [ac, sc])
    if not extents or any(size == 0 or address + size > 1 << (ac * 8) for address, size in extents):
        raise ValueError("invalid device reg extent")
    for i in range(len(chain) - 2, 0, -1):
        bus, parent = chain[i], chain[i - 1]
        child_width, parent_width = width(bus, "#address-cells"), width(parent, "#address-cells")
        raw = bus["properties"].get("ranges")
        if raw is None:
            raise ValueError("bus has no address translation")
        if raw:
            translations = tuples(raw, [child_width, parent_width, width(bus, "#size-cells")])
            mapped = []
            for address, size in extents:
                candidates = []
                for child, host, span in translations:
                    if span == 0 or child + span > 1 << (child_width * 8) or host + span > 1 << (parent_width * 8):
                        raise ValueError("invalid ranges extent")
                    if child <= address and address + size <= child + span:
                        candidates.append([host + address - child, size])
                if len(candidates) != 1:
                    raise ValueError("unmapped or ambiguous device extent")
                mapped.append(candidates[0])
            extents = mapped
        if any(address + size > 1 << (parent_width * 8) for address, size in extents):
            raise ValueError("parent bus address overflow")
    if any(address + size > 1 << 40 for address, size in extents):
        raise ValueError("translated address exceeds Pi physical profile")
    return [(address, address + size) for address, size in extents]
