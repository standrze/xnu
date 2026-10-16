#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct whole current Apple environment family; original negatives retained.

The accepted archive is never changed. Its three old environment objects are
removed only from a new private copy, so all new readers and mutators share the
actual current lock/ownership state. This does not qualify timezone/notify or SSH.
"""
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_rwlock_transport as prior
from tools.rpi5 import prepare_pid1

ROOT,sha=prior.ROOT,prior.sha
LIBC=prior.source.LIBC
BASE=ROOT/'build/rpi5/apple-ssh-rwlock-transport-a35pfswk'
BASE_SHA='7529c89500f244594b9f14f8fde7340d448950a1b4107acb3bf225ce4641a0d7'
OLD=ROOT/'build/rpi5/apple-ssh-case-signal-z9p6dj86/private-apple-runtime-current-comparisons.a'
MEMBERS=tuple('stdlib.subproj-'+n+'.o' for n in ('getenv','setenv','putenv'))
UNITS=tuple('stdlib/FreeBSD/'+n+'.c' for n in ('getenv','setenv','putenv'))
HARNESS=ROOT/'tools/rpi5/tests/ssh_environment_host.c'
FRAGMENTS=ROOT/'build/rpi5/apple-runtime-api-fragments-bg8jq8u2/libapple-selected-runtime-apis.a'
FORCE=('_getenv','_getenv_copy_np','_setenv','_unsetenv','_putenv','_environ_lock_np','_environ_unlock_np',
       '___environ_lock_fork_child','__allocenvstate','__deallocenvstate','__setenvp','__getenvp','__unsetenvp','__putenvp')
NAMES=('getenv','getenv_copy_np','setenv','unsetenv','putenv','environ_lock_np','environ_unlock_np',
       '__findenv_locked','__environ_lock_fork_child','_getenvp','_setenvp','_unsetenvp','_putenvp',
       '_allocenvstate','_copyenv','_deallocenvstate','__env_owned','__init__env_owned_locked',
       '__setenv_locked','__unsetenv_locked','_owned_ptr_search','_owned_ptr_add','_owned_ptr_alloc',
       '_owned_ptr_delete','_owned_ptr_free','_cthread_init_routine')
RENAMES={n:'fixture_'+n.lstrip('_') for n in NAMES}
RENAMES.update({'__environ_lock_fork_child':'fixture__environ_lock_fork_child',
                '__env_owned':'fixture_env_owned'})
EXPECTED='APPLE_ENV PASS LEAKS=0 ERROR_CONTRACT_PRESERVED THREADS=4 ITERATIONS=128 TEST_ONLY_ENVIRONMENT\n'
ORIGINAL_EXPECTED='APPLE_ENV ORIGINAL_LEAKS=2 ERROR_CONTRACT_PRESERVED THREADS=4 ITERATIONS=128 TEST_ONLY_ENVIRONMENT\n'


def repaired(text):
    old='\t\tif (++attempts > 5) {\n\t\t\terrno = EAGAIN;'
    if text.count(old)!=1:raise ValueError('Exact retry cleanup site required')
    text=text.replace(old,'\t\tif (++attempts > 5) {\n\t\t\tfree(result_buffer);\n\t\t\terrno = EAGAIN;',1)
    old='\t\tif (!value)\n\t\t\treturn NULL;'
    if text.count(old)!=1:raise ValueError('Exact disappeared-value cleanup site required')
    return text.replace(old,'\t\tif (!value) {\n\t\t\tint saved_errno = errno;\n\t\t\tfree(result_buffer);\n\t\t\terrno = saved_errno;\n\t\t\treturn NULL;\n\t\t}',1)


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen transport prerequisite differs')
    base=json.loads((BASE/'manifest.json').read_text());pins={str(BASE/'manifest.json'):BASE_SHA,
        str(Path(__file__).resolve()):sha(__file__),str(HARNESS):sha(HARNESS),str(OLD):sha(OLD),str(FRAGMENTS):sha(FRAGMENTS)}
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
        for n,h in base[key].items():
            if n in pins and pins[n]!=h:raise ValueError('Pin conflict')
            pins[n]=h
    for name in (*UNITS,'tests/getenv.c'):
        p=LIBC/name;pins[str(p)]=sha(p)
        if p.read_bytes()!=subprocess.check_output(['git','-C',LIBC,'show','HEAD:'+name]):raise ValueError('Whole original differs')
    def verify():
        for n,h in pins.items():
            if sha(n)!=h:raise ValueError('Input drift '+n)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-ssh-environment-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[];headers={};records={}
    def run(args,label,allowed=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=90)
        for stream in ('stdout','stderr'):(out/(label+'.'+stream)).write_text(getattr(r,stream))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-5000:])
        return r
    def deps(text):return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    def compile_(flags,path,label):
        before=deps(run([*flags,'-M',path],label+'-scan').stdout);obj=out/(label+'.o');dep=out/(label+'.d')
        run([*flags,'-MD','-MF',dep,'-c',path,'-o',obj],label+'-compile');after=deps(dep.read_text())
        if before!=after:raise ValueError('Compile dependency closure differs')
        headers.update(before);records[label]=dict(scanned_sha256=before,consumed_sha256=after);return obj
    flags=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/thread-switch-compile.stdout'))
    flags=flags[:flags.index('-MD')]
    corrected=out/'getenv_cleanup_checked.c';corrected.write_text(repaired((LIBC/UNITS[0]).read_text()))
    original=compile_(flags,LIBC/UNITS[0],'original-getenv')
    objects=[compile_(flags,corrected,'getenv'),*[compile_(flags,LIBC/n,Path(n).stem) for n in UNITS[1:]]]
    archive=out/'libapple-current-environment.a';run(['xcrun','ar','rcs',archive,*objects],'archive')
    private=out/'private-apple-runtime-current-environment.a';shutil.copyfile(OLD,private)
    before=run(['xcrun','ar','-t',OLD],'old-members').stdout.splitlines()
    if any(before.count(n)!=1 for n in MEMBERS):raise ValueError('Exact three old environment members required')
    run(['xcrun','ar','-d',private,*MEMBERS],'remove-old-environment')
    after=run(['xcrun','ar','-t',private],'private-members').stdout.splitlines()
    if after!=[n for n in before if n not in MEMBERS]:raise ValueError('Unrelated member changed')
    for n in after:
        if n=='__.SYMDEF SORTED':continue  # Archive index necessarily changes; object bytes may not.
        if subprocess.check_output(['xcrun','ar','-p',OLD,n])!=subprocess.check_output(['xcrun','ar','-p',private,n]):raise ValueError('Unrelated member bytes differ')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    if link.count(str(OLD))!=1:raise ValueError('Exact old archive link slot required')
    link[link.index(str(OLD))]=str(private);link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    r=run([*link,archive],'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',r.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",r.stderr)))
    if (sorted(set(base['target_missing_symbols'])-set(missing))!=['_getenv_copy_np'] or
        set(missing)-set(base['target_missing_symbols']) or duplicates):raise ValueError('Exact environment delta differs')
    contract=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/contract-link.stdout')))
    contract[contract.index(str(OLD))]=str(private);target=out/'NOT_RUN_environment_contract';mapping=out/'contract.map'
    contract[contract.index('-o')+1]=str(target);contract[contract.index('-map')+1]=str(mapping)
    contract+=[str(FRAGMENTS),str(archive)]
    for symbol in FORCE:contract+=['-u',symbol]
    cr=run(contract,'contract-link',True)
    if cr.returncode:raise ValueError('Actual forced environment static contract incomplete: '+cr.stderr[-3000:])
    inspected=None;owners={}
    if cr.returncode==0:
        if run(['xcrun','nm','-ju',target],'contract-undefined').stdout:raise ValueError('Static providers missing')
        inspected=prepare_pid1.inspect(target.read_bytes());text=mapping.read_text()
        table={int(n):p for n,p in re.findall(r'(?m)^\[\s*(\d+)\]\s+(.+)$',text)}
        for symbol in (*FORCE,'_os_unfair_lock_lock_with_options','_os_unfair_lock_unlock','__NSGetEnviron','_reallocf'):
            hits=re.findall(r'(?m)^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+'+re.escape(symbol)+'$',text)
            if len(hits)!=1:raise ValueError('Exact live owner missing '+symbol)
            owners[symbol]=table[int(hits[0])]
        if any(s in text for s in ('fixture_','__asan','__ubsan')):raise ValueError('Test-only provider in target')
    native=[n for n in flags if n not in ('-ffreestanding','-mcpu=cortex-a76')];i=native.index('-target');del native[i:i+2]
    native+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=undefined']
    renames=[f'-D{n}={v}' for n,v in RENAMES.items()]+['-D_NSGetEnviron=fixture_NSGetEnviron',
        '-Dos_unfair_lock_lock_with_options=fixture_lock','-Dos_unfair_lock_unlock=fixture_unlock','-Dreallocf=fixture_reallocf','-Dfree=fixture_free']
    host_objects=[compile_(native+renames,LIBC/n,'host-'+Path(n).stem) for n in UNITS]
    fixed=compile_(native+renames,corrected,'host-getenv-fixed');harness=compile_(native,HARNESS,'host-harness')
    old_host=out/'original-environment-host';new_host=out/'environment-host'
    run([*native,*host_objects,harness,'-o',old_host],'original-host-link')
    run([*native,fixed,*host_objects[1:],harness,'-o',new_host],'host-link')
    original_result=run([old_host,'original-leaks'],'original-host-negative')
    if original_result.stdout!=ORIGINAL_EXPECTED or original_result.stderr:raise ValueError('Original negative oracle differs')
    if run([old_host],'original-contract-failure',True).returncode!=32:raise ValueError('Original leaks not reproduced')
    result=run([new_host],'host-run')
    if result.stdout!=EXPECTED or result.stderr:raise ValueError('Derived oracle differs')
    if run([new_host,'original-leaks'],'derived-negative',True).returncode!=32:raise ValueError('Derived original expectation did not fail')
    if run([new_host,'bad-expected'],'host-negative',True).returncode!=37:raise ValueError('Bad oracle accepted')
    verify()
    for n,h in headers.items():
        if sha(n)!=h:raise ValueError('Header drift')
    m=dict(profile='current-apple-environment-whole-family-cleanup-derived-v1',source_inputs_sha256=pins,
        headers_sha256=headers,dependency_records=records,commands=commands,target_archive=str(archive),private_archive=str(private),
        removed_old_members=list(MEMBERS),unrelated_members_byte_identical=True,original_units=list(UNITS),
        target_missing_symbols=missing,target_duplicate_symbols=duplicates,
        closed_symbols=sorted(set(base['target_missing_symbols'])-set(missing)),newly_reachable_symbols=sorted(set(missing)-set(base['target_missing_symbols'])),
        forced_apis=list(FORCE),contract_returncode=cr.returncode,target=str(target),target_sha256=sha(target) if target.exists() else None,
        static_inspection=inspected,live_symbol_owners=owners,native_original_stdout=original_result.stdout,native_stdout=result.stdout,
        native_asan_ubsan_pass=True,native_environment_pointer_and_lock_are_test_doubles=True,original_leaks_reproduced=2,
        original_getenv_object=str(original),derived_cleanup_only=True,accepted_runtime_modified=False,provider_stubs=False,
        target_executed=False,full_client_qualified=False,stdtime_qualified=False,notification_feature_unchanged=True,
        target_multithreaded_fork_coordination_qualified=False,prior_qualified_client_import_count=41,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),manifest_sha256=sha(out/'manifest.json'),closed=m['closed_symbols'],added=m['newly_reachable_symbols'],remaining=len(missing),contract_rc=cr.returncode),indent=2))
    return out,m


if __name__=='__main__':build()
