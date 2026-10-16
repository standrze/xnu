#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original Apple logging dependencies; no runtime/bootstrap implementation."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'build/rpi5/apple-pthread-messaging-headers-mubxo_kh'
BASE_SHA = '77d1fa636ab6307ff46d0b014c0211f2695b2f3090d2fe8e2b65734fb4cd8265'
PLATFORM = ROOT / 'build/rpi5/apple-libplatform-main-candidate-20261013'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA: raise ValueError('Frozen parent drift')
    base = json.loads((BASE / 'manifest.json').read_text())
    pins = {str(BASE / 'manifest.json'): BASE_SHA, str(Path(__file__).resolve()): sha(__file__)}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'): pins.update(base[key])
    for path, digest in pins.items():
        if sha(path) != digest: raise ValueError('Frozen input drift: ' + path)
    out = Path(tempfile.mkdtemp(prefix='apple-pthread-log-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers, units, installations, migrations = [], {}, [], {}, []
    def run(args, label, allowed=False):
        args = list(map(str, args))
        proc = subprocess.run(args, cwd=out, capture_output=True, text=True, timeout=90)
        (out / (label + '.stdout')).write_text(proc.stdout)
        (out / (label + '.stderr')).write_text(proc.stderr)
        commands.append(dict(command=args, returncode=proc.returncode,
            stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if proc.returncode and not allowed: raise ValueError(label + ': ' + proc.stderr)
        return proc
    def deps(raw):
        paths = shlex.split(raw.replace('\\\n', ' ').partition(':')[2])
        return {str(Path(p).resolve()): sha(Path(p).resolve()) for p in paths if Path(p).is_file()}, [p for p in paths if not Path(p).is_file()]
    template = next(c['command'] for c in base['commands'] if c['stdout'].endswith('/mach_msg-compile.stdout'))
    flags = list(template[:template.index('-MD')])
    overlay = out / 'include'; (overlay / 'mach').mkdir(parents=True)
    flags[1:1] = ['-I', str(overlay), '-I', str(overlay / 'mach')]
    flags += ['-I', str(ROOT / 'libsyscall/wrappers/libproc')]
    compiler = flags[0]; sdk = flags[flags.index('-isysroot') + 1]
    mig = subprocess.check_output(['xcrun', '--find', 'mig'], text=True).strip()
    pins[mig] = sha(mig)
    generated_sources = []
    for name in ('mach_vm', 'vm_map'):
        original = ROOT / 'libsyscall/mach' / (name + '.defs')
        pins[str(original)] = sha(original)
        pp = [compiler, '-isysroot', sdk, '-target', 'arm64-apple-darwin', '-x', 'c',
              '-DKOBJECT_SERVER', '-I', str(ROOT / 'osfmk')]
        before, missing = deps(run(pp + ['-M', original], name + '-mig-deps').stdout)
        if missing: raise ValueError('MIG input dependency missing')
        dep = out / (name + '-mig.d')
        raw = run(pp + ['-E', '-MD', '-MF', dep, original], name + '-mig-preprocess').stdout
        (out / (name + '.defs.i')).write_text(raw)
        if deps(dep.read_text())[0] != before: raise ValueError('MIG consumed closure drift')
        headers.update(before)
        user = out / (name + 'User.c')
        proc = run([mig, '-arch', 'arm64', '-novouchers', '-cc', compiler, '-isysroot', sdk,
                    '-DKOBJECT_SERVER', '-I' + str(ROOT / 'osfmk'),
                    '-header', overlay / 'mach' / (name + '_internal.h'), '-user', user,
                    '-server', out / (name + 'Server.c'), original], name + '-mig', True)
        after, missing = deps(run(pp + ['-M', original], name + '-mig-after-deps').stdout)
        if missing or before != after: raise ValueError('MIG input drift')
        migrations.append(dict(name=name, generated=not proc.returncode, input_dependencies=before))
        if not proc.returncode: generated_sources.append((user, name + '-mig-user', flags))
    assembly_template = next(c['command'] for c in base['commands'] if c['stdout'].endswith('/pthread-exit-traps-preprocess.stdout'))
    assembly_flags = list(assembly_template[:assembly_template.index('-E')])
    # The original macro emitter preserves normal errno/carry semantics. No
    # target network operation or fabricated registration is executed here.
    numbers = {'socket':97, 'sendto':133, 'proc_info':336, 'sys_close_nocancel':399,
               'sys_fcntl_nocancel':406, 'connect_nocancel':409}
    master = ROOT / 'bsd/kern/syscalls.master'; pins[str(master)] = sha(master)
    rows = master.read_text().splitlines()
    for name, number in numbers.items():
        if not any(row.split()[0] == str(number) and name + '(' in ''.join(row.split()) for row in rows if row.split() and row.split()[0].isdigit()):
            raise ValueError('Original syscall table mismatch: ' + name)
    sources = [
        (ROOT / 'libsyscall/mach/mach_vm.c', 'mach-vm', flags),
        (ROOT / 'libsyscall/wrappers/libproc/libproc.c', 'libproc', flags),
        (ROOT / 'libsyscall/wrappers/mach_continuous_time.c', 'continuous-time', flags),
        (PLATFORM / 'src/string/generic/strlcpy.c', 'platform-strlcpy', flags + ['-DVARIANT_STATIC=0']),
        (ROOT / 'tools/rpi5/user/pthread_log_runtime_calls.S', 'log-traps', assembly_flags),
        *generated_sources,
    ]
    for iteration in range(12):
        added = {}
        for source, label, selected in sources:
            scan = run(selected + ['-M', '-MG', source], f'closure-{iteration}-' + label, True)
            if scan.returncode: continue
            _, missing = deps(scan.stdout)
            for name in missing:
                rel = Path(name)
                if rel.is_absolute() or '..' in rel.parts: continue
                candidates = [root / rel for root in (ROOT / 'osfmk', ROOT / 'bsd', ROOT / 'libkern',
                    ROOT / 'libsyscall', ROOT / 'libsyscall/mach', ROOT / 'libsyscall/wrappers/libproc') if (root / rel).is_file()]
                if len(candidates) == 1 and not (overlay / rel).exists(): added[name] = candidates[0]
        if not added: break
        for name, original in added.items():
            destination = overlay / name; destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(original.read_bytes()); pins[str(original)] = sha(original)
            installations[str(destination)] = dict(source=str(original), sha256=sha(original))
    else: raise ValueError('Original header installation bound exceeded')
    objects = []
    for source, label, selected in sources:
        pins[str(source)] = sha(source)
        scan = run(selected + ['-M', '-MG', source], label + '-deps', True)
        before, missing = deps(scan.stdout) if not scan.returncode else ({}, [])
        headers.update(before)
        obj, dep = out / (label + '.o'), out / (label + '.d')
        if label == 'log-traps':
            proc = run(selected + ['-E', '-P', '-MD', '-MF', dep, source], label + '-preprocess', True)
            if not proc.returncode:
                asm = out / (label + '.s'); asm.write_text(proc.stdout.replace('%%', '\n').replace(';', '\n'))
                proc = run([compiler, '-target', 'arm64-apple-darwin', '-mcpu=cortex-a76', '-x', 'assembler', '-c', asm, '-o', obj], label + '-assemble', True)
        else: proc = run(selected + ['-MD', '-MF', dep, '-c', source, '-o', obj], label + '-compile', True)
        actual = deps(dep.read_text())[0] if dep.exists() else None
        if not proc.returncode:
            if missing or actual != before: raise ValueError('Actual dependency mismatch: ' + label)
            objects.append(obj)
        units.append(dict(label=label, source=str(source), compiled=not proc.returncode,
            object=str(obj) if not proc.returncode else None, missing_headers=missing,
            actual_headers_sha256=actual, preprocessor_headers_sha256=before,
            diagnostics=[line for line in proc.stderr.splitlines() if 'error:' in line or 'warning:' in line]))
    archive = out / 'libapple-pthread-log.a'
    run(['xcrun', 'ar', 'rcs', archive, *objects], 'archive')
    link = next(list(c['command']) for c in base['commands'] if c['stdout'].endswith('/init-live-link.stdout'))
    link[link.index('-o') + 1] = str(out / 'NOT_RUN_init-live')
    link[link.index('-map') + 1] = str(out / 'init-live.map')
    link += [str(archive)]
    attempt = run(link, 'init-live-link', True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', attempt.stderr, re.M)))
    duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", attempt.stderr)))
    for path, digest in {**pins, **headers}.items():
        if sha(path) != digest: raise ValueError('Input drift: ' + path)
    report = dict(profile='original-apple-pthread-log-provider-inventory-v1', source_inputs_sha256=pins,
        headers_sha256=headers, commands=commands, units=units, migrations=migrations,
        original_header_installations=installations, syscall_numbers=numbers,
        target_archive=str(archive), target_archive_sha256=sha(archive),
        compiled_units=sum(u['compiled'] for u in units), attempted_units=len(units),
        target_missing_symbols=missing, target_duplicate_symbols=duplicates,
        target_link_complete=not attempt.returncode, real_libkernel_init_forced_live=True,
        real_pthread_init_forced_live=True, original_implementation_bodies_unchanged=True,
        source_configuration_weakened=False, target_startup_created=False,
        target_main_thread_initialized=False, accepted_runtime_modified=False, pi_executed=False,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), compiled=report['compiled_units'], attempted=len(units),
        failures={u['label']:u['diagnostics'][:6] for u in units if not u['compiled']}, missing=missing, duplicates=duplicates), indent=2))
    return out, report


if __name__ == '__main__': build()
