#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Current Apple strchrnul/hooks and original cancellable pselect, private link.

One recorded hook-output byte-pointer correction; no disabled callbacks, feature
configuration changes, target execution, or real host socket/process activity.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_process_providers as previous

ROOT,sha=previous.ROOT,previous.sha
BASE=ROOT/'build/rpi5/apple-ssh-process-providers-0mgunedd'
BASE_SHA='3f8b0da4dee23b2c325f8356c64942cb53ae728aea289ceee41713c57ea88349'
LIBC=previous.LIBC
HARNESS=ROOT/'tools/rpi5/tests/ssh_file_wait_leaves_host.c'
EXPECTED='APPLE_SSH_FILE_WAIT PASS STRCHRNUL=4160 HOOK_TAILS=4 PSELECT=7 SYSCALL_DOUBLES\n'
HOOK_OLD='bzero(old_hooks + sizeof(libc_hooks), size - sizeof(libc_hooks));'
HOOK_NEW='bzero((char *)old_hooks + sizeof(libc_hooks), size - sizeof(libc_hooks));'


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen process receipt changed')
    base=json.loads((BASE/'manifest.json').read_text());pins={str(BASE/'manifest.json'):BASE_SHA}
    for k in ('source_inputs_sha256','headers_sha256','generated_sha256'):pins.update(base[k])
    sources=[LIBC/'string/FreeBSD/strchrnul.c',LIBC/'darwin/libc_hooks.c',
             ROOT/'libsyscall/wrappers/cancelable/select-cancel.c']
    for p in [Path(__file__).resolve(),HARNESS,*sources]:pins[str(p)]=sha(p)
    for p in sources[:2]:
        if subprocess.check_output(['git','-C',LIBC,'show','HEAD:'+str(p.relative_to(LIBC))])!=p.read_bytes():
            raise ValueError('Current Apple source differs')
    def verify():
        for n,h in pins.items():
            if sha(n)!=h:raise ValueError('Pinned input drift: '+n)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-ssh-file-wait-',dir=ROOT/'build/rpi5'))
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
    old=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/raise-compile.stdout'))
    target=old[:old.index('-MD')]+['-I',str(LIBC/'darwin'),'-include','strings.h']
    native=[x for x in target if x not in ('-ffreestanding','-mcpu=cortex-a76')]
    i=native.index('-target');del native[i:i+2]
    native+=['-O1','-g','-fsanitize=address,undefined']
    fixed=out/'libc_hooks_checked.c';original=sources[1].read_text()
    if original.count(HOOK_OLD)!=1:raise ValueError('Original hook-tail expression changed')
    fixed.write_text(original.replace(HOOK_OLD,HOOK_NEW))
    def compile(source,label,flags):
        before=deps(run(flags+['-M',source],label+'-scan').stdout)
        obj=out/(label+'.o');dep=out/(label+'.d')
        run(flags+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        consumed=deps(dep.read_text())
        if before!=consumed:raise ValueError('Actually consumed dependency mismatch')
        headers.update(before);records[label]=dict(scanned_sha256=before,consumed_sha256=consumed)
        return obj
    freebsd=['-include',str(LIBC/'fbsdcompat/_fbsd_compat_.h')]
    objects.append(compile(sources[0],'strchrnul',target+freebsd))
    objects.append(compile(fixed,'libc-hooks',target))
    # Existing public select belongs to the preserved runtime. Only namespace the
    # complete original select implementation used by this pselect's fallback.
    objects.append(compile(sources[2],'pselect',target+['-Dselect=rpi5_pselect_fallback_select']))
    join=json.loads((previous.previous.JOIN/'manifest.json').read_text())
    a=next(c['command'] for c in join['commands'] if c['stdout'].endswith('/create-trap-preprocess.stdout'))
    assembly=a[:a.index('-E')]
    socket=json.loads((previous.BASE/'manifest.json').read_text());generated=Path(socket['generated_directory'])
    for name in ('pselect','select'):
        source=generated/('___'+name+'.s');dep=out/('trap-'+name+'.d');asm=out/('trap-'+name+'.s');obj=out/('trap-'+name+'.o')
        raw=run(assembly+['-E','-P','-MD','-MF',dep,source],name+'-preprocess').stdout
        before=deps(run(assembly+['-M',source],name+'-scan').stdout);consumed=deps(dep.read_text())
        if before!=consumed:raise ValueError('Trap actual dependency mismatch')
        headers.update(before);records[name+'-trap']=dict(scanned_sha256=before,consumed_sha256=consumed)
        asm.write_text(raw.replace('%%','\n').replace(';','\n'))
        run([assembly[0],'-target','arm64-apple-darwin','-mcpu=cortex-a76','-x','assembler','-c',asm,'-o',obj],name+'-assemble')
        objects.append(obj)
    renames=['-Dlibc_hooks=fixture_hooks','-Dlibc_set_introspection_hooks=fixture_set_hooks']
    string=compile(sources[0],'host-strchrnul',native+freebsd+renames+['-Dstrchrnul=fixture_strchrnul'])
    hooks=compile(fixed,'host-hooks',native+renames)
    badhooks=compile(sources[1],'host-original-hooks',native+renames)
    pselect=compile(sources[2],'host-pselect',native+['-Dselect=fixture_select','-Dpselect=fixture_pselect',
        '-D__pselect=fixture_pselect_trap','-D__select=fixture_select_trap','-D__pthread_sigmask=fixture_sigmask'])
    caller=compile(HARNESS,'host-caller',native)
    host=out/'original-file-wait-host';badhost=out/'original-hooks-negative-host'
    run(native+[caller,string,hooks,pselect,'-o',host],'host-link')
    run(native+[caller,string,badhooks,pselect,'-o',badhost],'original-host-link')
    bad=run([badhost,'original-oversize'],'original-oversize',True)
    if bad.returncode==0 or 'AddressSanitizer: heap-buffer-overflow' not in bad.stderr:
        raise ValueError('Original hook overflow negative did not reproduce')
    result=run([host],'host-run')
    if result.stdout!=EXPECTED or result.stderr:raise ValueError('Native file/wait oracle differs')
    archive=out/'libapple-ssh-file-wait.a';run(['xcrun','ar','rcs',archive,*objects],'archive')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map');link.append(str(archive))
    result=run(link,'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    verify()
    for n,h in headers.items():
        if sha(n)!=h:raise ValueError('Header changed during build')
    report=dict(profile='apple-ssh-file-wait-hooks-byte-tail-v1',source_inputs_sha256=pins,
        headers_sha256=headers,dependency_records=records,commands=commands,target_archive=str(archive),
        original_sources=list(map(str,sources)),private_source=str(fixed),hook_correction=dict(old=HOOK_OLD,new=HOOK_NEW),
        hook_error_reproduced_asan=True,hook_setter_only_single_threaded=True,native_asan_ubsan_pass=True,
        native_stdout=EXPECTED,native_syscalls_are_doubles=True,original_cancellation_and_enosys_fallback=True,
        namespace_only_select_fallback=True,target_missing_symbols=missing,target_duplicate_symbols=duplicates,
        closed_symbols=sorted(set(base['target_missing_symbols'])-set(missing)),
        newly_reachable_symbols=sorted(set(missing)-set(base['target_missing_symbols'])),
        remaining_provider_groups=previous.previous.previous.categories(missing),
        target_link_complete=not result.returncode,target_executed=False,host_processes_or_sockets_executed=False,
        provider_stubs=False,original_openssh_config_unchanged=True,accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),closed=report['closed_symbols'],new=report['newly_reachable_symbols'],
                          remaining=len(missing),duplicates=duplicates),indent=2))
    return out,report


if __name__=='__main__':build()
