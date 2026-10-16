#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Close original cancellable join's custom-stack wait using the real syscall."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'tools/rpi5/build_apple_pthread_create_join.py'
EXPECTED = '6dec0f32687fcdf7ba6ba729626dfebb6be32af1facf41907d73a75f132a5f7e'


def build():
    original_receipt = ROOT / 'build/rpi5/apple-pthread-create-join-pjaazcj7/manifest.json'
    if hashlib.sha256(original_receipt.read_bytes()).hexdigest() != EXPECTED:
        raise ValueError('Frozen create/join receipt changed')
    import json
    receipt = json.loads(original_receipt.read_text())
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != receipt['source_inputs_sha256'][str(SOURCE)]:
        raise ValueError('Frozen create/join builder changed')
    source = SOURCE.read_text()
    replacements = {
        "prefix='apple-pthread-create-join-'": "prefix='apple-pthread-join-wait-'",
        "ROOT/'tools/rpi5/user/pthread_create_runtime_calls.S'": "ROOT/'tools/rpi5/user/pthread_join_runtime_calls.S'",
        "profile='original-apple-cancellable-join-create-trap-v1'": "profile='original-apple-cancellable-join-real-wait-v1'",
        "actual_bsdthread_create_syscall=360,": "actual_bsdthread_create_syscall=360,actual_semwait_signal_nocancel_syscall=423,",
        "if not re.search(r'^360": "if not re.search(r'^423\\s+[^\\n]*\\b__semwait_signal_nocancel\\(',master.read_text(),re.M):raise ValueError('Actual join wait syscall changed')\n    if not re.search(r'^360",
        "for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):pins.update(base[key])":
            "for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):pins.update(base[key])\n    pins[str(_source_builder)]=sha(_source_builder)\n    pins[str(_source_receipt)]=sha(_source_receipt)",
        "--disassemble-symbols=_pthread_join,___bsdthread_create": "--disassemble-symbols=_pthread_join,___bsdthread_create,___semwait_signal_nocancel",
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise ValueError('Exact preserved builder derivation changed: ' + old)
        source = source.replace(old, new)
    scope = {'__file__':str(Path(__file__).resolve()), '__name__':'private_join_wait',
             '_source_builder':SOURCE, '_source_receipt':original_receipt}
    exec(compile(source,str(SOURCE),'exec'),scope)
    return scope['build']()


if __name__ == '__main__':
    build()
