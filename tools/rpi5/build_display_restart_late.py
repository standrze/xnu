#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct root33: replace only project /sbin/launchd; retain fixed copy loader."""
import json
from pathlib import Path
import subprocess
import tempfile
import uuid
from . import build_display_restart_copy as prior, check_display_restart_copy as oldcheck
from . import init_shutdown_late_profile as init, root_capacity_profile as rootfs, payload_container

ROOT=prior.ROOT;sha=prior.sha;document=prior.document
BASE=ROOT/'build/rpi5/display-restart-copy-sgf9_m1d'
BASE_SHA='e01f4e177cbb89a0f9b0663a711683de4b7ea92551c8a10a3885b2d1b38b7aa2'
INIT=ROOT/'build/rpi5/init-shutdown-late-benslain'
INIT_SHA='8273a4c1e20d9f564a2ded2c23737e2ecc5afad1cfc99a65a3eeebdfcfe09a42'
PROFILE='rpi5-display-restart-pid1-late-readiness-v1'
MARKER='RPI5XNU:DISPLAYRESTART_LATE:ENTRY TAG='
CONTRACT={**prior.CONTRACT,'kernel_root_payload_unchanged':False,'kernel_unchanged':True,'root_only_replaced':'/sbin/launchd'}

def sources():return [Path(__file__).resolve(),ROOT/'tools/rpi5/check_display_restart_late.py',ROOT/'tools/rpi5/tests/test_display_restart_late.py',*init.sources()]
def generated_main():
    raw=(BASE/'probe_main.c').read_text()
    if raw.count(prior.MARKER)!=1:raise ValueError('Exact copy-phase parent tag')
    return raw.replace(prior.MARKER,MARKER,1)
def payload_source(out):return '.section .payload,"a"\n.balign 64\n.incbin "'+str(out/'payload.bin')+'"\n'
def command_plan(out,tag):
    old={r['label']:r for r in document(BASE/'manifest.json')['commands']}
    flags=prior.prior.original.display.compiler_flags(old['loader-main-compile']['command'],BASE/'probe_main.c')
    flags=[('-DRPI5_DISPLAY_XNU_TAG="'+tag+'"') if a.startswith('-DRPI5_DISPLAY_XNU_TAG=') else a for a in flags]
    old_payload=str(prior.BASE/'loader-payload.o')
    changes={str(BASE/'loader-main.o'):str(out/'loader-main.o'),old_payload:str(out/'loader-payload.o'),str(BASE/'display_restart.elf'):str(out/'display_restart.elf')}
    if any(old['loader-link']['command'].count(n)!=1 for n in changes):raise ValueError('Exact main/payload object owners')
    plan=[]
    for label,source in [('loader-main',out/'probe_main.c'),('loader-payload',out/'payload.S')]:
        plan += [(label+'-scan',[*flags,'-M','-MF',out/(label+'.scan.d'),source]),
            (label+'-compile',[*flags,'-c','-MD','-MF',out/(label+'.actual.d'),source,'-o',out/(label+'.o')])]
    plan += [('loader-link',[changes.get(a,a) for a in old['loader-link']['command']]),
        ('loader-objcopy',[ROOT/'tools/rpi5/tfa-objcopy','-O','binary',out/'display_restart.elf',out/'probe.bin']),
        ('loader-undefined',['xcrun','llvm-nm','--undefined-only',out/'display_restart.elf'])]
    return [dict(label=label,command=list(map(str,args)),cwd=str(ROOT)) for label,args in plan]

def build():
    pins={}
    def pin(path,expected=None):
        n=str(Path(path).absolute());h=sha(n)
        if expected is not None and h!=expected:raise ValueError('Exact input required '+n)
        if n in pins and pins[n]!=h:raise ValueError('Conflicting source '+n)
        pins[n]=h
    for directory,digest in [(BASE,BASE_SHA),(INIT,INIT_SHA)]:
        pin(directory/'manifest.json',digest)
        for key in ('inputs_sha256','source_inputs_sha256','headers_sha256','generated_sha256'):
            for name,value in document(directory/'manifest.json').get(key,{}).items():pin(name,value)
    for path in sources():pin(path)
    out=Path(tempfile.mkdtemp(prefix='display-restart-late-',dir=ROOT/'build/rpi5'));tag=uuid.uuid4().hex
    print('OUTPUT='+str(out),flush=True)
    kernel=(BASE/'kernel.display-restart').read_bytes();(out/'kernel.display-restart').write_bytes(kernel)
    files=rootfs.files_from((BASE/'ramdisk.bin').read_bytes());old_pid1=files['/sbin/launchd']
    files['/sbin/launchd']=((INIT/'NOT_RUN_launchd').read_bytes(),old_pid1[1])
    root,catalog=rootfs.build(files)
    if len(catalog['entries'])!=33 or rootfs.inspect(root)!=catalog:raise ValueError('Exact root33 build')
    (out/'ramdisk.bin').write_bytes(root);(out/'root-catalog.json').write_text(json.dumps(catalog,indent=2,sort_keys=True)+'\n')
    (out/'payload.bin').write_bytes(payload_container.encode(kernel,root))
    (out/'probe_main.c').write_text(generated_main());(out/'payload.S').write_text(payload_source(out))
    headers={};scans={};commands=[]
    print('PHASE=root33-only-launchd-two-A76-loader-objects',flush=True)
    for row in command_plan(out,tag):
        r=subprocess.run(row['command'],cwd=row['cwd'],capture_output=True,text=True,timeout=120)
        log=out/(row['label']+'.log');log.write_text(r.stdout+r.stderr)
        commands.append(dict(row,returncode=r.returncode,log=str(log),log_sha256=sha(log)))
        if r.returncode or 'warning:' in r.stderr:raise ValueError(row['label']+': '+r.stderr[-5000:])
        if row['label'].endswith('-scan'):
            label=row['label'][:-5];scans[label]=sorted(prior.prior.original.display.dependencies(out/(label+'.scan.d'),ROOT))
            for name in scans[label]:pin(name);headers[name]=pins[name]
        if row['label'].endswith('-compile'):
            label=row['label'][:-8]
            if sorted(prior.prior.original.display.dependencies(out/(label+'.actual.d'),ROOT))!=scans[label]:raise ValueError('Actual header mismatch')
        if row['label']=='loader-undefined' and r.stdout.strip():raise ValueError('Loader imports')
    for n,h in {**pins,**headers}.items():
        if sha(n)!=h:raise ValueError('Input drift '+n)
    raw=(out/'probe.bin').read_bytes();payload=(out/'payload.bin').read_bytes();offset=raw.find(payload)
    if offset<0 or offset%64 or raw.find(payload,offset+1)>=0:raise ValueError('Actual unique payload')
    m=dict(profile=PROFILE,parent=str(BASE),parent_manifest_sha256=BASE_SHA,init_package=str(INIT),init_manifest_sha256=INIT_SHA,
        tag=tag,image=str(out/'probe.bin'),image_sha256=sha(out/'probe.bin'),image_bytes=len(raw),payload_offset=offset,
        root_sha256=sha(out/'ramdisk.bin'),root_bytes=len(root),root_nodes=33,kernel_sha256=sha(out/'kernel.display-restart'),
        launchd_sha256=sha(INIT/'NOT_RUN_launchd'),root_only_replaced='/sbin/launchd',
        init_shutdown_ready_marker=init.READY,init_shutdown_ready_max_reports=3,
        init_readiness_min_successful_sleep_seconds=1,init_readiness_full_mask_revalidated=True,init_uart_line_atomicity_claimed=False,copy_phase_contract=CONTRACT,
        commands=commands,inputs_sha256=pins,headers_sha256=headers,compiler_scans=scans,
        generated_sha256={str(f):sha(f) for f in out.iterdir() if f.is_file()})
    (out/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),manifest_sha256=sha(out/'manifest.json'),image_sha256=m['image_sha256'],root_bytes=len(root)),indent=2),flush=True)
    return out
if __name__=='__main__':build()

