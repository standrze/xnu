#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct original-header closure over the frozen initial Mach inventory."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / 'tools/rpi5/build_apple_pthread_mach_providers.py'


def build():
    raw = ORIGINAL.read_text()
    replacements = {
        "prefix='apple-pthread-mach-'": "prefix='apple-pthread-mach-headers-'",
        "flags[1:1] = ['-I', str(overlay)]": """flags[1:1] = ['-I', str(overlay), '-I', str(overlay / 'mach')]
    flags += ['-include', 'string.h']
    for name in ('mach/message.h', 'mach/mach_traps.h'):
        original = ROOT / 'osfmk' / name
        destination = overlay / name
        destination.write_bytes(original.read_bytes())
        pins[str(original)] = sha(original)
        installations[str(destination)] = dict(source=str(original), sha256=sha(original))
    pins[str(ROOT / 'tools/rpi5/build_apple_pthread_mach_providers.py')] = sha(ROOT / 'tools/rpi5/build_apple_pthread_mach_providers.py')""",
        "profile='original-apple-mach-thread-and-libkernel-provider-inventory-v1'":
            "profile='original-apple-mach-thread-and-libkernel-provider-headers-v2'",
    }
    for old, new in replacements.items():
        if raw.count(old) != 1: raise ValueError('Frozen builder derivation no longer exact')
        raw = raw.replace(old, new)
    scope = {'__name__': 'private_mach_header_builder', '__file__': str(Path(__file__).resolve())}
    exec(compile(raw, str(ORIGINAL), 'exec'), scope)
    return scope['build']()


if __name__ == '__main__': build()
