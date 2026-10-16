#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original current Apple map/set prerequisite for genuine notify registries.

This does not define notify APIs or make the original client/service available.
Whole source and template units stay unchanged; no accepted archive is replaced.
"""
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_environment as prior
from tools.rpi5 import prepare_pid1

ROOT,sha,LIBC=prior.ROOT,prior.sha,prior.LIBC
BASE=ROOT/'build/rpi5/apple-ssh-environment-id9imlth'
BASE_SHA='ba01dc58574d6349761bd648314c8341898ffd2ef46b1ef54952ecf71fa667f5'
BLOCKS=ROOT/'build/rpi5/apple-blocks-runtime-ga1_x5sg'
BLOCKS_SHA='447d6841cc058fd09ad8ef39ed9e338db364c88850ad207b7df4e56e709f49f5'
HARNESS=ROOT/'tools/rpi5/tests/apple_notify_collections_host.c'
UNITS=('collections_map.c','collections_set.c')
OPERATIONS=('init','destroy','insert','find','delete','clear','count','foreach')
FORCE=tuple('_os_map_'+kind+'_'+op for kind in ('str','32','64','128') for op in OPERATIONS)+('_os_map_str_entry',)+tuple('_os_set_'+kind+'_ptr_'+op for kind in ('str','32','64') for op in OPERATIONS)
EXPECTED='APPLE_COLLECTIONS PASS MAPS=4 SETS=3 ELEMENTS=1024 COLLISION_SET=1024 ALLOCATION_ABORTS=4 ORIGINAL_BLOCKS HOST_ONLY\n'


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA or sha(BLOCKS/'manifest.json')!=BLOCKS_SHA:
        raise ValueError('Frozen environment/Blocks prerequisite differs')
    base=json.loads((BASE/'manifest.json').read_text());blocks=json.loads((BLOCKS/'manifest.json').read_text())
    pins={str(BASE/'manifest.json'):BASE_SHA,str(BLOCKS/'manifest.json'):BLOCKS_SHA,
          str(Path(__file__).resolve()):sha(__file__),str(HARNESS):sha(HARNESS)}
    for m in (base,blocks):
        for group in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for n,h in m[group].items():
                if n in pins and pins[n]!=h:raise ValueError('Source pin conflict')
                pins[n]=h
    original=sorted(p for p in (LIBC/'collections').rglob('*') if p.is_file())
    for p in original:
        if p.read_bytes()!=subprocess.check_output(['git','-C',LIBC,'show','71bbe350ab79eef58113991d817ccc6165061a64:'+str(p.relative_to(LIBC))]):
            raise ValueError('Whole original collection source differs')
        pins[str(p)]=sha(p)
    def verify():
        for n,h in pins.items():
            if sha(n)!=h:raise ValueError('Pinned input drift '+n)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-notify-collections-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[];headers={};records={}
    include=out/'include/os';include.mkdir(parents=True)
    for p in (LIBC/'collections/PublicHeader').iterdir():shutil.copyfile(p,include/p.name)
    def run(args,label,allowed=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=90)
        for stream in ('stdout','stderr'):(out/(label+'.'+stream)).write_text(getattr(r,stream))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-6000:])
        return r
    def deps(text):return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    def compile_(flags,p,label):
        scanned=deps(run([*flags,'-M',p],label+'-scan').stdout)
        obj=out/(label+'.o');dep=out/(label+'.d')
        run([*flags,'-MD','-MF',dep,'-c',p,'-o',obj],label+'-compile')
        consumed=deps(dep.read_text())
        if scanned!=consumed:raise ValueError('Actual compile header closure differs')
        headers.update(scanned);records[label]=dict(scanned_sha256=scanned,consumed_sha256=consumed)
        return obj
    flags=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/setenv-compile.stdout'))
    flags=flags[:flags.index('-MD')]+['-fblocks','-I'+str(out/'include'),'-I'+str(ROOT/'libkern')]
    target=[compile_(flags,LIBC/'collections/Source'/n,'target-'+Path(n).stem) for n in UNITS]
    archive=out/'libapple-current-collections.a';run(['xcrun','ar','rcs',archive,*target],'archive')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    r=run([*link,archive],'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',r.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",r.stderr)))
    if missing!=base['target_missing_symbols'] or duplicates:raise ValueError('Unexpected client link delta')
    contract=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/contract-link.stdout')))
    target_path=out/'NOT_RUN_collections_contract';mapping=out/'contract.map'
    contract[contract.index('-o')+1]=str(target_path);contract[contract.index('-map')+1]=str(mapping)
    contract+=[str(archive),blocks['target_archive']]
    for name in FORCE:contract+=['-u',name]
    run(contract,'contract-link')
    if run(['xcrun','nm','-ju',target_path],'contract-undefined').stdout:raise ValueError('Static imports remain')
    inspected=prepare_pid1.inspect(target_path.read_bytes());text=mapping.read_text()
    table={int(n):p for n,p in re.findall(r'(?m)^\[\s*(\d+)\]\s+(.+)$',text)};owners={}
    for name in (*FORCE,'__NSConcreteStackBlock','___assert_rtn','_calloc','_free'):
        hits=re.findall(r'(?m)^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+'+re.escape(name)+'$',text)
        if len(hits)!=1:raise ValueError('Exact live owner missing '+name)
        owners[name]=table[int(hits[0])]
    if any(not owners[name].startswith(str(archive)+'(') for name in FORCE):
        raise ValueError('Original collection owner was not selected')
    if owners['__NSConcreteStackBlock']!=blocks['target_archive']+'(target-data.o)':
        raise ValueError('Genuine Blocks stack owner missing')
    if any(v in text for v in ('fixture_','__asan','__ubsan')):raise ValueError('Test provider in target')
    native=[n for n in flags if n not in ('-ffreestanding','-mcpu=cortex-a76')]
    i=native.index('-target');del native[i:i+2]
    native+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=undefined']
    objects=[compile_(native+['-Dcalloc=fixture_calloc'],LIBC/'collections/Source'/n,'host-'+Path(n).stem) for n in UNITS]
    caller=compile_(native,HARNESS,'host-caller');host=out/'collections-host'
    # The same unchanged original Blocks source objects qualified in the prior
    # package; this is not the host libSystem implementation of collection ops.
    block_objects=[BLOCKS/'native-runtime.o',BLOCKS/'native-data.o']
    run([*native,*objects,caller,*block_objects,'-Wl,-map,'+str(out/'host.map'),'-o',host],'host-link')
    result=run([host],'host-run')
    if result.stdout!=EXPECTED or result.stderr:raise ValueError('Original collection native oracle differs')
    if run([host,'bad-oracle'],'host-negative',True).returncode!=37:raise ValueError('Bad expectation accepted')
    verify()
    for n,h in headers.items():
        if sha(n)!=h:raise ValueError('Header drift')
    m=dict(profile='original-apple-collections-notify-prerequisite-v1',source_inputs_sha256=pins,
        headers_sha256=headers,dependency_records=records,commands=commands,target_archive=str(archive),
        whole_original_units=list(UNITS),original_source_modified=False,forced_apis=list(FORCE),
        target=str(target_path),target_sha256=sha(target_path),static_inspection=inspected,live_symbol_owners=owners,
        target_missing_symbols=missing,target_duplicate_symbols=duplicates,closed_symbols=[],newly_reachable_symbols=[],
        notification_api_provider_created=False,notification_service_executed=False,client_import_delta=0,
        prior_qualified_client_import_count=41,stdtime_branch_import_count=len(missing),full_client_qualified=False,
        native_asan_ubsan_pass=True,native_stdout=result.stdout,native_fault_allocator_only=True,
        native_blocks_original_objects=True,target_executed=False,accepted_runtime_modified=False,
        collections_require_external_serialization=True,allocation_failure_contract='original assertion abort; no recoverable error fabricated',
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),manifest_sha256=sha(out/'manifest.json'),forced=len(FORCE),remaining=len(missing)),indent=2))
    return out,m


if __name__=='__main__':build()
