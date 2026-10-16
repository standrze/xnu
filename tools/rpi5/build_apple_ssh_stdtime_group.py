#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Whole current Apple timezone family, without disabling notify or file paths.

Compile/link diagnostics are retained even if genuine service dependencies do
not close. No target, process, notification service or filesystem data is used.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import check_apple_ssh_spawn_contract as preceding

ROOT,LIBC,sha=preceding.ROOT,preceding.LIBC,preceding.sha
BASE=ROOT/'build/rpi5/apple-ssh-spawn-contract-o1r3nnno'
BASE_SHA='08e28e13a755e593ce315df0b0454b53339455675aedd81b05006ef6f85b09eb'
UNITS=('stdtime/FreeBSD/localtime.c','stdtime/FreeBSD/asctime.c',
       'stdtime/timezone_unix03.c','stdtime/FreeBSD/difftime.c',
       'stdtime/FreeBSD/strftime.c','stdtime/FreeBSD/timelocal.c')


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen41 prerequisite differs')
    base=json.loads((BASE/'manifest.json').read_text())
    pins={str(BASE/'manifest.json'):BASE_SHA,str(Path(__file__).resolve()):sha(__file__)}
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
        for name,h in base[key].items():
            if name in pins and pins[name]!=h:raise ValueError('Conflicting source pin')
            pins[name]=h
    for name in (*UNITS,'Platforms/macosx/Makefile.inc','xcodescripts/generate_features.pl'):
        path=LIBC/name;pins[str(path)]=sha(path)
        if path.read_bytes()!=subprocess.check_output(['git','-C',LIBC,'show','HEAD:'+name]):
            raise ValueError('Whole original Apple source differs')
    def verify():
        for name,h in pins.items():
            if sha(name)!=h:raise ValueError('Frozen source drift '+name)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-ssh-stdtime-group-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True)
    commands=[];headers={};records={};objects={};failures={}
    def run(args,label):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=90)
        for stream in ('stdout','stderr'):(out/(label+'.'+stream)).write_text(getattr(r,stream))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        return r
    def deps(text):
        return {str(Path(p).resolve()):sha(Path(p).resolve()) for p in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    command=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/system-compile.stdout'))
    flags=command[:command.index('-MD')]
    flags=[x for x in flags if x!='-DVARIANT_CANCELABLE']
    for name in UNITS:
        source=LIBC/name;label=source.stem
        scanned=run([*flags,'-M',source],label+'-scan')
        if scanned.returncode:failures[name]='scan';continue
        before=deps(scanned.stdout);headers.update(before)
        obj,dep=out/(label+'.o'),out/(label+'.d')
        result=run([*flags,'-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        after=deps(dep.read_text()) if dep.is_file() else {}
        records[label]=dict(scanned_sha256=before,consumed_sha256=after)
        if result.returncode:failures[name]='compile';continue
        if before!=after:raise ValueError('Consumed headers differ from pre-scan')
        objects[name]=str(obj);run(['xcrun','nm','-g',obj],label+'-symbols')
    feature=next((p for p in headers if p.endswith('/arm64/libc-features.h')),None)
    if not feature or '#define NOTIFY_TZ 1' not in Path(feature).read_text():raise ValueError('Normal notification feature must remain enabled')
    archive=out/'UNQUALIFIED-apple-stdtime.a'
    if run(['xcrun','ar','rcs',archive,*objects.values()],'archive').returncode:raise ValueError('Archive failed')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    result=run([*link,archive],'target-link')
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicate=sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    verify()
    for path,h in headers.items():
        if sha(path)!=h:raise ValueError('Header drift')
    m=dict(profile='whole-current-apple-stdtime-normal-notify-inventory-v1',source_inputs_sha256=pins,
        headers_sha256=headers,dependency_records=records,commands=commands,objects=objects,compile_failures=failures,
        original_units=list(UNITS),original_units_unchanged=True,notify_tz_enabled=True,target_archive=str(archive),
        target_missing_symbols=missing,target_duplicate_symbols=duplicate,
        closed_symbols=sorted(set(base['target_missing_symbols'])-set(missing)),
        newly_reachable_symbols=sorted(set(missing)-set(base['target_missing_symbols'])),
        native_contract_passed=False,target_executed=False,provider_stubs=False,full_client_qualified=False,
        accepted_runtime_modified=False,original_openssh_config_unchanged=True,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),manifest_sha256=sha(out/'manifest.json'),failures=failures,
        closed=m['closed_symbols'],new=m['newly_reachable_symbols'],remaining=len(missing),duplicates=duplicate),indent=2))
    return out,m


if __name__=='__main__':build()
