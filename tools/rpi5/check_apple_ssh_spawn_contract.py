#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Current Apple system/spawn contract with a narrowly derived errno repair.

The whole modern popen TU is preserved only in the preceding inventory: its
fwide dependency cannot use the unchanged Libc-167 byte-only FILE ABI. This
archive deliberately excludes popen instead of substituting an orientation stub.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_spawn_group as audit
from tools.rpi5 import prepare_pid1

ROOT,LIBC,sha=audit.ROOT,audit.LIBC,audit.sha
INVENTORY=ROOT/'build/rpi5/apple-ssh-spawn-group-e7hiad29'
INVENTORY_SHA='268e2b11873129cd5a367eeb0829e705ca90cc2ceeedbdfe48d62ba07d6c08b3'
HARNESS=ROOT/'tools/rpi5/tests/ssh_spawn_group_host.c'
TRAP=ROOT/'build/rpi5/apple-ssh-socket-syscalls-n4wc59z7/generated/___posix_spawn.s'
FORCE=('_system','_posix_spawn','_posix_spawnattr_init','_posix_spawnattr_destroy',
       '_posix_spawnattr_setflags','_posix_spawnattr_getflags',
       '_posix_spawnattr_setsigmask','_posix_spawnattr_getsigmask',
       '_posix_spawnattr_setsigdefault','_posix_spawnattr_getsigdefault',
       '_posix_spawn_file_actions_init','_posix_spawn_file_actions_destroy',
       '_posix_spawn_file_actions_addopen','_posix_spawn_file_actions_addclose',
       '_posix_spawn_file_actions_adddup2','___posix_spawn')
CALLBACKS=('__posix_spawn','__execve','_NSGetEnviron','access','sigaction','sigprocmask',
           'wait4','pthread_testcancel','malloc','free','realloc','reallocf')
EXPECTED='APPLE_SPAWN PASS ATTRIBUTES ACTIONS SPAWN SYSTEM THREADS=4 ITERATIONS=32 APPLE_BODIES_SYSTEM_ERRNO_CORRECTION TEST_ONLY_KERNEL_SIGNAL_IO\n'
ORIGINAL_EXPECTED='APPLE_SYSTEM ORIGINAL_FAILURE_OBSERVED ENOMEM EAGAIN RETURN_MINUS_ONE STALE_EDOM TEST_ONLY_KERNEL_SIGNAL_IO\n'
ORIGINAL_SYSTEM=LIBC/'stdlib/FreeBSD/system.c'
OLD='\t} else if (err == ENOMEM || err == EAGAIN) { /* as if fork failed */\n\t\tpstat = -1;'
NEW='\t} else if (err == ENOMEM || err == EAGAIN) { /* as if fork failed */\n\t\terrno = err;\n\t\tpstat = -1;'
SPEC=ROOT/'tools/rpi5/ssh_spawn_errno_contract.md'


def build():
    pins={str(Path(__file__).resolve()):sha(__file__),str(HARNESS):sha(HARNESS),
          str(TRAP):sha(TRAP),str(SPEC):sha(SPEC),str(Path(prepare_pid1.__file__).resolve()):sha(prepare_pid1.__file__)}
    docs=[]
    for directory,digest in ((audit.BASE,audit.BASE_SHA),(INVENTORY,INVENTORY_SHA)):
        path=directory/'manifest.json'
        if sha(path)!=digest:raise ValueError('Frozen original prerequisite changed')
        pins[str(path)]=digest;doc=json.loads(path.read_text());docs.append(doc)
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for name,h in doc[key].items():
                if name in pins and pins[name]!=h:raise ValueError('Pin conflict '+name)
                pins[name]=h
    for path in (LIBC/'xcodescripts/variants.xcconfig',LIBC/'xcodescripts/libc.xcconfig',
                 LIBC/'stdlib/FreeBSD/system.3',ROOT/'libsyscall/Platforms/syscall.map',ROOT/'experiments/darwin-container/userland/build_apple_runtime.py'):
        pins[str(path)]=sha(path)
    base,inventory=docs
    if inventory['compile_failures']:raise ValueError('Whole original compile failed')
    def verify():
        for name,h in pins.items():
            if sha(name)!=h:raise ValueError('Input drift '+name)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-ssh-spawn-contract-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[];headers={};records={}
    def run(args,label,allowed=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=90)
        for stream in ('stdout','stderr'):(out/(label+'.'+stream)).write_text(getattr(r,stream))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-4500:])
        return r
    def deps(text):return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    def compile_(flags,source,label):
        before=deps(run([*flags,'-M',source],label+'-scan').stdout)
        obj,dep=out/(label+'.o'),out/(label+'.d')
        run([*flags,'-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        after=deps(dep.read_text())
        if before!=after:raise ValueError('Actual consumed headers differ')
        headers.update(before);records[label]=dict(scanned_sha256=before,consumed_sha256=after)
        return obj
    command=next(c['command'] for c in inventory['commands'] if c['stdout'].endswith('/system-compile.stdout'))
    flags=command[:command.index('-MD')]+['-U__DARWIN_NON_CANCELABLE','-D__DARWIN_NON_CANCELABLE=0']
    original_text=ORIGINAL_SYSTEM.read_text()
    if original_text.count(OLD)!=1:raise ValueError('Exact original system errno branch changed')
    derived=out/'system_errno_checked.c';derived.write_text(original_text.replace(OLD,NEW))
    system=compile_(flags,derived,'system')
    asm=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/___write_nocancel-preprocess.stdout'))
    assembly=asm[:asm.index('-E')];dep=out/'spawn-trap.d'
    before=deps(run([*assembly,'-M',TRAP],'spawn-trap-scan').stdout)
    expanded=run([*assembly,'-E','-P','-MD','-MF',dep,TRAP],'spawn-trap-preprocess').stdout
    after=deps(dep.read_text())
    if before!=after:raise ValueError('Original trap headers differ')
    headers.update(before);records['spawn-trap']=dict(scanned_sha256=before,consumed_sha256=after)
    generated,obj=out/'spawn-trap.s',out/'spawn-trap.o';generated.write_text(expanded.replace('%%','\n').replace(';','\n'))
    run([assembly[0],'-target','arm64-apple-darwin','-mcpu=cortex-a76','-x','assembler','-c',generated,'-o',obj],'spawn-trap-assemble')
    archive=out/'libapple-ssh-system-spawn.a'
    run(['xcrun','ar','rcs',archive,system,inventory['objects']['posix_spawn'],obj],'archive')
    run(['xcrun','nm','-g',archive],'target-symbols');run(['xcrun','llvm-objdump','-d','-r',archive],'target-disassembly')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    result=run([*link,archive],'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    closed=sorted(set(base['target_missing_symbols'])-set(missing));added=sorted(set(missing)-set(base['target_missing_symbols']))
    if closed!=['_system'] or added or duplicates:raise ValueError('Unexpected full current-client delta')
    contract=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/contract-link.stdout')))
    target,mapping=out/'NOT_RUN_spawn_contract',out/'contract.map'
    contract[contract.index('-o')+1]=str(target);contract[contract.index('-map')+1]=str(mapping)
    contract+=[str(archive)]
    for name in FORCE:contract+=['-u',name]
    run(contract,'contract-link')
    if run(['xcrun','nm','-ju',target],'contract-undefined').stdout:raise ValueError('Undefined static contract')
    inspected=prepare_pid1.inspect(target.read_bytes());text=mapping.read_text()
    table={int(n):p for n,p in re.findall(r'(?m)^\[\s*(\d+)\]\s+(.+)$',text)};owners={}
    for symbol in FORCE:
        matches=re.findall(r'(?m)^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+'+re.escape(symbol)+'$',text)
        if len(matches)!=1:raise ValueError('Unique live owner absent: '+symbol)
        owners[symbol]=table[int(matches[0])]
        if str(archive)+'(' not in owners[symbol]:raise ValueError('Wrong live provider: '+symbol)
    if any(s in text for s in ('fixture_','__asan','__ubsan')):raise ValueError('Test double in static target')
    names=set(CALLBACKS)|{'system','execve','__unix_conforming'}
    symbols=(INVENTORY/'posix_spawn-symbols.stdout').read_text()
    names.update(n[1:] for n in re.findall(r'^[0-9a-f]+ [A-Z] (_\S+)$',symbols,re.M))
    rename=out/'native_names.h';rename.write_text('/* Native-only names; never passed to target compiler. */\n'+
        ''.join('#define '+n+' fixture_'+n+'\n' for n in sorted(names)))
    native=[n for n in flags if n not in ('-ffreestanding','-mcpu=cortex-a76')]
    i=native.index('-target');del native[i:i+2]
    native+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=undefined']
    original_host=compile_(native+['-include',str(rename)],ORIGINAL_SYSTEM,'host-system-original')
    objects=[compile_(native+['-include',str(rename)],source,'host-'+source.stem) for source in
        (derived,ROOT/'libsyscall/wrappers/spawn/posix_spawn.c')]
    for index,obj in enumerate([original_host,*objects]):
        undefined=run(['xcrun','nm','-ju',obj],'host-undefined-'+str(index)).stdout.splitlines()
        if any('_'+n in undefined for n in CALLBACKS):raise ValueError('Native external boundary not isolated')
        defined=run(['xcrun','nm','-gU',obj],'host-defined-'+str(index)).stdout
        exports=re.findall(r'^[0-9a-f]+ [A-Z] (_\S+)$',defined,re.M)
        if not exports or any(not n.startswith('_fixture_') and n!='____asan_globals_registered' for n in exports):
            raise ValueError('Original host exports must all be explicitly namespaced')
    caller=compile_(native,HARNESS,'host-harness');host=out/'spawn-host';original_executable=out/'spawn-original-host'
    run([*native,caller,original_host,objects[1],'-Wl,-dead_strip','-o',original_executable],'host-original-link')
    result=run([original_executable,'original-errno'],'host-original-error-observed')
    if result.stdout!=ORIGINAL_EXPECTED or result.stderr:raise ValueError('Original errno defect not reproduced')
    if run([original_executable,'require-errno'],'host-original-error-contract',True).returncode!=32:
        raise ValueError('Original failed contract unexpectedly accepted')
    run([*native,caller,*objects,'-Wl,-dead_strip','-o',host],'host-link')
    if run([host,'require-errno'],'host-derived-error-contract').stdout:raise ValueError('Unexpected errno contract output')
    result=run([host],'host-run')
    if result.stdout!=EXPECTED or result.stderr:raise ValueError('Native actual-source oracle differs')
    if run([host,'bad-expected'],'host-negative',True).returncode!=31:raise ValueError('Native oracle negative not rejected')
    verify()
    for name,h in headers.items():
        if sha(name)!=h:raise ValueError('Header drift '+name)
    report=dict(profile='apple-system-errno-checked-spawn-static-native-v1',source_inputs_sha256=pins,
        headers_sha256=headers,dependency_records=records,commands=commands,target_archive=str(archive),
        target_missing_symbols=missing,target_duplicate_symbols=duplicates,closed_symbols=closed,newly_reachable_symbols=added,
        target=str(target),target_sha256=sha(target),static_inspection=inspected,live_symbol_owners=owners,
        original_units_unchanged=False,system_original_cancellation_point=True,spawn_execve_only_namespaced=True,
        system_errno_correction=dict(original=str(ORIGINAL_SYSTEM),original_sha256=sha(ORIGINAL_SYSTEM),
            derived=str(derived),derived_sha256=sha(derived),exact_old=OLD,exact_new=NEW,
            native_original_failure_observed=True,original_stdout=ORIGINAL_EXPECTED,
            original_error_contract_exit=32,derived_error_contract_exit=0,specification=str(SPEC)),
        original_spawn_and_trap_bodies_unchanged=True,
        modern_popen_excluded_reason='fwide requires an orientation state absent from accepted Libc-167 byte-only FILE',
        native_asan_ubsan_pass=True,native_stdout=EXPECTED,host_process_io_signal_boundaries_are_doubles=True,
        target_executed=False,full_client_qualified=False,provider_stubs=False,accepted_runtime_modified=False,
        original_openssh_config_unchanged=True,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(output=str(out),manifest_sha256=sha(out/'manifest.json'),closed=closed,remaining=len(missing),forced=len(FORCE),native=EXPECTED),indent=2))
    return out,report


if __name__=='__main__':build()
