#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Expose genuine private Mach trap table and original libkernel declarations."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / 'tools/rpi5/build_apple_pthread_mach_providers.py'


def build():
    raw = ORIGINAL.read_text()
    replacements = {
        "prefix='apple-pthread-mach-'": "prefix='apple-pthread-mach-linkable-'",
        "flags[1:1] = ['-I', str(overlay)]": """flags[1:1] = ['-I', str(overlay), '-I', str(overlay / 'mach')]
    flags += ['-include', str(ROOT / 'libsyscall/wrappers/string/strings.h')]
    for name in ('mach/message.h', 'mach/mach_traps.h'):
        original = ROOT / 'osfmk' / name
        destination = overlay / name
        destination.write_bytes(original.read_bytes())
        pins[str(original)] = sha(original)
        installations[str(destination)] = dict(source=str(original), sha256=sha(original))
    pins[str(ROOT / 'tools/rpi5/build_apple_pthread_mach_providers.py')] = sha(ROOT / 'tools/rpi5/build_apple_pthread_mach_providers.py')""",
        "'-x', 'assembler-with-cpp', '-D__ASSEMBLER__=1'": "'-x', 'assembler-with-cpp', '-D__ASSEMBLER__=1', '-DPRIVATE=1'",
        "profile='original-apple-mach-thread-and-libkernel-provider-inventory-v1'":
            "profile='original-apple-mach-thread-and-libkernel-provider-linkable-v3'",
        "archive = out / 'libapple-pthread-mach-partial.a'": """trap_symbols = run(['xcrun', 'nm', '-g', out / 'mach-traps.o'], 'actual-mach-trap-symbols').stdout
    for symbol in ('_host_self_trap', '_thread_self_trap', '__kernelrpc_mach_port_construct_trap', '__kernelrpc_mach_port_deallocate_trap'):
        if not re.search(r'^[0-9a-f]+ T ' + symbol + '$', trap_symbols, re.M):
            raise ValueError('Original trap table implementation absent: ' + symbol)
    archive = out / 'libapple-pthread-mach-partial.a'""",
    }
    for old, new in replacements.items():
        if raw.count(old) != 1: raise ValueError('Frozen builder derivation no longer exact')
        raw = raw.replace(old, new)
    scope = {'__name__': 'private_mach_linkable_builder', '__file__': str(Path(__file__).resolve())}
    exec(compile(raw, str(ORIGINAL), 'exec'), scope)
    return scope['build']()


if __name__ == '__main__': build()
