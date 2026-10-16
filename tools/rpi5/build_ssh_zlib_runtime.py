#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build official zlib and measure its contribution to the original SSH link."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import tempfile
from tools.rpi5 import build_apple_ssh_client_leaves as previous

ROOT, sha = previous.ROOT, previous.sha
BASE = previous.ROOT / 'build/rpi5/apple-ssh-client-leaves-8svd9i48'
BASE_SHA = 'ef270aebee087a072eed44dfd2c15183b8a3ce3de36e1c897b380699687f6b08'
INPUT = ROOT / 'build/rpi5/zlib-1.3.2-input-i5ckXK'
ARCHIVE_SHA = 'bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16'
SOURCE = INPUT / 'zlib-1.3.2'
CLOSED = {'_deflate', '_deflateEnd', '_deflateInit_', '_inflate', '_inflateEnd', '_inflateInit_'}
EXPECTED = 'SSH_ZLIB_SDK_ABI PASS STREAMS=8 BAD_CHECKSUM=1 TRUNCATED=1 VERSION=1.3.2\n'


def original_units():
    text = (SOURCE / 'Makefile.in').read_text()
    units = []
    for group in ('OBJZ', 'OBJG'):
        matches = re.findall(r'^' + group + r' = ([^\n]+)$', text, re.M)
        if len(matches) != 1:
            raise ValueError('Exact upstream source group required')
        units.extend(name.removesuffix('.o') + '.c' for name in matches[0].split())
    if len(units) != 15 or len(set(units)) != 15:
        raise ValueError('Unexpected upstream source membership')
    return units


def build():
    archive = INPUT / 'zlib-1.3.2.tar.gz'
    if sha(archive) != ARCHIVE_SHA or sha(BASE / 'manifest.json') != BASE_SHA:
        raise ValueError('Frozen input changed')
    base = json.loads((BASE / 'manifest.json').read_text())
    pins = {str(archive): ARCHIVE_SHA, str(BASE / 'manifest.json'): BASE_SHA}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
        for name, digest in base[key].items():
            if name in pins and pins[name] != digest:
                raise ValueError('Conflicting inherited input')
            pins[name] = digest
    # Compare every extracted source file with the verified release, including
    # the license, rather than trusting an already extracted directory.
    with tarfile.open(archive, 'r:gz') as release:
        for member in release.getmembers():
            if not member.isfile():
                continue
            parts = Path(member.name).parts
            if parts[0] != 'zlib-1.3.2' or '..' in parts:
                raise ValueError('Unexpected official release member')
            path = INPUT / member.name
            if path.read_bytes() != release.extractfile(member).read():
                raise ValueError('Original release source changed: ' + str(path))
            pins[str(path)] = sha(path)
    harness = ROOT / 'tools/rpi5/tests/ssh_zlib_sdk_host.c'
    for path in (Path(__file__).resolve(), harness):
        pins[str(path)] = sha(path)

    def verify():
        for name, digest in pins.items():
            if sha(name) != digest:
                raise ValueError('Input drift: ' + name)

    verify()
    out = Path(tempfile.mkdtemp(prefix='ssh-zlib-runtime-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers, records, target_objects, native_objects = [], {}, {}, [], []

    def run(args, label, allowed=False):
        args = list(map(str, args))
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=90)
        for name in ('stdout', 'stderr'):
            (out / (label + '.' + name)).write_text(getattr(result, name))
        commands.append(dict(command=args, cwd=str(ROOT), returncode=result.returncode,
            stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if result.returncode and not allowed:
            raise ValueError(label + ': ' + result.stderr[-6000:])
        return result

    def dependencies(text):
        return {str(Path(name).resolve()): sha(Path(name).resolve())
            for name in shlex.split(text.replace('\\\n', ' ').partition(':')[2])}

    def compile_(flags, source, label):
        before = dependencies(run(flags + ['-M', source], label + '-scan').stdout)
        dep, obj = out / (label + '.d'), out / (label + '.o')
        run(flags + ['-MD', '-MF', dep, '-c', source, '-o', obj], label + '-compile')
        consumed = dependencies(dep.read_text())
        if before != consumed:
            raise ValueError('Consumed source dependencies changed')
        headers.update(before)
        records[label] = dict(scanned_sha256=before, consumed_sha256=consumed)
        return obj

    old = next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-getopt-compile.stdout'))
    target = old[:old.index('-MD')]
    target = target[:1] + ['-I', str(SOURCE), '-DHAVE_UNISTD_H=1'] + target[1:]
    native = [flag for flag in target if flag not in ('-ffreestanding', '-mcpu=cortex-a76')]
    at = native.index('-target')
    del native[at:at + 2]
    native += ['-g', '-O1', '-fsanitize=address,undefined']
    units = original_units()
    for unit in units:
        target_objects.append(compile_(target, SOURCE / unit, 'target-' + Path(unit).stem))
        native_objects.append(compile_(native, SOURCE / unit, 'native-' + Path(unit).stem))
    target_archive, native_archive = out / 'libz-target.a', out / 'libz-native.a'
    run(['xcrun', 'ar', 'rcs', target_archive, *target_objects], 'target-archive')
    run(['xcrun', 'ar', 'rcs', native_archive, *native_objects], 'native-archive')
    example = compile_(native, SOURCE / 'test/example.c', 'native-original-example')
    run(native + [example, native_archive, '-o', out / 'original-example'], 'original-example-link')
    example_result = run([out / 'original-example', out / 'example.gz'], 'original-example-run')
    if example_result.stderr or not example_result.stdout.startswith('zlib version 1.3.2 = '):
        raise ValueError('Original upstream example failed')
    # This TU consumes the same SDK zlib.h as the original full SSH client,
    # while its deflate/inflate calls resolve to our new upstream archive.
    sdk_flags = list(native)
    at = sdk_flags.index(str(SOURCE))
    del sdk_flags[at - 1:at + 1]
    obj = compile_(sdk_flags, harness, 'sdk-client')
    run(sdk_flags + [obj, native_archive, '-Wl,-map,' + str(out / 'sdk-client.map'),
        '-o', out / 'sdk-client'], 'sdk-client-link')
    mixed = run([out / 'sdk-client'], 'sdk-client-run')
    if mixed.stdout != EXPECTED or mixed.stderr:
        raise ValueError('SDK client/upstream archive stream oracle failed')
    dylibs = run(['xcrun', 'otool', '-L', out / 'sdk-client'], 'sdk-client-dylibs').stdout
    if re.search(r'/libz\.', dylibs):
        raise ValueError('Host test accidentally uses system zlib')

    link = list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o') + 1] = str(out / 'NOT_RUN_ssh')
    link[link.index('-map') + 1] = str(out / 'target.map')
    link.append(str(target_archive))
    result = run(link, 'target-link', True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', result.stderr, re.M)))
    duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", result.stderr)))
    closed = set(base['target_missing_symbols']) - set(missing)
    added = set(missing) - set(base['target_missing_symbols'])
    if not result.returncode or duplicates or closed != CLOSED or added:
        raise ValueError('Unexpected original client link delta: ' + result.stderr[-6000:])
    verify()
    for name, digest in headers.items():
        if sha(name) != digest:
            raise ValueError('Consumed header drift: ' + name)
    report = dict(profile='original-openssh-upstream-zlib-1.3.2-closure-v1',
        release_url='https://zlib.net/zlib-1.3.2.tar.gz', release_sha256=ARCHIVE_SHA,
        release_version='1.3.2', apple_source_selected=False,
        apple_source_observation=dict(repository='https://github.com/apple-oss-distributions/zlib',
            commit='06673bf7cb4066003fd14a0b87085c05739fc4ac', published_version='1.2.12'),
        source_inputs_sha256=pins, headers_sha256=headers, dependency_records=records,
        commands=commands, upstream_sources_unchanged=True, requested_translation_units=units,
        target_archive=str(target_archive), original_example_stdout=example_result.stdout,
        native_asan_ubsan_pass=True, sdk_header_client_original_archive_pass=True,
        host_dynamic_zlib=False, original_openssh_config_unchanged=True,
        previous_missing_count=len(base['target_missing_symbols']), closed_symbols=sorted(closed),
        newly_reachable_dependencies=sorted(added), target_missing_symbols=missing,
        remaining_provider_groups=previous.categories(missing), target_duplicate_symbols=duplicates,
        target_link_complete=False, target_executed=False, provider_stubs=False,
        network_access=False, live_keys=False, accepted_runtime_modified=False,
        generated_sha256={str(p): sha(p) for p in out.iterdir() if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), closed=sorted(closed), remaining=len(missing)), indent=2))
    return out, report


if __name__ == '__main__':
    build()
