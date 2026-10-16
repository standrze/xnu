#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Close two random API imports with an adapter and original LibreSSL sampler."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_ssh_zlib_runtime as previous

ROOT, sha = previous.ROOT, previous.sha
BASE, BASE_SHA = previous.BASE, previous.BASE_SHA
LIBRESSL = ROOT / 'build/rpi5/libressl-4.3.3-input-X8xG1B/libressl-4.3.3'
UNIFORM = LIBRESSL / 'crypto/compat/arc4random_uniform.c'
UNIFORM_SHA = '1b28fad6ed420644da0807a7da5f96279952f2fceac730227555c71dcf9e808e'
WORD = ROOT / 'tools/rpi5/user/kernel_entropy_random_word.c'
HOST = ROOT / 'tools/rpi5/tests/kernel_entropy_word_host.c'
EXPECTED = 'KERNEL_RANDOM_WORD_API PASS WORD=1 BOUNDS=10 RESIDUE_GROUPS=256 SYNTHETIC_SOURCE\n'


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA or sha(UNIFORM) != UNIFORM_SHA:
        raise ValueError('Frozen original input changed')
    base = json.loads((BASE / 'manifest.json').read_text())
    pins = {str(BASE / 'manifest.json'): BASE_SHA, str(UNIFORM): UNIFORM_SHA}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
        for name, digest in base[key].items():
            if name in pins and pins[name] != digest:
                raise ValueError('Conflicting inherited input')
            pins[name] = digest
    for path in (Path(__file__).resolve(), WORD, HOST):
        pins[str(path)] = sha(path)

    def verify():
        for name, digest in pins.items():
            if sha(name) != digest:
                raise ValueError('Input drift: ' + name)

    verify()
    out = Path(tempfile.mkdtemp(prefix='kernel-entropy-word-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers, records = [], {}, {}

    def run(args, label, allowed=False):
        args = list(map(str, args))
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=60)
        for name in ('stdout', 'stderr'):
            (out / (label + '.' + name)).write_text(getattr(result, name))
        commands.append(dict(command=args, cwd=str(ROOT), returncode=result.returncode,
            stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if result.returncode and not allowed:
            raise ValueError(label + ': ' + result.stderr[-4000:])
        return result

    def deps(text):
        return {str(Path(name).resolve()): sha(Path(name).resolve())
            for name in shlex.split(text.replace('\\\n', ' ').partition(':')[2])}

    def compile_(flags, source, label):
        before = deps(run(flags + ['-M', source], label + '-scan').stdout)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        run(flags + ['-MD', '-MF', dep, '-c', source, '-o', obj], label + '-compile')
        consumed = deps(dep.read_text())
        if consumed != before:
            raise ValueError('Actual dependency membership differs')
        headers.update(before)
        records[label] = dict(scanned_sha256=before, consumed_sha256=consumed)
        return obj

    old = next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-getopt-compile.stdout'))
    target = old[:old.index('-MD')]
    native = [flag for flag in target if flag not in ('-ffreestanding', '-mcpu=cortex-a76')]
    at = native.index('-target'); del native[at:at + 2]
    native += ['-g', '-O1', '-fsanitize=address,undefined'] + [
        '-D' + name + '=fixture_' + name for name in ('arc4random', 'arc4random_buf', 'arc4random_uniform')]
    objects = [compile_(target, path, 'target-' + name) for path, name in ((WORD, 'word'), (UNIFORM, 'uniform'))]
    hosts = [compile_(native, path, 'native-' + name) for path, name in ((WORD, 'word'), (UNIFORM, 'uniform'))]
    native_target = out / 'synthetic-source-host'
    run(native + [HOST, *hosts, '-o', native_target], 'native-link')
    result = run([native_target], 'native-run')
    if result.stdout != EXPECTED or result.stderr:
        raise ValueError('Original rejection sampler/API oracle failed')
    archive = out / 'librandom-word-api.a'
    run(['xcrun', 'ar', 'rcs', archive, *objects], 'archive')
    run(['xcrun', 'nm', '-g', archive], 'symbols')
    run(['xcrun', 'llvm-objdump', '-d', '-r', *objects], 'disassembly')
    link = list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o') + 1] = str(out / 'NOT_RUN_ssh')
    link[link.index('-map') + 1] = str(out / 'target.map')
    link.append(str(archive))
    result = run(link, 'target-link', True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', result.stderr, re.M)))
    duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", result.stderr)))
    closed = set(base['target_missing_symbols']) - set(missing)
    added = set(missing) - set(base['target_missing_symbols'])
    if not result.returncode or duplicates or closed != {'_arc4random', '_arc4random_uniform'} or added:
        raise ValueError('Unexpected full-client link delta: ' + result.stderr[-4000:])
    verify()
    for name, digest in headers.items():
        if sha(name) != digest:
            raise ValueError('Consumed header drift')
    report = dict(profile='project-kernel-random-word-original-libressl-uniform-v1',
        source_inputs_sha256=pins, headers_sha256=headers, dependency_records=records, commands=commands,
        target_archive=str(archive), original_uniform_source=str(UNIFORM), original_uniform_unchanged=True,
        word_adapter_project_owned=True, user_space_generator=False, retained_random_state=False,
        accepted_buf_adapter_unchanged=True, original_openssh_config_unchanged=True,
        native_asan_ubsan_pass=True, native_source_is_synthetic=True, native_stdout=EXPECTED,
        previous_missing_count=len(base['target_missing_symbols']), closed_symbols=sorted(closed),
        newly_reachable_dependencies=sorted(added), target_missing_symbols=missing,
        target_duplicate_symbols=duplicates, target_link_complete=False, target_executed=False,
        entropy_qualified=False, live_keys=False, provider_stubs=False, accepted_runtime_modified=False,
        generated_sha256={str(path): sha(path) for path in out.iterdir() if path.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), closed=sorted(closed), remaining=len(missing)), indent=2))
    return out, report


if __name__ == '__main__':
    build()
