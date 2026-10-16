#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original complete Apple stpcpy TU under original Libc provider build policy."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_fortify_runtime_v2 as previous

ROOT, sha = previous.ROOT, previous.sha
LIBC = previous.original.LIBC
BASE = ROOT / 'build/rpi5/apple-fortify-runtime-punnvr0c'
BASE_SHA = 'adcab45b4082c864520a6101d4fc5efa8e2ada095aa1a23b4dbc01aaeb3cc365'
SOURCE = LIBC / 'string/stpcpy.c'
HOST = ROOT / 'tools/rpi5/tests/apple_stpcpy_host.c'
EXPECTED = 'APPLE_STPCPY PASS CASES=65536 SOURCE_ALIGNMENTS=16 DEST_ALIGNMENTS=16 LENGTHS=256\n'


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA:
        raise ValueError('Frozen full-client runtime composition changed')
    base = json.loads((BASE / 'manifest.json').read_text())
    pins = {str(BASE / 'manifest.json'): BASE_SHA}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
        for name, digest in base[key].items():
            if name in pins and pins[name] != digest: raise ValueError('Inherited pin conflict')
            pins[name] = digest
    if subprocess.check_output(['git', '-C', str(LIBC), 'show', 'HEAD:string/stpcpy.c']) != SOURCE.read_bytes():
        raise ValueError('Original complete stpcpy source changed')
    if subprocess.check_output(['git', '-C', str(LIBC), 'rev-parse', 'HEAD'], text=True).strip() != base['original_libc_commit']:
        raise ValueError('Original Apple commit changed')
    for path in (SOURCE, HOST, Path(__file__).resolve()): pins[str(path)] = sha(path)
    def verify():
        for name, digest in pins.items():
            if sha(name) != digest: raise ValueError('Pinned input drift: ' + name)
    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-stpcpy-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers, records = [], {}, {}
    def run(args, label, allowed=False):
        args = list(map(str, args)); result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=90)
        for name in ('stdout', 'stderr'): (out / (label + '.' + name)).write_text(getattr(result, name))
        commands.append(dict(command=args, cwd=str(ROOT), returncode=result.returncode,
            stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if result.returncode and not allowed: raise ValueError(label + ': ' + result.stderr[-6000:])
        return result
    def deps(raw):
        return {str(Path(n).resolve()): sha(Path(n).resolve()) for n in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}
    def compile_(flags, source, label):
        before = deps(run(flags + ['-M', source], label + '-scan').stdout)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        run(flags + ['-MD', '-MF', dep, '-c', source, '-o', obj], label + '-compile')
        actual = deps(dep.read_text())
        if actual != before: raise ValueError('Consumed headers differ')
        records[label] = dict(scanned_sha256=before, consumed_sha256=actual); headers.update(actual)
        return obj
    old = next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-strcpy_chk-compile.stdout'))
    target = old[:old.index('-MD')]
    if '-D_FORTIFY_SOURCE=0' not in target: raise ValueError('Real Libc provider policy missing')
    native = [x for x in target if x not in ('-ffreestanding', '-mcpu=cortex-a76')]
    i = native.index('-target'); del native[i:i + 2]
    native += ['-O1', '-g', '-fsanitize=address,undefined', '-Dstpcpy=fixture_stpcpy']
    obj = compile_(target, SOURCE, 'target-stpcpy')
    host_obj = compile_(native, SOURCE, 'native-stpcpy')
    caller = compile_(native, HOST, 'native-caller')
    executable = out / 'host-stpcpy'
    run(native + [caller, host_obj, '-o', executable], 'native-link')
    result = run([executable], 'native-run')
    if (result.stdout, result.stderr) != (EXPECTED, ''): raise ValueError('Original stpcpy oracle failed')
    archive = out / 'libapple-stpcpy.a'; run(['xcrun', 'ar', 'rcs', archive, obj], 'archive')
    run(['xcrun', 'nm', '-g', archive], 'symbols'); run(['xcrun', 'llvm-objdump', '-d', '-r', obj], 'disassembly')
    link = list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o') + 1] = str(out / 'NOT_RUN_ssh'); link[link.index('-map') + 1] = str(out / 'target.map')
    link.append(str(archive)); result = run(link, 'target-link', True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', result.stderr, re.M)))
    duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", result.stderr)))
    closed, added = set(base['target_missing_symbols']) - set(missing), set(missing) - set(base['target_missing_symbols'])
    if not result.returncode or duplicates or closed != {'_stpcpy'} or added:
        raise ValueError('Unexpected genuine provider delta')
    verify()
    for name, digest in headers.items():
        if sha(name) != digest: raise ValueError('Consumed input drift')
    report = dict(profile='current-apple-original-stpcpy-provider-v1', source_inputs_sha256=pins,
        headers_sha256=headers, dependency_records=records, commands=commands, original_libc_commit=base['original_libc_commit'],
        original_source_unchanged=True, whole_original_translation_unit_compiled=True, provider_only_fortify_source=0,
        target_archive=str(archive), native_stdout=EXPECTED, native_asan_ubsan_pass=True,
        native_runtime_boundary=['real host strlen/memcpy and allocator/I/O'], previous_missing_count=len(base['target_missing_symbols']),
        closed_symbols=sorted(closed), newly_reachable_symbols=sorted(added), target_missing_symbols=missing,
        target_duplicate_symbols=duplicates, original_openssh_config_unchanged=True, target_link_complete=False,
        target_executed=False, accepted_runtime_modified=False,
        generated_sha256={str(p): sha(p) for p in out.iterdir() if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), manifest_sha256=sha(out / 'manifest.json'), remaining=len(missing)), indent=2))
    return out, report


if __name__ == '__main__': build()
