#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Whole original Apple process-launch group, separate from accepted runtime.

No programs/targets are launched. Full current OpenSSH inputs and configuration
are inherited byte-for-byte. Compile/link evidence alone is not qualification.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_stdio_audit as old

ROOT, LIBC, sha = old.ROOT, old.LIBC, old.sha
BASE = ROOT/'build/rpi5/apple-ssh-tty-temp-contract-bicg15ou'
BASE_SHA = '9f55971e5feb4d9b25a48419a279f19ff9c2aa5d18003eb79dd1d3abb92552df'
FLAGS = ROOT/'build/rpi5/apple-ssh-tty-temp-bm2n0nkz/manifest.json'
UNITS = (LIBC/'stdlib/FreeBSD/system.c', LIBC/'gen/FreeBSD/popen.c',
         ROOT/'libsyscall/wrappers/spawn/posix_spawn.c')
HEADER_COPIES = {
    'spawn.h': 'libsyscall/wrappers/spawn/spawn.h',
    'spawn_private.h': 'libsyscall/wrappers/spawn/spawn_private.h',
    'sys/spawn_internal.h': 'bsd/sys/spawn_internal.h',
    'sys/spawn.h': 'bsd/sys/spawn.h',
    'sys/process_policy.h': 'bsd/sys/process_policy.h',
    'sys/kern_memorystatus.h': 'bsd/sys/kern_memorystatus.h',
    'sys/reason.h': 'bsd/sys/reason.h',
    'mach/coalition.h': 'osfmk/mach/coalition.h',
    'mach/mach_param.h': 'osfmk/mach/mach_param.h',
}


def build():
    if sha(BASE/'manifest.json') != BASE_SHA: raise ValueError('Exact frozen42 predecessor required')
    base = json.loads((BASE/'manifest.json').read_text())
    pins = {str(BASE/'manifest.json'): BASE_SHA, str(Path(__file__).resolve()): sha(__file__)}
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
        for name,digest in base[key].items():
            if name in pins and pins[name] != digest: raise ValueError('Conflicting original pin')
            pins[name] = digest
    for path in (*UNITS, *[ROOT/n for n in HEADER_COPIES.values()], FLAGS):
        pins[str(path)] = sha(path)
    for path in UNITS:
        repository = LIBC if path.is_relative_to(LIBC) else ROOT
        if subprocess.check_output(['git','-C',repository,'show','HEAD:'+str(path.relative_to(repository))]) != path.read_bytes():
            raise ValueError('Whole original source changed: '+str(path))
    def verify():
        for name,digest in pins.items():
            if sha(name) != digest: raise ValueError('Input drift '+name)
    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-ssh-spawn-group-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True)
    include = out/'include'
    for name,source in HEADER_COPIES.items():
        target = include/name; target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((ROOT/source).read_bytes())
    commands,headers,records,objects,failures = [],{},{},{},{}
    def run(args,label):
        args = list(map(str,args))
        r = subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=90)
        for stream in ('stdout','stderr'): (out/(label+'.'+stream)).write_text(getattr(r,stream))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        return r
    def deps(text):
        return {str(Path(n).resolve()):sha(Path(n).resolve())
            for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    f = json.loads(FLAGS.read_text())
    command = next(c['command'] for c in f['commands'] if c['stdout'].endswith('/readpassphrase-compile.stdout'))
    flags = command[:command.index('-MD')]
    flags = [flags[0],'-I',str(include),*flags[1:]]
    # The whole original spawn TU also supplies execve; preserve its body with
    # a private symbol name instead of replacing the accepted public owner.
    extra = {'system': ['-DVARIANT_CANCELABLE'], 'popen': [],
             'posix_spawn': ['-Dexecve=rpi5_spawn_group_execve']}
    for path in UNITS:
        label = path.stem; target = flags+extra[label]
        scan = run([*target,'-M',path],label+'-scan')
        if scan.returncode: failures[label]='scan';continue
        before = deps(scan.stdout);headers.update(before)
        obj,dep = out/(label+'.o'),out/(label+'.d')
        result = run([*target,'-MD','-MF',dep,'-c',path,'-o',obj],label+'-compile')
        after = deps(dep.read_text()) if dep.is_file() else {}
        records[label] = dict(scanned_sha256=before,consumed_sha256=after)
        if result.returncode: failures[label]='compile';continue
        if before != after:raise ValueError('Actual consumed header closure differs')
        objects[label] = str(obj);run(['xcrun','nm','-g',obj],label+'-symbols')
    archive = out/'UNQUALIFIED-apple-spawn-group.a'
    if run(['xcrun','ar','rcs',archive,*objects.values()],'archive').returncode:raise ValueError('Archive failed')
    link = list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1] = str(out/'NOT_RUN_ssh');link[link.index('-map')+1] = str(out/'target.map')
    result = run([*link,archive],'target-link')
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    verify()
    for name,digest in headers.items():
        if sha(name) != digest:raise ValueError('Header drift '+name)
    report = dict(profile='whole-original-apple-spawn-group-inventory-v1',source_inputs_sha256=pins,
        headers_sha256=headers,dependency_records=records,commands=commands,objects=objects,compile_failures=failures,
        original_units=list(map(str,UNITS)),original_units_unchanged=True,header_copies=HEADER_COPIES,
        target_archive=str(archive),target_link_returncode=result.returncode,target_missing_symbols=missing,
        target_duplicate_symbols=duplicates,closed_symbols=sorted(set(base['target_missing_symbols'])-set(missing)),
        newly_reachable_symbols=sorted(set(missing)-set(base['target_missing_symbols'])),
        target_executed=False,full_client_qualified=False,provider_stubs=False,
        accepted_runtime_modified=False,original_openssh_config_unchanged=True,native_contract_passed=False,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(output=str(out),manifest_sha256=sha(out/'manifest.json'),failures=failures,
        missing=len(missing),closed=report['closed_symbols'],new=report['newly_reachable_symbols'],duplicates=duplicates),indent=2))
    return out,report


if __name__=='__main__':build()
