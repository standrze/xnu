# SPDX-License-Identifier: BSD-2-Clause
"""Encode Apple flattened trees, not Linux FDT blobs or board descriptions."""
import struct


def encode(root, *, max_bytes=16 * 1024 * 1024):
    """Nodes contain name, properties (bytes values), and children.

    Property semantics and hardware truth are the caller's responsibility.
    Integer values must be deliberately encoded by the caller; this prevents
    implicitly copying Linux FDT's big-endian cells into Apple DT properties.
    """
    if type(max_bytes) is not int or not 0 < max_bytes <= 0xffffffff:
        raise ValueError("invalid tree size limit")
    output = bytearray()
    active = set()

    def append(value):
        if len(value) > max_bytes - len(output):
            raise ValueError("tree exceeds size limit")
        output.extend(value)

    def text(value, limit):
        if not isinstance(value, str) or not value or "\0" in value:
            raise ValueError("invalid tree name")
        result = value.encode("ascii")
        if len(result) > limit:
            raise ValueError("tree name too long")
        return result

    def node(value, depth):
        if depth > 64 or id(value) in active:
            raise ValueError("tree depth or cycle")
        if not isinstance(value, dict) or set(value) != {"name", "properties", "children"}:
            raise ValueError("invalid node schema")
        name = text(value["name"], 63)
        if b"/" in name:
            raise ValueError("node name must be a single path component")
        props, children = value["properties"], value["children"]
        if not isinstance(props, dict) or "name" in props or not isinstance(children, list):
            raise ValueError("invalid properties or children")
        active.add(id(value))
        append(struct.pack("<II", len(props) + 1, len(children)))
        for key, data in [("name", name + b"\0"), *props.items()]:
            key_bytes = text(key, 31)
            if not isinstance(data, bytes) or len(data) > 0xffffffff:
                raise ValueError("property values must be bounded bytes")
            append(key_bytes.ljust(32, b"\0") + struct.pack("<I", len(data)))
            append(data)
            append(bytes((-len(data)) % 4))
        seen = set()
        for child in children:
            if not isinstance(child, dict) or not isinstance(child.get("name"), str):
                raise ValueError("invalid child")
            if child["name"] in seen:
                raise ValueError("duplicate child name")
            seen.add(child["name"])
            node(child, depth + 1)
        active.remove(id(value))

    node(root, 0)
    return bytes(output)
