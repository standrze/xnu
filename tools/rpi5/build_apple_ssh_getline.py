#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Qualify Apple OpenSSH's public getline compatibility provider offline."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_asprintf as prior

ROOT,sha=prior.ROOT,prior.sha
BASE=ROOT/'build/rpi5/apple-ssh-asprintf-ewo2v725'
BASE_SHA='20bf991bbe83b4f02308aa21217ddf1172b1ea79bc0114ad06784565236e8f28'
OPENSSH=prior.OPENSSH;COMMIT=prior.COMMIT
SOURCE=OPENSSH/'openssh/openbsd-compat/bsd-getline.c'
ANNOTATIONS=ROOT/'tools/rpi5/user/apple_getline_build.h'
HARNESS=ROOT/'tools/rpi5/tests/ssh_getline_host.c'
TEST=ROOT/'tools/rpi5/tests/test_apple_ssh_getline.py'
CLOSURE_TEST=prior.CLOSURE_TEST


def merge(*groups):
    result={}
    for group in groups:
        for name,digest in group.items():
            if name in result and result[name]!=digest:raise ValueError('Conflicting source pin '+name)
            result[name]=digest
    return result


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Exact genuine full37 predecessor required')
    relative='openssh/openbsd-compat/bsd-getline.c'
    if SOURCE.read_bytes()!=subprocess.check_output(['git','-C',OPENSSH,'show',COMMIT+':'+relative]):
        raise ValueError('Exact Apple-distributed OpenSSH source required')
    base=json.loads((BASE/'manifest.json').read_text())
    pins=merge({str(BASE/'manifest.json'):BASE_SHA},
        *[base[k] for k in ('source_inputs_sha256','headers_sha256','generated_sha256')])
    for path in (Path(__file__).resolve(),SOURCE,ANNOTATIONS,HARNESS,TEST,CLOSURE_TEST,
                 ROOT/'tools/rpi5/prepare_pid1.py'):
        pins=merge(pins,{str(path):sha(path)})
    tools={str(Path(subprocess.check_output(['xcrun','--find',n],text=True).strip()).resolve()):None
           for n in ('clang','ar','nm','ld','llvm-objdump')}
    tools[str(Path('/usr/bin/xcrun').resolve())]=None;tools={n:sha(n) for n in tools};pins=merge(pins,tools)
    def verify():
        for name,digest in pins.items():
            if sha(name)!=digest:raise ValueError('Source drift '+name)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-ssh-getline-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[];headers={};records={}
    def run(args,label,allowed=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=90)
        for stream in ('stdout','stderr'):(out/(label+'.'+stream)).write_text(getattr(r,stream))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-5000:])
        return r
    def deps(text):
        return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    def compile_(flags,path,label):
        before=deps(run([*flags,'-M',path],label+'-scan').stdout)
        dep,obj=out/(label+'.d'),out/(label+'.o');run([*flags,'-MD','-MF',dep,'-c',path,'-o',obj],label+'-compile')
        after=deps(dep.read_text())
        if before!=after:raise ValueError('Actual compiler dependency changed')
        headers.update(after);records[label]=dict(scanned_sha256=before,consumed_sha256=after)
        return obj
    old=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-asprintf-compile.stdout'))
    flags=old[:old.index('-DRPI5_APPLE_ASPRINTF=1')]+['-include',str(ANNOTATIONS),'-I',str(OPENSSH/'openssh')]
    native=[n for n in flags if n not in ('-ffreestanding','-mcpu=cortex-a76')]
    at=native.index('-target');del native[at:at+2]
    native+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=undefined']
    target_obj=compile_(flags,SOURCE,'target-getline');host_obj=compile_(native,SOURCE,'host-getline')
    caller=compile_(native,HARNESS,'host-caller')
    archive=out/'libapple-openssh-getline.a';run(['xcrun','ar','rcs',archive,target_obj],'archive')
    exports=run(['xcrun','nm','-gjU',target_obj],'target-exports').stdout.splitlines()
    if exports!=['_getline']:raise ValueError('Exact public getline API required')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    original_link=list(link);link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    linked=run([*link,archive],'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',linked.stderr,re.M)))
    duplicate=sorted(set(re.findall(r"duplicate symbol '([^']+)'",linked.stderr)))
    closed=sorted(set(base['target_missing_symbols'])-set(missing));added=sorted(set(missing)-set(base['target_missing_symbols']))
    if linked.returncode==0 or duplicate or closed!=['_getline'] or added:
        raise ValueError('Unexpected full-client getline closure delta '+repr((closed,added,duplicate)))
    contract=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/contract-link.stdout')))
    contract[contract.index('-o')+1]=str(out/'NOT_RUN_getline_contract');contract[contract.index('-map')+1]=str(out/'contract.map')
    contract += [str(archive),'-u','_getline'];run(contract,'contract-link')
    target=out/'NOT_RUN_getline_contract'
    if run(['xcrun','nm','-ju',target],'contract-undefined').stdout:raise ValueError('Forced target provider unresolved')
    inspection=prior.prior.prepare_pid1.inspect(target.read_bytes())
    mapping=(out/'contract.map').read_text();object_map={int(i):n for i,n in re.findall(r'^\[\s*(\d+)\]\s+(.+)$',mapping,re.M)};owner=None
    for line in mapping.splitlines():
        m=re.match(r'^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+_getline$',line)
        if m:owner=object_map[int(m[1])]
    if not (owner or '').startswith(str(archive)+'('):raise ValueError('getline not owned by new archive')
    host=out/'getline-host';run([*native,host_obj,caller,'-o',host],'host-link')
    good=run([host],'host-run');expected='APPLE_OPENSSH_GETLINE PASS API=1 LONG=9000 EOF=1 TARGET_NOT_RUN\n'
    if good.stdout!=expected or good.stderr:raise ValueError('Native oracle differs')
    if run([host,'negative'],'host-negative',True).returncode!=37:raise ValueError('Negative oracle accepted')
    verify()
    if any(sha(n)!=h for n,h in headers.items()):raise ValueError('Consumed header drift')
    report=dict(profile='apple-distributed-openssh-public-getline-v1',source_inputs_sha256=pins,
        headers_sha256=headers,generated_sha256={},tools_sha256=tools,dependency_records=records,commands=commands,
        apple_openssh_commit=COMMIT,original_source=str(SOURCE),original_source_unchanged=True,
        provider_selection_only=True,global_openssh_config_unchanged=True,uses_only_public_FILE_apis=True,
        FILE_internals_accessed=False,target_archive=str(archive),exported_apis=exports,live_symbol_owner=owner,
        static_inspection=inspection,original_full_client_link_command=original_link,
        target_missing_symbols=missing,target_duplicate_symbols=duplicate,closed_symbols=closed,
        newly_reachable_symbols=added,previous_missing_count=37,remaining_missing_count=len(missing),
        native_asan_ubsan_pass=True,native_stdout=good.stdout,native_host_libc=True,
        accepted_runtime_modified=False,provider_stubs=False,optional_features_removed=False,target_executed=False,
        full_client_qualified=False,filesystem_layout=['/usr/bin/ssh','/usr/sbin/sshd','/usr/libexec','/private/etc/ssh'],
        remaining_provider_groups=prior.prior.prior.categories(missing))
    report['generated_sha256']={str(p):sha(p) for p in out.rglob('*') if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(output=str(out),manifest_sha256=sha(out/'manifest.json'),closed=closed,
        added=added,remaining=len(missing),native_stdout=good.stdout),indent=2))
    return out,report


if __name__=='__main__':build()
