#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Project getentropy adapter + original LibreSSL, private offline target only."""
import json
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile
from tools.rpi5 import build_apple_entropy_probe as prior

ROOT,sha=prior.ROOT,prior.sha
BASE=ROOT/'build/rpi5/apple-entropy-api-x4zxvaug'
BASE_SHA='b488248ba8522edfd445d5b4d36bc0b260feef92171451d41d2af1dedc842c47'
CRYPTO=ROOT/'build/rpi5/libressl-runtime-j_dt94vs'
CRYPTO_SHA='1aeae7b5aba4491af5c7dd25199919ed5336c4bc16580e3533077fd06b5b5231'
ADAPTER=ROOT/'tools/rpi5/user/kernel_entropy_arc4random.c'
WORKLOAD=ROOT/'tools/rpi5/user/kernel_entropy_rand_probe.c'
FIXTURE=ROOT/'tools/rpi5/tests/kernel_entropy_arc4random_contract.c'


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA or sha(CRYPTO/'manifest.json')!=CRYPTO_SHA:
        raise ValueError('Frozen prerequisite changed')
    base=json.loads((BASE/'manifest.json').read_text());crypto=json.loads((CRYPTO/'manifest.json').read_text())
    pins={str(BASE/'manifest.json'):BASE_SHA,str(CRYPTO/'manifest.json'):CRYPTO_SHA}
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):pins.update(base[key])
    for p in (ADAPTER,WORKLOAD,FIXTURE,Path(__file__).resolve(),CRYPTO/'native/compile_commands.json'):
        pins[str(p)]=sha(p)
    def verify():
        for name,digest in pins.items():
            if sha(name)!=digest:raise ValueError('Frozen input drift: '+name)
    verify();out=Path(tempfile.mkdtemp(prefix='kernel-entropy-rand-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[];headers={}
    def run(args,label):
        args=list(map(str,args));result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60)
        (out/(label+'.stdout')).write_text(result.stdout);(out/(label+'.stderr')).write_text(result.stderr)
        commands.append(dict(command=args,cwd=str(ROOT),returncode=result.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if result.returncode:raise ValueError(label+': '+result.stderr[-6000:])
        return result
    def deps(raw):
        return {str(Path(p).resolve()):sha(Path(p).resolve()) for p in shlex.split(raw.replace('\\\n',' ').partition(':')[2])}
    def compile(flags,source,label):
        before=deps(run(flags+['-M',source],label+'-deps').stdout)
        obj=out/(label+'.o');dep=out/(label+'.d')
        run(flags+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        if deps(dep.read_text())!=before:raise ValueError('Actual consumed header mismatch')
        headers.update(before);return obj
    command=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/source-compile.stdout'))
    flags=command[:command.index('-MD')]
    source=Path(crypto['source']);rand_source=source/'crypto/rand/rand_lib.c';pins[str(rand_source)]=sha(rand_source)
    include=['-I'+str(source/'include'),'-I'+str(CRYPTO/'native/include')]
    adapter=compile(flags,ADAPTER,'kernel-entropy-adapter')
    workload=compile(flags+include,WORKLOAD,'randprobe')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/rng-force-link.stdout')))
    if link.count(str(BASE/'entropyprobe.o'))!=1:raise ValueError('Exact workload replacement required')
    link[link.index(str(BASE/'entropyprobe.o'))]=str(workload)
    link[link.index('-o')+1]=str(out/'target.unstripped');link[link.index('-map')+1]=str(out/'target.map')
    link+=[str(adapter)];run(link,'target-link')
    target=out/'NOT_RUN_kernel_randprobe'
    run(['xcrun','strip','-S',out/'target.unstripped','-o',target],'strip-debug')
    old,new=prior.previous.macho.MachO(out/'target.unstripped'),prior.previous.macho.MachO(target)
    if old.sections!=new.sections:raise ValueError('Debug strip geometry changed')
    for section in new.sections:
        if section['offset'] and section['size'] and old.at(section['address'],section['size'])!=new.at(section['address'],section['size']):
            raise ValueError('Debug strip loadable bytes changed')
    ct=next(s for s in new.sections if s['name']=='__DATA,__mod_init_func')
    addresses=struct.unpack('<'+'Q'*(ct['size']//8),new.at(ct['address'],ct['size']))
    names=['_initialized_constructor','_openssl_init_crypto_constructor']
    ctors=[next(n for n in names if new.names.get(n,{}).get('address')==a) for a in addresses]
    # RAND's original syscall-delegation TU does not reference the CPU-capability
    # initializer. Unlike packet ciphers, it pulls no libcrypto constructor.
    if ctors!=['_initialized_constructor']:raise ValueError('Actual live constructor order changed')
    if run(['xcrun','nm','-ju',target],'target-undefined').stdout:raise ValueError('Target imports remain')
    run(['xcrun','nm','-ju',adapter],'adapter-imports')
    run(['xcrun','llvm-objdump','--disassemble-symbols=_arc4random_buf,_random_request_failed,_getentropy,__exit,_RAND_bytes,_rpi5_pthread_smoke_main',target],'target-contract')
    run(['xcrun','otool','-rv',adapter],'adapter-relocations')
    run(['xcrun','nm','-m',adapter],'adapter-symbols')
    # Host tests execute the actual adapter and original RAND body against an
    # explicitly named getentropy double, never a host random implementation.
    native=['xcrun','clang','-std=c11','-O1','-Wall','-Wextra','-Werror','-fsanitize=address,undefined']
    host_adapter=compile(native+['-Darc4random_buf=fixture_arc4random_buf','-Dgetentropy=fixture_getentropy'],ADAPTER,'host-adapter')
    row=next(c for c in json.loads((CRYPTO/'native/compile_commands.json').read_text()) if c['file']==str(rand_source))
    native_rand=shlex.split(row['command']);native_rand=native_rand[:native_rand.index('-o')]
    native_rand+=['-fsanitize=address,undefined','-Darc4random_buf=fixture_arc4random_buf']
    host_rand=compile(native_rand,rand_source,'host-original-rand')
    host_fixture=compile(native+include,FIXTURE,'host-contract')
    run(native+[host_adapter,host_rand,host_fixture,'-o',out/'host-contract'],'host-link')
    native_output=run([out/'host-contract'],'host-run').stdout
    verify()
    for name,digest in headers.items():
        if sha(name)!=digest:raise ValueError('Header drift')
    report=dict(profile='project-stateless-getentropy-arc4random-buf-v1',source_inputs_sha256=pins,
        headers_sha256=headers,commands=commands,target=str(target),target_sha256=sha(target),
        target_link_complete=True,target_missing_symbols=[],
        macho_audit=prior.previous.prepare_pid1.inspect(target.read_bytes()),actual_constructor_order=ctors,
        original_startup_object=base['original_startup_object'],original_crypto_archive=crypto['target_archive'],
        exact_link_replacement={'old':str(BASE/'entropyprobe.o'),'new':str(workload)},added_adapter_object=str(adapter),
        original_rand_source=str(rand_source),native_stdout=native_output,native_syscall_is_double=True,
        adapter_is_project_code=True,apple_corecrypto_implementation=False,rc4_fallback=False,
        mutable_adapter_state=False,cached_generator=False,adapter_heap=False,adapter_lock=False,
        zero_length_null_is_noop=True,overflow_rejected=True,chunk_limit=256,any_syscall_error_is_fatal=True,
        fatal_exit_status=127,getentropy_syscall=500,exit_syscall=1,
        entropy_qualified=False,firmware_attestation=False,live_keys=False,raw_random_or_seed_output=False,
        installed=False,pi_executed=False,accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'package':str(out),'target_sha256':sha(target),'native_stdout':native_output},indent=2))
    return out,report


if __name__=='__main__':build()
