#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct loader-only copy-phase repair; frozen diagnostic kernel/root unchanged."""
import json
from pathlib import Path
import subprocess
import tempfile
import uuid
from . import build_display_restart_diagnostic as prior
from . import check_display_restart_diagnostic as previous_check
from . import loader_copy_phase_profile as phase

ROOT=prior.ROOT
BASE=ROOT/'build/rpi5/display-restart-diagnostic-gb38kpad'
BASE_SHA='fb09729396cf9bbec7ced1b50b7846c8fa23e4b9b03c51e2dd0304725257f5ae'
PROFILE='rpi5-display-restart-two-copy-phases-v1'
MARKER='RPI5XNU:DISPLAYRESTART_COPY:ENTRY TAG='
sha=prior.sha
document=prior.document
COPIES=('kernel.display-restart','ramdisk.bin','root-catalog.json','payload.bin')
CONTRACT=dict(loader_outer_seconds=60,hash_renewal_max=128,copy_renewal_max=2,
    countdown_seconds=15,copy_phases=['verified_plan_before_materialize','materialized_equal_dsb_before_readback'],
    post_readback_renewal=False,transfer_admission_before_outer_deadline=True,
    transfer_admission_before_nominal_copy_countdown=True,hardware_clock_rate_bound_proven=False,
    kernel_root_payload_unchanged=True,terminal_seconds=180,target_executed=False)

def sources():
    return [Path(__file__).resolve(),ROOT/'tools/rpi5/check_display_restart_copy.py',
        ROOT/'tools/rpi5/tests/test_display_restart_copy.py',*phase.sources()]

def generated_main():
    raw=(BASE/'probe_main.c').read_text()
    if raw.count(prior.MARKER)!=1:raise ValueError('Exact frozen diagnostic tag owner')
    return phase.transform(raw).replace(prior.MARKER,MARKER,1)

def command_plan(out,tag):
    old={r['label']:r for r in document(BASE/'manifest.json')['commands']}
    flags=prior.original.display.compiler_flags(old['loader-main-compile']['command'],BASE/'probe_main.c')
    flags=[('-DRPI5_DISPLAY_XNU_TAG="'+tag+'"') if a.startswith('-DRPI5_DISPLAY_XNU_TAG=') else a for a in flags]
    changes={str(BASE/'loader-main.o'):str(out/'loader-main.o'),str(BASE/'display_restart.elf'):str(out/'display_restart.elf')}
    return [dict(label=label,command=list(map(str,args)),cwd=str(ROOT)) for label,args in (
        ('loader-main-scan',[*flags,'-M','-MF',out/'loader-main.scan.d',out/'probe_main.c']),
        ('loader-main-compile',[*flags,'-c','-MD','-MF',out/'loader-main.actual.d',out/'probe_main.c','-o',out/'loader-main.o']),
        ('loader-link',[changes.get(a,a) for a in old['loader-link']['command']]),
        ('loader-objcopy',[ROOT/'tools/rpi5/tfa-objcopy','-O','binary',out/'display_restart.elf',out/'probe.bin']),
        ('loader-undefined',['xcrun','llvm-nm','--undefined-only',out/'display_restart.elf']))]

def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen failed-candidate parent required')
    base=document(BASE/'manifest.json');pins={str(BASE/'manifest.json'):BASE_SHA}
    def pin(path,expected=None):
        path=str(Path(path).absolute());value=sha(path)
        if expected is not None and expected!=value:raise ValueError('Changed input '+path)
        if path in pins and pins[path]!=value:raise ValueError('Conflicting input '+path)
        pins[path]=value
    for key in ('inputs_sha256','headers_sha256','generated_sha256'):
        for name,value in base[key].items():pin(name,value)
    for path in sources():pin(path)
    out=Path(tempfile.mkdtemp(prefix='display-restart-copy-',dir=ROOT/'build/rpi5'));tag=uuid.uuid4().hex
    print('OUTPUT='+str(out),flush=True)
    (out/'probe_main.c').write_text(generated_main())
    for name in COPIES:(out/name).write_bytes((BASE/name).read_bytes())
    headers={};commands=[];scanned=[]
    print('PHASE=one-A76-loader-TU-and-original-object-link',flush=True)
    for row in command_plan(out,tag):
        r=subprocess.run(row['command'],cwd=row['cwd'],capture_output=True,text=True,timeout=120)
        log=out/(row['label']+'.log');log.write_text(r.stdout+r.stderr)
        commands.append(dict(row,returncode=r.returncode,log=str(log),log_sha256=sha(log)))
        if r.returncode or 'warning:' in r.stderr:raise ValueError(row['label']+': '+r.stderr[-5000:])
        if row['label']=='loader-main-scan':
            scanned=sorted(prior.original.display.dependencies(out/'loader-main.scan.d',ROOT))
            for name in scanned:pin(name);headers[name]=pins[name]
        if row['label']=='loader-main-compile':
            if sorted(prior.original.display.dependencies(out/'loader-main.actual.d',ROOT))!=scanned:raise ValueError('Actual compiler closure differs')
            for name,value in headers.items():pin(name,value)
        if row['label']=='loader-undefined' and r.stdout.strip():raise ValueError('Linked loader imports')
    for name,value in pins.items():
        if sha(name)!=value:raise ValueError('Source changed while composing '+name)
    raw=(out/'probe.bin').read_bytes();payload=(out/'payload.bin').read_bytes();offset=raw.find(payload)
    if offset<0 or offset%64 or raw.find(payload,offset+1)>=0:raise ValueError('Unique actual payload')
    m=dict(profile=PROFILE,parent=str(BASE),parent_manifest_sha256=BASE_SHA,tag=tag,
        image=str(out/'probe.bin'),image_sha256=sha(out/'probe.bin'),image_bytes=len(raw),
        payload_offset=offset,kernel_sha256=base['kernel_sha256'],root_sha256=base['root_sha256'],
        root_bytes=base['root_bytes'],root_nodes=33,copy_phase_contract=CONTRACT,
        commands=commands,inputs_sha256=pins,headers_sha256=headers,compiler_scans={'loader-main':scanned},
        generated_sha256={str(path):sha(path) for path in out.iterdir() if path.is_file()})
    (out/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(directory=str(out),manifest_sha256=sha(out/'manifest.json'),image_sha256=m['image_sha256']),indent=2),flush=True)
    return out

if __name__=='__main__':build()
