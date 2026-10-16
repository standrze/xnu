#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original Apple peer/process/file providers in a private full-client link.

Cancellation uses the original waitpid variant and generated private wait4,
not the legacy public noncancel alias. No program, socket or target is run.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_socket_syscalls as previous

ROOT,sha=previous.ROOT,previous.sha
BASE=ROOT/'build/rpi5/apple-ssh-socket-syscalls-n4wc59z7'
BASE_SHA='f036194116d2048dc4102f3728191b7bd6f449cf95c5f58c78be9785662b677b'
LIBC=previous.previous.LIBC
UNITS=('gen/FreeBSD/getpeereid.c','gen/FreeBSD/getprogname.c',
       'gen/FreeBSD/waitpid.c','gen/FreeBSD/exec.c','gen/raise.c')
KERNEL_UNITS=('libsyscall/wrappers/rmdir.c','libsyscall/wrappers/remove-counter.c')
GENERATED={'mkdir':136,'rmdir':137,'__pthread_kill':328,'wait4':7}


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Socket closure changed')
    base=json.loads((BASE/'manifest.json').read_text());pins={str(BASE/'manifest.json'):BASE_SHA}
    for k in ('source_inputs_sha256','headers_sha256','generated_sha256'):
        for n,h in base[k].items():
            if n in pins and pins[n]!=h:raise ValueError('Conflicting original pin')
            pins[n]=h
    for p in (Path(__file__).resolve(),LIBC/'xcodescripts/libc.xcconfig',LIBC/'xcodescripts/variants.xcconfig',
              *[LIBC/n for n in UNITS],*[ROOT/n for n in KERNEL_UNITS]):
        if p.is_relative_to(LIBC):
            original=subprocess.check_output(['git','-C',str(LIBC),'show','HEAD:'+str(p.relative_to(LIBC))])
            if original!=p.read_bytes():raise ValueError('Original Apple source differs')
        pins[str(p)]=sha(p)
    def verify():
        for n,h in pins.items():
            if sha(n)!=h:raise ValueError('Pinned input changed: '+n)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-ssh-process-providers-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[];headers={};records={};objects=[];failures=[]
    def run(args,label,allowed=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        for k in ('stdout','stderr'):(out/(label+'.'+k)).write_text(getattr(r,k))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-5000:])
        return r
    def deps(text):
        return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    leaves=json.loads((previous.BASE/'manifest.json').read_text())
    old=next(c['command'] for c in leaves['commands'] if c['stdout'].endswith('/target-getopt-compile.stdout'))
    flags=old[:old.index('-MD')]
    def compile(source,label,extra=()):
        before=deps(run(flags+list(extra)+['-M',source],label+'-scan').stdout)
        obj,dep=out/(label+'.o'),out/(label+'.d')
        result=run(flags+list(extra)+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile',True)
        consumed=deps(dep.read_text()) if dep.is_file() else {}
        if not result.returncode and before!=consumed:raise ValueError('Actual consumed dependency differs')
        headers.update(before|consumed);records[label]=dict(scanned_sha256=before,consumed_sha256=consumed)
        if result.returncode:failures.append(dict(source=str(source),diagnostic=result.stderr))
        else:objects.append(obj)
    for n in UNITS:
        extra=['-include',str(LIBC/'fbsdcompat/_fbsd_compat_.h')] if '/FreeBSD/' in n else []
        if n.endswith('/waitpid.c'):extra+=['-DVARIANT_CANCELABLE','-D__DARWIN_UNIX03=1']
        compile(LIBC/n,Path(n).stem,extra)
    for n in KERNEL_UNITS:compile(ROOT/n,Path(n).stem)
    join=json.loads((previous.JOIN/'manifest.json').read_text())
    old=next(c['command'] for c in join['commands'] if c['stdout'].endswith('/create-trap-preprocess.stdout'))
    assembly=old[:old.index('-E')]
    generated=Path(base['generated_directory'])
    for n,number in GENERATED.items():
        candidates=[generated/(prefix+n+'.s') for prefix in ('_','___')]
        candidates=[p for p in candidates if p.is_file()]
        if len(candidates)!=1:raise ValueError('Ambiguous original generated call')
        source=candidates[0];obj=out/(n+'.o');dep=out/(n+'.d');asm=out/(n+'.s')
        raw=run(assembly+['-E','-P','-MD','-MF',dep,source],n+'-preprocess').stdout
        before=deps(run(assembly+['-M',source],n+'-scan').stdout);consumed=deps(dep.read_text())
        if before!=consumed:raise ValueError('Generated actual headers differ')
        headers.update(before);records[n+'-trap']=dict(scanned_sha256=before,consumed_sha256=consumed)
        asm.write_text(raw.replace('%%','\n').replace(';','\n'))
        run([assembly[0],'-target','arm64-apple-darwin','-mcpu=cortex-a76','-x','assembler','-c',asm,'-o',obj],n+'-assemble')
        objects.append(obj)
    archive=out/'libapple-ssh-process-providers.a'
    run(['xcrun','ar','rcs',archive,*objects],'archive')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    link.append(str(archive));r=run(link,'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',r.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",r.stderr)))
    verify()
    for n,h in headers.items():
        if sha(n)!=h:raise ValueError('Header drift')
    report=dict(profile='original-apple-ssh-peer-process-file-providers-v1',
        source_inputs_sha256=pins,headers_sha256=headers,dependency_records=records,commands=commands,
        original_libc_units=UNITS,original_kernel_units=KERNEL_UNITS,generated_calls=GENERATED,
        compile_failures=failures,all_units_compiled=not failures,target_archive=str(archive),
        original_freebsd_compatibility_header=True,original_cancellable_waitpid_variant=True,
        target_missing_symbols=missing,target_duplicate_symbols=duplicates,target_link_complete=not r.returncode,
        closed_symbols=sorted(set(base['target_missing_symbols'])-set(missing)),
        newly_reachable_symbols=sorted(set(missing)-set(base['target_missing_symbols'])),
        remaining_provider_groups=previous.previous.categories(missing),
        target_executed=False,host_processes_or_sockets_executed=False,native_semantics_tested=False,
        original_openssh_config_unchanged=True,provider_stubs=False,accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),compile_failures=len(failures),closed=report['closed_symbols'],
        new=report['newly_reachable_symbols'],remaining=len(missing),duplicates=duplicates),indent=2))
    return out,report


if __name__=='__main__':build()
