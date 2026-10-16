#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original cancellable variant and actual thread creation kernel emitter."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'build/rpi5/apple-pthread-dyld-threads-zmg7gxfj'
BASE_SHA='2240cedc9ad943b913193f703420fb40443e10af830950d4f71be91d6410107a'
NORMAL=ROOT/'build/rpi5/apple-pthread-bcm2712-qualified-x9kp1ral'
MACH=ROOT/'build/rpi5/apple-pthread-messaging-headers-mubxo_kh'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen thread closure drift')
    base=json.loads((BASE/'manifest.json').read_text());normal=json.loads((NORMAL/'manifest.json').read_text())
    mach=json.loads((MACH/'manifest.json').read_text())
    pins={str(BASE/'manifest.json'):BASE_SHA,str(Path(__file__).resolve()):sha(__file__)}
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):pins.update(base[key])
    master=ROOT/'bsd/kern/syscalls.master';pins[str(master)]=sha(master)
    if not re.search(r'^360\s+[^\n]*\bbsdthread_create\(',master.read_text(),re.M):raise ValueError('Actual creation syscall changed')
    out=Path(tempfile.mkdtemp(prefix='apple-pthread-create-join-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True)
    commands,headers=[],{}
    def run(args,label,allowed=False):
        args=list(map(str,args));p=subprocess.run(args,cwd=out,capture_output=True,text=True,timeout=90)
        (out/(label+'.stdout')).write_text(p.stdout);(out/(label+'.stderr')).write_text(p.stderr)
        commands.append(dict(command=args,returncode=p.returncode,stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if p.returncode and not allowed:raise ValueError(label+': '+p.stderr[-6000:])
        return p
    def deps(raw):return {str(Path(p).resolve()):sha(Path(p).resolve()) for p in shlex.split(raw.replace('\\\n',' ').partition(':')[2])}
    def compile(flags,source,label,assembly=False):
        pins[str(source)]=sha(source);before=deps(run(flags+['-M',source],label+'-deps').stdout)
        obj,dep=out/(label+'.o'),out/(label+'.d')
        if assembly:
            raw=run(flags+['-E','-P','-MD','-MF',dep,source],label+'-preprocess').stdout
            generated=out/(label+'.s');generated.write_text(raw.replace('%%','\n').replace(';','\n'))
            run([flags[0],'-target','arm64-apple-darwin','-mcpu=cortex-a76','-x','assembler','-c',generated,'-o',obj],label+'-assemble')
        else:run(flags+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        if deps(dep.read_text())!=before:raise ValueError('Actual consumed thread dependency mismatch')
        headers.update(before);return obj
    template=next(c['command'] for c in normal['commands'] if c['stdout'].endswith('/pthread-pthread-compile.stdout'))
    flags=list(template[:template.index('-H')])
    source=ROOT/'build/rpi5/apple-libpthread-main-candidate-20261013/src/variants/pthread_cancelable_cancel.c'
    # This exact original source sets BUILDING_VARIANT, VARIANT_CANCELABLE and
    # __DARWIN_NON_CANCELABLE=0 before including pthread_cancelable.c.
    variant=compile(flags,source,'original-cancelable')
    template=next(c['command'] for c in mach['commands'] if c['stdout'].endswith('/pthread-exit-traps-preprocess.stdout'))
    assembly=list(template[:template.index('-E')])
    trap=compile(assembly,ROOT/'tools/rpi5/user/pthread_create_runtime_calls.S','create-trap',True)
    archive=out/'libapple-pthread-create-join.a';run(['xcrun','ar','rcs',archive,variant,trap],'archive')
    symbols=run(['xcrun','nm','-g',variant],'actual-cancelable-symbols').stdout
    if not re.search(r'^[0-9a-f]+ T _pthread_join$',symbols,re.M):raise ValueError('Actual public join definition missing')
    if ' U _pthread_testcancel' not in symbols:raise ValueError('Cancellation precheck was lost')
    link=next(list(c['command']) for c in base['commands'] if c['stdout'].endswith('/init-live-link.stdout'))
    link[link.index('-o')+1]=str(out/'NOT_RUN_init-live');link[link.index('-map')+1]=str(out/'init-live.map')
    link+=[str(archive)]
    attempt=run(link,'init-live-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',attempt.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",attempt.stderr)))
    if not attempt.returncode:
        run(['xcrun','nm','-u',out/'NOT_RUN_init-live'],'target-undefined')
        run(['xcrun','llvm-objdump','--disassemble-symbols=_pthread_join,___bsdthread_create',out/'NOT_RUN_init-live'],'actual-create-join-disassembly')
    for path,digest in {**pins,**headers}.items():
        if sha(path)!=digest:raise ValueError('Source drift: '+path)
    report=dict(profile='original-apple-cancellable-join-create-trap-v1',source_inputs_sha256=pins,headers_sha256=headers,
        commands=commands,target_archive=str(archive),target_archive_sha256=sha(archive),
        target_link_complete=not attempt.returncode,target_missing_symbols=missing,target_duplicate_symbols=duplicates,
        actual_public_join_cancellation_preserved=True,actual_bsdthread_create_syscall=360,
        original_create_join_forced_live=True,original_implementation_bodies_unchanged=True,
        target_startup_created=False,target_main_thread_initialized=False,constructors_order_wired=False,
        accepted_runtime_modified=False,pi_executed=False,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),linked=not attempt.returncode,missing=missing,duplicates=duplicates),indent=2))
    return out,report


if __name__=='__main__':build()
