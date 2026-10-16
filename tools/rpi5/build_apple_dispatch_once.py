#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Real original once/lock algorithm with an explicit selected private header.

The whole original once.c bytes are unchanged; its private internal.h boundary
is deliberately selected. The waiting/gate/atomic functions are exact original
fragments, not a substitute once implementation. Objective-C callout handling,
queue scheduling and the complete libdispatch runtime are not qualified here.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_stpcpy as previous
from tools.rpi5 import build_apple_blocks_runtime as blocks

ROOT, sha = previous.ROOT, previous.sha
SOURCE = blocks.SOURCE
BASE = ROOT / 'build/rpi5/apple-stpcpy-i77u3elg'
BASE_SHA = '2af08054a8d368beb4fe0dceb53e89c0c9b0dcd376be0bb132ab7875bcba9381'
HOST = ROOT / 'tools/rpi5/tests/apple_dispatch_once_host.c'
ULOCK = ROOT / 'bsd/sys/ulock.h'
CAPABILITIES = ROOT / 'osfmk/arm/cpu_capabilities.h'
COMMPAGE = ROOT / 'bsd/sys/commpage_private.h'
EXPECTED = 'APPLE_DISPATCH_ONCE PASS THREADS=8 PREDICATES=128 PUBLICATION_WORDS=512 CONTEXT=1 RECURSIVE_TRAP=1 NATIVE_COUNTER_DOUBLE\n'


def between(text, begin, end):
    if text.count(begin) != 1: raise ValueError('Ambiguous original fragment')
    at = text.index(begin); stop = text.find(end, at + len(begin))
    if stop < 0: raise ValueError('Original fragment end missing')
    return text[at:stop] + '\n'


def fragments():
    lock = (SOURCE / 'src/shims/lock.h').read_text()
    impl = (SOURCE / 'src/shims/lock.c').read_text()
    internal = (SOURCE / 'src/internal.h').read_text()
    inline = (SOURCE / 'src/inline_internal.h').read_text()
    license_ = lock[:lock.index('*/') + 2] + '\n'
    header = license_ + '''/* Selected original private algorithm declarations.
 * Public pthread Mach-thread binding below is the explicit Pi C ABI boundary. */
#include <dispatch/dispatch.h>
#include <pthread.h>
#include <mach/mach.h>
#include <errno.h>
#include <stdint.h>
#include <stdbool.h>
#include <os/atomic_private.h>
#include "Block_private.h"
#include "rpi5-original-ulock.h"
#ifdef RPI5_NATIVE_ONCE_COUNTER
extern uintptr_t rpi5_native_once_generation;
#define _COMM_PAGE_CPU_QUIESCENT_COUNTER ((uintptr_t)&rpi5_native_once_generation)
#else
#include "CAPABILITIES_PATH"
#endif
#define DISPATCH_NOINLINE __attribute__((__noinline__))
#define likely(x) __builtin_expect(!!(x), 1)
#define unlikely(x) __builtin_expect(!!(x), 0)
#define DISPATCH_ONCE_USE_QUIESCENT_COUNTER 1
#define HAVE_UL_UNFAIR_LOCK 1
#define HAVE_FUTEX 0
#define _dispatch_thread_port() pthread_mach_thread_np(pthread_self())
'''.replace('CAPABILITIES_PATH', str(CAPABILITIES))
    header += between(lock, 'DISPATCH_OPTIONS(dispatch_lock_options,', '\n#if TARGET_OS_MAC')
    header += between(lock, 'typedef mach_port_t dispatch_tid;', '\n#elif defined(__linux__)')
    header += between(lock, 'DISPATCH_ALWAYS_INLINE\nstatic inline dispatch_lock\n_dispatch_lock_value_from_tid',
        '\n#if __has_include(<sys/ulock.h>)')
    header += '\n#define DLOCK_GATE_UNLOCKED ((dispatch_lock)0)\n#define DLOCK_ONCE_UNLOCKED ((uintptr_t)0)\n#define DLOCK_ONCE_DONE (~(uintptr_t)0)\n'
    header += between(lock, 'typedef struct dispatch_gate_s {', '\nDISPATCH_ALWAYS_INLINE\nstatic inline bool\n_dispatch_gate_tryenter')
    header += between(lock, 'DISPATCH_ALWAYS_INLINE\nstatic inline bool\n_dispatch_once_gate_tryenter', '\n#if TARGET_OS_MAC\n\nDISPATCH_NOT_TAIL_CALLED')
    header += between(inline, 'DISPATCH_ALWAYS_INLINE\nstatic inline void\n_dispatch_client_callout(void *ctxt',
        '\nDISPATCH_ALWAYS_INLINE\nstatic inline void\n_dispatch_client_callout2')
    header += between(internal, '#define _dispatch_Block_invoke(bb)', '\nvoid *_dispatch_Block_copy')
    header += between(internal, '#define _dispatch_hardware_crash()', '\n#ifdef _WIN32')
    # This is the original non-Windows source branch, not empty project logging.
    header += between(internal, '#define _dispatch_set_crash_log_cause_and_message(ac, msg) ((void)(ac))', '\n#endif // _WIN32')
    header += between(internal, '#define DISPATCH_INTERNAL_CRASH(c, x)', '\n#define _OS_OBJECT_CLIENT_CRASH')
    waits = impl[:impl.index('*/') + 2] + '\n#include "internal.h"\n'
    waits += between(impl, 'static int\n_dlock_wait(', '\n#endif // HAVE_UL_COMPARE_AND_WAIT || HAVE_UL_UNFAIR_LOCK')
    waits += between(impl, 'static int\n_dispatch_unfair_lock_wait(', '\n#endif // HAVE_UL_UNFAIR_LOCK')
    waits += between(impl, 'void\n_dispatch_once_wait(', '\n#if TARGET_OS_MAC\n\nvoid\n_dispatch_firehose_gate_wait')
    return {'internal.h': header, 'selected-once-wait.c': waits,
        'once.c': (SOURCE / 'src/once.c').read_text(), 'rpi5-original-ulock.h': ULOCK.read_text(),
        'sys/commpage_private.h': COMMPAGE.read_text()}


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA: raise ValueError('Frozen runtime composition changed')
    base = json.loads((BASE / 'manifest.json').read_text()); pins = {str(BASE / 'manifest.json'): BASE_SHA}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
        for name, digest in base[key].items():
            if name in pins and pins[name] != digest: raise ValueError('Inherited pin conflict')
            pins[name] = digest
    for path in (Path(__file__).resolve(), HOST, ULOCK, CAPABILITIES, COMMPAGE): pins[str(path)] = sha(path)
    def verify():
        for name, digest in pins.items():
            if sha(name) != digest: raise ValueError('Pinned input drift: ' + name)
    verify(); out = Path(tempfile.mkdtemp(prefix='apple-dispatch-once-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    for name, text in fragments().items():
        path = out / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
    commands, headers, records = [], {}, {}
    def run(args, label, allowed=False):
        args = list(map(str, args)); result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=90)
        for name in ('stdout', 'stderr'): (out / (label + '.' + name)).write_text(getattr(result, name))
        commands.append(dict(command=args, cwd=str(ROOT), returncode=result.returncode,
            stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if result.returncode and not allowed: raise ValueError(label + ': ' + result.stderr[-7000:])
        return result
    def deps(raw):
        return {str(Path(n).resolve()): sha(Path(n).resolve()) for n in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}
    def compile_(flags, source, label):
        before = deps(run(flags + ['-M', source], label + '-scan').stdout)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        run(flags + ['-MD', '-MF', dep, '-c', source, '-o', obj], label + '-compile')
        actual = deps(dep.read_text())
        if actual != before: raise ValueError('Consumed header membership changed')
        records[label] = dict(scanned_sha256=before, consumed_sha256=actual); headers.update(actual)
        return obj
    old = next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-stpcpy-compile.stdout'))
    target = old[:old.index('-MD')] + ['-fblocks', '-DPRIVATE=1', '-I', str(out), '-I', str(ROOT / 'libkern'),
        '-I', str(SOURCE / 'src/BlocksRuntime')]
    native = [x for x in target if x not in ('-ffreestanding', '-mcpu=cortex-a76')]
    i = native.index('-target'); del native[i:i + 2]
    native += ['-O1', '-g', '-fsanitize=address,undefined', '-DRPI5_NATIVE_ONCE_COUNTER=1']
    objects = [compile_(target, out / n, 'target-' + Path(n).stem) for n in ('once.c', 'selected-once-wait.c')]
    host = [compile_(native, out / n, 'native-' + Path(n).stem) for n in ('once.c', 'selected-once-wait.c')]
    caller = compile_(native, HOST, 'native-caller'); executable = out / 'host-once'
    block_package = ROOT / 'build/rpi5/apple-blocks-runtime-ga1_x5sg'
    run(native + [caller, *host, block_package / 'native-runtime.o', block_package / 'native-data.o',
        '-Wl,-map,' + str(out / 'host.map'), '-o', executable], 'native-link')
    result = run([executable], 'native-run')
    if (result.stdout, result.stderr) != (EXPECTED, ''): raise ValueError('Native original once oracle failed')
    archive = out / 'libapple-dispatch-once.a'; run(['xcrun', 'ar', 'rcs', archive, *objects], 'archive')
    run(['xcrun', 'nm', '-g', archive], 'symbols'); run(['xcrun', 'llvm-objdump', '-d', '-r', *objects], 'disassembly')
    link = list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o') + 1] = str(out / 'NOT_RUN_ssh'); link[link.index('-map') + 1] = str(out / 'target.map')
    link.append(str(archive)); result = run(link, 'target-link', True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', result.stderr, re.M)))
    duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", result.stderr)))
    if not result.returncode or duplicates: raise ValueError('Unexpected full client result')
    verify()
    for name, digest in headers.items():
        if sha(name) != digest: raise ValueError('Consumed input drift')
    report = dict(profile='apple-original-once-selected-private-header-v1', source_inputs_sha256=pins,
        headers_sha256=headers, dependency_records=records, commands=commands,
        whole_original_once_c_bytes_unchanged=True, original_lock_function_bodies_unchanged=True,
        original_full_internal_header_used=False, private_header_boundary_explicit=True,
        public_pthread_mach_thread_binding=True, quiescent_counter_semantics_retained=True,
        native_counter_is_explicit_double=True, native_actual_ulock_and_pthread=True,
        original_non_objc_callout_selected=True, complete_libdispatch_runtime_qualified=False,
        target_archive=str(archive), native_stdout=EXPECTED, native_asan_ubsan_pass=True,
        previous_missing_count=len(base['target_missing_symbols']), target_missing_symbols=missing,
        closed_symbols=sorted(set(base['target_missing_symbols']) - set(missing)),
        newly_reachable_symbols=sorted(set(missing) - set(base['target_missing_symbols'])),
        target_duplicate_symbols=duplicates, original_openssh_config_unchanged=True,
        target_link_complete=False, target_executed=False, accepted_runtime_modified=False,
        generated_sha256={str(p): sha(p) for p in out.rglob('*') if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), manifest_sha256=sha(out / 'manifest.json'),
        closed=report['closed_symbols'], new=report['newly_reachable_symbols'], remaining=len(missing)), indent=2))
    return out, report


if __name__ == '__main__': build()
