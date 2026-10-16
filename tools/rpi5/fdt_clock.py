# SPDX-License-Identifier: BSD-2-Clause
"""Resolve fixed-clock FDT consumers; programmable clock trees are unsupported."""


def fixed_clock_rates(tree, consumer_path):
    paths, handles = {}, {}
    def visit(node, path):
        paths[path] = node
        raw = node["properties"].get("phandle")
        if raw is not None:
            if len(raw) != 4 or int.from_bytes(raw, "big") in (0, 0xffffffff):
                raise ValueError("invalid clock-tree phandle")
            handle = int.from_bytes(raw, "big")
            if handle in handles:
                raise ValueError("duplicate phandle")
            handles[handle] = node
        for child in node["children"]:
            visit(child, path.rstrip("/") + "/" + child["name"])
    visit(tree["root"], "/")
    if consumer_path not in paths:
        raise ValueError("missing clock consumer")
    props = paths[consumer_path]["properties"]
    names = props.get("clock-names", b"")
    clocks = props.get("clocks", b"")
    if not names.endswith(b"\0") or not clocks or len(clocks) % 4:
        raise ValueError("invalid named clock references")
    names = names[:-1].decode("ascii").split("\0")
    if not all(names) or len(set(names)) != len(names):
        raise ValueError("duplicate/empty clock names")
    pos, result = 0, {}
    for name in names:
        if pos + 4 > len(clocks):
            raise ValueError("missing clock reference")
        handle = int.from_bytes(clocks[pos:pos + 4], "big")
        pos += 4
        if handle not in handles:
            raise ValueError("unresolved clock phandle")
        provider = handles[handle]["properties"]
        if (provider.get("#clock-cells") != bytes(4) or
            provider.get("compatible") != b"fixed-clock\0" or
            provider.get("status", b"okay\0") not in (b"okay\0", b"ok\0")):
            raise ValueError("unsupported or unavailable clock provider")
        rate = provider.get("clock-frequency", b"")
        if len(rate) != 4 or int.from_bytes(rate, "big") == 0:
            raise ValueError("invalid fixed clock rate")
        result[name] = int.from_bytes(rate, "big")
    if pos != len(clocks):
        raise ValueError("extra clock references")
    return result
