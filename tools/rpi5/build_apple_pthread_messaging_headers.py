#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Install genuine public/private declarations needed by original log paths."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / 'tools/rpi5/build_apple_pthread_messaging.py'


def build():
    script = PARENT.read_text()
    insertion = '''extra.update({
        "prefix='apple-pthread-messaging-'": "prefix='apple-pthread-messaging-headers-'",
        "flags += ['-include', str(ROOT / 'libsyscall/wrappers/string/strings.h')]": """flags += ['-include', str(ROOT / 'libsyscall/wrappers/string/strings.h')]
    flags += ['-include', 'pthread.h', '-include', str(ROOT / 'bsd/sys/proc_info_private.h')]
    sdk_path = Path(flags[flags.index('-isysroot') + 1])
    public_dyld = sdk_path / 'usr/include/mach-o/dyld.h'
    installed_dyld = overlay / 'mach-o/dyld.h'
    installed_dyld.parent.mkdir(parents=True, exist_ok=True)
    installed_dyld.write_bytes(public_dyld.read_bytes())
    pins[str(public_dyld)] = sha(public_dyld)
    installations[str(installed_dyld)] = dict(source=str(public_dyld), sha256=sha(public_dyld))
    pins[str(ROOT / 'tools/rpi5/build_apple_pthread_messaging.py')] = sha(ROOT / 'tools/rpi5/build_apple_pthread_messaging.py')""",
        "profile='original-apple-pthread-messaging-provider-inventory-v1'": "profile='original-apple-pthread-messaging-headers-v2'",
    })
    for old, new in extra.items():'''
    # This source transformation becomes part of the exact recorded builder
    # chain. It only installs original declarations; it does not alter bodies.
    if script.count('    for old, new in extra.items():') != 1: raise ValueError('Frozen wrapper changed')
    script = script.replace('    for old, new in extra.items():', '    ' + insertion)
    scope = {'__name__': 'private_messaging_headers_builder', '__file__': str(Path(__file__).resolve())}
    exec(compile(script, str(PARENT), 'exec'), scope)
    return scope['build']()


if __name__ == '__main__': build()
