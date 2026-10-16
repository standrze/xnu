#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Unique trap/wrapper outputs and original-source native behavior evidence."""
import hashlib
from pathlib import Path
import shlex

ROOT=Path(__file__).resolve().parents[2]
SOURCE=Path(__file__).with_name('build_apple_ssh_process_providers.py')
EXPECTED='5b621871f21271d40229fb2235a89749fd9dd7f7550da20c54fe4eb5cfcbe354'
HARNESS=ROOT/'tools/rpi5/tests/ssh_process_providers_host.c'
STDOUT='APPLE_SSH_PROCESS PASS PEER=3 RAISE=3 WAIT=3 RMDIR=2 EXEC=6 PROGNAME=1 SYSCALL_PROCESS_DOUBLES\n'


def native(run,flags,out,headers,records):
    libc=ROOT/'build/rpi5/apple-libc-main-candidate-20261013'
    common=[s for s in flags if s not in ('-ffreestanding','-mcpu=cortex-a76')]
    i=common.index('-target');del common[i:i+2]
    common+=['-O1','-g','-fsanitize=address,undefined']
    rename={
        'gen/FreeBSD/getpeereid.c':{'getpeereid':'fixture_getpeereid','getsockopt':'fixture_getsockopt'},
        'gen/FreeBSD/getprogname.c':{'getprogname':'fixture_getprogname','_NSGetProgname':'fixture_NSGetProgname'},
        'gen/FreeBSD/waitpid.c':{'waitpid':'fixture_waitpid','__wait4':'fixture_wait4'},
        'gen/raise.c':{n:'fixture_'+n for n in ('raise','pthread_self','pthread_kill','getpid','kill')},
        'gen/FreeBSD/exec.c':{n:'fixture_'+n for n in ('execv','execl','execle','execlp','execvp','execvP','_execvpe','execve','getenv','write','stat')}|{'_NSGetEnviron':'fixture_NSGetEnviron'},
        'libsyscall/wrappers/rmdir.c':{'rmdir':'fixture_rmdir','__rmdir':'fixture_rmdir_trap','__inc_remove_counter':'fixture_inc_remove_counter'},
        'libsyscall/wrappers/remove-counter.c':{'__inc_remove_counter':'fixture_inc_remove_counter','__get_remove_counter':'fixture_get_remove_counter'},
    }
    objects=[]
    def deps(text):
        return {str(Path(n).resolve()):hashlib.sha256(Path(n).read_bytes()).hexdigest()
                for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    for name,names in rename.items():
        source=(ROOT if name.startswith('libsyscall/') else libc)/name
        args=common+['-D'+a+'='+b for a,b in names.items()]
        if '/FreeBSD/' in name:args+=['-include',str(libc/'fbsdcompat/_fbsd_compat_.h')]
        if name.endswith('/waitpid.c'):args+=['-DVARIANT_CANCELABLE','-D__DARWIN_UNIX03=1']
        label='host-'+Path(name).stem;obj=out/(label+'.o');dep=out/(label+'.d')
        before=deps(run(args+['-M',source],label+'-scan').stdout)
        run(args+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        consumed=deps(dep.read_text())
        if before!=consumed:raise ValueError('Native actual header closure changed')
        headers.update(before);records[label]=dict(scanned_sha256=before,consumed_sha256=consumed)
        objects.append(obj)
    host=out/'original-process-host'
    run(common+[HARNESS,*objects,'-o',host],'host-link')
    result=run([host],'host-run')
    if result.stdout!=STDOUT or result.stderr:raise ValueError('Original process error oracle failed')


def implementation():
    raw=SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED:raise ValueError('Frozen process precursor changed')
    text=raw.decode()
    replacements={
        "source=candidates[0];obj=out/(n+'.o');dep=out/(n+'.d');asm=out/(n+'.s')":
        "source=candidates[0];obj=out/('trap-'+n+'.o');dep=out/('trap-'+n+'.d');asm=out/('trap-'+n+'.s')",
        "pins={str(BASE/'manifest.json'):BASE_SHA}":
        "pins={str(BASE/'manifest.json'):BASE_SHA,str(_source_builder):sha(_source_builder),str(_harness):sha(_harness)}",
        "archive=out/'libapple-ssh-process-providers.a'":
        "_native(run,flags,out,headers,records)\n    archive=out/'libapple-ssh-process-providers.a'\n    if len(objects)!=len(set(objects)):raise ValueError('Trap/wrapper output collision')",
        "profile='original-apple-ssh-peer-process-file-providers-v1'":
        "profile='original-apple-ssh-peer-process-file-providers-v2'",
        "native_semantics_tested=False":
        "native_semantics_tested=True,native_asan_ubsan_pass=True,native_syscalls_are_doubles=True,native_stdout=_stdout",
    }
    for old,new in replacements.items():
        if text.count(old)!=1:raise ValueError('Exact private derivation changed: '+old)
        text=text.replace(old,new)
    scope=dict(__name__=__name__+'.private',__file__=str(Path(__file__).resolve()),
               _source_builder=SOURCE,_harness=HARNESS,_native=native,_stdout=STDOUT)
    exec(compile(text,str(SOURCE),'exec'),scope)
    return scope


if __name__=='__main__':implementation()['build']()
