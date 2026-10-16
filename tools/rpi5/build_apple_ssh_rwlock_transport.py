#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original pthread RW-lock trap closure; no target or host psynch execution."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_stdtime_group as source
from tools.rpi5 import prepare_pid1

ROOT,sha=source.ROOT,source.sha
TIME=ROOT/'build/rpi5/apple-ssh-stdtime-group-m0v5p_ge'
TIME_SHA='2209b0c9f1edefd09d73e4a344eb9527ca338c9bae32675c45b305df4b150c82'
GENERATED=ROOT/'build/rpi5/apple-ssh-socket-syscalls-n4wc59z7/generated'
WRAPPER=ROOT/'libsyscall/mach/ms_thread_switch.c'
HARNESS=ROOT/'tools/rpi5/tests/ssh_rwlock_transport_host.c'
CALLS={'psynch_rw_rdlock':306,'psynch_rw_wrlock':307,'psynch_rw_unlock':308}
FORCE=('___psynch_rw_rdlock','___psynch_rw_wrlock','___psynch_rw_unlock','_thread_switch',
       '_pthread_rwlock_init','_pthread_rwlock_destroy','_pthread_rwlock_rdlock',
       '_pthread_rwlock_wrlock','_pthread_rwlock_tryrdlock','_pthread_rwlock_trywrlock','_pthread_rwlock_unlock')
EXPECTED='APPLE_THREAD_SWITCH PASS CASES=336 ORIGINAL_WRAPPER TEST_ONLY_MACH_TRAP NO_KERNEL_EXECUTION\n'


def build():
    pins={str(Path(__file__).resolve()):sha(__file__),str(WRAPPER):sha(WRAPPER),str(HARNESS):sha(HARNESS),
          str(Path(prepare_pid1.__file__).resolve()):sha(prepare_pid1.__file__)}
    parents=[]
    for directory,pin in ((source.BASE,source.BASE_SHA),(TIME,TIME_SHA)):
        path=directory/'manifest.json'
        if sha(path)!=pin:raise ValueError('Exact current predecessor changed')
        pins[str(path)]=pin;doc=json.loads(path.read_text());parents.append(doc)
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for name,h in doc[key].items():
                if name in pins and pins[name]!=h:raise ValueError('Pin conflict '+name)
                pins[name]=h
    base,timing=parents;master=ROOT/'bsd/kern/syscalls.master'
    pins[str(master)]=sha(master)
    if WRAPPER.read_bytes()!=subprocess.check_output(['git','show','HEAD:libsyscall/mach/ms_thread_switch.c'],cwd=ROOT):
        raise ValueError('Whole original Mach wrapper differs')
    for name,number in CALLS.items():
        path=GENERATED/('___'+name+'.s');pins[str(path)]=sha(path)
        if not re.search(r'^'+str(number)+r'\s+[^\n]*\b'+name+r'\(',master.read_text(),re.M):raise ValueError('Kernel syscall number differs')
        if 'SYSCALL_NONAME('+name+', 5, cerror_nocancel)' not in path.read_text():raise ValueError('Original error policy differs')
    def verify():
        for name,h in pins.items():
            if sha(name)!=h:raise ValueError('Input drift '+name)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-ssh-rwlock-transport-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[];headers={};records={};objects=[]
    def run(args,label,allowed=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=90)
        for stream in ('stdout','stderr'):(out/(label+'.'+stream)).write_text(getattr(r,stream))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-4500:])
        return r
    def deps(text):return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    def compile_(flags,path,label):
        before=deps(run([*flags,'-M',path],label+'-scan').stdout);dep=out/(label+'.d');obj=out/(label+'.o')
        run([*flags,'-MD','-MF',dep,'-c',path,'-o',obj],label+'-compile');after=deps(dep.read_text())
        if before!=after:raise ValueError('Actual compile closure differs')
        headers.update(before);records[label]=dict(scanned_sha256=before,consumed_sha256=after);return obj
    command=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/system-compile.stdout'))
    flags=[n for n in command[:command.index('-MD')] if n!='-DVARIANT_CANCELABLE']
    objects.append(compile_(flags,WRAPPER,'thread-switch'))
    command=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/spawn-trap-preprocess.stdout'))
    assembly=command[:command.index('-E')]
    for name in CALLS:
        path=GENERATED/('___'+name+'.s');before=deps(run([*assembly,'-M',path],name+'-scan').stdout)
        dep=out/(name+'.d');raw=run([*assembly,'-E','-P','-MD','-MF',dep,path],name+'-preprocess').stdout
        after=deps(dep.read_text())
        if before!=after:raise ValueError('Actual assembler header closure differs')
        headers.update(before);records[name]=dict(scanned_sha256=before,consumed_sha256=after)
        asm=out/(name+'.s');asm.write_text(raw.replace('%%','\n').replace(';','\n'));obj=out/(name+'.o')
        run([assembly[0],'-target','arm64-apple-darwin','-mcpu=cortex-a76','-x','assembler','-c',asm,'-o',obj],name+'-assemble')
        objects.append(obj)
    archive=out/'libapple-pthread-rwlock-transport.a';run(['xcrun','ar','rcs',archive,*objects],'archive')
    run(['xcrun','llvm-objdump','-d','-r',archive],'target-disassembly')
    link=list(next(c['command'] for c in timing['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    result=run([*link,archive],'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    closed=sorted(set(timing['target_missing_symbols'])-set(missing));added=sorted(set(missing)-set(timing['target_missing_symbols']))
    if closed!=sorted(['___'+n for n in CALLS]+['_thread_switch']) or added or duplicates:raise ValueError('Exact four transport providers did not close')
    contract=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/contract-link.stdout')))
    target=out/'NOT_RUN_rwlock_contract';mapping=out/'contract.map'
    contract[contract.index('-o')+1]=str(target);contract[contract.index('-map')+1]=str(mapping)
    contract.append(str(archive))
    for symbol in FORCE:contract+=['-u',symbol]
    run(contract,'contract-link')
    if run(['xcrun','nm','-ju',target],'contract-undefined').stdout:raise ValueError('Forced reader/writer lock ABI remains incomplete')
    inspected=prepare_pid1.inspect(target.read_bytes());text=mapping.read_text()
    owners={};table={int(n):p for n,p in re.findall(r'(?m)^\[\s*(\d+)\]\s+(.+)$',text)}
    for symbol in (*FORCE,'_syscall_thread_switch','_cerror_nocancel'):
        hits=re.findall(r'(?m)^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+'+re.escape(symbol)+'$',text)
        if len(hits)!=1:raise ValueError('Unique actual owner absent '+symbol)
        owners[symbol]=table[int(hits[0])]
    if any(s in text for s in ('fixture_','__asan','__ubsan')):raise ValueError('Native double in target')
    native=[n for n in flags if n not in ('-ffreestanding','-mcpu=cortex-a76')]
    i=native.index('-target');del native[i:i+2]
    native+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=undefined']
    wrapper=compile_(native+['-Dthread_switch=fixture_thread_switch','-Dsyscall_thread_switch=fixture_syscall_thread_switch'],WRAPPER,'host-wrapper')
    harness=compile_(native,HARNESS,'host-harness');host=out/'thread-switch-host'
    run([*native,harness,wrapper,'-o',host],'host-link');result=run([host],'host-run')
    if result.stdout!=EXPECTED or result.stderr:raise ValueError('Original wrapper native oracle differs')
    if run([host,'bad-expected'],'host-negative',True).returncode!=37:raise ValueError('Negative oracle not detected')
    verify()
    for name,h in headers.items():
        if sha(name)!=h:raise ValueError('Header drift '+name)
    m=dict(profile='original-apple-rwlock-mach-transport-static-native-v1',source_inputs_sha256=pins,
        headers_sha256=headers,dependency_records=records,commands=commands,target_archive=str(archive),
        target_missing_symbols=missing,target_duplicate_symbols=duplicates,closed_symbols=closed,newly_reachable_symbols=added,
        target=str(target),target_sha256=sha(target),static_inspection=inspected,live_symbol_owners=owners,
        normal_stdtime_before_count=len(timing['target_missing_symbols']),qualified_client_before_count=len(base['target_missing_symbols']),
        original_wrapper_unchanged=True,original_generated_traps_unchanged=True,syscall_numbers=CALLS,
        native_stdout=EXPECTED,native_asan_ubsan_pass=True,native_mach_trap_is_callback=True,
        host_psynch_executed=False,target_executed=False,full_client_qualified=False,
        stdtime_qualified=False,provider_stubs=False,accepted_runtime_modified=False,original_openssh_config_unchanged=True,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),manifest_sha256=sha(out/'manifest.json'),closed=closed,remaining=len(missing),forced=len(FORCE)),indent=2))
    return out,m


if __name__=='__main__':build()
