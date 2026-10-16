#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bounded current Apple strtoll/xlocale archive and actual client link audit.

Whole original translation units only. No target is ever executed here.
The distinct startup wires the genuine locale initializer after pthread init,
before allocation, constructors, or client code. Unclosed imports stay errors.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

from tools.rpi5 import build_apple_ssh_client_leaves as previous

ROOT, sha = previous.ROOT, previous.sha
BASE = ROOT / 'build/rpi5/apple-ssh-client-leaves-8svd9i48'
BASE_SHA = 'ef270aebee087a072eed44dfd2c15183b8a3ce3de36e1c897b380699687f6b08'
LIBC = previous.LIBC
THREADS = ROOT / 'build/rpi5/apple-libpthread-main-candidate-20261013'
START = ROOT / 'build/rpi5/apple-pthread-static-complete-gm82fjkz'
START_SHA = '4a22b183000378e842d59c643ed1f8a80a520e1e77d62370880a7c095adfc35a'
UNITS = ('stdlib/FreeBSD/strtoll.c', 'locale/xlocale.c',
         'locale/FreeBSD/table.c', 'locale/FreeBSD/none.c',
         'locale/FreeBSD/collate.c', 'locale/FreeBSD/runetype.c',
         'locale/FreeBSD/nomacros.c')


def startup_source(text):
    before = '    rpi5_pthread_startup_stage = 2;\n'
    after = ('    /* Genuine current Libc TSD key/destructor, after main pthread. */\n'
             '    extern void __xlocale_init(void);\n'
             '    __xlocale_init();\n' + before)
    if text.count(before) != 1 or '__xlocale_init' in text:
        raise ValueError('Original startup binding differs')
    return text.replace(before, after)


def build():
    if sha(BASE/'manifest.json') != BASE_SHA or sha(START/'manifest.json') != START_SHA:
        raise ValueError('Frozen predecessor differs')
    base = json.loads((BASE/'manifest.json').read_text())
    start = json.loads((START/'manifest.json').read_text())
    pins = {str(BASE/'manifest.json'): BASE_SHA, str(START/'manifest.json'): START_SHA}
    for report in (base, start):
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, digest in report[key].items():
                if name in pins and pins[name] != digest:
                    raise ValueError('Conflicting predecessor pin')
                pins[name] = digest
    commit = subprocess.check_output(['git','-C',LIBC,'rev-parse','HEAD'],text=True).strip()
    if commit != previous.LIBC_COMMIT:
        raise ValueError('Wrong current Libc')
    for name in UNITS:
        source = LIBC/name
        if source.read_bytes() != subprocess.check_output(['git','-C',LIBC,'show','HEAD:'+name]):
            raise ValueError('Original translation unit changed')
        pins[str(source)] = sha(source)
    original_start = ROOT/'tools/rpi5/user/pthread_static_start.c'
    for path in (Path(__file__).resolve(), original_start,
                 LIBC/'xcodescripts/libc.xcconfig', LIBC/'sys/_libc_init.c'):
        digest = sha(path)
        if str(path) in pins and pins[str(path)] != digest:
            raise ValueError('Source drift')
        pins[str(path)] = digest
    def verify():
        for name, digest in pins.items():
            if sha(name) != digest:
                raise ValueError('Pinned input drift: '+name)
    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-ssh-locale-slice-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True)
    commands, headers, records, failures, objects = [], {}, {}, {}, {}
    def run(args,label):
        args = list(map(str,args))
        result = subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=90)
        for suffix in ('stdout','stderr'):
            (out/(label+'.'+suffix)).write_text(getattr(result,suffix))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=result.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        return result
    def deps(text):
        return {str(Path(n).resolve()):sha(Path(n).resolve())
                for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    def compile(flags,source,label):
        scan = run(flags+['-M',source],label+'-scan')
        if scan.returncode:
            failures[label] = 'dependency-scan'; return None
        before = deps(scan.stdout)
        obj, dep = out/(label+'.o'), out/(label+'.d')
        result = run(flags+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        consumed = deps(dep.read_text()) if dep.exists() else {}
        if result.returncode:
            failures[label] = 'compile'; headers.update(before); return None
        if before != consumed:
            raise ValueError('Consumed headers differ: '+label)
        headers.update(before)
        records[label] = dict(scanned_sha256=before,consumed_sha256=consumed)
        objects[label] = str(obj)
        run(['xcrun','nm','-g',obj],label+'-symbols')
        run(['xcrun','llvm-objdump','-d','-r',obj],label+'-disassembly')
        return obj
    old = next(c['command'] for c in base['commands']
               if c['stdout'].endswith('/target-strtonum-compile.stdout'))
    flags = old[:old.index('-MD')]
    flags += ['-I',str(LIBC/'locale'),'-I',str(LIBC/'locale/FreeBSD'),
              '-I',str(THREADS/'private'),'-I',str(THREADS/'include'),
              '-I',str(LIBC)]
    for name in UNITS:
        compile(flags,LIBC/name,'target-'+Path(name).stem)
    generated_start = out/'pthread_locale_start.c'
    generated_start.write_text(startup_source(original_start.read_text()))
    old_start = next(c['command'] for c in start['commands']
                     if c['stdout'].endswith('/startup-compile.stdout'))
    start_flags = old_start[:old_start.index('-MD')]+[
        '-iquote',str(original_start.parent)]
    compile(start_flags,generated_start,'startup-locale')
    archive = out/'libapple-ssh-locale.a'
    archive_inputs = [obj for name,obj in objects.items() if name != 'startup-locale']
    archived = run(['xcrun','ar','rcs',archive,*archive_inputs],'archive')
    if archived.returncode:
        raise ValueError('Archive failed')
    link = list(next(c['command'] for c in base['commands']
                     if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1] = str(out/'NOT_RUN_ssh')
    link[link.index('-map')+1] = str(out/'target.map')
    if 'startup-locale' in objects:
        if link.count(str(START/'startup.o')) != 1:
            raise ValueError('Exact startup replacement missing')
        link[link.index(str(START/'startup.o'))] = objects['startup-locale']
    link.append(str(archive))
    linked = run(link,'target-link')
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',linked.stderr,re.M)))
    duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'",linked.stderr)))
    if not linked.returncode or duplicates:
        raise ValueError('Unexpected complete or duplicate full client link')
    verify()
    for name,digest in headers.items():
        if sha(name) != digest:
            raise ValueError('Consumed input drift')
    report = dict(profile='original-apple-current-strtoll-xlocale-slice-v1',
        source_inputs_sha256=pins,headers_sha256=headers,dependency_records=records,
        commands=commands,current_libc_commit=commit,original_units=list(UNITS),
        original_sources_unchanged=True,compile_failures=failures,objects=objects,
        target_archive=str(archive),previous_missing_count=len(base['target_missing_symbols']),
        closed_symbols=sorted(set(base['target_missing_symbols'])-set(missing)),
        newly_reachable_dependencies=sorted(set(missing)-set(base['target_missing_symbols'])),
        target_missing_symbols=missing,target_duplicate_symbols=duplicates,
        startup_replacement_source=str(generated_start),
        locale_init_after_real_pthread_before_constructors='startup-locale' in objects,
        actual_locale_runtime_exercised=False,non_c_locale_data_files_present=False,
        full_current_libc_initialized=False,target_link_complete=False,
        target_executed=False,network_access=False,provider_stubs=False,
        accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),compile_failures=failures,
        closed=report['closed_symbols'],added=report['newly_reachable_dependencies'],remaining=len(missing)),indent=2))
    return out,report


if __name__ == '__main__':
    build()
