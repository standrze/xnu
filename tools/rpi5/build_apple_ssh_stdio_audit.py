#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserved whole-current-Apple stdio closure audit, never runtime admission.

The accepted runtime has older FILE internals. This diagnostic does NOT replace
them or qualify mixed FILE use merely because a link succeeds. Target binaries
are never executed; compile/link failures and exact dependencies are retained.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_locale_slice as source

ROOT, LIBC, sha = source.ROOT, source.LIBC, source.sha
BASE = ROOT/'build/rpi5/apple-clock-checked-acrq3vpm'
BASE_SHA = 'a2db7650517f1a30ba7374f9737ed18965c92fd4ec2126596e85febe193b7a52'
LOCALE = ROOT/'build/rpi5/apple-ssh-locale-slice-p7_8ertv'
UNITS = ('stdio/FreeBSD/asprintf.c', 'stdio/FreeBSD/vasprintf.c',
         'stdio/FreeBSD/xprintf.c', 'stdio/FreeBSD/vfprintf.c',
         'stdio/FreeBSD/fvwrite.c', 'stdio/FreeBSD/printf-pos.c')


def build():
    if sha(BASE/'manifest.json') != BASE_SHA:
        raise ValueError('Exact qualified software clock predecessor required')
    base = json.loads((BASE/'manifest.json').read_text())
    locale = json.loads((LOCALE/'manifest.json').read_text())
    pins = {str(BASE/'manifest.json'):BASE_SHA,
            str(LOCALE/'manifest.json'):sha(LOCALE/'manifest.json'),
            str(Path(__file__).resolve()):sha(__file__)}
    for parent in (base, locale):
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name,digest in parent[key].items():
                if name in pins and pins[name] != digest:raise ValueError('Pin conflict '+name)
                pins[name] = digest
    for name in UNITS:
        path = LIBC/name
        if path.read_bytes() != subprocess.check_output(['git','-C',LIBC,'show','HEAD:'+name]):
            raise ValueError('Whole original Apple source changed')
        pins[str(path)] = sha(path)
    for name,digest in pins.items():
        if sha(name) != digest:raise ValueError('Input drift '+name)
    out = Path(tempfile.mkdtemp(prefix='apple-ssh-stdio-audit-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True)
    commands,headers,records,failures,objects = [],{},{},{},{}

    def run(args,label):
        args = list(map(str,args))
        r = subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        for stream in ('stdout','stderr'):(out/(label+'.'+stream)).write_text(getattr(r,stream))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        return r

    def deps(text):
        return {str(Path(p).resolve()):sha(Path(p).resolve())
                for p in shlex.split(text.replace('\\\n',' ').partition(':')[2])}

    prior = next(c['command'] for c in locale['commands']
                 if c['stdout'].endswith('/target-strtoll-compile.stdout'))
    flags = prior[:prior.index('-MD')]
    for directory in (LIBC/'stdio',LIBC/'stdio/FreeBSD',LIBC/'gdtoa',LIBC/'gdtoa/FreeBSD',
                      ROOT/'build/rpi5/apple-dyld-headers-main-candidate-20261013/include'):
        flags += ['-I',str(directory)]
    for name in UNITS:
        path=LIBC/name;label=path.stem
        scan=run([*flags,'-M',path],label+'-scan')
        if scan.returncode:failures[name]='dependency-scan';continue
        before=deps(scan.stdout);headers.update(before)
        obj,dep=out/(label+'.o'),out/(label+'.d')
        compiled=run([*flags,'-MD','-MF',dep,'-c',path,'-o',obj],label+'-compile')
        if compiled.returncode:failures[name]='compile';continue
        actual=deps(dep.read_text())
        if before != actual:raise ValueError('Actual header closure changed')
        objects[name]=str(obj);records[name]=dict(scanned_sha256=before,consumed_sha256=actual)
        run(['xcrun','nm','-g',obj],label+'-symbols')
    archive=out/'UNQUALIFIED-current-stdio.a'
    if run(['xcrun','ar','rcs',archive,*objects.values()],'archive').returncode:raise ValueError('Archive failed')
    link=list(next(c['command'] for c in base['commands'] if c.get('label')=='target-link'))
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh')
    link[link.index('-map')+1]=str(out/'target.map')
    result=run([*link,archive],'target-link')
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    for name,digest in {**pins,**headers}.items():
        if sha(name) != digest:raise ValueError('Final input drift '+name)
    report=dict(profile='original-current-apple-stdio-closure-unqualified-v1',
        source_inputs_sha256=pins,headers_sha256=headers,dependency_records=records,
        commands=commands,original_units=list(UNITS),original_units_unchanged=True,
        objects=objects,compile_failures=failures,target_archive=str(archive),
        target_link_returncode=result.returncode,target_missing_symbols=missing,
        target_duplicate_symbols=duplicates,
        closed_symbols=sorted(set(base['target_missing_symbols'])-set(missing)),
        newly_reachable_symbols=sorted(set(missing)-set(base['target_missing_symbols'])),
        accepted_runtime_modified=False,target_executed=False,provider_stubs=False,
        mixed_stdio_abi_qualified=False,full_client_qualified=False,
        original_openssh_config_unchanged=True,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(package=str(out),compile_failures=failures,closed=report['closed_symbols'],
        new=report['newly_reachable_symbols'],duplicates=duplicates,remaining=len(missing)),indent=2))
    return out,report


if __name__=='__main__':build()
