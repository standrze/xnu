#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserve the first startup diagnostic; add its real cancellation syscall."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'tools/rpi5/build_apple_pthread_static_smoke.py'
RECEIPT=ROOT/'build/rpi5/apple-pthread-static-smoke-kixn1y0m/manifest.json'
EXPECTED='1cbcc5f9cf847b9e4d1381c9f352ee9bea21108f09dc592d5c7bf1d4c0c510e9'

ADDITION='''
    # The original libkernel cancellation callback reaches real syscall 333.
    master=ROOT/'bsd/kern/syscalls.master'
    pins[str(master)]=sha(master)
    if not re.search(r'^333\\s+[^\\n]*\\b__pthread_canceled\\(',master.read_text(),re.M):
        raise ValueError('Actual cancellation syscall changed')
    template=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/create-trap-preprocess.stdout'))
    flags=list(template[:template.index('-E')])
    source=SOURCE/'pthread_cancel_runtime_call.S';pins[str(source)]=sha(source)
    before=deps(run(flags+['-M',source],'cancel-deps').stdout)
    dep=out/'cancel.d';assembly=out/'cancel.s';obj=out/'cancel.o'
    raw=run(flags+['-E','-P','-MD','-MF',dep,source],'cancel-preprocess').stdout
    assembly.write_text(raw.replace('%%','\\n').replace(';','\\n'))
    if deps(dep.read_text())!=before:raise ValueError('Cancellation emitter dependencies changed')
    headers.update(before)
    run([flags[0],'-target','arm64-apple-darwin','-mcpu=cortex-a76','-x','assembler','-c',assembly,'-o',obj],'cancel-assemble')
    link.append(str(obj))
'''


def build():
    if hashlib.sha256(RECEIPT.read_bytes()).hexdigest()!=EXPECTED:raise ValueError('Frozen startup receipt changed')
    r=json.loads(RECEIPT.read_text())
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=r['source_inputs_sha256'][str(SOURCE)]:raise ValueError('Startup builder drift')
    source=SOURCE.read_text()
    replacements={
        "prefix='apple-pthread-static-smoke-'":"prefix='apple-pthread-static-complete-'",
        "profile='genuine-apple-pthread-private-static-startup-smoke-v1'":"profile='genuine-apple-pthread-private-static-startup-complete-v1'",
        "for field in ('source_inputs_sha256','headers_sha256','generated_sha256'): pins.update(base[field])":
            "for field in ('source_inputs_sha256','headers_sha256','generated_sha256'): pins.update(base[field])\n    pins[str(_builder)]=sha(_builder)\n    pins[str(_receipt)]=sha(_receipt)",
        "    link += [str(startup),str(smoke)]":"    link += [str(startup),str(smoke)]\n"+ADDITION,
        "libkernel_callbacks_version=4,pthread_callbacks_version=2,":"libkernel_callbacks_version=4,pthread_callbacks_version=2,actual_pthread_canceled_syscall=333,",
    }
    for old,new in replacements.items():
        if source.count(old)!=1:raise ValueError('Exact startup derivation changed: '+old)
        source=source.replace(old,new)
    scope={'__file__':str(Path(__file__).resolve()),'__name__':'private_complete','_builder':SOURCE,'_receipt':RECEIPT}
    exec(compile(source,str(SOURCE),'exec'),scope)
    return scope['build']()


if __name__=='__main__':build()
