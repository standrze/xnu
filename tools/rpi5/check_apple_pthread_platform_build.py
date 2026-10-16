#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserved target archive, real packet link, isolated original host primitives."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'build/rpi5/apple-pthread-platform-linkable-ydcl_6yv'
BASE_SHA = 'c31e25c5c81d14423d3204f6e9f215f2a15f6da35b63d4dd7b378d8bce45138c'
SYSCTL = ROOT / 'build/rpi5/apple-sysctl-runtime-nfhrya57'
SYSCTL_SHA = '6f42910a9bce37cd42d43a4febadee40498edd57c484d0312048c6a34413bd91'
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    pins = {str(Path(__file__).resolve()): sha(__file__)}
    receipts = []
    for package, expected in ((BASE, BASE_SHA), (SYSCTL, SYSCTL_SHA)):
        manifest = package / 'manifest.json'
        if sha(manifest) != expected: raise ValueError('Frozen input receipt drift')
        pins[str(manifest)] = expected
        receipt = json.loads(manifest.read_text()); receipts.append(receipt)
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            pins.update(receipt[key])
    base, sysctl = receipts
    harness = ROOT / 'tools/rpi5/tests/apple_platform_concurrency_host.c'
    pins[str(harness)] = sha(harness)
    def verify():
        for path, digest in pins.items():
            if sha(path) != digest: raise ValueError('Input drift: ' + path)
    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-pthread-platform-check-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers = [], {}
    def run(args, label, must_pass=True):
        args = list(map(str, args))
        proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=60)
        (out / (label + '.stdout')).write_text(proc.stdout)
        (out / (label + '.stderr')).write_text(proc.stderr)
        commands.append(dict(command=args, returncode=proc.returncode,
            stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if must_pass and proc.returncode: raise ValueError(label + ': ' + proc.stderr)
        return proc
    # This is a diagnostic link, not a replacement bootstrap. Preserve the
    # accepted startup and its incompatible key map so collisions remain visible.
    link = next(list(r['command']) for r in sysctl['commands'] if r['stdout'].endswith('/target-static-link.stdout'))
    link[link.index('-o') + 1] = str(out / 'sshpacketprobe')
    link[link.index('-map') + 1] = str(out / 'packet.map')
    link.append(base['partial_archive'])
    attempt = run(link, 'target-static-link', False)
    if attempt.returncode == 0: raise ValueError('Unexpected complete link; review startup before accepting')
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', attempt.stderr, re.M)))
    duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", attempt.stderr)))
    # Only rename definitions to isolate the test module from host libSystem.
    # All algorithms/configuration and original source bytes remain unchanged.
    labels = ('platform-lock', 'platform-atomic', 'platform-semaphore')
    symbols = set()
    for label in labels:
        text = run(['xcrun', 'nm', '-g', BASE / (label + '.o')], label + '-symbols').stdout
        for name in re.findall(r'^[0-9a-f]+ [TSD] (_[A-Za-z_][A-Za-z_0-9]*)$', text, re.M):
            symbols.add(name[1:])
    namespace = out / 'native_namespace.h'
    namespace.write_text('/* Test isolation only; target archive is untouched. */\n' +
        ''.join('#define ' + s + ' rpi5_native_' + s + '\n' for s in sorted(symbols)))
    def deps(raw):
        return {str(Path(p).resolve()): sha(Path(p).resolve()) for p in
            shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}
    objects = []
    native_flags = None
    for label in (*labels, 'harness'):
        original_label = labels[0] if label == 'harness' else label
        command = next(r['command'] for r in base['commands'] if r['stdout'].endswith('/' + original_label + '-compile.stdout'))
        flags = list(command[:command.index('-H')])
        for option in ('-target', '-mcpu=cortex-a76'):
            if option == '-target':
                index = flags.index(option); del flags[index:index + 2]
            else: flags.remove(option)
        flags += ['-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-include', str(namespace)]
        source = harness if label == 'harness' else Path(next(u['source'] for u in base['units'] if u['label'] == label))
        before = deps(run(flags + ['-M', source], label + '-native-deps').stdout)
        obj, dep = out / (label + '-native.o'), out / (label + '-native.d')
        run(flags + ['-MD', '-MF', dep, '-c', source, '-o', obj], label + '-native')
        if deps(dep.read_text()) != before: raise ValueError('Native actual dependency mismatch')
        headers.update(before); objects.append(obj)
        native_flags = flags
    host = out / 'apple-platform-host'
    run(native_flags + objects + ['-o', host], 'native-link')
    result = run([host], 'native-run')
    if result.stderr: raise ValueError('Native runtime diagnostics: ' + result.stderr)
    verify()
    for path, digest in headers.items():
        if sha(path) != digest: raise ValueError('Native consumed input drift')
    report = dict(profile='original-apple-platform-concurrency-and-link-v1',
        source_inputs_sha256=pins, headers_sha256=headers, commands=commands,
        target_compiled_units=base['compiled_units'], target_attempted_units=base['attempted_units'],
        original_target_archive=base['partial_archive'], target_archive_sha256=sha(base['partial_archive']),
        target_missing_symbols=missing, target_duplicate_symbols=duplicates,
        target_link_complete=False, original_target_algorithms_unchanged=True,
        native_namespaced_symbols=sorted(symbols), native_asan_ubsan=True,
        native_stdout=result.stdout, host_real_pthread_and_mach_services=True,
        native_original_platform_units=list(labels), native_pthread_implementation_tested=False,
        target_main_pthread_compiles=False, pthread_runtime_qualified=False,
        accepted_startup_modified=False, installed=False, pi_executed=False,
        generated_sha256={str(p): sha(p) for p in out.rglob('*') if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), host=result.stdout.strip(), missing=missing, duplicates=duplicates), indent=2))
    return out, report


if __name__ == '__main__': build()
