#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Genuine memory/trap providers and explicit private static symbol isolation."""
import difflib
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'build/rpi5/apple-pthread-bcm2712-check-kgbwgqa0'
BASE_SHA = '7b377e6b732a8da13f74fa1f0500ed3ebbe9c6962ed5d8da65ac52b0a6626c8b'
TARGET = ROOT / 'build/rpi5/apple-pthread-bcm2712-qualified-x9kp1ral'
WAIT = ROOT / 'build/rpi5/apple-pthread-wait-if5o744t'
CALLS = {'bsdthread_register': 366, 'workq_open': 367, 'exit': 1}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA: raise ValueError('Frozen input drift')
    base = json.loads((BASE / 'manifest.json').read_text())
    target = json.loads((TARGET / 'manifest.json').read_text())
    wait = json.loads((WAIT / 'manifest.json').read_text())
    pins = {str(BASE / 'manifest.json'): BASE_SHA, str(Path(__file__).resolve()): sha(__file__)}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'): pins.update(base[key])
    source = ROOT / 'tools/rpi5/user/pthread_registration_runtime_calls.S'
    harness = ROOT / 'tools/rpi5/tests/pthread_memory_providers_host.c'
    for path in (source, harness, ROOT / 'bsd/kern/syscalls.master'): pins[str(path)] = sha(path)
    for name, number in CALLS.items():
        if not re.search(r'^' + str(number) + r'\s+[^\n]*\b' + name + r'\(', (ROOT / 'bsd/kern/syscalls.master').read_text(), re.M):
            raise ValueError('Syscall mismatch: ' + name)
    out = Path(tempfile.mkdtemp(prefix='apple-pthread-memory-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers, units = [], {}, []
    def run(args, label, allowed=False):
        args = list(map(str, args)); proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=90)
        (out / (label + '.stdout')).write_text(proc.stdout); (out / (label + '.stderr')).write_text(proc.stderr)
        commands.append(dict(command=args, returncode=proc.returncode, stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if proc.returncode and not allowed: raise ValueError(label + ': ' + proc.stderr)
        return proc
    def deps(raw): return {str(Path(p).resolve()): sha(Path(p).resolve()) for p in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}
    def compile(flags, src, label):
        pins[str(src)] = sha(src)
        before = deps(run(flags + ['-M', src], label + '-deps').stdout)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        run(flags + ['-MD', '-MF', dep, '-c', src, '-o', obj], label + '-compile')
        if deps(dep.read_text()) != before: raise ValueError('Actual consumed header mismatch')
        headers.update(before); units.append(dict(label=label, source=str(src), object=str(obj), actual_headers_sha256=before)); return obj
    command = next(c['command'] for c in target['commands'] if c['stdout'].endswith('/platform-lock-compile.stdout'))
    flags = list(command[:command.index('-H')])
    # Original non-static variant exports only platform implementations, except
    # its hidden compiler-support memset wrapper. Namespace that one wrapper.
    flags[flags.index('-DVARIANT_STATIC=1')] = '-DVARIANT_STATIC=0'
    flags += ['-Dmemset=rpi5_platform_private_memset']
    platform = ROOT / 'build/rpi5/apple-libplatform-main-candidate-20261013/src/string/generic'
    implementations = ('bzero', 'memset_pattern', 'strlen', 'memmove')
    objects = [compile(flags, platform / (name + '.c'), 'platform-' + name) for name in implementations]
    asmcommand = next(c['command'] for c in wait['commands'] if c['stdout'].endswith('/target-deps.stdout'))
    asmflags = list(asmcommand[:asmcommand.index('-M')])
    traps = []
    for label in ('target', 'host'):
        selected = list(asmflags)
        if label == 'host':
            selected += ['-D___' + name + '=_rpi5_host_' + name for name in CALLS]
            selected += ['-Dcerror_nocancel=rpi5_host_cerror']
        before = deps(run(selected + ['-M', source], label + '-trap-deps').stdout)
        dep = out / (label + '-trap.d')
        raw = run(selected + ['-E', '-P', source, '-MD', '-MF', dep], label + '-trap-preprocess').stdout
        if deps(dep.read_text()) != before: raise ValueError('Trap dependencies differ')
        headers.update(before)
        assembly = out / (label + '-trap.s'); assembly.write_text(raw.replace(';', '\n'))
        obj = out / (label + '-trap.o')
        run(selected[:selected.index('-I')] + ['-x', 'assembler', '-c', assembly, '-o', obj], label + '-trap-assemble')
        run(['xcrun', 'otool', '-tvV', obj], label + '-trap-disassembly')
        run(['xcrun', 'otool', '-rv', obj], label + '-trap-relocations')
        traps.append(obj)
    archive = out / 'libapple-pthread-memory.a'
    run(['xcrun', 'ar', 'rcs', archive, *objects, traps[0]], 'provider-archive')
    # Original pthread's three dylib-private compiler wrappers otherwise collide
    # with the accepted static archive. Change only their definition identifiers
    # in a private copy, preserving all three bodies and every public API name.
    original = Path(target['units'][0]['source'])
    raw = original.read_text(); boundary = raw.index('#pragma mark libplatform shims')
    tail = raw[boundary:]; renames = {}
    for name in ('memset', 'bzero', 'memcpy'):
        replacement = 'rpi5_pthread_private_' + name
        tail, count = re.subn(r'(?m)^' + name + r'\(', replacement + '(', tail)
        if count != 1: raise ValueError('Expected one private wrapper definition')
        renames[name] = replacement
    scoped = out / 'pthread-private.c'; scoped.write_text(raw[:boundary] + tail)
    (out / 'pthread-private.diff').write_text(''.join(difflib.unified_diff(raw.splitlines(True), scoped.read_text().splitlines(True), fromfile=str(original), tofile=str(scoped))))
    cmd = next(c['command'] for c in target['commands'] if c['stdout'].endswith('/pthread-pthread-compile.stdout'))
    threadflags = list(cmd[:cmd.index('-H')]) + ['-I', str(original.parent)]
    scoped_obj = compile(threadflags, scoped, 'pthread-private')
    scoped_archive = out / 'libapple-pthread-platform-scoped.a'
    run(['xcrun', 'ar', 'rcs', scoped_archive, scoped_obj, *[u['object'] for u in target['units'][1:]]], 'scoped-archive')
    link = next(list(c['command']) for c in base['commands'] if c['stdout'].endswith('/init-live-link.stdout'))
    link[link.index(target['partial_archive'])] = str(scoped_archive)
    link[link.index('-o') + 1] = str(out / 'NOT_RUN_init-live')
    link[link.index('-map') + 1] = str(out / 'init-live.map'); link.append(str(archive))
    attempt = run(link, 'init-live-link', True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', attempt.stderr, re.M)))
    duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", attempt.stderr)))
    if duplicates: raise ValueError('Private static symbol isolation incomplete: ' + repr(duplicates))
    if not attempt.returncode: raise ValueError('Unexpected completed startup link requires review')
    native = list(flags); index = native.index('-target'); del native[index:index + 2]; native.remove('-mcpu=cortex-a76')
    native += ['-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    for name in ('bzero', 'memset', 'memset_pattern4', 'memset_pattern8', 'memset_pattern16', 'strlen', 'memmove'):
        native += ['-D_platform_' + name + '=rpi5_native__platform_' + name]
    native_objects = [compile(native, platform / (name + '.c'), 'native-' + name) for name in implementations]
    # Do not rename the harness's libc reference oracle.
    harnessflags = list(native)
    harnessflags.remove('-Dmemset=rpi5_platform_private_memset')
    harness_obj = compile(harnessflags, harness, 'native-harness')
    host = out / 'memory-provider-host'
    run(native + [*native_objects, harness_obj, traps[1], '-o', host], 'native-link')
    result = run([host], 'native-run')
    if result.stderr: raise ValueError('Host diagnostics: ' + result.stderr)
    for path, digest in {**pins, **headers}.items():
        if sha(path) != digest: raise ValueError('Input drift: ' + path)
    report = dict(profile='genuine-apple-pthread-memory-and-registration-providers-v1',
        source_inputs_sha256=pins, headers_sha256=headers, commands=commands, units=units,
        syscall_numbers=CALLS, target_archive=str(archive), target_archive_sha256=sha(archive),
        scoped_pthread_archive=str(scoped_archive), scoped_pthread_archive_sha256=sha(scoped_archive),
        original_pthread_source=str(original), original_pthread_sha256=sha(original), private_wrapper_renames=renames,
        scoped_pthread_source=str(scoped), original_memory_implementation_bodies_unchanged=True,
        original_pthread_body_changes=False, explicit_static_namespace=True,
        target_missing_symbols=missing, target_duplicate_symbols=duplicates,
        native_stdout=result.stdout, host_asan_ubsan=True, host_real_exit=True,
        host_registration_executed=False, host_workqueue_executed=False,
        target_main_thread_initialized=False, target_startup_created=False,
        accepted_runtime_modified=False, pi_executed=False,
        generated_sha256={str(p): sha(p) for p in out.rglob('*') if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), missing=missing, duplicates=duplicates, host=result.stdout.strip()), indent=2))
    return out, report


if __name__ == '__main__': build()
