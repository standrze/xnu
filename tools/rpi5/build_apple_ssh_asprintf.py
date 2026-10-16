#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Qualify Apple OpenSSH's public compatibility asprintf provider offline.

The unchanged 176-unit client configuration continues to describe Darwin's
native APIs.  Only this provider translation unit selects the fallback bodies
that Apple ships for platforms whose libc does not own them.  No target runs.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_dns_wire as prior

ROOT, sha = prior.ROOT, prior.sha
BASE = ROOT/'build/rpi5/apple-ssh-dns-wire-8gn7d87_'
BASE_SHA = '94cbbbb09610948dd30142aebcb5b1df07fe302c1c9bc3169c1cffb004926b19'
OPENSSH = ROOT/'build/rpi5/apple-openssh-candidate-20261013'
COMMIT = 'f386b2e948280f6ecac875329c0b56020821d558'
SOURCE = OPENSSH/'openssh/openbsd-compat/bsd-asprintf.c'
ANNOTATIONS = ROOT/'tools/rpi5/user/apple_current_command_build.h'
HARNESS = ROOT/'tools/rpi5/tests/ssh_asprintf_host.c'
TEST = ROOT/'tools/rpi5/tests/test_apple_ssh_asprintf.py'
CLOSURE_TEST = ROOT/'tools/rpi5/tests/test_apple_pthread_startup_contract.py'


def merge(*groups):
    result={}
    for group in groups:
        for name,digest in group.items():
            if name in result and result[name]!=digest:raise ValueError('Conflicting source pin '+name)
            result[name]=digest
    return result


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Exact genuine full39 predecessor required')
    if SOURCE.read_bytes()!=subprocess.check_output(['git','-C',OPENSSH,'show',COMMIT+':openssh/openbsd-compat/bsd-asprintf.c']):
        raise ValueError('Exact Apple-distributed OpenSSH source required')
    base=json.loads((BASE/'manifest.json').read_text())
    pins=merge({str(BASE/'manifest.json'):BASE_SHA},
        *[base[k] for k in ('source_inputs_sha256','headers_sha256','generated_sha256')])
    for path in (Path(__file__).resolve(),SOURCE,ANNOTATIONS,HARNESS,TEST,CLOSURE_TEST,
                 prior.prior.preceding.FLAGS,ROOT/'tools/rpi5/prepare_pid1.py'):
        pins=merge(pins,{str(path):sha(path)})
    tools={str(Path(subprocess.check_output(['xcrun','--find',n],text=True).strip()).resolve()):None
           for n in ('clang','ar','nm','ld','llvm-objdump')}
    tools[str(Path('/usr/bin/xcrun').resolve())]=None
    tools={n:sha(n) for n in tools};pins=merge(pins,tools)
    def verify():
        for name,digest in pins.items():
            if sha(name)!=digest:raise ValueError('Source drift '+name)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-ssh-asprintf-',dir=ROOT/'build/rpi5'))
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
        dep,obj=out/(label+'.d'),out/(label+'.o')
        run([*flags,'-MD','-MF',dep,'-c',path,'-o',obj],label+'-compile')
        after=deps(dep.read_text())
        if before!=after:raise ValueError('Actual compiler dependency changed')
        headers.update(after);records[label]=dict(scanned_sha256=before,consumed_sha256=after)
        return obj
    flags_doc=json.loads(prior.prior.preceding.FLAGS.read_text())
    template=next(c['command'] for c in flags_doc['commands'] if c['stdout'].endswith('/readpassphrase-compile.stdout'))
    flags=template[:template.index('-MD')]+['-DRPI5_APPLE_ASPRINTF=1','-include',str(ANNOTATIONS),'-I',str(OPENSSH/'openssh')]
    native=[n for n in flags if n not in ('-ffreestanding','-mcpu=cortex-a76')]
    at=native.index('-target');del native[at:at+2]
    native+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=undefined']
    target_obj=compile_(flags,SOURCE,'target-asprintf')
    host_obj=compile_(native,SOURCE,'host-asprintf')
    caller=compile_(native,HARNESS,'host-caller')
    archive=out/'libapple-openssh-asprintf.a';run(['xcrun','ar','rcs',archive,target_obj],'archive')
    exports=run(['xcrun','nm','-gjU',target_obj],'target-exports').stdout.splitlines()
    if sorted(exports)!=['_asprintf','_vasprintf']:raise ValueError('Exact two public APIs required')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    original_link=list(link);link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    linked=run([*link,archive],'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',linked.stderr,re.M)))
    duplicate=sorted(set(re.findall(r"duplicate symbol '([^']+)'",linked.stderr)))
    closed=sorted(set(base['target_missing_symbols'])-set(missing));added=sorted(set(missing)-set(base['target_missing_symbols']))
    if linked.returncode==0 or duplicate or closed!=['_asprintf','_vasprintf'] or added:
        raise ValueError('Unexpected full-client asprintf closure delta '+repr((closed,added,duplicate)))
    directory=json.loads((prior.prior.BASE/'manifest.json').read_text())
    contract=list(next(c['command'] for c in directory['commands'] if c['stdout'].endswith('/contract-link.stdout')))
    contract[contract.index('-o')+1]=str(out/'NOT_RUN_asprintf_contract');contract[contract.index('-map')+1]=str(out/'contract.map')
    contract += [str(archive),'-u','_asprintf','-u','_vasprintf'];run(contract,'contract-link')
    target=out/'NOT_RUN_asprintf_contract'
    if run(['xcrun','nm','-ju',target],'contract-undefined').stdout:raise ValueError('Forced target provider unresolved')
    inspection=prior.prepare_pid1.inspect(target.read_bytes())
    mapping=(out/'contract.map').read_text();object_map={int(i):n for i,n in re.findall(r'^\[\s*(\d+)\]\s+(.+)$',mapping,re.M)}
    owners={}
    for line in mapping.splitlines():
        m=re.match(r'^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+(\S+)$',line)
        if m and m[2] in exports:owners[m[2]]=object_map[int(m[1])]
    if any(not owners.get(n,'').startswith(str(archive)+'(') for n in exports):raise ValueError('Provider APIs not owned by new archive')
    host=out/'asprintf-host';run([*native,host_obj,caller,'-o',host],'host-link')
    good=run([host],'host-run')
    expected='APPLE_OPENSSH_ASPRINTF PASS APIS=2 REALLOC_PATH=1 TARGET_NOT_RUN\n'
    if good.stdout!=expected or good.stderr:raise ValueError('Native oracle differs')
    if run([host,'negative'],'host-negative',True).returncode!=37:raise ValueError('Negative oracle accepted')
    verify()
    if any(sha(n)!=h for n,h in headers.items()):raise ValueError('Consumed header drift')
    report=dict(profile='apple-distributed-openssh-public-asprintf-v1',source_inputs_sha256=pins,
        headers_sha256=headers,generated_sha256={},tools_sha256=tools,dependency_records=records,commands=commands,
        apple_openssh_commit=COMMIT,original_source=str(SOURCE),original_source_unchanged=True,
        provider_selection_only=True,global_openssh_config_unchanged=True,target_archive=str(archive),
        exported_apis=exports,live_symbol_owners=owners,static_inspection=inspection,
        original_full_client_link_command=original_link,target_missing_symbols=missing,target_duplicate_symbols=duplicate,
        closed_symbols=closed,newly_reachable_symbols=added,previous_missing_count=39,remaining_missing_count=len(missing),
        native_asan_ubsan_pass=True,native_stdout=good.stdout,native_host_libc=True,
        accepted_runtime_modified=False,provider_stubs=False,optional_features_removed=False,target_executed=False,
        full_client_qualified=False,filesystem_layout=['/usr/bin/ssh','/usr/sbin/sshd','/usr/libexec','/private/etc/ssh'],
        remaining_provider_groups=prior.prior.categories(missing))
    report['generated_sha256']={str(p):sha(p) for p in out.rglob('*') if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(output=str(out),manifest_sha256=sha(out/'manifest.json'),closed=closed,
        added=added,remaining=len(missing),native_stdout=good.stdout),indent=2))
    return out,report


if __name__=='__main__':build()
