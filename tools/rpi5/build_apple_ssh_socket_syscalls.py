#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Reuse Apple's original syscall generator/aliases, including cancellation.

Do not reuse old diagnostic-wide nocancel adapters for a threaded client.
This is static provider/link evidence only; neither sockets nor target run.
"""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_client_leaves as previous

ROOT,sha=previous.ROOT,previous.sha
BASE=ROOT/'build/rpi5/apple-ssh-client-leaves-8svd9i48'
BASE_SHA='ef270aebee087a072eed44dfd2c15183b8a3ce3de36e1c897b380699687f6b08'
JOIN=ROOT/'build/rpi5/apple-pthread-join-wait-ri8lyyub'
CALLS={'recvmsg':27,'sendmsg':28,'accept':30,'getpeername':31,'getsockname':32,
       'connect':98,'bind':104,'setsockopt':105,'listen':106,'getsockopt':118,
       'shutdown':134,'socketpair':135}
CANCEL={'accept','connect','recvmsg','sendmsg'}


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen leaves changed')
    base=json.loads((BASE/'manifest.json').read_text());pins={str(BASE/'manifest.json'):BASE_SHA}
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
        for n,h in base[key].items():
            if n in pins and pins[n]!=h:raise ValueError('Conflicting pin')
            pins[n]=h
    generator=ROOT/'libsyscall/xcodescripts/create-syscalls.pl'
    custom=ROOT/'libsyscall/custom';platforms=ROOT/'libsyscall/Platforms'
    master=ROOT/'bsd/kern/syscalls.master'
    for p in (Path(__file__).resolve(),generator,master,JOIN/'manifest.json',
              *custom.iterdir(),platforms/'syscall.map',platforms/'MacOSX/arm64/syscall.map'):
        if not p.is_file():continue
        if str(p) in pins and pins[str(p)]!=sha(p):raise ValueError('Original source drift')
        pins[str(p)]=sha(p)
    def verify():
        for n,h in pins.items():
            if sha(n)!=h:raise ValueError('Frozen source drift: '+n)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-ssh-socket-syscalls-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);generated=out/'generated';generated.mkdir()
    commands=[];headers={};objects={};records={}
    def run(args,label,allowed=False,env=None):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90,env=env)
        for k in ('stdout','stderr'):(out/(label+'.'+k)).write_text(getattr(r,k))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-4000:])
        return r
    env=dict(os.environ,ARCHS='arm64')
    run(['/usr/bin/perl',generator,master,custom,platforms,'MacOSX',generated],'original-generator',env=env)
    original=json.loads((JOIN/'manifest.json').read_text())
    template=next(c['command'] for c in original['commands'] if c['stdout'].endswith('/create-trap-preprocess.stdout'))
    flags=template[:template.index('-E')]
    # Original copied SYS.h next to each generated .s wins quoted lookup.
    def deps(text):
        return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    for name,number in CALLS.items():
        candidates=[generated/(prefix+name+'.s') for prefix in ('_','___')]
        candidates=[p for p in candidates if p.is_file()]
        if len(candidates)!=1:raise ValueError('Exact generated symbol source ambiguous')
        source=candidates[0];raw=source.read_text()
        handler='cerror' if name in CANCEL else 'cerror_nocancel'
        if not re.search(r'SYSCALL_NONAME\('+name+r', \d+, '+handler+r'\)',raw):
            raise ValueError('Original generated cancellation contract differs: '+name)
        if not re.search(r'^'+str(number)+r'\s+[^\n]*\b'+name+r'\(',master.read_text(),re.M):
            raise ValueError('Kernel syscall numbering changed')
        before=deps(run(flags+['-M',source],name+'-scan').stdout)
        dep=out/(name+'.d');asm=out/(name+'.s');obj=out/(name+'.o')
        preprocessed=run(flags+['-E','-P','-MD','-MF',dep,source],name+'-preprocess').stdout
        consumed=deps(dep.read_text())
        if before!=consumed:raise ValueError('Actual consumed assembly headers differ')
        headers.update(before);records[name]=dict(scanned_sha256=before,consumed_sha256=consumed)
        # Same semicolon/%% statement separators as original Apple XNU build.
        asm.write_text(preprocessed.replace('%%','\n').replace(';','\n'))
        run([flags[0],'-target','arm64-apple-darwin','-mcpu=cortex-a76','-x','assembler','-c',asm,'-o',obj],name+'-assemble')
        run(['xcrun','llvm-objdump','-d','-r',obj],name+'-disassembly')
        objects[name]=str(obj)
        undefined=run(['xcrun','nm','-ju',obj],name+'-undefined').stdout.splitlines()
        if undefined!=['_'+handler]:raise ValueError('Unexpected syscall imports: '+repr(undefined))
    archive=out/'libapple-ssh-socket-syscalls.a'
    run(['xcrun','ar','rcs',archive,*objects.values()],'archive')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    link.append(str(archive));r=run(link,'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',r.stderr,re.M)))
    duplicate=sorted(set(re.findall(r"duplicate symbol '([^']+)'",r.stderr)))
    closed={'_'+n for n in CALLS}
    if not r.returncode or duplicate or set(base['target_missing_symbols'])-set(missing)!=closed or set(missing)-set(base['target_missing_symbols']):
        raise ValueError('Unexpected full-link delta: '+r.stderr[-4000:])
    verify()
    for n,h in headers.items():
        if sha(n)!=h:raise ValueError('Consumed input drift')
    report=dict(profile='original-apple-full-ssh-generated-socket-syscalls-v1',
        source_inputs_sha256=pins,headers_sha256=headers,dependency_records=records,commands=commands,
        original_generator=str(generator),generator_environment={'ARCHS':'arm64'},
        generated_directory=str(generated),objects=objects,syscall_numbers=CALLS,
        cancelable_error_calls=sorted(CANCEL),nocancel_error_calls=sorted(set(CALLS)-CANCEL),
        original_arm64_public_aliases_preserved=True,original_syscall_emitter_unchanged=True,
        syscall_error_handlers_existing_genuine_runtime=True,target_archive=str(archive),
        previous_missing_count=len(base['target_missing_symbols']),closed_symbols=sorted(closed),
        target_missing_symbols=missing,target_duplicate_symbols=duplicate,target_link_complete=False,
        remaining_provider_groups=previous.categories(missing),
        original_openssh_config_unchanged=True,provider_stubs=False,
        host_socket_calls=False,target_executed=False,target_cancellation_exercised=False,
        kernel_sysent_rechecked=False,live_keys=False,network_access=False,entropy_qualified=False,
        accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),closed=len(closed),remaining=len(missing)),indent=2))
    return out,report


if __name__=='__main__':build()
