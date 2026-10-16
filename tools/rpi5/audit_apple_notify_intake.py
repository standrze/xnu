#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bounded original Libnotify build intake, never a fake notification provider.

Retains the exact compiler's first missing-private-header result and the real
service path. This is not a complete dependency closure or a client link pass.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'build/rpi5/apple-libnotify-main-candidate-20261014'
COMMIT='715d461778f6b93c821d99390a0078bd6f6d8c04'
FILES=('notify_client.c','libnotify.c','libnotify.h','notify_internal.h','notify_ipc.defs',
       'notify_old_ipc.defs','notify.h','notify_private.h','notify_probes.d',
       'xcodeconfig/base.xcconfig','xcodeconfig/libnotify.xcconfig','APPLE_LICENSE')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    if subprocess.check_output(['git','-C',SOURCE,'rev-parse','HEAD'],text=True).strip()!=COMMIT:
        raise ValueError('Exact original Libnotify commit required')
    pins={str(Path(__file__).resolve()):sha(__file__)}
    for name in FILES:
        p=SOURCE/name
        if p.read_bytes()!=subprocess.check_output(['git','-C',SOURCE,'show',COMMIT+':'+name]):
            raise ValueError('Original source drift')
        pins[str(p)]=sha(p)
    out=Path(tempfile.mkdtemp(prefix='apple-notify-intake-',dir=ROOT/'build/rpi5'))
    compiler=Path(subprocess.check_output(['xcrun','-f','clang'],text=True).strip()).resolve()
    sdk=Path(subprocess.check_output(['xcrun','--show-sdk-path'],text=True).strip()).resolve()
    commands=[];observed_headers={}
    flags=[str(compiler),'-target','arm64-apple-darwin','-mcpu=cortex-a76','-ffreestanding','-fblocks',
        '-O2','-fno-exceptions','-D__DARWIN_NON_CANCELABLE=1','-isysroot',str(sdk),
        '-I'+str(sdk/'System/Library/Frameworks/System.framework/PrivateHeaders'),'-I'+str(SOURCE),
        '-I'+str(ROOT/'libkern'),'-I'+str(ROOT/'build/rpi5/apple-libplatform-main-candidate-20261013/private')]
    for name in ('notify_client.c','libnotify.c'):
        command=[*flags,'-H','-c',str(SOURCE/name),'-o',str(out/(Path(name).stem+'.o'))]
        r=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=30)
        for header in re.findall(r'^\.+ (/[^\n]+)$',r.stderr,re.M):
            p=Path(header).resolve()
            if p.is_file():observed_headers[str(p)]=sha(p)
        for stream in ('stdout','stderr'):(out/(name+'.'+stream)).write_text(getattr(r,stream))
        commands.append(dict(command=command,cwd=str(ROOT),returncode=r.returncode,
            stdout=str(out/(name+'.stdout')),stderr=str(out/(name+'.stderr'))))
    for n,h in pins.items():
        if sha(n)!=h:raise ValueError('Input drift')
    manifest=dict(profile='original-libnotify-intake-blockers-no-provider-v1',commit=COMMIT,
        upstream='https://github.com/apple-oss-distributions/Libnotify',source_inputs_sha256=pins,
        compiler=str(compiler),compiler_sha256=sha(compiler),sdk=str(sdk),commands=commands,
        observed_partial_headers_sha256=observed_headers,
        whole_original_units_attempted=['notify_client.c','libnotify.c'],
        complete_header_closure=False,target_provider_created=False,full_client_link_performed=False,
        notify_tz_disabled=False,notification_loopback_forced=False,server_failure_stub=False,
        target_executed=False,hardware_executed=False,
        actual_source_requirements=['bootstrap_look_up2 and real notification service port',
            'original notify MIG clients and server protocol version3',
            'shared-memory registration and regeneration state',
            'dispatch queues/sources and original Block callbacks',
            'real XPC entitlement objects and original dyld immutable-memory query',
            'notifyd file monitoring for monitor_file; self/loopback tokens are rejected'],
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),manifest_sha256=sha(out/'manifest.json'),
        errors=[Path(c['stderr']).read_text().split('fatal error:',1)[-1].splitlines()[0] for c in commands]),indent=2))


if __name__=='__main__':build()
