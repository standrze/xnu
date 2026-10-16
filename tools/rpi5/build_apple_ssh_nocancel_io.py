#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original variadic open$NOCANCEL and original mapped read$NOCANCEL for locale."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_file_wait_leaves as previous

ROOT,sha=previous.ROOT,previous.sha
BASE=ROOT/'build/rpi5/apple-ssh-file-wait-99k0lf5s'
BASE_SHA='1160079aeaeb39bfbecfa932dfe785a1a929b61c489213f905ee5c40870f2e61'
HARNESS=ROOT/'tools/rpi5/tests/ssh_nocancel_io_host.c'
EXPECTED='APPLE_SSH_NOCANCEL_IO PASS OPEN=8 ORIGINAL_VARIADIC_AND_COMPAT_POLICY IO_DOUBLES\n'
CALLS={'open_nocancel':398,'read_nocancel':396,'openat_nocancel':464,'close_nocancel':399,'fcntl_nocancel':406}


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen file/wait receipt changed')
    base=json.loads((BASE/'manifest.json').read_text());pins={str(BASE/'manifest.json'):BASE_SHA}
    for k in ('source_inputs_sha256','headers_sha256','generated_sha256'):pins.update(base[k])
    sources=[ROOT/'libsyscall/wrappers/open-base.c',ROOT/'libsyscall/wrappers/system-version-compat-support.c']
    for p in [Path(__file__).resolve(),HARNESS,*sources]:pins[str(p)]=sha(p)
    def verify():
        for n,h in pins.items():
            if sha(n)!=h:raise ValueError('Pinned input drift: '+n)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-ssh-nocancel-io-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[];headers={};records={};objects=[]
    def run(args,label,allowed=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        for k in ('stdout','stderr'):(out/(label+'.'+k)).write_text(getattr(r,k))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,
                             stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-6000:])
        return r
    def deps(text):
        return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    old=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/libc-hooks-compile.stdout'))
    target=old[:old.index('-MD')]
    native=[x for x in target if x not in ('-ffreestanding','-mcpu=cortex-a76')]
    i=native.index('-target');del native[i:i+2]
    native+=['-O1','-g','-fsanitize=address,undefined']
    def compile(source,label,flags):
        before=deps(run(flags+['-M',source],label+'-scan').stdout)
        obj=out/(label+'.o');dep=out/(label+'.d')
        run(flags+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        consumed=deps(dep.read_text())
        if before!=consumed:raise ValueError('Actual dependency mismatch')
        headers.update(before);records[label]=dict(scanned_sha256=before,consumed_sha256=consumed)
        return obj
    objects.extend(compile(s,p.stem,target) for s,p in [(s,s) for s in sources])
    join=json.loads((previous.previous.previous.JOIN/'manifest.json').read_text())
    a=next(c['command'] for c in join['commands'] if c['stdout'].endswith('/create-trap-preprocess.stdout'))
    assembly=a[:a.index('-E')]
    socket=json.loads((previous.previous.BASE/'manifest.json').read_text());generated=Path(socket['generated_directory'])
    for name in CALLS:
        source=generated/('___'+name+'.s');dep=out/('trap-'+name+'.d');asm=out/('trap-'+name+'.s');obj=out/('trap-'+name+'.o')
        raw=run(assembly+['-E','-P','-MD','-MF',dep,source],name+'-preprocess').stdout
        before=deps(run(assembly+['-M',source],name+'-scan').stdout);consumed=deps(dep.read_text())
        if before!=consumed:raise ValueError('Trap actual dependency mismatch')
        headers.update(before);records[name+'-trap']=dict(scanned_sha256=before,consumed_sha256=consumed)
        asm.write_text(raw.replace('%%','\n').replace(';','\n'))
        run([assembly[0],'-target','arm64-apple-darwin','-mcpu=cortex-a76','-x','assembler','-c',asm,'-o',obj],name+'-assemble')
        objects.append(obj)
    rename={'open$NOCANCEL':'fixture_open','openat$NOCANCEL':'fixture_openat',
            '__open_nocancel':'fixture_open_trap','__openat_nocancel':'fixture_openat_trap',
            '__close_nocancel':'fixture_close_trap','__fcntl_nocancel':'fixture_fcntl_trap',
            'system_version_compat_check_path_suffix':'fixture_check_suffix',
            'system_version_compat_open_shim':'fixture_open_shim',
            'system_version_compat_mode':'fixture_compat_mode'}
    hostflags=native+['-D'+a+'='+b for a,b in rename.items()]
    hostobjects=[compile(s,'host-'+s.stem,hostflags) for s in sources]
    caller=compile(HARNESS,'host-caller',native);host=out/'original-nocancel-io-host'
    run(native+[caller,*hostobjects,'-o',host],'host-link');result=run([host],'host-run')
    if result.stdout!=EXPECTED or result.stderr:raise ValueError('Original noncancel I/O policy oracle differs')
    archive=out/'libapple-ssh-nocancel-io.a';run(['xcrun','ar','rcs',archive,*objects],'archive')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    link+=[str(archive),'-u','_open$NOCANCEL','-u','_openat$NOCANCEL','-u','_read$NOCANCEL']
    result=run(link,'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    verify()
    for n,h in headers.items():
        if sha(n)!=h:raise ValueError('Header changed during build')
    report=dict(profile='apple-original-nocancel-locale-io-v1',source_inputs_sha256=pins,headers_sha256=headers,
        dependency_records=records,commands=commands,target_archive=str(archive),original_sources=list(map(str,sources)),
        original_generated_calls=CALLS,original_system_version_compat_enabled=True,source_or_config_changes=False,
        original_variadic_mode_and_hook_policy=True,native_asan_ubsan_pass=True,native_stdout=EXPECTED,
        native_io_are_doubles=True,forced_symbols=['_open$NOCANCEL','_openat$NOCANCEL','_read$NOCANCEL'],
        target_missing_symbols=missing,target_duplicate_symbols=duplicates,target_link_complete=not result.returncode,
        newly_reachable_symbols=sorted(set(missing)-set(base['target_missing_symbols'])),
        closed_symbols=sorted(set(base['target_missing_symbols'])-set(missing)),
        target_executed=False,host_io_executed=False,provider_stubs=False,accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),remaining=len(missing),new=report['newly_reachable_symbols'],duplicates=duplicates),indent=2))
    return out,report


if __name__=='__main__':build()
