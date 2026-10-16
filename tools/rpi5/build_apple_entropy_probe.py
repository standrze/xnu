#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Private real-syscall/counter diagnostic; never executes its Pi target."""
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_packet_pthread as previous

ROOT,sha=previous.ROOT,previous.sha
BASE=ROOT/'build/rpi5/apple-ssh-packet-pthread-iabcb1gr'
BASE_SHA='b1ca5bec6b327284fd8df985753ac5a10bcd324295ab981c946cc7ebb4d3cef3'
SOURCE=ROOT/'tools/rpi5/user/entropyprobe.c'


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen packet/startup changed')
    base=json.loads((BASE/'manifest.json').read_text())
    pins={str(BASE/'manifest.json'):BASE_SHA}
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
        for name,value in base[key].items():
            if name in pins and pins[name]!=value:raise ValueError('Conflicting inherited input')
            pins[name]=value
    for p in (Path(__file__).resolve(),SOURCE,ROOT/'bsd/dev/random/randomdev.c',
              ROOT/'bsd/crypto/entropy/entropy_sysctl.c',ROOT/'bsd/kern/syscalls.master'):
        pins[str(p)]=sha(p)
    def verify():
        for name,value in pins.items():
            if sha(name)!=value:raise ValueError('Frozen input drift: '+name)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-entropy-api-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[]
    def run(args,label,allowed=False):
        args=list(map(str,args));result=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=60)
        (out/(label+'.stdout')).write_text(result.stdout);(out/(label+'.stderr')).write_text(result.stderr)
        commands.append(dict(command=args,cwd=str(ROOT),returncode=result.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if result.returncode and not allowed:raise ValueError(label+': '+result.stderr[-6000:])
        return result
    def deps(raw):
        return {str(Path(p).resolve()):sha(Path(p).resolve()) for p in shlex.split(raw.replace('\\\n',' ').partition(':')[2])}
    old=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-composition-compile.stdout'))
    flags=old[:old.index('-MD')]
    before=deps(run(flags+['-M',SOURCE],'source-deps').stdout)
    obj=out/'entropyprobe.o';dep=out/'entropyprobe.d'
    run(flags+['-MD','-MF',dep,'-c',SOURCE,'-o',obj],'source-compile')
    if deps(dep.read_text())!=before:raise ValueError('Actual consumed headers differ')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    if link.count(str(BASE/'target-composition.o'))!=1:raise ValueError('Exact composition object required')
    link[link.index(str(BASE/'target-composition.o'))]=str(obj)
    removed=[base[k] for k in ('original_packet_object','original_packet_archive','original_crypto_archive')]
    if any(link.count(p)!=1 for p in removed):raise ValueError('Exact unused packet inputs required')
    link=[p for p in link if p not in removed]
    target=out/'NOT_RUN_entropyprobe';unstripped=out/'target.unstripped'
    link[link.index('-o')+1]=str(unstripped);link[link.index('-map')+1]=str(out/'target.map')
    result=run(link,'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    if result.returncode:raise ValueError('Actual diagnostic link failed: '+repr(missing))
    run(['xcrun','strip','-S',unstripped,'-o',target],'strip-debug')
    before_image,after=previous.macho.MachO(unstripped),previous.macho.MachO(target)
    if before_image.sections!=after.sections:raise ValueError('Debug strip geometry changed')
    for s in after.sections:
        if s['offset'] and s['size'] and before_image.at(s['address'],s['size'])!=after.at(s['address'],s['size']):
            raise ValueError('Debug strip changes loadable bytes')
    table=next(s for s in after.sections if s['name']=='__DATA,__mod_init_func')
    addresses=struct.unpack('<'+'Q'*(table['size']//8),after.at(table['address'],table['size']))
    ctors=[next(n for n in ('_initialized_constructor','_openssl_init_crypto_constructor') if after.names.get(n,{}).get('address')==a) for a in addresses]
    if ctors!=['_initialized_constructor']:raise ValueError('Only genuine pthread constructor should remain reachable')
    audit=previous.prepare_pid1.inspect(target.read_bytes())
    if run(['xcrun','nm','-ju',target],'undefined').stdout:raise ValueError('Unresolved target imports')
    run(['xcrun','llvm-objdump','--disassemble-symbols=_getentropy,_sysctlbyname,_darwin_static_start,_rpi5_pthread_smoke_main',target],'target-contract')
    # Link-only evidence for the next unresolved genuine RNG service. Never run
    # the failed/partial image, and do not change LibreSSL feature detection.
    rng=list(link);rng[rng.index('-o')+1]=str(out/'NOT_RUN_rng_force_link')
    rng[rng.index('-map')+1]=str(out/'rng-force.map')
    rng+=['-u','_RAND_bytes',base['original_crypto_archive']]
    forced=run(rng,'rng-force-link',True)
    rng_missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',forced.stderr,re.M)))
    if not forced.returncode or rng_missing!=['_arc4random_buf']:raise ValueError('RNG closure changed: '+repr(rng_missing))
    verify()
    for n,h in before.items():
        if sha(n)!=h:raise ValueError('Consumed header drift')
    report=dict(profile='genuine-apple-getentropy-counter-diagnostic-v1',source_inputs_sha256=pins,
        headers_sha256=before,commands=commands,target=str(target),target_sha256=sha(target),
        target_link_complete=True,target_missing_symbols=[],macho_audit=audit,
        actual_constructor_order=ctors,original_startup_object=base['original_startup_object'],
        exact_link_replacement={'old':str(BASE/'target-composition.o'),'new':str(obj)},
        removed_unused_packet_inputs=removed,
        getentropy_syscall=500,getentropy_requests=[0,1,256,257],invalid_destination_bytes=1,
        expected_oversize_errno='EINVAL',expected_bad_destination_errno='EFAULT',
        counter_queries=10,raw_random_or_seed_output=False,random_output_hashing=False,
        health_counters_are_quality_proof=False,firmware_attestation=False,
        forced_rand_bytes_missing=rng_missing,entropy_qualified=False,live_keys=False,
        installed=False,pi_executed=False,accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'package':str(out),'target_sha256':report['target_sha256'],'rng_missing':rng_missing},indent=2))
    return out,report


if __name__=='__main__':build()
