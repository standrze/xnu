#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compile exact selected Apple API bodies with a small public-header boundary.

This selects source fragments, not whole libmalloc/libtrace translation units.
The existing real allocator and the original caller's crash trap remain owners.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_client_leaves as previous

ROOT, sha = previous.ROOT, previous.sha
BASE = ROOT / 'build/rpi5/apple-ssh-runtime-groups-12k4lp6u'
BASE_SHA = 'b1bc88e185700a8cfd0c55f6ccc3fa81fb5072f7e242b458026ca081924eb552'
LIBC = ROOT / 'build/rpi5/apple-libc-main-candidate-20261013'
MALLOC = ROOT / 'build/rpi5/apple-libmalloc-main-candidate-20261013'
PINS = {
    MALLOC / 'src/malloc.c': '756266669e8251f475d8939a3770f4d430b644104b9f3cb65460c71edea94ec6',
    MALLOC / 'src/base.h': '2671b62f0f79926aa5ec5fa92bd6dbff6dcbfb415d33d63838747cd97719f494',
    LIBC / 'os/assumes.c': '6fb0ca27e284fd65e09d522985b8b1e485009194308573bcbbcfcbf39ac3e3e2',
    LIBC / 'os/assumes.h': '7b15fe8e9e26cf81bfcc785c014edfb2babcf619e22a09ee0949d4ac427e6379',
}
COMMITS = {LIBC: '71bbe350ab79eef58113991d817ccc6165061a64',
           MALLOC: 'c49dafa25f1efe8607701ae6014a663ad2ee437f'}
HOST = ROOT / 'tools/rpi5/tests/apple_runtime_api_fragments_host.c'
EXPECTED = 'APPLE_RUNTIME_API_FRAGMENTS PASS REALLOCF=8 CRASH_CALLBACK=2 CALLER_TRAP=1 HOST_DOUBLES\n'


def between(text, start, end):
    if text.count(start) != 1:
        raise ValueError('Original fragment start is ambiguous')
    begin = text.index(start)
    finish = text.find(end, begin + len(start))
    if finish < 0:
        raise ValueError('Original fragment end is absent')
    return text[begin:finish]


def fragments():
    malloc = (MALLOC / 'src/malloc.c').read_text()
    crash = (LIBC / 'os/assumes.c').read_text()
    header = (LIBC / 'os/assumes.h').read_text()
    noinline = '#define MALLOC_NOINLINE __attribute__((noinline))\n'
    if (MALLOC / 'src/base.h').read_text().count(noinline) != 1:
        raise ValueError('Original noinline definition changed')
    typedef = 'typedef void (*os_crash_callback_t) (const char *);\n'
    trap = '#define os_hardware_trap() __asm__ __volatile__ (""); __builtin_trap()\n'
    if header.count(typedef) != 1 or header.count(trap) != 1:
        raise ValueError('Original callback/trap declaration changed')
    simple = between(header, '#define __os_crash_simple(msg)', '\n#if defined(OS_CRASH_ENABLE_EXPERIMENTAL_LIBTRACE)')
    accessors = between(header, 'extern os_crash_callback_t _os_crash_callback;', '\n#define os_crash_redirect(func)')
    api_header = ('#include <stddef.h>\n#include <stdlib.h>\n#include <errno.h>\n'
        '#include <sys/_types/_errno_t.h>\n#include <TargetConditionals.h>\n' +
        noinline + typedef + 'void _os_crash(const char *);\n' + accessors + '\n' + trap + simple)
    reallocf = between(malloc, 'MALLOC_NOINLINE\nvoid *\nreallocf(', '\nMALLOC_NOINLINE\nvoid *\nvalloc(')
    reporting = between(crash, '#if __has_include(<CrashReporterClient.h>)', '\n#if !TARGET_OS_DRIVERKIT\nstatic const char *')
    implementation = between(crash, 'os_crash_callback_t _os_crash_callback = NULL;', '\n#if !TARGET_OS_DRIVERKIT\n__attribute__((always_inline))\nstatic inline bool')
    public = between(crash, 'void _os_crash(const char *message)', '\n#if !TARGET_OS_DRIVERKIT\nvoid _os_crash_fmt')
    # Retain the complete original leading license in each derived source.
    return dict(header=api_header,
        reallocf=malloc[:malloc.index('*/') + 2] + '\n#include "selected-apis.h"\n' + reallocf + '\n',
        crash=crash[:crash.index('*/') + 2] + '\n#include "selected-apis.h"\n' + reporting + '\n' + implementation + '\n' + public + '\n')


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA:
        raise ValueError('Frozen full-client composition changed')
    base = json.loads((BASE / 'manifest.json').read_text())
    pins = {str(BASE / 'manifest.json'): BASE_SHA}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
        for name, digest in base.get(key, {}).items():
            if name in pins and pins[name] != digest:
                raise ValueError('Conflicting inherited input')
            pins[name] = digest
    for repository, commit in COMMITS.items():
        actual = subprocess.check_output(['git', '-C', str(repository), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != commit:
            raise ValueError('Wrong current Apple source commit')
    for path, digest in PINS.items():
        repository = MALLOC if path.is_relative_to(MALLOC) else LIBC
        if sha(path) != digest or subprocess.check_output(
                ['git', '-C', str(repository), 'show', 'HEAD:' + str(path.relative_to(repository))]) != path.read_bytes():
            raise ValueError('Original Apple source changed')
        pins[str(path)] = digest
    for path in (Path(__file__).resolve(), HOST):
        pins[str(path)] = sha(path)

    def verify():
        for name, digest in pins.items():
            if sha(name) != digest:
                raise ValueError('Input drift: ' + name)

    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-runtime-api-fragments-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    text = fragments()
    generated = {}
    for key, filename in (('header', 'selected-apis.h'), ('reallocf', 'selected-reallocf.c'), ('crash', 'selected-crash.c')):
        path = out / filename; path.write_text(text[key]); generated[key] = path
    commands, headers, records = [], {}, {}

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

    def deps(raw):
        return {str(Path(name).resolve()): sha(Path(name).resolve())
            for name in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}

    def compile_(flags, source, label):
        before = deps(run(flags + ['-M', source], label + '-scan').stdout)
        dep, obj = out / (label + '.d'), out / (label + '.o')
        run(flags + ['-MD', '-MF', dep, '-c', source, '-o', obj], label + '-compile')
        consumed = deps(dep.read_text())
        if consumed != before:
            raise ValueError('Actual consumed source/header membership differs')
        records[label] = dict(scanned_sha256=before, consumed_sha256=consumed)
        headers.update(before)
        return obj

    source = json.loads((previous.BASE / 'manifest.json').read_text())
    old = next(c['command'] for c in source['commands'] if c['stdout'].endswith('/000-ssh_api-compile.stdout'))
    target = old[:old.index('-MD')] + ['-I', str(out)]
    native = [flag for flag in target if flag not in ('-ffreestanding', '-mcpu=cortex-a76')]
    at = native.index('-target'); del native[at:at + 2]
    native += ['-O1', '-g', '-fsanitize=address,undefined'] + [
        '-D' + name + '=fixture_' + name for name in ('reallocf', 'realloc', 'free', '_os_crash', '_os_crash_callback')]
    target_objects = [compile_(target, generated[name], 'target-' + name) for name in ('reallocf', 'crash')]
    native_objects = [compile_(native, generated[name], 'native-' + name) for name in ('reallocf', 'crash')]
    caller = compile_(native, HOST, 'native-caller')
    executable = out / 'host-contract'
    run(native + [caller, *native_objects, '-o', executable], 'native-link')
    result = run([executable], 'native-run')
    if result.stdout != EXPECTED or result.stderr:
        raise ValueError('Original selected API contract failed: ' + repr(result))
    archive = out / 'libapple-selected-runtime-apis.a'
    run(['xcrun', 'ar', 'rcs', archive, *target_objects], 'archive')
    run(['xcrun', 'nm', '-g', archive], 'symbols')
    run(['xcrun', 'llvm-objdump', '-d', '-r', *target_objects], 'disassembly')
    link = list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o') + 1] = str(out / 'NOT_RUN_ssh')
    link[link.index('-map') + 1] = str(out / 'target.map')
    link.append(str(archive)); result = run(link, 'target-link', True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', result.stderr, re.M)))
    duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", result.stderr)))
    closed = set(base['target_missing_symbols']) - set(missing)
    added = set(missing) - set(base['target_missing_symbols'])
    if not result.returncode or duplicates or closed != {'__os_crash', '_reallocf'} or added:
        raise ValueError('Unexpected full-client selected-API delta: ' + result.stderr[-6000:])
    verify()
    for name, digest in headers.items():
        if sha(name) != digest:
            raise ValueError('Consumed input drift')
    report = dict(profile='current-apple-selected-reallocf-crash-bodies-v1',
        source_inputs_sha256=pins, headers_sha256=headers, dependency_records=records,
        commands=commands, original_commits={str(p): h for p, h in COMMITS.items()},
        generated_fragment_files={name: str(path) for name, path in generated.items()},
        selected_function_bodies_unchanged=True, whole_original_translation_units_compiled=False,
        original_license_headers_preserved=True, public_header_boundary_project_selected=True,
        existing_allocator_unchanged=True, original_crash_callback_retained=True,
        original_caller_trap_retained=True, full_libmalloc_or_logging_qualified=False,
        native_asan_ubsan_pass=True, host_allocator_calls_are_explicit_doubles=True,
        native_stdout=EXPECTED, target_archive=str(archive),
        previous_missing_count=len(base['target_missing_symbols']), closed_symbols=sorted(closed),
        newly_reachable_dependencies=sorted(added), target_missing_symbols=missing,
        remaining_provider_groups=previous.categories(missing), target_duplicate_symbols=duplicates,
        target_link_complete=False, target_executed=False, live_keys=False,
        original_openssh_config_unchanged=True, accepted_runtime_modified=False,
        generated_sha256={str(p): sha(p) for p in out.iterdir() if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), closed=sorted(closed), remaining=len(missing)), indent=2))
    return out, report


if __name__ == '__main__':
    build()
