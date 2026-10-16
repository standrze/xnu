#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original Apple memmem/dirname and explicit ABI alias to genuine bzero body."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_nocancel_io as previous

ROOT,sha=previous.ROOT,previous.sha
BASE=ROOT/'build/rpi5/apple-ssh-nocancel-io-97n771iy'
BASE_SHA='9f754e50a8e2d09b8ba8420c58bbe7d043adb4a586bba59d34ff4ac44898518d'
LIBC=ROOT/'build/rpi5/apple-libc-main-candidate-20261013'
RAND=ROOT/'build/rpi5/kernel-entropy-rand-hfrb7y67'
RAND_SHA='f46bd17a8171c4272985875cfbb6a49d7305a49e26d2ee716facbe6aaac924f8'
HARNESS=ROOT/'tools/rpi5/tests/ssh_path_memory_host.c'
EXPECTED='APPLE_SSH_PATH_MEMORY PASS MEMMEM=12 DIRNAME=26 ORIGINAL_APPLE_POLICY\n'
ALIAS=['-alias','_rpi5_pthread_private_bzero','_bzero']


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA or sha(RAND/'manifest.json')!=RAND_SHA:raise ValueError('Frozen prerequisite changed')
    base=json.loads((BASE/'manifest.json').read_text());rand=json.loads((RAND/'manifest.json').read_text())
    pins={str(BASE/'manifest.json'):BASE_SHA,str(RAND/'manifest.json'):RAND_SHA}
    for r in (base,rand):
        for k in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for n,h in r.get(k,{}).items():
                if n in pins and pins[n]!=h:raise ValueError('Conflicting input pin')
                pins[n]=h
    sources=[LIBC/'string/FreeBSD/memmem.c',LIBC/'gen/FreeBSD/dirname.c']
    for p in [Path(__file__).resolve(),HARNESS,*sources]:pins[str(p)]=sha(p)
    for p in sources:
        if subprocess.check_output(['git','-C',LIBC,'show','HEAD:'+str(p.relative_to(LIBC))])!=p.read_bytes():raise ValueError('Original source differs')
    def verify():
        for n,h in pins.items():
            if sha(n)!=h:raise ValueError('Input changed: '+n)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-ssh-path-memory-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[];headers={};records={}
    def run(args,label,allowed=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        for k in ('stdout','stderr'):(out/(label+'.'+k)).write_text(getattr(r,k))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-6000:])
        return r
    def deps(text):return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    old=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/open-base-compile.stdout'))
    target=old[:old.index('-MD')]+['-include',str(LIBC/'fbsdcompat/_fbsd_compat_.h')]
    native=[x for x in target if x not in ('-ffreestanding','-mcpu=cortex-a76')]
    i=native.index('-target');del native[i:i+2]
    native+=['-O1','-g','-fsanitize=address,undefined']
    def compile(source,label,flags):
        before=deps(run(flags+['-M',source],label+'-scan').stdout);obj=out/(label+'.o');dep=out/(label+'.d')
        run(flags+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile');consumed=deps(dep.read_text())
        if before!=consumed:raise ValueError('Actual dependency mismatch')
        headers.update(before);records[label]=dict(scanned_sha256=before,consumed_sha256=consumed);return obj
    objects=[compile(s,s.stem,target) for s in sources]
    rename=['-Dmemmem=fixture_memmem','-Ddirname=fixture_dirname','-Ddirname_r=fixture_dirname_r','-Dmalloc=fixture_malloc']
    hostobjects=[compile(s,'host-'+s.stem,native+rename) for s in sources]
    caller=compile(HARNESS,'host-caller',native);host=out/'original-path-memory-host'
    run(native+[caller,*hostobjects,'-o',host],'host-link')
    result=run([host],'host-run');failed=run([host,'alloc-fail'],'host-allocation-failure')
    if result.stdout!=EXPECTED or result.stderr or failed.stdout!='APPLE_SSH_PATH_MEMORY ALLOC_FAILURE PASS\n' or failed.stderr:raise ValueError('Native path/memory oracle differs')
    archive=out/'libapple-ssh-path-memory.a';run(['xcrun','ar','rcs',archive,*objects],'archive')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map');link+=[str(archive),*ALIAS]
    result=run(link,'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    forced=list(next(c['command'] for c in rand['commands'] if c['stdout'].endswith('/target-link.stdout')))
    forced[forced.index('-o')+1]=str(out/'NOT_RUN_forced_path_memory');forced[forced.index('-map')+1]=str(out/'forced.map')
    forced+=[str(archive),*ALIAS,'-u','_bzero','-u','_memmem','-u','_dirname']
    run(forced,'forced-link');run(['xcrun','nm','-u',out/'NOT_RUN_forced_path_memory'],'forced-undefined')
    verify()
    for n,h in headers.items():
        if sha(n)!=h:raise ValueError('Header drift')
    report=dict(profile='apple-original-path-memory-existing-bzero-alias-v1',source_inputs_sha256=pins,headers_sha256=headers,
        dependency_records=records,commands=commands,target_archive=str(archive),original_sources=list(map(str,sources)),
        genuine_bzero_alias=ALIAS,dirname_original_static_storage=True,native_stdout=EXPECTED,native_asan_ubsan_pass=True,
        original_apple_empty_memmem_policy=True,target_missing_symbols=missing,target_duplicate_symbols=duplicates,
        closed_symbols=sorted(set(base['target_missing_symbols'])-set(missing)),newly_reachable_symbols=sorted(set(missing)-set(base['target_missing_symbols'])),
        target_link_complete=not result.returncode,forced_contract=str(out/'NOT_RUN_forced_path_memory'),forced_contract_is_not_full_ssh=True,
        target_executed=False,host_filesystem_executed=False,provider_stubs=False,accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),closed=report['closed_symbols'],remaining=len(missing),new=report['newly_reachable_symbols'],duplicates=duplicates),indent=2))
    return out,report


if __name__=='__main__':build()
