#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Real Apple emitters, kernel errno semantics, no manufactured pthread state."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'build/rpi5/apple-pthread-platform-check-m7im0unk'
BASE_SHA = '463cdcb6bd64b4cecb756ed1886288bb81b116a1ab3592ffa987a67dc0c2d6dd'
SYSCTL = ROOT / 'build/rpi5/apple-sysctl-runtime-nfhrya57'
CALLS = {'psynch_mutexwait': 301, 'psynch_mutexdrop': 302, 'ulock_wait': 515, 'ulock_wait2': 544, 'ulock_wake': 516}
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA: raise ValueError('Frozen receipt drift')
    baseline = json.loads((BASE / 'manifest.json').read_text())
    sysctl = json.loads((SYSCTL / 'manifest.json').read_text())
    pins = {str(BASE / 'manifest.json'): BASE_SHA}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'): pins.update(baseline[key])
    source = ROOT / 'tools/rpi5/user/pthread_wait_runtime_calls.S'
    harness = ROOT / 'tools/rpi5/tests/pthread_wait_syscalls_host.c'
    kernel_syscalls = ROOT / 'bsd/kern/syscalls.master'
    kernel_ulock = ROOT / 'bsd/kern/sys_ulock.c'
    for path in (source, harness, kernel_syscalls, kernel_ulock, Path(__file__).resolve()): pins[str(path)] = sha(path)
    for name, number in CALLS.items():
        if not re.search(r'^' + str(number) + r'\s+[^\n]*\b(?:sys_)?' + name + r'\(', kernel_syscalls.read_text(), re.M):
            raise ValueError('XNU syscall number mismatch: ' + name)
    out = Path(tempfile.mkdtemp(prefix='apple-pthread-wait-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers = [], {}
    def run(args, label, allowed=False):
        args = list(map(str, args)); result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=60)
        (out / (label + '.stdout')).write_text(result.stdout); (out / (label + '.stderr')).write_text(result.stderr)
        commands.append(dict(command=args, returncode=result.returncode, stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if result.returncode and not allowed: raise ValueError(label + ': ' + result.stderr)
        return result
    def deps(raw):
        return {str(Path(p).resolve()): sha(Path(p).resolve()) for p in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}
    old = next(r['command'] for r in sysctl['commands'] if r['stdout'].endswith('/syscall-deps.stdout'))
    flags = list(old[:old.index(str(ROOT / 'tools/rpi5/user/sysctl_runtime_calls.S'))])
    objects = []
    for label in ('target', 'host'):
        selected = list(flags)
        if label == 'host':
            selected += ['-D___' + name + '=_rpi5_host_' + name for name in CALLS]
            selected += ['-Dcerror_nocancel=rpi5_host_cerror']
        before = deps(run(selected + ['-M', source], label + '-deps').stdout)
        dep = out / (label + '.d')
        raw = run(selected + ['-E', '-P', source, '-MD', '-MF', dep], label + '-preprocess').stdout
        if deps(dep.read_text()) != before: raise ValueError('Actual trap dependency drift')
        headers.update(before)
        asm = out / (label + '.s'); asm.write_text(raw.replace(';', '\n'))
        obj = out / (label + '.o')
        run(selected[:selected.index('-I')] + ['-x', 'assembler', '-c', asm, '-o', obj], label + '-assemble')
        run(['xcrun', 'otool', '-tvV', obj], label + '-disassembly')
        objects.append(obj)
    archive = out / 'libapple-pthread-wait.a'
    run(['xcrun', 'ar', 'rcs', archive, objects[0]], 'archive')
    link = next(list(r['command']) for r in baseline['commands'] if r['stdout'].endswith('/target-static-link.stdout'))
    link[link.index('-o') + 1] = str(out / 'sshpacketprobe'); link[link.index('-map') + 1] = str(out / 'packet.map')
    link.append(str(archive))
    attempt = run(link, 'target-static-link', True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', attempt.stderr, re.M)))
    expected = ['__pthread_ptr_munge_token', '_abort_with_reason', '_pthread_equal']
    if not attempt.returncode or missing != expected: raise ValueError('Unexpected static dependency result: ' + attempt.stderr)
    compiler = flags[0]; sdk = flags[flags.index('-isysroot') + 1]
    native = [compiler, '-isysroot', sdk, '-g', '-std=c11', '-DPRIVATE=1', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
        '-fno-sanitize-recover=all', '-I', str(ROOT / 'bsd')]
    # Avoid exposing all kernel headers: an isolated byte-identical ulock header.
    include = out / 'include/sys'; include.mkdir(parents=True)
    ulock = ROOT / 'bsd/sys/ulock.h'; pins[str(ulock)] = sha(ulock)
    (include / 'ulock.h').write_bytes(ulock.read_bytes()); native[-1] = str(out / 'include')
    before = deps(run(native + ['-M', harness], 'harness-deps').stdout)
    dep = out / 'harness.d'; test_object = out / 'harness.o'
    run(native + ['-MD', '-MF', dep, '-c', harness, '-o', test_object], 'harness-compile')
    if deps(dep.read_text()) != before: raise ValueError('Actual harness dependency drift')
    headers.update(before)
    host = out / 'pthread-wait-host'; run(native + [test_object, objects[1], '-o', host], 'host-link')
    result = run([host], 'host-run')
    if result.stderr: raise ValueError('Host diagnostics: ' + result.stderr)
    for path, digest in {**pins, **headers}.items():
        if sha(path) != digest: raise ValueError('Input drift: ' + path)
    report = dict(profile='genuine-apple-pthread-wait-traps-v1', source_inputs_sha256=pins,
        headers_sha256=headers, commands=commands, syscall_numbers=CALLS,
        target_archive=str(archive), target_archive_sha256=sha(archive), target_missing_symbols=missing,
        native_stdout=result.stdout, host_asan_ubsan=True, real_host_kernel_syscalls=True,
        host_errors=96000, host_timeouts=2, host_wake=1, host_psynch_executed=False,
        kernel_owns_no_errno_conversion=True, original_syscall_emitter=True,
        target_link_complete=False, pthread_state_invented=False, target_startup_created=False,
        target_errno_kernel_semantics_executed=False, pi_executed=False,
        generated_sha256={str(p): sha(p) for p in out.rglob('*') if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), host=result.stdout.strip(), missing=missing), indent=2))
    return out, report


if __name__ == '__main__': build()
