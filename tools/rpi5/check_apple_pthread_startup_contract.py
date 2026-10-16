#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Actual original layout agreement and honest abort wrapper failure tests."""
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
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA: raise ValueError('Frozen input drift')
    base = json.loads((BASE / 'manifest.json').read_text())
    target = json.loads((TARGET / 'manifest.json').read_text())
    pins = {str(BASE / 'manifest.json'): BASE_SHA, str(Path(__file__).resolve()): sha(__file__)}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'): pins.update(base[key])
    harness = ROOT / 'tools/rpi5/tests/pthread_abort_original_host.c'; pins[str(harness)] = sha(harness)
    out = Path(tempfile.mkdtemp(prefix='apple-pthread-startup-contract-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers = [], {}
    def run(args, label):
        args = list(map(str, args)); proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=60)
        (out / (label + '.stdout')).write_text(proc.stdout); (out / (label + '.stderr')).write_text(proc.stderr)
        commands.append(dict(command=args, returncode=proc.returncode, stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if proc.returncode: raise ValueError(label + ': ' + proc.stderr)
        return proc
    def deps(raw): return {str(Path(p).resolve()): sha(Path(p).resolve()) for p in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}
    def compile(flags, source, label):
        before = deps(run(flags + ['-M', source], label + '-deps').stdout)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        run(flags + ['-MD', '-MF', dep, '-c', source, '-o', obj], label + '-compile')
        if deps(dep.read_text()) != before: raise ValueError('Actual consumed header mismatch')
        headers.update(before); return obj
    cmd = next(r['command'] for r in target['commands'] if r['stdout'].endswith('/pthread-pthread-compile.stdout'))
    flags = list(cmd[:cmd.index('-H')]); native = list(flags)
    index = native.index('-target'); del native[index:index + 2]; native.remove('-mcpu=cortex-a76')
    native += ['-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-include', 'sys/cdefs.h']
    prefix = ('abort_with_reason', 'abort_with_payload', 'terminate_with_reason', 'terminate_with_payload', '__darwin_check_fd_set_overflow')
    rename = ['-D' + name + '=rpi5_original_' + name for name in prefix]
    rename += ['-D__abort_with_payload=rpi5_test_abort', '-D__terminate_with_payload=rpi5_test_terminate']
    source = ROOT / 'libsyscall/wrappers/terminate_with_reason.c'
    wrapper = compile(native + rename, source, 'abort-original-native')
    test = compile(native, harness, 'abort-test-native')
    host = out / 'abort-wrapper-host'
    run(native + [wrapper, test, '-Wl,-dead_strip', '-o', host], 'abort-host-link')
    abort_result = run([host], 'abort-host-run')
    if abort_result.stderr: raise ValueError('Host abort-wrapper diagnostics')
    kernel = ROOT / 'build/rpi5-xcode27/pthread-provider/20148551e88bda2dbffd/libpthread-libpthread-539.100.4/kern/kern_internal.h'
    original = kernel.read_text()
    match = re.search(r'struct _pthread_registration_data \{.*?\} __attribute__ \(\(packed\)\);', original, re.S)
    if not match: raise ValueError('Actual linked provider registration structure missing')
    kernel_struct = match.group(0).replace('struct _pthread_registration_data', 'struct rpi5_kernel_registration', 1)
    fields = ('version', 'dispatch_queue_offset', 'main_qos', 'tsd_offset', 'return_to_kernel_offset', 'mach_thread_self_offset',
        'stack_addr_hint', 'mutex_default_policy', 'joinable_offset_bits', 'wq_quantum_expiry_offset')
    layout = out / 'layout.c'
    expressions = {'pthread_bytes': 'sizeof(struct pthread_s)', 'pthread_tsd_offset': 'offsetof(struct pthread_s, tsd)',
        'pthread_sig_offset': 'offsetof(struct pthread_s, sig)', 'pthread_thread_id_offset': 'offsetof(struct pthread_s, thread_id)',
        'registration_bytes': 'sizeof(struct _pthread_registration_data)'}
    expressions.update({name + '_offset': 'offsetof(struct _pthread_registration_data, ' + name + ')' for name in fields})
    raw = '#include "internal.h"\n#include <stdio.h>\n' + kernel_struct + '\n'
    raw += '_Static_assert(sizeof(struct _pthread_registration_data) == sizeof(struct rpi5_kernel_registration), "registration size");\n'
    for field in fields:
        raw += '_Static_assert(offsetof(struct _pthread_registration_data, ' + field + ') == offsetof(struct rpi5_kernel_registration, ' + field + '), "' + field + '");\n'
    raw += 'int main(void) {\n' + ''.join('printf("' + key + '=%zu\\n", (size_t)(' + expression + '));\n' for key, expression in expressions.items()) + 'return 0; }\n'
    layout.write_text(raw)
    source_dir = Path(target['units'][0]['source']).parent
    layout_native = compile(native + ['-I', str(source_dir)], layout, 'layout-native')
    layout_host = out / 'layout-host'; run(native + [layout_native, '-o', layout_host], 'layout-native-link')
    values = dict((k, int(v)) for k, v in (line.split('=') for line in run([layout_host], 'layout-native-run').stdout.splitlines()))
    if set(values) != set(expressions): raise ValueError('Unexpected layout record')
    # Independently compile the actual target headers with all measured values
    # asserted. Native execution supplies numbers, not a target runtime claim.
    target_layout = out / 'layout-target.c'
    target_layout.write_text(raw + ''.join('_Static_assert((' + expressions[k] + ') == ' + str(v) + ', "A76 ' + k + '");\n' for k, v in values.items()))
    compile(flags + ['-I', str(source_dir)], target_layout, 'layout-target')
    for path, digest in {**pins, **headers}.items():
        if sha(path) != digest: raise ValueError('Source/consumed input drift: ' + path)
    report = dict(profile='actual-apple-pthread-layout-and-abort-contract-v1', source_inputs_sha256=pins, headers_sha256=headers,
        commands=commands, original_linked_kernel_registration=kernel_struct, registration_fields=list(fields),
        actual_layout=values, kernel_user_registration_layout_equal=True, actual_a76_static_assertions=True,
        host_abort_wrapper_stdout=abort_result.stdout, abort_test_simulated_endpoints=True,
        original_abort_signal_and_fallback_preserved=True, host_asan_ubsan=True,
        target_main_thread_initialized=False, target_pthread_startup_created=False, pi_executed=False,
        generated_sha256={str(p): sha(p) for p in out.rglob('*') if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), layout=values, abort=abort_result.stdout.strip()), indent=2))
    return out, report


if __name__ == '__main__': build()
