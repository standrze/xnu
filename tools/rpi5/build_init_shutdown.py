#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct project PID1 signal policy; offline host doubles and real A76 link."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from . import init_shutdown_profile as p
from . import prepare_pid1

ROOT=p.ROOT
BASE=ROOT/'build/rpi5/userland-shell-appendfix-20261011'
ROOT_PARENT=ROOT/'build/rpi5/display-restart-copy-sgf9_m1d'
ROOT_PARENT_SHA='e01f4e177cbb89a0f9b0663a711683de4b7ea92551c8a10a3885b2d1b38b7aa2'
OLD_USERLAND_SHA='9e373b2ff45145c0172c48ae83a9b2a23e8446ed2bd6afa89f9aa811b320b161'
HARNESS=ROOT/'tools/rpi5/tests/init_shutdown_host.c'
sha=p.sha

def build():
    from . import root_capacity_profile as rootfs
    if sha(BASE/'userland')!=OLD_USERLAND_SHA or sha(ROOT_PARENT/'manifest.json')!=ROOT_PARENT_SHA:
        raise ValueError('Exact accepted project PID1 and failed root parent required')
    files=rootfs.files_from((ROOT_PARENT/'ramdisk.bin').read_bytes())
    if files['/sbin/launchd'][0]!=(BASE/'userland').read_bytes():raise ValueError('Actual root PID1 binding')
    base=json.loads((BASE/'manifest.json').read_text())
    if base['source_inputs_sha256'][str(p.ORIGINAL)]!=p.ORIGINAL_SHA or sha(p.ORIGINAL)!=p.ORIGINAL_SHA:
        raise ValueError('Actual old PID1 source binding')
    out=Path(tempfile.mkdtemp(prefix='init-shutdown-',dir=ROOT/'build/rpi5'));print('OUTPUT='+str(out),flush=True)
    pins={};headers={};records={};commands=[]
    def pin(path):pins[str(Path(path).resolve())]=sha(path)
    for path in [*p.sources(),Path(__file__),ROOT/'tools/rpi5/prepare_pid1.py',ROOT/'tools/rpi5/root_capacity_profile.py',
            BASE/'manifest.json',BASE/'userland',ROOT_PARENT/'manifest.json',ROOT_PARENT/'ramdisk.bin']:
        pin(path)
    def run(args,label,allow=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        (out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
        commands.append(dict(label=label,command=args,cwd=str(ROOT),returncode=r.returncode))
        if r.returncode and not allow:raise ValueError(label+': '+r.stderr[-4000:])
        return r
    def deps(text):return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    def compile_(flags,source,label):
        pre=deps(run([*flags,'-M',source],label+'-scan').stdout)
        obj=out/(label+'.o');dep=out/(label+'.d')
        run([*flags,'-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        post=deps(dep.read_text())
        if pre!=post:raise ValueError('Actual header drift')
        headers.update(pre);records[label]=dict(before=pre,after=post);return obj
    original=next(c for c in base['commands'] if str(p.ORIGINAL) in c)
    flags=[x for x in original[:original.index(str(p.ORIGINAL))] if x!='-c']
    for name in ('clang','ld','nm','llvm-objdump'):
        pin(subprocess.check_output(['xcrun','--find',name],text=True).strip())
    pin('/usr/bin/xcrun')
    original_obj=compile_(flags,p.ORIGINAL,'original-init')
    if original_obj.read_bytes()!=(BASE/'init.o').read_bytes():raise ValueError('Original source does not reproduce packaged init.o')
    new=out/'init.c';new.write_text(p.derive(p.ORIGINAL.read_text()))
    target=compile_([*flags,'-mcpu=cortex-a76','-I',p.ORIGINAL.parent],new,'shutdown-init')
    link=list(base['commands'][-1]);old_link=list(link)
    if link.count(str(BASE/'init.o'))!=1:raise ValueError('Exact one init object owner')
    link=[str(target) if a==str(BASE/'init.o') else a for a in link]
    link[link.index('-o')+1]=str(out/'NOT_RUN_launchd');link+=['-map',str(out/'target.map')]
    for name in old_link:
        if name.endswith('.o'):pin(name)
    run(link,'target-link');image=out/'NOT_RUN_launchd';shape=prepare_pid1.inspect(image.read_bytes())
    if run(['xcrun','nm','-ju',image],'target-undefined').stdout.strip():raise ValueError('Unexpected target runtime dependency')
    run(['xcrun','llvm-objdump','-d','-r',target],'target-disassembly')
    sdk=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()
    native=[flags[0],'-isysroot',sdk,'-std=c11','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=undefined','-I',str(p.ORIGINAL.parent)]
    hobj=compile_(native,new,'host-init');harness=compile_(native,HARNESS,'host-harness')
    host=out/'init-host';run([*native,hobj,harness,'-o',host],'host-link')
    good=run([host],'host-run')
    if good.stderr or not re.fullmatch(r'INIT_SHUTDOWN PASS CASES=\d+ CALLBACK_TERM_POINTS=\d+ NO_PID1_EXIT NO_RESPAWN_AFTER_OBSERVATION CHILD_MASK_RESTORED HOST_DOUBLES_ONLY\n',good.stdout):raise ValueError('Native policy oracle')
    if run([host,'bad-expectation'],'host-negative',True).returncode!=37:raise ValueError('Native negative oracle')
    for name,h in {**pins,**headers}.items():
        if sha(name)!=h:raise ValueError('Source changed '+name)
    report=dict(profile='project-pid1-blocked-sigterm-stop-respawn-v1',old_pid1_sha256=OLD_USERLAND_SHA,
        original_source_sha256=p.ORIGINAL_SHA,target=str(image),target_sha256=sha(image),target_inspection=shape,
        original_init_object_reproduced=True,original_link=old_link,commands=commands,
        source_inputs_sha256=pins,headers_sha256=headers,dependency_records=records,
        native_stdout=good.stdout,raw_syscalls={'sigprocmask':48,'sigpending':52,'wait4':7},
        signal_trampoline_required=False,pthread_dependency_added=False,kernel_panic_modified=False,
        stops_after_first_observation=True,arrival_fork_atomicity_claimed=False,max_poll_sleep_seconds=1,
        child_inherited_mask_restored=True,target_executed=False,kernel_shutdown_qualified=False,
        generated_sha256={str(f):sha(f) for f in out.iterdir() if f.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),manifest_sha256=sha(out/'manifest.json'),target_sha256=sha(image),native=good.stdout),indent=2),flush=True)
    return out
if __name__=='__main__':build()
