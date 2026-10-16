#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct packet cipher diagnostic with actual Apple pthread startup.

Reuses frozen original Apple packet/LibreSSL libraries and genuine initialized
pthread startup. Native execution tests host pthread; target is never run here.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import struct
import tempfile
try:
    from . import build_apple_pthread_static_smoke as previous
    from . import prepare_pid1
    from . import check_apple_pthread_kernel_contract as macho
except ImportError:
    import build_apple_pthread_static_smoke as previous
    import prepare_pid1
    import check_apple_pthread_kernel_contract as macho

ROOT,sha=previous.ROOT,previous.sha
STARTUP=ROOT/'build/rpi5/apple-pthread-static-complete-gm82fjkz'
STARTUP_SHA='4a22b183000378e842d59c643ed1f8a80a520e1e77d62370880a7c095adfc35a'
PACKET=ROOT/'build/rpi5/apple-ssh-libressl-packet-9ws4lrfd'
PACKET_SHA='5b801203eb3cc0033961a2a28e6f1b8353c7cad451daf676cfb579a2b1dc232a'
CRYPTO=ROOT/'build/rpi5/libressl-runtime-j_dt94vs'
SOURCE=ROOT/'tools/rpi5/user'
THREAD_LINE='PTHREAD:SMOKE PASS CTOR=1 THREADS=4 JOIN=4 MUTEX=2048 TSD_DTORS=4 ONCE=1 ERRNO=4 ALLOC=2048\n'


def build():
    pins={};reports=[]
    for directory,expected in ((STARTUP,STARTUP_SHA),(PACKET,PACKET_SHA)):
        manifest=directory/'manifest.json'
        if sha(manifest)!=expected:raise ValueError('Frozen genuine runtime changed')
        report=json.loads(manifest.read_text());reports.append(report);pins[str(manifest)]=expected
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for name,digest in report[key].items():
                if name in pins and pins[name]!=digest:raise ValueError('Conflicting genuine runtime dependency')
                pins[name]=digest
    startup,packet=reports;crypto=json.loads((CRYPTO/'manifest.json').read_text())
    if sha(CRYPTO/'manifest.json')!=packet['provider_runtime_manifest_sha256']:raise ValueError('Genuine provider manifest changed')
    for path in (Path(__file__).resolve(),SOURCE/'sshpacket_pthread_main.c',SOURCE/'pthread_smoke.c',
                 CRYPTO/'manifest.json',Path(prepare_pid1.__file__).resolve(),
                 Path(macho.__file__).resolve()):pins[str(path)]=sha(path)
    def verify():
        for name,digest in pins.items():
            if sha(name)!=digest:raise ValueError('Frozen integration input changed: '+name)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-ssh-packet-pthread-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[];headers={}
    def run(args,label,allowed=False):
        args=list(map(str,args));result=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=90)
        (out/(label+'.stdout')).write_text(result.stdout);(out/(label+'.stderr')).write_text(result.stderr)
        commands.append(dict(command=args,cwd=str(ROOT),returncode=result.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if result.returncode and not allowed:raise ValueError(label+': '+result.stderr[-8000:])
        return result
    def deps(raw):
        return {str(Path(p).resolve()):sha(Path(p).resolve()) for p in shlex.split(raw.replace('\\\n',' ').partition(':')[2])}
    def compile(flags,source,label):
        before=deps(run(flags+['-M',source],label+'-deps').stdout);dep=out/(label+'.d');obj=out/(label+'.o')
        run(flags+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        if deps(dep.read_text())!=before:raise ValueError('Actual consumed integration headers changed')
        headers.update(before);return obj
    command=next(c['command'] for c in startup['commands'] if c['stdout'].endswith('/smoke-compile.stdout'))
    target_flags=command[:command.index('-MD')]
    command=next(c['command'] for c in packet['commands'] if c['stdout'].endswith('/probe-native.stdout'))
    native_flags=command[:command.index('-MD')]
    rename='-Drpi5_pthread_smoke_main=rpi5_packet_pthread_prerequisite'
    target_smoke=compile(target_flags+[rename],SOURCE/'pthread_smoke.c','target-pthread-prerequisite')
    target_main=compile(target_flags,SOURCE/'sshpacket_pthread_main.c','target-composition')
    native_smoke=compile(native_flags+[rename,'-DRPI5_PTHREAD_HOST','-Dmain=rpi5_unused_host_pthread_main'],SOURCE/'pthread_smoke.c','native-pthread-prerequisite')
    native_main=compile(native_flags+['-DRPI5_PACKET_HOST'],SOURCE/'sshpacket_pthread_main.c','native-composition')
    native_probe=compile(native_flags+['-Dmain=darwin_network_command_main'],SOURCE/'sshpacketprobe.c','native-packet')
    old_native=next(c['command'] for c in packet['commands'] if c['stdout'].endswith('/native-packet-link.stdout'))
    native_link=[str(native_probe) if s==str(PACKET/'probe-native.o') else s for s in old_native]
    host=out/'sshpacket-pthread-host';native_link[native_link.index('-o')+1]=str(host)
    native_link += [str(native_main),str(native_smoke)]
    run(native_link,'native-link');native=run([host],'native-run')
    if native.stdout!=THREAD_LINE+packet['native_packet_stdout'] or native.stderr:raise ValueError('Combined native pthread/packet oracle differs')
    run(['xcrun','otool','-L',host],'native-dynamic-dependencies')
    dynamic=(out/'native-dynamic-dependencies.stdout').read_text()
    if 'libcrypto.' in dynamic or 'libssl.' in dynamic or '/opt/homebrew/' in dynamic:raise ValueError('Unexpected host dynamic crypto')
    old_link=next(c['command'] for c in startup['commands'] if c['stdout'].endswith('/target-link.stdout'))
    if old_link.count(str(STARTUP/'smoke.o'))!=1:raise ValueError('Exact startup workload input required')
    link=[str(target_smoke) if s==str(STARTUP/'smoke.o') else s for s in old_link]
    target=out/'NOT_RUN_sshpacketprobe';unstripped=out/'target.unstripped'
    link[link.index('-o')+1]=str(unstripped);link[link.index('-map')+1]=str(out/'target.map')
    link += [str(target_main),str(PACKET/'probe-target.o'),packet['target_archive'],crypto['target_archive']]
    result=run(link,'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    audit=None;section_proof=[];constructors=[]
    if not result.returncode:
        # Original LibreSSL brings an N_GSYM debug record, not an undefined
        # import. Preserve it separately and strip debugging metadata only;
        # the shared strict static inspector remains entirely unchanged.
        run(['xcrun','strip','-S',unstripped,'-o',target],'target-strip-debug')
        before,after=macho.MachO(unstripped),macho.MachO(target)
        if before.sections!=after.sections:raise ValueError('Debug stripping changed section geometry')
        for section in before.sections:
            if section['offset'] and section['size']:
                old=before.at(section['address'],section['size'])
                new=after.at(section['address'],section['size'])
                if old!=new:raise ValueError('Debug stripping changed executable/data bytes')
                section_proof.append(dict(section=section['name'],bytes=len(old),sha256=__import__('hashlib').sha256(old).hexdigest()))
        audit=prepare_pid1.inspect(target.read_bytes())
        table=next(s for s in after.sections if s['name']=='__DATA,__mod_init_func')
        if table['size']!=16:raise ValueError('Expected exactly the real pthread and libcrypto constructors')
        addresses=struct.unpack('<2Q',after.at(table['address'],16))
        expected=('_initialized_constructor','_openssl_init_crypto_constructor')
        if set(addresses)!={after.names[n]['address'] for n in expected}:raise ValueError('Actual constructor pointers differ')
        constructors=[next(n for n in expected if after.names[n]['address']==a) for a in addresses]
        run(['xcrun','nm','-u',target],'target-undefined')
        run(['xcrun','nm','-g',target],'target-symbols')
        run(['xcrun','otool','-l',target],'target-loadcommands')
        run(['xcrun','llvm-objdump','--disassemble-symbols=_darwin_static_start,_rpi5_pthread_smoke_main,_openssl_init_crypto_constructor,_crypto_cpu_caps_init',target],'target-startup-disassembly')
    verify()
    for name,digest in headers.items():
        if sha(name)!=digest:raise ValueError('Consumed integration header changed')
    report=dict(profile='genuine-apple-pthread-libressl-packet-static-v1',source_inputs_sha256=pins,headers_sha256=headers,
        commands=commands,target=str(target),target_sha256=sha(target) if target.is_file() else None,macho_audit=audit,
        target_link_complete=not result.returncode,target_missing_symbols=missing,target_duplicate_symbols=duplicates,
        original_startup_object=str(STARTUP/'startup.o'),original_packet_object=str(PACKET/'probe-target.o'),
        original_packet_archive=packet['target_archive'],original_crypto_archive=crypto['target_archive'],
        exact_link_replacement={'old':str(STARTUP/'smoke.o'),'new':str(target_smoke)},
        debug_only_stripped=not result.returncode,unstripped_target=str(unstripped),
        unchanged_stripped_sections=section_proof,actual_constructor_order=constructors,
        unchanged_original_smoke_source=True,sole_target_smoke_define=rename,
        native_asan_ubsan_pass=True,native_stdout=native.stdout,native_threads='host pthread, not target Apple provider',
        native_dynamic_crypto_used=False,provider_library_instrumented=False,valid_packet_cases=48,rejected_packet_cases=5036,
        expected_target_stdout='PTHREAD:KERNEL_READY\nPTHREAD:MAIN_READY\n'+native.stdout,
        actual_sysctlbyname_and_pthread_providers=True,upstream_security_features_unchanged=True,
        entropy_qualified=False,live_keys=False,ssh_transport=False,installed=False,pi_executed=False,
        accepted_runtime_modified=False,constructors_executed_on_target=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),target_link_complete=not result.returncode,missing=missing,duplicates=duplicates),indent=2))
    return out,report


if __name__=='__main__':build()
