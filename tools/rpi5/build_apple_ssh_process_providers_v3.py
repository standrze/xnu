#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserve v2; include the native caller's actually consumed headers as well."""
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SOURCE=Path(__file__).with_name('build_apple_ssh_process_providers_v2.py')
EXPECTED='c324bc0ca153999a87803d6885f6ac2f28240626a0d586c4794b55c458cbc7ca'


def implementation():
    raw=SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED:raise ValueError('Frozen v2 builder changed')
    text=raw.decode()
    old="    run(common+[HARNESS,*objects,'-o',host],'host-link')"
    new="""    obj=out/'host-caller.o';dep=out/'host-caller.d'
    before=deps(run(common+['-M',HARNESS],'host-caller-scan').stdout)
    run(common+['-MD','-MF',dep,'-c',HARNESS,'-o',obj],'host-caller-compile')
    consumed=deps(dep.read_text())
    if before!=consumed:raise ValueError('Caller actual header closure changed')
    headers.update(before);records['host-caller']=dict(scanned_sha256=before,consumed_sha256=consumed)
    run(common+[obj,*objects,'-o',host],'host-link')"""
    if text.count(old)!=1:raise ValueError('Exact native caller derivation changed')
    text=text.replace(old,new)
    old="profile='original-apple-ssh-peer-process-file-providers-v2'"
    if text.count(old)!=1:raise ValueError('Exact v2 profile derivation changed')
    text=text.replace(old,"profile='original-apple-ssh-peer-process-file-providers-v3'")
    scope=dict(__name__=__name__+'.v2',__file__=str(SOURCE))
    exec(compile(text,str(SOURCE),'exec'),scope)
    derived=scope['implementation']()
    derived['__file__']=str(Path(__file__).resolve())
    # v2 is already a checked prerequisite; the final receipt adds its exact bytes.
    def run():
        out,report=derived['build']()
        import json
        report['source_inputs_sha256'][str(SOURCE)]=EXPECTED
        if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!=EXPECTED:raise ValueError('V2 builder changed during build')
        (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
        return out,report
    return run


if __name__=='__main__':implementation()()
