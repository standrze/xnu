#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build a default-off evidence gate for FILEX/popen pthread semantics.

The host executable is a behavioral oracle only.  Existing physical evidence
is admitted only for the exact target behaviors it actually exercised.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PROFILE = 'apple-pthread-filex-prerequisite-default-off-v1'
EXPECTED = {
    'build/rpi5/apple-pthread-bcm2712-qualified-x9kp1ral/manifest.json': 'a1f0a4a25efad30a2fb152e5c3a0b0797348deea88786bb28546310ca9e1f00b',
    'build/rpi5/apple-pthread-memory-4idfg5qr/manifest.json': 'd229d0b2854d70b36515fc421912866067079d329e4e4bc4cb77463e0bbaa8f1',
    'build/rpi5/apple-pthread-create-join-pjaazcj7/manifest.json': '6dec0f32687fcdf7ba6ba729626dfebb6be32af1facf41907d73a75f132a5f7e',
    'build/rpi5/apple-pthread-join-wait-ri8lyyub/manifest.json': '7a1b4a1953a3d565e30526d6f27fbb7e1ee99ce04dbbd0736fed62d899295fd8',
    'build/rpi5/root42-ready-serial-20261013/return.json': 'b27050d11003dbec79dde10fb829c63a10a887a1ebfa77db5bc8284261187876',
    'build/rpi5/root42-pthread-serial-20261013/return.json': '67f0a77a0eb61a16db5cf8506d6ff1f423a7eaf9454833970557b991ffb94bdd',
    'build/rpi5/apple-libpthread-main-candidate-20261013/src/pthread.c': '20dbfe99ea37add77c34da12d3590d267aacb4e92c862d649db4d43bc3274669',
    'build/rpi5/apple-libpthread-main-candidate-20261013/src/pthread_mutex.c': '28e355c987bcde9db2bc001933fd543b925a395344aedf7b029b79069b6744f3',
    'build/rpi5/apple-libpthread-main-candidate-20261013/src/pthread_tsd.c': '3722b5cac4f5ec6d61b729d68e97682fe70bb0a25425f8728eec77a148d91d2f',
    'build/rpi5/apple-libpthread-main-candidate-20261013/src/pthread_atfork.c': '1ea6a2de7158740b7d3c4971030f7a2546159bd200d3ae79cbe565f73c840ea9',
    'build/rpi5/apple-libpthread-main-candidate-20261013/src/pthread_cancelable.c': '982676f930ec0d7a3feb6279d653c8dd431ddd6b35be52b242169140bb214fda',
    'build/rpi5/apple-libc-main-candidate-20261013/sys/fork.c': 'd2b445ce7830a78840cdea0f0ebc0540cbd5cc49464a1d51c34de2d070b11f80',
    'bsd/kern/syscalls.master': '06f9afb58579b7d1be2cd37f009f8d479f5d282eee66682ceddada3d431d0a26',
}
ARCHIVES = {
    'selected': ('build/rpi5/apple-pthread-bcm2712-qualified-x9kp1ral/libapple-pthread-platform-selected.a',
        '51fb7045065efba964349e90dc770bfdf1bab0a16c87a5764a4df70f99612911'),
    'scoped': ('build/rpi5/apple-pthread-memory-4idfg5qr/libapple-pthread-platform-scoped.a',
        '162e135968d0b3922ce03aa884f2f2c4beaec92dd2d7835eba3436e346311031'),
}
REQUIRED_EXPORTS = {
    '_pthread_atfork', '_pthread_cancel', '_pthread_key_create',
    '_pthread_mutex_init', '_pthread_mutex_lock', '_pthread_mutex_unlock',
    '_pthread_mutexattr_settype', '_pthread_once', '_pthread_setcancelstate',
    '_pthread_setcanceltype', '_pthread_testcancel',
}
HOST_LINE = ('PTHREAD_FILEX_HOST_ORACLE PASS RECURSIVE=1 CONTENTION=24576 '
             'TLS_ERRNO=6 ATFORK=1 CANCEL=1 HOST_ONLY\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_inputs():
    pins = {}
    for relative, expected in EXPECTED.items():
        path = ROOT / relative
        actual = sha(path)
        if actual != expected:
            raise ValueError(f'frozen input drift: {relative}: {actual}')
        pins[str(path)] = actual
    for name, (relative, expected) in ARCHIVES.items():
        path = ROOT / relative
        actual = sha(path)
        if actual != expected:
            raise ValueError(f'frozen {name} archive drift: {actual}')
        pins[str(path)] = actual
    for relative in ('tools/rpi5/tests/pthread_filex_prerequisite_host.c',
                     'tools/rpi5/build_apple_pthread_filex_prerequisite.py'):
        path = ROOT / relative
        pins[str(path)] = sha(path)
    return pins


def run(command, output, label, commands):
    result = subprocess.run(list(map(str, command)), cwd=ROOT, text=True,
        capture_output=True, timeout=90)
    stdout = output / f'{label}.stdout'
    stderr = output / f'{label}.stderr'
    stdout.write_text(result.stdout)
    stderr.write_text(result.stderr)
    commands.append(dict(command=list(map(str, command)), returncode=result.returncode,
        stdout=str(stdout), stderr=str(stderr)))
    if result.returncode:
        raise ValueError(f'{label} failed: {result.stderr}')
    return result


def exported_symbols(archive, output, label, commands):
    result = run(['xcrun', 'nm', '-g', archive], output, label, commands)
    return sorted(set(re.findall(r'\b[ST] ([_A-Za-z][_A-Za-z0-9$]*)$', result.stdout, re.M)))


def source_contracts():
    pthread = (ROOT / 'build/rpi5/apple-libpthread-main-candidate-20261013/src')
    checks = {
        'recursive_mutex_implementation': (pthread / 'pthread_mutex.c',
            ('pthread_mutexattr_settype(', '_pthread_mutex_is_recursive(', 'options.lock_count')),
        'errno_tls_implementation': (pthread / 'pthread_tsd.c',
            ('pthread_setspecific(', 'pthread_getspecific(', '_pthread_tsd_cleanup_key(')),
        'atfork_implementation': (pthread / 'pthread_atfork.c',
            ('pthread_atfork(', '_pthread_atfork_prepare_handlers(', '_pthread_atfork_child(')),
        'cancellation_implementation': (pthread / 'pthread_cancelable.c',
            ('pthread_cancel(', 'pthread_testcancel(', 'PTHREAD_CONFORM_UNIX03_CANCELABLE')),
        'once_contention_implementation': (pthread / 'pthread.c',
            ('pthread_once(', '__pthread_once_handler(', '_os_once(')),
        'libc_fork_composition': (ROOT / 'build/rpi5/apple-libc-main-candidate-20261013/sys/fork.c',
            ('_libc_fork_init(', '_libSystem_atfork_prepare_v2', 'ret = __fork();')),
    }
    result = {}
    for name, (path, needles) in checks.items():
        text = path.read_text()
        missing = [needle for needle in needles if needle not in text]
        if missing:
            raise ValueError(f'{name} source contract changed: {missing}')
        result[name] = dict(source=str(path), source_sha256=sha(path),
            required_fragments=list(needles), present=True)
    return result


def kernel_contract():
    text = (ROOT / 'bsd/kern/syscalls.master').read_text()
    required = {
        'fork': 2, 'psynch_mutexwait': 301, 'psynch_mutexdrop': 302,
        'bsdthread_create': 360, 'bsdthread_terminate': 361,
        'sys_ulock_wait': 515, 'sys_ulock_wake': 516,
        'sys_ulock_wait2': 544,
    }
    missing = {}
    for name, number in required.items():
        if not re.search(rf'^\s*{number}\s+[^\n]*\b{name}\s*\(', text, re.M):
            missing[name] = number
    if missing:
        raise ValueError(f'kernel syscall ownership changed: {missing}')
    return dict(source=str(ROOT / 'bsd/kern/syscalls.master'),
        source_sha256=sha(ROOT / 'bsd/kern/syscalls.master'), syscall_numbers=required,
        source_presence_only=True, target_behavior_qualified=False)


def build():
    pins = require_inputs()
    output = Path(tempfile.mkdtemp(prefix='apple-pthread-filex-gate-',
        dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(output), flush=True)
    commands = []
    symbols = {}
    for name, (relative, _) in ARCHIVES.items():
        archive = ROOT / relative
        symbols[name] = exported_symbols(archive, output, f'{name}-symbols', commands)
    missing_exports = sorted(REQUIRED_EXPORTS - set(symbols['scoped']))
    if missing_exports:
        raise ValueError(f'current target archive lacks source-owned exports: {missing_exports}')
    target_manifest = json.loads((ROOT /
        'build/rpi5/apple-pthread-bcm2712-qualified-x9kp1ral/manifest.json').read_text())
    cancel_compile = [entry['command'] for entry in target_manifest['commands']
        if entry['stdout'].endswith('/pthread-pthread_cancelable-compile.stdout')]
    if len(cancel_compile) != 1 or '-DVARIANT_STATIC=1' not in cancel_compile[0] or \
       '-DVARIANT_CANCELABLE' in cancel_compile[0]:
        raise ValueError('exact current pthread cancellation compile variant changed')

    compiler = subprocess.check_output(['xcrun', '--find', 'clang'], text=True).strip()
    sdk = subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()
    host_source = ROOT / 'tools/rpi5/tests/pthread_filex_prerequisite_host.c'
    executable = output / 'pthread-filex-host-oracle'
    flags = [compiler, '-isysroot', sdk, '-std=c11', '-Wall', '-Wextra', '-Werror', '-O1', '-g',
        '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-pthread']
    run([*flags, host_source, '-o', executable], output, 'host-compile', commands)
    host = run([executable], output, 'host-run', commands)
    if host.stdout != HOST_LINE or host.stderr:
        raise ValueError('host behavioral oracle output changed')

    accepted = json.loads((ROOT / 'build/rpi5/root42-ready-serial-20261013/return.json').read_text())
    rejected = json.loads((ROOT / 'build/rpi5/root42-pthread-serial-20261013/return.json').read_text())
    diagnostic = accepted.get('diagnostic') or {}
    batch = diagnostic.get('batch') or {}
    expected_marker = ('Exact four-thread diagnostic workload; not full libSystem, '
                       'general dyld or multi-zone allocator proof')
    existing_target = {
        'create_join': bool(batch.get('actual_pthread_startup_constructor_create_join_mutex_tsd_errno')),
        'mutex_contention': bool(batch.get('actual_pthread_startup_constructor_create_join_mutex_tsd_errno')),
        'errno_tls': bool(batch.get('actual_pthread_startup_constructor_create_join_mutex_tsd_errno')),
        'tsd_destructors': bool(batch.get('actual_pthread_startup_constructor_create_join_mutex_tsd_errno')),
        'pthread_once': bool(batch.get('actual_pthread_startup_constructor_create_join_mutex_tsd_errno')),
        'scope_exact': batch.get('pthread_scope') == expected_marker,
        'recursive_mutex': False,
        'atfork_fork': False,
        'deferred_cancellation': False,
    }
    if not all(existing_target[k] for k in ('create_join', 'mutex_contention',
            'errno_tls', 'tsd_destructors', 'pthread_once', 'scope_exact')):
        raise ValueError('accepted root42 physical pthread evidence changed')
    if rejected.get('capture_valid') is not False or not rejected.get('capture_error'):
        raise ValueError('failed root42 trial must remain explicit non-evidence')

    blockers = [
        dict(id='target-recursive-mutex', behavior='PTHREAD_MUTEX_RECURSIVE lock depth and ownership',
            required='fresh target execution using the genuine current pthread archive', qualified=False),
        dict(id='target-atfork-fork-composition', behavior='prepare/parent/child order and child pthread reinitialization',
            required='compose current Libc fork.c with libSystem callbacks and execute a real target fork', qualified=False),
        dict(id='target-cancelable-variant', behavior='deferred cancellation at cond/join cancellation points with cleanup',
            required='build the genuine VARIANT_CANCELABLE APIs and execute target cancel/wake/cleanup paths', qualified=False),
        dict(id='target-filex-locking', behavior='recursive stream lock ownership around current __sFILEX',
            required='complete coherent FILEX migration before testing current fwide/_flock_stub/popen', qualified=False),
    ]
    semantics = {
        'recursive_mutex': False,
        'contention': existing_target['mutex_contention'],
        'errno_tls': existing_target['errno_tls'],
        'atfork_fork': False,
        'cancellation_boundaries': False,
    }
    report = dict(profile=PROFILE, default_off=True, admitted=False,
        unresolved_provider_admitted=False, target_image_changed=False,
        source_inputs_sha256=pins, source_contracts=source_contracts(),
        kernel_ownership=kernel_contract(), archive_exports=symbols,
        required_exports=sorted(REQUIRED_EXPORTS), missing_required_exports=missing_exports,
        host_oracle=dict(command_executed=True, stdout=host.stdout,
            asan_ubsan=True, target_evidence=False, host_pthread_only=True,
            behaviors=dict(recursive_mutex=True, contention=True, errno_tls=True,
                atfork_fork=True, cancellation_boundaries=True)),
        existing_target_evidence=existing_target,
        rejected_trial=dict(path=str(ROOT / 'build/rpi5/root42-pthread-serial-20261013/return.json'),
            capture_valid=False, reason=rejected['capture_error'], contributes_no_positive_evidence=True),
        target_semantics_qualified=semantics,
        gate_open=all(semantics.values()), blockers=blockers,
        current_compile_variant=dict(variant_static=True, variant_cancelable=False,
            command=cancel_compile[0], consequence='join/cond wrappers select noncancelable conformance'),
        filex_popen_admission_allowed=False, pi_executed=False,
        commands=commands)
    report['generated_sha256'] = {str(path): sha(path) for path in output.rglob('*') if path.is_file()}
    manifest = output / 'manifest.json'
    manifest.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(output), gate_open=report['gate_open'],
        qualified=semantics, blockers=[b['id'] for b in blockers]), indent=2))
    return output, report


def check(package):
    package = Path(package).resolve()
    report = json.loads((package / 'manifest.json').read_text())
    require_inputs()
    if report.get('profile') != PROFILE or report.get('default_off') is not True:
        raise ValueError('not the default-off FILEX pthread gate')
    if report.get('gate_open') is not False or report.get('admitted') is not False or \
       report.get('filex_popen_admission_allowed') is not False:
        raise ValueError('incomplete pthread semantics may not open FILEX/popen admission')
    expected_false = {'recursive_mutex', 'atfork_fork', 'cancellation_boundaries'}
    actual = {name for name, value in report['target_semantics_qualified'].items() if not value}
    if actual != expected_false:
        raise ValueError(f'exact target blockers changed: {sorted(actual)}')
    for name, digest in report['generated_sha256'].items():
        path = Path(name)
        if package not in path.parents or path.name == 'manifest.json' or sha(path) != digest:
            raise ValueError(f'generated evidence drift: {name}')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', type=Path)
    arguments = parser.parse_args()
    if arguments.check:
        checked = check(arguments.check)
        print(json.dumps(dict(profile=checked['profile'], gate_open=checked['gate_open'],
            blockers=[b['id'] for b in checked['blockers']]), indent=2))
    else:
        build()
