# SPDX-License-Identifier: BSD-2-Clause
"""Version 1 integrity envelope. Not a boot image, signature or seed transport."""
import hashlib
import struct


def encode(kernel, init=None):
    payloads = [kernel] if init is None else [kernel, init]
    if any(not isinstance(p, bytes) or not 0 < len(p) <= 256 << 20 for p in payloads):
        raise ValueError("payload must be nonempty bounded bytes")
    table = bytearray()
    data = bytearray(64 + 64 * len(payloads))
    for kind, payload in enumerate(payloads, 1):
        data.extend(bytes(-len(data) % 64))
        offset = len(data)
        data.extend(payload)
        table.extend(struct.pack("<IIQQ32sQ", kind, 0, offset, len(payload), hashlib.sha256(payload).digest(), 0))
    if len(data) > 512 << 20:
        raise ValueError("container exceeds limit")
    data[:64] = struct.pack("<8sIIQII32s", b"RPI5XNU\0", 1, 64, len(data), len(payloads), 0, hashlib.sha256(table).digest())
    data[64:64+len(table)] = table
    return bytes(data)
