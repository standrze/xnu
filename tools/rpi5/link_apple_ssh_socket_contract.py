#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Force all original socket emitters live with real pthread/cerror; never run."""
import json
from pathlib import Path
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_socket_syscalls as sockets
from tools.rpi5 import check_apple_pthread_kernel_contract as macho
from tools.rpi5 import prepare_pid1

ROOT,sha=sockets.ROOT,sockets.sha
BASE=ROOT/'build/rpi5/apple-ssh-socket-syscalls-n4wc59z7'
BASE_SHA='f036194116d2048dc4102f3728191b7bd6f449cf95c5f58c78be9785662b677b'
RUNTIME=ROOT/'build/rpi5/kernel-entropy-rand-hfrb7y67'


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Socket receipt changed')
    base=json.loads((BASE/'manifest.json').read_text());pins={str(BASE/'manifest.json'):BASE_SHA}
    for k in ('source_inputs_sha256','headers_sha256','generated_sha256'):pins.update(base[k])
    for p in (Path(__file__).resolve(),Path(macho.__file__).resolve(),Path(prepare_pid1.__file__).resolve()):pins[str(p)]=sha(p)
    def verify():
        for n,h in pins.items():
            if sha(n)!=h:raise ValueError('Pinned input changed: '+n)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-ssh-socket-contract-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[]
    def run(args,label):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60)
        for k in ('stdout','stderr'):(out/(label+'.'+k)).write_text(getattr(r,k))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode:raise ValueError(label+': '+r.stderr)
        return r
    runtime=json.loads((RUNTIME/'manifest.json').read_text())
    link=list(next(c['command'] for c in runtime['commands'] if c['stdout'].endswith('/target-link.stdout')))
    unstripped=out/'target.unstripped';target=out/'NOT_RUN_forced_socket_contract'
    link[link.index('-o')+1]=str(unstripped);link[link.index('-map')+1]=str(out/'target.map')
    for n in sockets.CALLS:link+=['-u','_'+n]
    link.append(base['target_archive']);run(link,'target-link')
    run(['xcrun','strip','-S',unstripped,'-o',target],'strip-debug')
    a,b=macho.MachO(unstripped),macho.MachO(target)
    if a.sections!=b.sections:raise ValueError('Debug strip geometry changed')
    for s in b.sections:
        if s['offset'] and s['size'] and a.at(s['address'],s['size'])!=b.at(s['address'],s['size']):
            raise ValueError('Loaded section bytes changed')
    audit=prepare_pid1.inspect(target.read_bytes())
    if run(['xcrun','nm','-ju',target],'undefined').stdout:raise ValueError('Undefined actual forced provider')
    names=['_'+n for n in sockets.CALLS]+['_cerror','_cerror_nocancel','__pthread_exit_if_canceled']
    if any(n not in b.names for n in names):raise ValueError('Missing executable provider')
    run(['xcrun','llvm-objdump','--disassemble-symbols='+','.join(names),target],'actual-provider-contract')
    verify()
    report=dict(profile='original-socket-emitter-real-pthread-error-linked-contract-v1',
        source_inputs_sha256=pins,commands=commands,target=str(target),target_sha256=sha(target),
        macho_audit=audit,target_missing_symbols=[],target_link_complete=True,
        original_error_cancellation_provider_live=True,forced_public_symbols=names,
        main_is_frozen_rand_diagnostic=True,not_full_client=True,
        target_executed=False,host_sockets_executed=False,live_keys=False,
        entropy_qualified=False,accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),target_sha256=report['target_sha256'],target_executed=False)))
    return out,report


if __name__=='__main__':build()
