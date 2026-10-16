#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original Apple strncpy_chk/stpncpy with explicit original overlap limits."""
import json
from pathlib import Path
import re
import shlex
import signal
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_libc_prereqs as libc

ROOT, sha, LIBC = libc.ROOT, libc.sha, libc.LIBC
BASE = ROOT / 'build/rpi5/apple-ssh-interface-helpers-o1gdvmp_'
BASE_SHA = '2165e237397a2d7ce8e364f6469a8044be29ce62575d3b985a1f68b372fe6f0f'
FORTIFY = ROOT / 'build/rpi5/apple-fortify-runtime-punnvr0c'
FORTIFY_SHA = 'adcab45b4082c864520a6101d4fc5efa8e2ada095aa1a23b4dbc01aaeb3cc365'
SOURCES = {'strncpy_chk': LIBC / 'secure/strncpy_chk.c', 'stpncpy': LIBC / 'string/stpncpy.c'}
HOST = ROOT / 'tools/rpi5/tests/apple_strncpy_chk_host.c'
EXPECTED = 'APPLE_STRNCPY_CHK PASS VALID=332304 UNTERMINATED=129 OVERFLOW_PREWRITE=2 OVERLAP_AFTERWRITE=1 ORIGINAL_CALLER_TRAP=1\n'
OVERLAP = 'APPLE_STRNCPY_CHK NONEMPTY_OVERLAP ORIGINAL_FAILURE_AFTER_COPY\n'


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA or sha(FORTIFY / 'manifest.json') != FORTIFY_SHA:
        raise ValueError('Frozen predecessor/fortify receipt changed')
    base = json.loads((BASE / 'manifest.json').read_text())
    original = json.loads((FORTIFY / 'manifest.json').read_text())
    pins = {str(BASE / 'manifest.json'): BASE_SHA, str(FORTIFY / 'manifest.json'): FORTIFY_SHA}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
        for name, digest in base[key].items():
            if name in pins and pins[name] != digest: raise ValueError('Inherited pin conflict')
            pins[name] = digest
    if subprocess.check_output(['git', '-C', str(LIBC), 'rev-parse', 'HEAD'], text=True).strip() != libc.COMMIT:
        raise ValueError('Original Apple Libc commit changed')
    policy = LIBC / 'xcodescripts/libc.xcconfig'
    for path in (*SOURCES.values(), policy, LIBC / 'secure/secure.h'):
        if subprocess.check_output(['git', '-C', str(LIBC), 'show', 'HEAD:' + str(path.relative_to(LIBC))]) != path.read_bytes():
            raise ValueError('Whole original source or provider policy changed')
    if '_FORTIFY_SOURCE=0' not in policy.read_text(): raise ValueError('Original provider policy missing')
    for path in (Path(__file__).resolve(), HOST, *SOURCES.values(), policy):
        if str(path) in pins and pins[str(path)] != sha(path): raise ValueError('Pinned input changed')
        pins[str(path)] = sha(path)
    def verify():
        for name, digest in pins.items():
            if sha(name) != digest: raise ValueError('Pinned input drift: ' + name)
    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-ssh-strncpy-chk-', dir=ROOT / 'build/rpi5'))
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
        if actual != before: raise ValueError('Actual consumed dependency closure differs')
        records[label] = dict(scanned_sha256=before, consumed_sha256=actual); headers.update(actual)
        return obj
    old = next(c['command'] for c in original['commands'] if c['stdout'].endswith('/target-strcpy_chk-compile.stdout'))
    target = old[:old.index('-MD')]
    if '-D_FORTIFY_SOURCE=0' not in target: raise ValueError('Provider-only original policy missing')
    native_old = next(c['command'] for c in original['commands'] if c['stdout'].endswith('/native-chk_fail-compile.stdout'))
    native = native_old[:native_old.index('-MD')] + ['-D__strncpy_chk=fixture___strncpy_chk', '-Dstpncpy=fixture_stpncpy']
    objects = {name: compile_(target, path, 'target-' + name) for name, path in SOURCES.items()}
    host = [compile_(native, path, 'native-' + name) for name, path in SOURCES.items()]
    caller = compile_(native, HOST, 'native-caller'); executable = out / 'host-strncpy-chk'
    run(native + [caller, *host, FORTIFY / 'native-chk_fail.o', FORTIFY / 'native-crash.o',
                  '-Wl,-map,' + str(out / 'native.map'), '-o', executable], 'native-link')
    result = run([executable], 'native-run')
    if (result.stdout, result.stderr) != (EXPECTED, ''): raise ValueError('Native original bounds/truncation oracle failed')
    negative = run([executable, 'nonempty-overlap'], 'native-overlap-negative', True)
    original_overlap_trap = negative.returncode in (-signal.SIGILL, -signal.SIGTRAP) and (negative.stdout, negative.stderr) == (OVERLAP, '')
    asan_overlap_rejection = bool(negative.returncode and 'AddressSanitizer: memcpy-param-overlap' in negative.stderr)
    if not original_overlap_trap and not asan_overlap_rejection:
        raise ValueError('Original nonempty overlap did not expose its actual pre-check copy/failure')
    archive = out / 'libapple-ssh-strncpy-chk.a'
    run(['xcrun', 'ar', 'rcs', archive, *objects.values()], 'archive')
    run(['xcrun', 'nm', '-g', archive], 'symbols')
    run(['xcrun', 'llvm-objdump', '-d', '-r', *objects.values()], 'disassembly')
    link = list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o') + 1] = str(out / 'NOT_RUN_ssh'); link[link.index('-map') + 1] = str(out / 'target.map')
    link.append(str(archive)); result = run(link, 'target-link', True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', result.stderr, re.M)))
    duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", result.stderr)))
    closed, added = set(base['target_missing_symbols']) - set(missing), set(missing) - set(base['target_missing_symbols'])
    if not result.returncode or duplicates or closed != {'___strncpy_chk'}:
        raise ValueError('Unexpected original-provider full-client delta')
    verify()
    for name, digest in headers.items():
        if sha(name) != digest: raise ValueError('Consumed header drift')
    report = dict(profile='apple-original-full-ssh-strncpy-chk-stpncpy-v1', source_inputs_sha256=pins,
        headers_sha256=headers, dependency_records=records, commands=commands, original_libc_commit=libc.COMMIT,
        whole_original_translation_units_compiled=['secure/strncpy_chk.c', 'string/stpncpy.c'],
        original_sources_unchanged=True, provider_only_fortify_source=0, consumer_flags_unchanged=True,
        original_bounds_checked_before_copy=True, original_overlap_checked_after_copy=True,
        original_overlap_after_padding_write_observed=True,
        native_nonempty_overlap_original_trap_after_write_observed=original_overlap_trap,
        native_nonempty_overlap_asan_rejection_observed=asan_overlap_rejection,
        overlap_prewrite_safety_claimed=False, original_zero_length_and_unterminated_source_semantics_retained=True,
        target_archive=str(archive), objects={name: str(path) for name, path in objects.items()},
        native_stdout=EXPECTED, native_asan_ubsan_valid_and_fatal_cases_pass=True,
        native_runtime_boundary=['original stpncpy with host strnlen/memcpy/memset',
            'frozen genuine Apple chk_fail/crash callback and caller trap', 'host allocator, fork, pipe, wait'],
        previous_missing_count=len(base['target_missing_symbols']), closed_symbols=sorted(closed),
        newly_reachable_symbols=sorted(added), target_missing_symbols=missing, target_duplicate_symbols=duplicates,
        original_openssh_config_unchanged=True, provider_stubs=False, target_link_complete=False,
        target_executed=False, accepted_runtime_modified=False, host_account_files_accessed=False,
        network_services_executed=False, generated_sha256={str(p): sha(p) for p in out.rglob('*') if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), manifest_sha256=sha(out / 'manifest.json'),
        closed=sorted(closed), new=sorted(added), remaining=len(missing)), indent=2))
    return out, report


if __name__ == '__main__': build()
