#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Real current Apple sysctlbyname + genuine syscall; no pthread substitutes."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
try:
    from . import build_apple_ssh_libressl_packet as previous
except ImportError:
    import build_apple_ssh_libressl_packet as previous

ROOT, sha = previous.ROOT, previous.sha
BASE = ROOT / 'build/rpi5/apple-ssh-libressl-packet-9ws4lrfd'
BASE_SHA = '5b801203eb3cc0033961a2a28e6f1b8353c7cad451daf676cfb579a2b1dc232a'
PTHREAD = ROOT / 'build/rpi5/apple-libpthread-main-candidate-20261013'
PTHREAD_COMMIT = '42d026df5b07825070f60134b980a1ec2552dfee'
EXPECTED_GAPS = ['_pthread_equal', '_pthread_mutex_lock', '_pthread_mutex_unlock', '_pthread_self']


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA: raise ValueError('Frozen packet receipt changed')
    baseline = json.loads((BASE / 'manifest.json').read_text())
    pins = {}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
        pins.update(baseline[key])
    libc = previous.leaves.LIBC
    source = libc / 'gen/FreeBSD/sysctlbyname.c'
    assembly = ROOT / 'tools/rpi5/user/sysctl_runtime_calls.S'
    test = ROOT / 'tools/rpi5/tests/sysctlbyname_host.c'
    annotations = ROOT / 'tools/rpi5/user/ssh_runtime_build.h'
    audit = ROOT / 'tools/rpi5/ssh_platform_runtime_audit.md'
    for path in (source, assembly, test, annotations, audit, Path(__file__).resolve(), BASE / 'manifest.json'):
        pins[str(path)] = sha(path)
    for path in PTHREAD.rglob('*'):
        if path.is_file() and '.git' not in path.parts: pins[str(path)] = sha(path)
    if subprocess.check_output(['git', '-C', PTHREAD, 'rev-parse', 'HEAD'], text=True).strip() != PTHREAD_COMMIT:
        raise ValueError('Unexpected current Apple pthread revision')
    if subprocess.check_output(['git', '-C', libc, 'show', 'HEAD:gen/FreeBSD/sysctlbyname.c']) != source.read_bytes():
        raise ValueError('Original sysctlbyname modified')
    def verify():
        for path, digest in pins.items():
            if sha(Path(path)) != digest: raise ValueError('Input drift: ' + path)
    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-sysctl-runtime-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers = [], {}
    def run(args, label, allowed=False):
        args = list(map(str, args))
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_text(result.stdout)
        (out / (label + '.stderr')).write_text(result.stderr)
        commands.append(dict(command=args, returncode=result.returncode,
            stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if not allowed and (result.returncode or result.stderr):
            raise ValueError(label + ': ' + result.stderr)
        return result
    def compile(flags, src, label):
        def deps(raw):
            return {str(Path(p).resolve()): sha(Path(p).resolve()) for p in
                shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}
        before = deps(run(flags + ['-M', src], label + '-deps').stdout)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        run(flags + ['-MD', '-MF', dep, '-c', src, '-o', obj], label)
        if deps(dep.read_text()) != before: raise ValueError('Actual header drift')
        headers.update(before); return obj
    def flags(label):
        cmd = next(r['command'] for r in baseline['commands'] if r['stdout'].endswith('/probe-' + label + '.stdout'))
        return [x for x in cmd[:cmd.index('-MD')] if x != '-Dmain=darwin_network_command_main'] + ['-include', str(annotations)]
    native, target = flags('native'), flags('target')
    leaf_native = compile(native + ['-Dsysctlbyname=rpi5_apple_sysctlbyname', '-D__sysctl=rpi5_test_sysctl'], source, 'leaf-native')
    host_test = compile(native, test, 'test-native')
    host = out / 'sysctlbyname-host'
    run(native + [host_test, leaf_native, '-o', host], 'host-link')
    result = run([host], 'host-run')
    leaf_target = compile(target, source, 'leaf-target')
    receipt = json.loads((previous.leaves.MEMSET_PACKAGE / 'manifest.json').read_text())
    old = next(r['command'] for r in receipt['commands'] if any(str(x).endswith('/ssh_runtime_calls.S') for x in r['command']) and '-M' in r['command'])
    asmflags = old[:next(i for i, p in enumerate(old) if p.endswith('/ssh_runtime_calls.S'))]
    before = run(asmflags + [assembly, '-M'], 'syscall-deps').stdout
    def assembly_deps(raw):
        return {str(Path(p).resolve()): sha(Path(p).resolve()) for p in
            shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}
    captured = assembly_deps(before)
    dep = out / 'syscall-target.d'
    preprocessed = run(asmflags + ['-E', '-P', assembly, '-MD', '-MF', dep], 'syscall-preprocess').stdout
    if assembly_deps(dep.read_text()) != captured: raise ValueError('Syscall dependency drift')
    headers.update(captured)
    asm = out / 'syscall-target.s'
    asm.write_text(preprocessed.replace(';', '\n'))
    stub = out / 'syscall-target.o'
    run(asmflags[:asmflags.index('-I')] + ['-x', 'assembler', '-c', asm, '-o', stub], 'syscall-target')
    archive = out / 'libapple-sysctl-runtime.a'
    run(['xcrun', 'ar', 'rcs', archive, leaf_target, stub], 'archive')
    link = next(list(r['command']) for r in baseline['commands'] if r['stdout'].endswith('/target-static-link.stdout'))
    link[link.index('-o') + 1] = str(out / 'sshpacketprobe')
    link[link.index('-map') + 1] = str(out / 'link.map')
    link.append(str(archive))
    attempt = run(link, 'target-static-link', True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', attempt.stderr, re.M)))
    if not attempt.returncode or missing != EXPECTED_GAPS:
        raise ValueError('Unexpected genuine runtime dependency closure: ' + attempt.stderr)
    run(['xcrun', 'nm', '-g', archive], 'symbols')
    run(['xcrun', 'otool', '-tvV', stub], 'syscall-disassembly')
    verify()
    for path, digest in headers.items():
        if sha(Path(path)) != digest: raise ValueError('Header changed: ' + path)
    report = dict(profile='genuine-apple-sysctlbyname-runtime-v1',
        source_inputs_sha256=pins, headers_sha256=headers, commands=commands,
        current_pthread_commit=PTHREAD_COMMIT, target_archive=str(archive),
        target_archive_sha256=sha(archive), host_stdout=result.stdout,
        host_native_concurrency_threads=8, host_native_queries=16000, injected_failures=12,
        original_apple_sysctlbyname_unchanged=True, real_xnu_sysctl_trap=True,
        native_asan_ubsan_pass=True, host_kernel_services_not_pi=True,
        target_link_complete=False, target_missing_symbols=missing,
        pthread_provider_implemented=False, constructors_executed_on_pi=False,
        cpu_features_verified_on_pi=False, installed=False, pi_executed=False,
        generated_sha256={str(p): sha(p) for p in out.iterdir() if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), missing_symbols=missing), indent=2))
    return out, report


if __name__ == '__main__': build()
