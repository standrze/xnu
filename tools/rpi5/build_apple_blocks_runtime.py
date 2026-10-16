#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original pure-C Apple Blocks runtime plus honest full-once compile inventory."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import tempfile

from tools.rpi5 import build_apple_runtime_api_fragments as previous

ROOT, sha = previous.ROOT, previous.sha
SOURCE = ROOT / 'build/rpi5/sources/libdispatch/libdispatch-libdispatch-1542.100.32'
TAR = ROOT / 'build/rpi5/downloads/libdispatch.tar.gz'
TAR_SHA = 'b251152f46d2cc16b87be85d32880144b44aadab62eb0712c31b27ca86556718'
BASE = ROOT / 'build/rpi5/apple-runtime-api-fragments-bg8jq8u2'
BASE_SHA = '6c858250877f14585768a8d3beb77b44a0c321c68227fc8cfe3934df88193ade'
HOST = ROOT / 'tools/rpi5/tests/apple_blocks_runtime_host.c'
EXPECTED = 'APPLE_BLOCKS_RUNTIME PASS GLOBAL=1 STACK_HEAP=1 BYREF_ESCAPE=1 NESTED=1 NULL=2 RETAIN_THREADS=4 RETAINS=4096\n'
UNITS = ('src/BlocksRuntime/runtime.c', 'src/BlocksRuntime/data.c')


def build():
    if sha(TAR) != TAR_SHA or sha(BASE / 'manifest.json') != BASE_SHA:
        raise ValueError('Frozen source or predecessor changed')
    base = json.loads((BASE / 'manifest.json').read_text())
    pins = {str(TAR): TAR_SHA, str(BASE / 'manifest.json'): BASE_SHA}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
        for name, digest in base[key].items():
            if name in pins and pins[name] != digest:
                raise ValueError('Inherited pin conflict')
            pins[name] = digest
    # Compare every real release file before compiling, without extracting or
    # writing into the preserved source checkout.
    with tarfile.open(TAR, 'r:gz') as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            path = SOURCE.parent / member.name
            if not path.is_relative_to(SOURCE) or archive.extractfile(member).read() != path.read_bytes():
                raise ValueError('Original release source differs: ' + member.name)
            pins[str(path)] = sha(path)
    for path in (Path(__file__).resolve(), HOST):
        pins[str(path)] = sha(path)

    def verify():
        for name, digest in pins.items():
            if sha(name) != digest:
                raise ValueError('Pinned input drift: ' + name)

    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-blocks-runtime-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers, records = [], {}, {}

    def run(args, label, allowed=False):
        args = list(map(str, args))
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=90)
        for name in ('stdout', 'stderr'):
            (out / (label + '.' + name)).write_text(getattr(result, name))
        commands.append(dict(command=args, cwd=str(ROOT), returncode=result.returncode,
            stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if result.returncode and not allowed:
            raise ValueError(label + ': ' + result.stderr[-7000:])
        return result

    def dependencies(raw):
        return {str(Path(name).resolve()): sha(Path(name).resolve())
            for name in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}

    def compile_(flags, source, label):
        before = dependencies(run(flags + ['-M', source], label + '-scan').stdout)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        run(flags + ['-MD', '-MF', dep, '-c', source, '-o', obj], label + '-compile')
        actual = dependencies(dep.read_text())
        if actual != before:
            raise ValueError('Actual dependency set differs')
        records[label] = dict(scanned_sha256=before, consumed_sha256=actual)
        headers.update(actual)
        return obj

    old = next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-reallocf-compile.stdout'))
    target = old[:old.index('-MD')] + ['-fblocks', '-DHAVE_OBJC=0', '-I', str(SOURCE / 'src/BlocksRuntime')]
    native = [flag for flag in target if flag not in ('-ffreestanding', '-mcpu=cortex-a76')]
    at = native.index('-target'); del native[at:at + 2]
    native += ['-O1', '-g', '-fsanitize=address,undefined']
    target_objects = [compile_(target, SOURCE / name, 'target-' + Path(name).stem) for name in UNITS]
    host_objects = [compile_(native, SOURCE / name, 'native-' + Path(name).stem) for name in UNITS]
    caller = compile_(native, HOST, 'native-caller')
    executable = out / 'host-blocks'
    run(native + [caller, *host_objects, '-Wl,-map,' + str(out / 'host.map'), '-o', executable], 'native-link')
    result = run([executable], 'native-run')
    if result.stdout != EXPECTED or result.stderr:
        raise ValueError('Original Blocks native oracle failed')
    archive = out / 'libapple-blocks-runtime.a'
    run(['xcrun', 'ar', 'rcs', archive, *target_objects], 'archive')
    run(['xcrun', 'nm', '-g', archive], 'symbols')
    run(['xcrun', 'llvm-objdump', '-d', '-r', *target_objects], 'disassembly')
    # Audit the full original once TU, not the unrelated ExclaveKit no-op. A
    # failed private-header inventory is retained and is never a provider.
    once_flags = target + ['-I', str(SOURCE), '-I', str(SOURCE / 'src'),
        '-I', str(SOURCE / 'private'), '-I', str(SOURCE / 'os')]
    once = run(once_flags + ['-fsyntax-only', SOURCE / 'src/once.c'], 'original-once-inventory', True)
    verify()
    for name, digest in headers.items():
        if sha(name) != digest:
            raise ValueError('Consumed header drift')
    report = dict(profile='original-apple-pure-c-blocks-runtime-v1', source_inputs_sha256=pins,
        headers_sha256=headers, dependency_records=records, commands=commands,
        source_release='libdispatch-1542.100.32', source_commit='701f4d1a24ae9c6863901bbbb22624b7d1b87321',
        release_file_bytes_verified=True, whole_original_translation_units_compiled=list(UNITS),
        original_source_modified=False, objective_c_enabled=False, target_archive=str(archive),
        native_asan_ubsan_pass=True, native_stdout=EXPECTED,
        native_host_boundary=['real system pthread', 'real system allocator/I/O', 'SDK assertion reporting'],
        native_blocks_runtime_from_original_objects=True, once_compile_returncode=once.returncode,
        dispatch_once_provider_qualified=False, exclavekit_noop_used=False,
        target_executed=False, accepted_runtime_modified=False,
        generated_sha256={str(p): sha(p) for p in out.iterdir() if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), original_once_inventory_returncode=once.returncode), indent=2))
    return out, report


if __name__ == '__main__':
    build()
