#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Namespaced genuine generated Mach host calls against the real host kernel."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'build/rpi5/apple-pthread-mach-linkable-9lq6yta2'
BASE_SHA = '96e38dda4d72ea8cdfe7d5a9e318dab08ed4a0a02b99eb7d11709d55ab3096af'
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA: raise ValueError('Frozen input drift')
    base = json.loads((BASE / 'manifest.json').read_text())
    pins = {str(BASE / 'manifest.json'): BASE_SHA, str(Path(__file__).resolve()): sha(__file__)}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'): pins.update(base[key])
    harness = ROOT / 'tools/rpi5/tests/pthread_mig_host.c'; pins[str(harness)] = sha(harness)
    out = Path(tempfile.mkdtemp(prefix='apple-pthread-mach-check-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers = [], {}
    def run(args, label, allowed=False):
        args = list(map(str, args)); proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=60)
        (out / (label + '.stdout')).write_text(proc.stdout); (out / (label + '.stderr')).write_text(proc.stderr)
        commands.append(dict(command=args, returncode=proc.returncode, stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if proc.returncode and not allowed: raise ValueError(label + ': ' + proc.stderr)
        return proc
    def deps(raw): return {str(Path(p).resolve()): sha(Path(p).resolve()) for p in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}
    def compile(flags, source, label):
        before = deps(run(flags + ['-M', source], label + '-deps').stdout)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        run(flags + ['-MD', '-MF', dep, '-c', source, '-o', obj], label + '-compile')
        if deps(dep.read_text()) != before: raise ValueError('Consumed header mismatch')
        headers.update(before); return obj
    command = next(c['command'] for c in base['commands'] if c['stdout'].endswith('/mach_host-mig-user-compile.stdout'))
    flags = list(command[:command.index('-MD')])
    index = flags.index('-target'); del flags[index:index + 2]; flags.remove('-mcpu=cortex-a76')
    flags += ['-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    symbols = run(['xcrun', 'nm', '-g', BASE / 'mach_host-mig-user.o'], 'target-host-symbols').stdout
    names = re.findall(r'^[0-9a-f]+ T _([a-zA-Z_0-9]+)$', symbols, re.M)
    renamed = flags + ['-D' + name + '=rpi5_native_' + name for name in names]
    obj = compile(renamed, BASE / 'mach_hostUser.c', 'native-mig')
    test = compile(flags, harness, 'native-harness')
    binary = out / 'mig-host-info'
    link = run(flags + [obj, test, '-Wl,-dead_strip', '-o', binary], 'native-link', True)
    result = run([binary], 'native-run') if not link.returncode else None
    for path, digest in {**pins, **headers}.items():
        if sha(path) != digest: raise ValueError('Source drift: ' + path)
    report = dict(profile='original-apple-mig-host-info-native-check-v1', source_inputs_sha256=pins,
        headers_sha256=headers, commands=commands, namespaced_definitions=names,
        native_linked=not link.returncode, native_stdout=result.stdout if result else None,
        native_asan_ubsan=True, native_runtime_executed=bool(result),
        real_host_kernel=bool(result), no_target_implementation_changes=True,
        target_startup_created=False, target_main_thread_initialized=False, pi_executed=False,
        generated_sha256={str(p): sha(p) for p in out.rglob('*') if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), host=report['native_stdout'], linked=report['native_linked'], link_error=link.stderr[:400] if link.returncode else None), indent=2))
    return out, report


if __name__ == '__main__': build()
