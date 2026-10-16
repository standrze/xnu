#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Validate explicit Pi capability selection and expose true startup imports."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'build/rpi5/apple-pthread-bcm2712-qualified-x9kp1ral'
BASE_SHA = 'a1f0a4a25efad30a2fb152e5c3a0b0797348deea88786bb28546310ca9e1f00b'
WAIT = ROOT / 'build/rpi5/apple-pthread-wait-if5o744t'
WAIT_SHA = '394565fbae712065b2a09adbdde6eb681ddc3045562ba3c5ccb62fcbbc95b23d'
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    receipts, pins = [], {str(Path(__file__).resolve()): sha(__file__)}
    for package, expected in ((BASE, BASE_SHA), (WAIT, WAIT_SHA)):
        path = package / 'manifest.json'
        if sha(path) != expected: raise ValueError('Frozen input receipt drift')
        pins[str(path)] = expected
        report = json.loads(path.read_text()); receipts.append(report)
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'): pins.update(report[key])
    base, wait = receipts
    harness = ROOT / 'tools/rpi5/tests/pthread_jit_unsupported_host.c'
    abort_source = ROOT / 'libsyscall/wrappers/terminate_with_reason.c'
    abort_assembly = ROOT / 'tools/rpi5/user/pthread_abort_runtime_calls.S'
    for path in (harness, abort_source, abort_assembly): pins[str(path)] = sha(path)
    out = Path(tempfile.mkdtemp(prefix='apple-pthread-bcm2712-check-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers = [], {}
    def run(args, label, allowed=False):
        args = list(map(str, args)); proc = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=60)
        (out / (label + '.stdout')).write_text(proc.stdout); (out / (label + '.stderr')).write_text(proc.stderr)
        commands.append(dict(command=args, returncode=proc.returncode, stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if proc.returncode and not allowed: raise ValueError(label + ': ' + proc.stderr)
        return proc
    def deps(raw):
        return {str(Path(p).resolve()): sha(Path(p).resolve()) for p in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}
    def compile(flags, source, label):
        before = deps(run(flags + ['-M', source], label + '-deps').stdout)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        run(flags + ['-MD', '-MF', dep, '-c', source, '-o', obj], label + '-compile')
        if deps(dep.read_text()) != before: raise ValueError('Actual dependency mismatch')
        headers.update(before); return obj
    original_compile = next(r['command'] for r in base['commands'] if r['stdout'].endswith('/pthread-pthread-compile.stdout'))
    flags = list(original_compile[:original_compile.index('-H')])
    # This is the full original libsyscall wrapper, not a replacement abort.
    abort_object = compile(flags + ['-include', 'sys/cdefs.h'], abort_source, 'abort-target')
    original_asm = next(r['command'] for r in wait['commands'] if r['stdout'].endswith('/target-deps.stdout'))
    asmflags = list(original_asm[:original_asm.index('-M')])
    before = deps(run(asmflags + ['-M', abort_assembly], 'abort-trap-deps').stdout)
    dep = out / 'abort-trap.d'
    raw = run(asmflags + ['-E', '-P', abort_assembly, '-MD', '-MF', dep], 'abort-trap-preprocess').stdout
    if deps(dep.read_text()) != before: raise ValueError('Trap dependency mismatch')
    headers.update(before)
    asm = out / 'abort-trap.s'; asm.write_text(raw.replace(';', '\n'))
    trap = out / 'abort-trap.o'; run(asmflags[:asmflags.index('-I')] + ['-x', 'assembler', '-c', asm, '-o', trap], 'abort-trap-assemble')
    archive = out / 'libapple-abort-reason.a'; run(['xcrun', 'ar', 'rcs', archive, abort_object, trap], 'abort-archive')
    link = next(list(r['command']) for r in wait['commands'] if r['stdout'].endswith('/target-static-link.stdout'))
    old_archive = str(ROOT / 'build/rpi5/apple-pthread-platform-linkable-ydcl_6yv/libapple-pthread-platform-partial.a')
    if link.count(old_archive) != 1: raise ValueError('Expected preserved partial archive path')
    link[link.index(old_archive)] = base['partial_archive']; link.append(str(archive))
    linked = {}
    for label in ('packet-uninitialized', 'init-live'):
        attempt = list(link)
        attempt[attempt.index('-o') + 1] = str(out / ('NOT_RUN_' + label))
        attempt[attempt.index('-map') + 1] = str(out / (label + '.map'))
        if label == 'init-live': attempt += ['-u', '___pthread_init']
        proc = run(attempt, label + '-link', True)
        linked[label] = dict(complete=proc.returncode == 0,
            missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', proc.stderr, re.M))),
            duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'", proc.stderr))))
    # Native tests use verbatim original public function bodies, isolated names.
    source = Path(base['units'][0]['source']); original = source.read_text()
    names = ('pthread_jit_write_protect_np', 'pthread_jit_write_protect_supported_np',
             'pthread_jit_write_with_callback_np', 'pthread_jit_write_freeze_callbacks_np')
    bodies = {}
    for name in names:
        match = re.search(r'\n(?:void|int)\n' + name + r'\([^\n]*(?:\n[^\{]*)?\n\{.*?\n\}', original, re.S)
        if not match: raise ValueError('Original public function not found: ' + name)
        bodies[name] = match.group(0)
    fragment = out / 'original-jit-public.c'
    fragment.write_text('#include <pthread.h>\n#include <os/thread_self_restrict.h>\n'
        '#define _PTHREAD_CONFIG_JIT_WRITE_PROTECT 0\n' + '\n'.join(bodies.values()) + '\n')
    native = list(flags)
    index = native.index('-target'); del native[index:index + 2]; native.remove('-mcpu=cortex-a76')
    native += ['-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    native += ['-D' + name + '=rpi5_original_' + name for name in names]
    jit = compile(native, fragment, 'jit-native'); test = compile(native, harness, 'jit-harness')
    binary = out / 'jit-unsupported-host'; run(native + [jit, test, '-o', binary], 'jit-native-link')
    result = run([binary], 'jit-native-run')
    if result.stderr: raise ValueError('Host runtime diagnostics')
    run(['xcrun', 'otool', '-tvV', BASE / 'pthread-pthread.o'], 'main-target-disassembly')
    for path, digest in {**pins, **headers}.items():
        if sha(path) != digest: raise ValueError('Input drift: ' + path)
    report = dict(profile='bcm2712-pthread-config-and-real-startup-gaps-v1', source_inputs_sha256=pins,
        headers_sha256=headers, commands=commands, exact_original_public_functions=bodies,
        all_selected_target_units_compile=True, original_implementation_sources_unchanged=True,
        explicit_jit_feature_absence=True, unsupported_native_stdout=result.stdout,
        host_asan_ubsan=True, target_abort_archive=str(archive), target_abort_archive_sha256=sha(archive),
        link_results=linked, target_pthread_initialized=False, target_startup_created=False,
        accepted_runtime_changed=False, executable_run=False, pi_executed=False,
        generated_sha256={str(p): sha(p) for p in out.rglob('*') if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), links=linked, native=result.stdout.strip()), indent=2))
    return out, report


if __name__ == '__main__': build()
