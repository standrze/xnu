#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Privately replace legacy Mach globals with original Apple owning objects.

This closes a forced-init link, NOT startup. The old argv entry and bootstrap
TSD remain in this nonexecuted diagnostic, deliberately labelled NOT_RUN.
"""
import difflib
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'build/rpi5/apple-pthread-log-clock-m3ct69va'
BASE_SHA = '47ed14c78a38d0c81f2325228e44f8205bc6a778e11cd4297b3bec6b1a821d9b'
LEGACY = ROOT / 'experiments/darwin-container/userland/build/darwin-abi-diagnostic-2'
SOURCE = ROOT / 'experiments/darwin-container/userland/runtime/darwin_static.c'
REMOVED = ('malloc_logger_t *__syscall_logger;\n', 'mach_port_t mach_task_self_;\n',
           'vm_size_t vm_page_size = 16384;\n', 'int vm_page_shift = 14;\n',
           'vm_size_t vm_page_mask = 16383;\n')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA: raise ValueError('Frozen base drift')
    base = json.loads((BASE / 'manifest.json').read_text())
    old = json.loads((LEGACY / 'manifest.json').read_text())
    pins = {str(BASE / 'manifest.json'):BASE_SHA, str(LEGACY / 'manifest.json'):sha(LEGACY / 'manifest.json'),
            str(Path(__file__).resolve()):sha(__file__)}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'): pins.update(base[key])
    for path, digest in old['inputs'].items(): pins[path] = digest
    pins[old['archive']] = old['sha256']
    for path, digest in pins.items():
        if sha(path) != digest: raise ValueError('Preserved runtime/source changed: ' + path)
    out = Path(tempfile.mkdtemp(prefix='apple-pthread-mach-state-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers = [], {}
    def run(args, label):
        args = list(map(str,args)); proc = subprocess.run(args,cwd=out,capture_output=True,text=True,timeout=90)
        (out / (label+'.stdout')).write_text(proc.stdout); (out / (label+'.stderr')).write_text(proc.stderr)
        commands.append(dict(command=args,returncode=proc.returncode,stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if proc.returncode: raise ValueError(label+': '+proc.stderr)
        return proc
    def deps(raw): return {str(Path(p).resolve()):sha(Path(p).resolve()) for p in shlex.split(raw.replace('\\\n',' ').partition(':')[2])}
    original = SOURCE.read_text(); text = original
    for definition in REMOVED:
        if text.count(definition) != 1: raise ValueError('Exact legacy Mach global changed')
        text = text.replace(definition, '')
    copied = out / 'darwin_static_mach_owned.c'; copied.write_text(text)
    (out / 'legacy-mach-global-removal.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True),text.splitlines(True),fromfile=str(SOURCE),tofile=str(copied))))
    compile_command = next(list(c) for c in old['commands'] if str(SOURCE) in c and '-c' in c)
    flags = compile_command[:compile_command.index('-c')]
    before = deps(run(flags+['-M',copied],'runtime-deps').stdout)
    dep=out/'runtime.d'; obj=out/'14-darwin_static.o'
    members=run(['xcrun','ar','t',old['archive']],'original-members').stdout.splitlines()
    if len(members)!=len(set(members)) or any('/' in n or n in ('.','..') for n in members): raise ValueError('Unsafe archive membership')
    run(['xcrun','ar','x',old['archive']],'extract-original-members')
    before_members={n:sha(out/n) for n in members}
    run(flags+['-MD','-MF',dep,'-c',copied,'-o',obj],'runtime-compile')
    if deps(dep.read_text())!=before: raise ValueError('Consumed runtime closure changed')
    headers.update(before)
    after_members={n:sha(out/n) for n in members}
    if {n for n in members if before_members[n]!=after_members[n]}!={'14-darwin_static.o'}: raise ValueError('Unexpected replaced object')
    archive=out/'libdarwin-static-mach-owned.a'
    run(['xcrun','ar','rcs',archive,*[out/n for n in members]],'private-runtime-archive')
    link=next(list(c['command']) for c in base['commands'] if c['stdout'].endswith('/init-live-link.stdout'))
    if link.count(old['archive'])!=1: raise ValueError('Legacy runtime link identity mismatch')
    link[link.index(old['archive'])]=str(archive)
    link[link.index('-o')+1]=str(out/'NOT_RUN_init-live')
    link[link.index('-map')+1]=str(out/'init-live.map')
    attempt=run(link,'init-live-link')
    if 'duplicate symbol' in attempt.stderr: raise ValueError('Duplicate provider remains')
    undefined=run(['xcrun','nm','-u',out/'NOT_RUN_init-live'],'target-undefined').stdout
    if undefined.strip(): raise ValueError('Undefined target symbol remains')
    symbols=run(['xcrun','nm','-g',out/'NOT_RUN_init-live'],'target-symbols').stdout
    for name in ('___pthread_init','___libkernel_init','_mach_init','_mach_absolute_time','_mach_continuous_time'):
        if not re.search(r'^[0-9a-f]+ T '+name+'$',symbols,re.M): raise ValueError('Actual implementation missing: '+name)
    maptext=(out/'init-live.map').read_text()
    # Merely linked initialization is not actual execution ordering.
    for path,digest in {**pins,**headers}.items():
        if sha(path)!=digest: raise ValueError('Input drift: '+path)
    report=dict(profile='original-apple-pthread-mach-global-ownership-link-v1',source_inputs_sha256=pins,
        headers_sha256=headers,commands=commands,removed_legacy_definitions=list(REMOVED),
        archive_member_order=members,original_archive_members_sha256=before_members,
        private_archive_members_sha256=after_members,target_archive=str(archive),target_archive_sha256=sha(archive),
        target=str(out/'NOT_RUN_init-live'),target_sha256=sha(out/'NOT_RUN_init-live'),
        target_missing_symbols=[],target_duplicate_symbols=[],target_link_complete=True,
        original_apple_implementation_bodies_unchanged=True,legacy_runtime_private_copy=True,
        legacy_argv_entry_retained=True,legacy_bootstrap_tsd_retained=True,
        real_libkernel_init_forced_live=True,real_pthread_init_forced_live=True,
        target_startup_created=False,target_main_thread_initialized=False,
        constructors_order_wired=False,accepted_runtime_modified=False,pi_executed=False,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),linked=True,undefined=[],duplicates=[],target_run=False),indent=2))
    return out,report


if __name__=='__main__': build()
