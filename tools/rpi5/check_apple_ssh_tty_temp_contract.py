#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original path/TTY providers: real generated traps, native doubles, static link.

No target execution, host terminal, filesystem request, signal or random-input
access. Host locale objects are the preserved namespaced original Apple group.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_stdio_audit as audit
from tools.rpi5 import prepare_pid1

ROOT,sha=audit.ROOT,audit.sha
BASE=ROOT/'build/rpi5/apple-ssh-tty-temp-bm2n0nkz'
BASE_SHA='8a180e0948079b107bf2af3e2f112dd0409045c971db67a443da7c14b7167c6f'
NATIVE_LOCALE=ROOT/'build/rpi5/apple-ssh-current-locale-contract-ni1pfpjw'
NATIVE_SHA='c45e4a7c3f672003dfa1b6afdb97b6c370153902a487ac0230457251b5da5c6b'
CLOCK=ROOT/'build/rpi5/apple-clock-read-contract-mrnnxc8f'
CLOCK_SHA='e5ef9437d8eb3aa615a17c8f7b972c3dc7e7f44d64ea0f82c0aaab0c348ee64e'
IO=ROOT/'build/rpi5/apple-ssh-nocancel-io-97n771iy'
IO_SHA='9f754e50a8e2d09b8ba8420c58bbe7d043adb4a586bba59d34ff4ac44898518d'
GENERATED=ROOT/'build/rpi5/apple-ssh-socket-syscalls-n4wc59z7/generated'
TRAPS=('_fstatat64.s','_mkdirat.s','___write_nocancel.s','_statfs64.s')
FORCE=('_mkdtemp','_readpassphrase','_devname_r','_statfs','_fstatat','_mkdirat','_write$NOCANCEL')
HARNESS=ROOT/'tools/rpi5/tests/ssh_tty_temp_host.c'
CALLBACKS=('arc4random_uniform','fstatat','mkdirat','open','read','write','close',
           'tcgetattr','tcsetattr','sigaction','getpid','kill','opendir','readdir','closedir','lstat')


def build():
    pins={str(Path(__file__).resolve()):sha(__file__),str(HARNESS):sha(HARNESS),
          str(Path(prepare_pid1.__file__).resolve()):sha(prepare_pid1.__file__)}
    docs=[]
    for directory,digest in ((BASE,BASE_SHA),(NATIVE_LOCALE,NATIVE_SHA),(CLOCK,CLOCK_SHA),(IO,IO_SHA)):
        path=directory/'manifest.json'
        if sha(path)!=digest:raise ValueError('Exact predecessor manifest required')
        pins[str(path)]=digest;doc=json.loads(path.read_text());docs.append(doc)
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for name,value in doc.get(key,{}).items():
                if name in pins and pins[name]!=value:raise ValueError('Inherited pin conflict '+name)
                pins[name]=value
    base,locale,clock,io=docs
    if base['compile_failures'] or base['target_duplicate_symbols']:raise ValueError('Whole unit compile prerequisite failed')
    for name in TRAPS:pins[str(GENERATED/name)]=sha(GENERATED/name)
    def verify():
        for name,value in pins.items():
            if sha(name)!=value:raise ValueError('Input drift '+name)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-ssh-tty-temp-contract-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True)
    commands,headers,records=[],{},{}
    def run(args,label,allowed=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        for stream in ('stdout','stderr'):(out/(label+'.'+stream)).write_text(getattr(r,stream))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-5000:])
        return r
    def deps(text):return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    def compile_(flags,source,label):
        before=deps(run([*flags,'-M',source],label+'-scan').stdout)
        obj,dep=out/(label+'.o'),out/(label+'.d')
        run([*flags,'-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        after=deps(dep.read_text())
        if before!=after:raise ValueError('Actual consumed header mismatch')
        headers.update(before);records[label]=dict(scanned_sha256=before,consumed_sha256=after)
        return obj
    command=next(c['command'] for c in io['commands'] if c['stdout'].endswith('/read_nocancel-preprocess.stdout'))
    asm_flags=command[:command.index('-E')];objects=list(base['objects'].values())
    for name in TRAPS:
        source=GENERATED/name;label=Path(name).stem;dep=out/(label+'.d');asm=out/(label+'.s');obj=out/(label+'.o')
        before=deps(run([*asm_flags,'-M',source],label+'-scan').stdout)
        expanded=run([*asm_flags,'-E','-P','-MD','-MF',dep,source],label+'-preprocess').stdout
        after=deps(dep.read_text())
        if before!=after:raise ValueError('Actual trap header mismatch')
        headers.update(before);records[label]=dict(scanned_sha256=before,consumed_sha256=after)
        asm.write_text(expanded.replace('%%','\n').replace(';','\n'))
        run([asm_flags[0],'-target','arm64-apple-darwin','-mcpu=cortex-a76','-x','assembler','-c',asm,'-o',obj],label+'-assemble')
        objects.append(str(obj))
    archive=out/'libapple-ssh-tty-temp.a';run(['xcrun','ar','rcs',archive,*objects],'archive')
    run(['xcrun','nm','-g',archive],'target-symbols')
    run(['xcrun','llvm-objdump','-d','-r',*objects],'target-disassembly')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    if link.pop()!=base['target_archive']:raise ValueError('Exact partial archive tail required')
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    result=run([*link,archive],'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    original=json.loads((audit.BASE/'manifest.json').read_text())
    closed=sorted(set(original['target_missing_symbols'])-set(missing))
    added=sorted(set(missing)-set(original['target_missing_symbols']))
    if closed!=['_devname_r','_mkdtemp','_readpassphrase','_statfs'] or added or duplicates:raise ValueError('Unexpected original full client delta')
    contract=list(next(c['command'] for c in clock['commands'] if c['stdout'].endswith('/contract-link.stdout')))
    target,mapping=out/'NOT_RUN_tty_temp_contract',out/'contract.map'
    contract[contract.index('-o')+1]=str(target);contract[contract.index('-map')+1]=str(mapping)
    # The read-clock contract did not exercise random/temp/TTY entrypoints.
    # Reuse exactly the already-qualified real providers in the full SSH link.
    for suffix in ('kernel-entropy-word-z34ff8bs/librandom-word-api.a',
                   'kernel-entropy-rand-hfrb7y67/kernel-entropy-adapter.o',
                   'apple-ssh-nocancel-io-97n771iy/libapple-ssh-nocancel-io.a'):
        candidate=str(ROOT/'build/rpi5'/suffix)
        if link.count(candidate)!=1 or candidate not in pins:raise ValueError('Exact full-client dependency required')
        contract.append(candidate)
    contract+=[str(archive)]
    for name in FORCE:contract+=['-u',name]
    run(contract,'contract-link')
    if run(['xcrun','nm','-ju',target],'contract-undefined').stdout:raise ValueError('Undefined static provider')
    inspected=prepare_pid1.inspect(target.read_bytes())
    mapping_text=mapping.read_text();owners={}
    table={int(n):p for n,p in re.findall(r'(?m)^\[\s*(\d+)\]\s+(.+)$',mapping_text)}
    for symbol in FORCE:
        hits=re.findall(r'(?m)^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+'+re.escape(symbol)+'$',mapping_text)
        if len(hits)!=1:raise ValueError('Exact live owner required '+symbol)
        owners[symbol]=table[int(hits[0])]
        if str(archive)+'(' not in owners[symbol]:raise ValueError('Wrong actual provider '+symbol)
    if any(word in mapping_text for word in ('fixture_','__asan','__ubsan')):raise ValueError('Host double in target')
    # Native symbols are isolated, including original libc's public entrypoints.
    names=set(CALLBACKS)
    for name in base['original_units']:
        symbols=(BASE/(Path(name).stem+'-symbols.stdout')).read_text()
        names.update(n[1:] for n in re.findall(r'^[0-9a-f]+ [A-Z] (_\S+)$',symbols,re.M))
    rename=out/'native_names.h'
    rename.write_text('/* Native-only entrypoint and external-boundary names. */\n'+
        ''.join('#define '+n+' fixture_'+n+'\n' for n in sorted(names)))
    old=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/readpassphrase-compile.stdout'))
    native=list(old[:old.index('-MD')]);i=native.index('-target');del native[i:i+2]
    native=[n for n in native if n not in ('-mcpu=cortex-a76','-ffreestanding')]
    native+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=undefined',
        '-include',str(NATIVE_LOCALE/'native_names.h'),'-include',str(rename)]
    hostobjects=[]
    for name in base['original_units']:
        obj=compile_(native,audit.LIBC/name,'host-'+Path(name).stem);hostobjects.append(obj)
        undefined=run(['xcrun','nm','-ju',obj],'host-'+Path(name).stem+'-undefined').stdout.splitlines()
        if any(n in undefined for name in CALLBACKS for n in ('_'+name,'_'+name+'$NOCANCEL')):
            raise ValueError('Real host boundary leaked from native original source')
    # The harness needs prototypes and actual locale names, not I/O macro names.
    harness_flags=native[:-2]
    harness=compile_(harness_flags,HARNESS,'host-harness')
    original_native=next(c['command'] for c in locale['commands'] if c['stdout'].endswith('/native-link.stdout'))
    locale_objects=[Path(p) for p in original_native if p.endswith('.o') and not p.endswith('/native-harness.o')]
    host=out/'tty-temp-host'
    run([*native,harness,*hostobjects,*locale_objects,'-Wl,-dead_strip',
        *['-Wl,-unexported_symbol,_'+n for n in ('__collate_load_error','wcwidth','sgetrune','sputrune','__sgetrune','__sputrune')],
        '-o',host],'host-link')
    result=run([host],'host-run')
    expected=('APPLE_LOCALE PASS VECTORS=23 MODES=3 THREADS=4 ITERATIONS=2048 DESTRUCTORS=4 HOST_KEY_MAPPING_ONLY\n'
        'APPLE_TTY_TEMP PASS TEMP=7 TTY=15 DEVICE=5 IO_SIGNAL_ENTROPY_DOUBLES\n')
    if result.stdout!=expected or result.stderr:raise ValueError('Native path/TTY oracle differs')
    if run([host,'bad-expected'],'host-negative',True).returncode!=29:raise ValueError('Bad native oracle not rejected')
    verify()
    for name,value in headers.items():
        if sha(name)!=value:raise ValueError('Header drift '+name)
    report=dict(profile='original-apple-tty-temp-static-native-contract-v1',source_inputs_sha256=pins,
        headers_sha256=headers,dependency_records=records,commands=commands,target_archive=str(archive),
        original_units=base['original_units'],original_units_unchanged=True,original_generated_traps=list(TRAPS),
        target_missing_symbols=missing,target_duplicate_symbols=duplicates,closed_symbols=closed,newly_reachable_symbols=added,
        target=str(target),target_sha256=sha(target),static_inspection=inspected,live_symbol_owners=owners,
        target_executed=False,full_client_qualified=False,original_openssh_config_unchanged=True,
        native_asan_ubsan_pass=True,native_stdout=expected,host_io_signals_random_are_doubles=True,
        host_terminal_or_filesystem_access=False,provider_stubs=False,accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(output=str(out),manifest_sha256=sha(out/'manifest.json'),closed=closed,missing=len(missing),forced_static_undefined=0,native=expected),indent=2))
    return out,report


if __name__=='__main__':build()
