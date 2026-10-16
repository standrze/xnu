#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original pthread/platform build with genuine generated private SDK headers."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
PTHREAD = ROOT / 'build/rpi5/apple-libpthread-main-candidate-20261013'
PLATFORM = ROOT / 'build/rpi5/apple-libplatform-main-candidate-20261013'
SYSTEM = ROOT / 'build/rpi5/apple-libsystem-main-candidate-20261013'
LIBC = ROOT / 'build/rpi5/apple-libc-main-candidate-20261013'
AVAILABILITY = ROOT / 'build/rpi5/apple-availability-main-candidate-20261013'
DYLD = ROOT / 'build/rpi5/apple-dyld-headers-main-candidate-20261013'
MALLOC = ROOT / 'build/rpi5/apple-libmalloc-main-candidate-20261013'
COMMITS = {DYLD: 'fd8d0c4d52320ebf64db34f3cb280310d905c5ae', AVAILABILITY: '149b1777f3e8c2133042d8e188f72e3adf6a7110',
           MALLOC: 'c49dafa25f1efe8607701ae6014a663ad2ee437f',
           SYSTEM: 'c23b51183e46e613375dc7639fb4bf11fbf59ba8', PTHREAD: '42d026df5b07825070f60134b980a1ec2552dfee',
           PLATFORM: '2512ffd8bb5c6caff3c8ea83331ab8a0adc820c3',
           LIBC: '71bbe350ab79eef58113991d817ccc6165061a64'}


def build():
    pins, commits = {}, {}
    for repo in (PTHREAD, PLATFORM, SYSTEM, LIBC, AVAILABILITY, MALLOC, DYLD):
        commit = subprocess.check_output(['git', '-C', repo, 'rev-parse', 'HEAD'], text=True).strip()
        if repo in COMMITS and commit != COMMITS[repo]: raise ValueError('Unexpected Apple source revision')
        if subprocess.check_output(['git', '-C', repo, 'status', '--porcelain'], text=True):
            raise ValueError('Source checkout is not pristine: ' + str(repo))
        commits[str(repo)] = commit
        # Entire pthread/platform/Libsystem source snapshots are intentionally
        # pinned; Libc is large and only consumed header inputs are needed.
        if repo != LIBC:
            for p in repo.rglob('*'):
                if p.is_file() and '.git' not in p.parts: pins[str(p)] = sha(p)
    pins[str(Path(__file__).resolve())] = sha(__file__)
    out = Path(tempfile.mkdtemp(prefix='apple-pthread-platform-bcm2712-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, units, headers, overlays = [], [], {}, {}
    def run(args, label):
        args = list(map(str, args))
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=90)
        (out / (label + '.stdout')).write_text(result.stdout)
        (out / (label + '.stderr')).write_text(result.stderr)
        commands.append(dict(command=args, returncode=result.returncode,
            stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        return result
    overlay = out / 'include'
    selected = {
        'os/alloc_once_private.h': SYSTEM / 'alloc_once_private.h',
        'mach/thread_policy.h': ROOT / 'osfmk/mach/thread_policy.h',
        'mach/thread_switch.h': ROOT / 'osfmk/mach/thread_switch.h',
        'mach/mach_sync_ipc.h': ROOT / 'libsyscall/mach/mach/mach_sync_ipc.h',
        'limits.h': LIBC / 'include/limits.h',
        'spawn.h': ROOT / 'libsyscall/wrappers/spawn/spawn.h',
        'spawn_private.h': ROOT / 'libsyscall/wrappers/spawn/spawn_private.h',
        'os/tsd.h': ROOT / 'libsyscall/os/tsd.h',
        'pthread/bsdthread_private.h': ROOT / 'bsd/pthread/bsdthread_private.h',
        'pthread/priority_private.h': ROOT / 'bsd/pthread/priority_private.h',
        'pthread/workqueue_syscalls.h': ROOT / 'bsd/pthread/workqueue_syscalls.h',
        'sys/ulock.h': ROOT / 'bsd/sys/ulock.h',
        'sys/reason.h': ROOT / 'bsd/sys/reason.h',
        'sys/event.h': ROOT / 'bsd/sys/event.h',
        'sys/event_private.h': ROOT / 'bsd/sys/event_private.h',
        'sys/commpage_private.h': ROOT / 'bsd/sys/commpage_private.h',
        'machine/cpu_capabilities.h': ROOT / 'osfmk/machine/cpu_capabilities.h',
        'arm/cpu_capabilities.h': ROOT / 'osfmk/arm/cpu_capabilities.h',
    }
    for relative, original in selected.items():
        pins[str(original)] = sha(original)
        target = overlay / relative; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(original.read_bytes())
        overlays[str(target)] = dict(source=str(original), sha256=sha(original), modified=False)
    # Preserve every Apple implementation. Only the private target capability
    # expression changes: Apple-specific per-thread JIT protection is absent.
    capability = ROOT / 'tools/rpi5/user/pthread_bcm2712_capabilities.h'
    target = overlay / 'os/thread_self_restrict.h'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(capability.read_bytes())
    pins[str(capability)] = sha(capability)
    overlays[str(target)] = dict(source=str(capability), sha256=sha(capability), modified=False)
    original = PTHREAD / 'kern/kern_internal.h'
    expression = '#if (TARGET_OS_OSX || PTHREAD_TARGET_OS_IOS_ONLY) && TARGET_CPU_ARM64 && !VARIANT_DYLD'
    raw = original.read_text()
    if raw.count(expression) != 1: raise ValueError('Original JIT target expression changed')
    target = overlay / 'kern/kern_internal.h'; target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(raw.replace(expression, expression + ' && !RPI5_PTHREAD_NO_PER_THREAD_JIT'))
    pins[str(original)] = sha(original)
    target_configuration = dict(original=str(original), original_sha256=sha(original),
        derived=str(target), derived_sha256=sha(target), exact_replacement=expression,
        replacement=expression + ' && !RPI5_PTHREAD_NO_PER_THREAD_JIT',
        per_thread_jit_protection_supported=False, mte_supported=False,
        public_unsupported_semantics='Original Apple documented behavior; no working APRR service',
        private_transition_semantics='unreachable __builtin_trap, never success',
        kernel_vm_protection_changed=False)
    for template in sorted((AVAILABILITY / 'templates').glob('*.h')):
        destination = overlay / ('os/availability.h' if template.name == 'os_availability.h' else
            'mach-o/dyld_version_defines.h' if template.name == 'dyld_version_defines.h' else template.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Upstream's optional --av_version currently passes a list to .encode();
        # omit it and use its real default "Local", coherent across all headers.
        # The exact source commit and all generated bytes are pinned separately.
        generated = run(['python3', AVAILABILITY / 'availability',
            '--preprocess', template, destination], 'availability-' + template.stem)
        if generated.returncode: raise ValueError('Original availability generator failed')
    compiler = subprocess.check_output(['xcrun', '--find', 'clang'], text=True).strip()
    sdk = subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip()
    common = [compiler, '-isysroot', sdk, '-target', 'arm64-apple-darwin', '-mcpu=cortex-a76',
        '-std=gnu11', '-fblocks', '-ferror-limit=0', '-Wno-int-conversion', '-Os', '-ffreestanding', '-fno-stack-protector', '-fno-stack-check',
        '-fno-builtin', '-fno-common', '-D_FORTIFY_SOURCE=0', '-DPRIVATE=1', '-DRPI5_PTHREAD_NO_PER_THREAD_JIT=1',
        '-include', str(ROOT / 'tools/rpi5/user/pthread_build_headers.h')]
    include = [overlay, PLATFORM / 'private', PLATFORM / 'include', PLATFORM / 'internal',
        ROOT / 'libkern', LIBC, MALLOC / 'private', DYLD / 'include']
    shared = [p for path in include for p in ('-I', str(path))]
    threadflags = common + ['-D' + x for x in ('__LIBC__', '__POSIX_LIB__', '__DARWIN_UNIX03=1',
        '__DARWIN_64_BIT_INO_T=1', '__DARWIN_NON_CANCELABLE=1', '__DARWIN_VERS_1050=1',
        '__PTHREAD_BUILDING_PTHREAD__=1', '__PTHREAD_EXPOSE_INTERNALS__',
        'OS_ATOMIC_CONFIG_MEMORY_ORDER_DEPENDENCY=1', 'VARIANT_STATIC=1')]
    threadflags += [p for path in (overlay, PTHREAD / 'src/resolver', PTHREAD / 'private',
        PTHREAD / 'include', PTHREAD) for p in ('-I', str(path))] + shared
    threadflags += ['-iquote', str(PTHREAD / 'include/pthread'), '-iquote', str(Path(sdk) / 'usr/include/pthread')]
    platformflags = common + ['-D' + x for x in ('VARIANT_STATIC=1', 'VARIANT_NO_RESOLVERS=1',
        'CONFIG_MTE=0', 'OSATOMIC_USE_INLINED=0', 'OSATOMIC_DEPRECATED=0',
        'OSSPINLOCK_USE_INLINED=0', 'OSSPINLOCK_DEPRECATED=0')] + shared
    platformflags += ['-I', str(PLATFORM / 'src/os/resolver'), '-I', str(PTHREAD / 'private')]
    sources = [(PTHREAD / 'src' / name, threadflags, 'pthread-' + name[:-2]) for name in
        ('pthread.c', 'pthread_mutex.c', 'pthread_tsd.c', 'pthread_cond.c', 'pthread_rwlock.c',
         'pthread_atfork.c', 'pthread_cancelable.c', 'pthread_cwd.c', 'qos.c')]
    sources += [(PLATFORM / 'src/os' / name, platformflags, 'platform-' + name[:-2]) for name in
        ('lock.c', 'semaphore.c', 'atomic.c', 'alloc_once.c')]
    sources += [(PLATFORM / 'src/simple/getenv.c', platformflags, 'platform-getenv'),
                (ROOT / 'libsyscall/os/alloc_once.c', common, 'syscall-alloc-once')]
    objects = []
    def parse_deps(raw):
        names = shlex.split(raw.replace('\\\n', ' ').partition(':')[2])
        return {str(Path(p).resolve()): sha(Path(p).resolve()) for p in names if Path(p).is_file()}, [p for p in names if not Path(p).is_file()]
    # Close only real, exact-named Apple header installations. No guessed
    # layouts/declarations and no generated success behavior. Reach a fixed
    # point for every TU before compilation so no later header shadows an
    # already compiled unit's inputs.
    for pass_number in range(12):
        additions = {}
        for source, flags, label in sources:
            scan = run(flags + ['-M', '-MG', source], f'closure-{pass_number}-' + label)
            if scan.returncode: continue
            _, missing = parse_deps(scan.stdout)
            for name in missing:
                relative = Path(name)
                if relative.is_absolute() or '..' in relative.parts: continue
                choices = [root / relative for root in (ROOT / 'osfmk', ROOT / 'bsd',
                    ROOT / 'libkern', ROOT / 'libsyscall', ROOT / 'libsyscall/mach') if (root / relative).is_file()]
                if len(choices) == 1 and not (overlay / relative).exists():
                    additions[name] = choices[0]
        if not additions: break
        if len(overlays) + len(additions) > 100: raise ValueError('Header closure exceeded bound')
        for name, original in sorted(additions.items()):
            target = overlay / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original.read_bytes())
            pins[str(original)] = sha(original)
            overlays[str(target)] = dict(source=str(original), sha256=sha(original), modified=False)
    else:
        raise ValueError('Original header closure did not converge')
    for source, flags, label in sources:
        pins[str(source)] = sha(source)
        # -MG inventories missing includes without making fabricated headers.
        scan = run(flags + ['-M', '-MG', source], label + '-scan')
        before, absent = parse_deps(scan.stdout) if scan.returncode == 0 else ({}, [])
        headers.update(before)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        result = run(flags + ['-H', '-MD', '-MF', dep, '-c', source, '-o', obj], label + '-compile')
        observed = {}
        for line in result.stderr.splitlines():
            match = re.match(r'^\.+ (/.+)$', line)
            if match and Path(match[1]).is_file(): observed[match[1]] = sha(match[1])
        headers.update(observed)
        actual = None
        if result.returncode == 0:
            actual, unknown = parse_deps(dep.read_text())
            if scan.returncode or absent or unknown or actual != before:
                raise ValueError('Successful unit lacks exact before/actual dependency match: ' + label)
            objects.append(obj)
        diagnostics = [s for s in result.stderr.splitlines() if 'error:' in s or 'warning:' in s]
        units.append(dict(source=str(source), label=label, compiled=result.returncode == 0,
            object=str(obj) if result.returncode == 0 else None, preprocessor_missing_headers=absent,
            preprocessor_headers_sha256=before, compiler_observed_headers_sha256=observed,
            actual_headers_sha256=actual, diagnostics=diagnostics))
    archive = out / 'libapple-pthread-platform-selected.a'
    if objects:
        result = run(['xcrun', 'ar', 'rcs', archive, *objects], 'partial-archive')
        if result.returncode: raise ValueError('Partial archive failed')
        result = run(['xcrun', 'nm', '-g', archive], 'partial-symbols')
        if result.returncode: raise ValueError('Partial archive audit failed')
    for path, digest in {**pins, **headers}.items():
        if sha(path) != digest: raise ValueError('Original/consumed input changed: ' + path)
    report = dict(profile='original-apple-pthread-platform-bcm2712-target-v1',
        commits=commits, source_inputs_sha256=pins, headers_sha256=headers,
        original_header_installations=overlays, commands=commands, units=units,
        compiled_units=sum(u['compiled'] for u in units), attempted_units=len(units),
        partial_archive=str(archive) if objects else None,
        config_preserved=True, private_header_exposure='PRIVATE=1, byte-identical original headers',
        mte_configuration='CONFIG_MTE=0 matches actual Cortex-A76 hardware, not Apple macOS arm64',
        target_configuration=target_configuration,
        implementation_shims=False, pthread_runtime_qualified=False, installed=False, pi_executed=False,
        generated_sha256={str(p): sha(p) for p in out.rglob('*') if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), compiled=report['compiled_units'], attempted=len(units),
        failures={u['label']: u['diagnostics'][:2] for u in units if not u['compiled']}), indent=2))
    return out, report


if __name__ == '__main__': build()





