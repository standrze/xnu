#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserved host adapter test plus exact empty/unterminated/two-arg bounds."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'tools/rpi5/check_apple_pthread_static_native.py'
RECEIPT=ROOT/'build/rpi5/apple-pthread-static-native-j911i_hm/manifest.json'
EXPECTED='8fa923a9e63ffcc074ac7c5378e68298e3d077cd998741f95884e94b80be965d'

def check():
    if hashlib.sha256(RECEIPT.read_bytes()).hexdigest()!=EXPECTED:raise ValueError('Host receipt drift')
    report=json.loads(RECEIPT.read_text())
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=report['source_inputs_sha256'][str(SOURCE)]:raise ValueError('Host builder drift')
    source=SOURCE.read_text()
    replacements={
        "prefix='apple-pthread-static-native-'":"prefix='apple-pthread-static-native-bounds-'",
        "ROOT/'tools/rpi5/tests/pthread_static_host.c'":"ROOT/'tools/rpi5/tests/pthread_static_host_bounds.c'",
        "pins={str(Path(__file__).resolve()):sha(__file__)};commands=[];headers={}":
            "pins={str(Path(__file__).resolve()):sha(__file__),str(_builder):sha(_builder),str(_receipt):sha(_receipt)};commands=[];headers={}",
        "profile='pthread-static-adapter-host-only-v1'":"profile='pthread-static-adapter-host-only-bounds-v2',vector_cases=16",
    }
    for old,new in replacements.items():
        if source.count(old)!=1:raise ValueError('Exact host builder derivation changed')
        source=source.replace(old,new)
    scope={'__file__':str(Path(__file__).resolve()),'__name__':'private_native_bounds','_builder':SOURCE,'_receipt':RECEIPT}
    exec(compile(source,str(SOURCE),'exec'),scope)
    return scope['check']()

if __name__=='__main__':check()
