#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original Mach/MIG, libkernel-init, and thread entrypoint compile closure."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'build/rpi5/apple-pthread-memory-4idfg5qr'
BASE_SHA = 'd229d0b2854d70b36515fc421912866067079d329e4e4bc4cb77463e0bbaa8f1'
TARGET = ROOT / 'build/rpi5/apple-pthread-bcm2712-qualified-x9kp1ral'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    if sha(BASE / 'manifest.json') != BASE_SHA: raise ValueError('Frozen input drift')
    base = json.loads((BASE / 'manifest.json').read_text())
    target = json.loads((TARGET / 'manifest.json').read_text())
    pins = {str(BASE / 'manifest.json'): BASE_SHA, str(Path(__file__).resolve()): sha(__file__)}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'): pins.update(base[key])
    out = Path(tempfile.mkdtemp(prefix='apple-pthread-mach-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers, units, installations, migrations = [], {}, [], {}, []
    def run(args, label, allowed=False):
        args = list(map(str, args)); proc = subprocess.run(args, cwd=out, capture_output=True, text=True, timeout=90)
        (out / (label + '.stdout')).write_text(proc.stdout); (out / (label + '.stderr')).write_text(proc.stderr)
        commands.append(dict(command=args, returncode=proc.returncode, stdout=str(out / (label + '.stdout')), stderr=str(out / (label + '.stderr'))))
        if proc.returncode and not allowed: raise ValueError(label + ': ' + proc.stderr)
        return proc
    def deps(raw):
        paths = shlex.split(raw.replace('\\\n', ' ').partition(':')[2])
        return {str(Path(p).resolve()): sha(Path(p).resolve()) for p in paths if Path(p).is_file()}, [p for p in paths if not Path(p).is_file()]
    common = next(c['command'] for c in target['commands'] if c['stdout'].endswith('/pthread-pthread-compile.stdout'))
    flags = list(common[:common.index('-H')])
    # Do not carry pthread library-building definitions into original libkernel.
    flags = [p for p in flags if p not in ('-D__PTHREAD_BUILDING_PTHREAD__=1', '-D__PTHREAD_EXPOSE_INTERNALS__')]
    overlay = out / 'include'; (overlay / 'mach').mkdir(parents=True)
    flags[1:1] = ['-I', str(overlay)]
    flags += ['-I', str(ROOT / 'libsyscall/mach'), '-I', str(ROOT / 'libsyscall/os'),
              '-I', str(ROOT / 'libsyscall/wrappers'), '-I', str(ROOT / 'libsyscall/wrappers/spawn')]
    compiler = flags[0]; sdk = flags[flags.index('-isysroot') + 1]
    mig = subprocess.check_output(['xcrun', '--find', 'mig'], text=True).strip()
    pins[mig] = sha(mig)
    generated_sources = []
    for name in ('mach_host', 'mach_port'):
        original = ROOT / 'libsyscall/mach' / (name + '.defs')
        pins[str(original)] = sha(original)
        pp = [compiler, '-isysroot', sdk, '-target', 'arm64-apple-darwin', '-x', 'c',
              '-DKOBJECT_SERVER', '-I', str(ROOT / 'osfmk')]
        before, missing = deps(run(pp + ['-M', original], name + '-mig-deps').stdout)
        if missing: raise ValueError('MIG input closure incomplete')
        dep = out / (name + '-mig.d'); preprocessed = out / (name + '.defs.i')
        raw = run(pp + ['-E', '-MD', '-MF', dep, original], name + '-mig-preprocess').stdout
        preprocessed.write_text(raw)
        if deps(dep.read_text())[0] != before: raise ValueError('MIG preprocessor closure drift')
        headers.update(before)
        user = out / (name + 'User.c')
        # XNU libsyscall builds generated user implementations without
        # LIBSYSCALL_INTERFACE, preserving _kernelrpc_ port RPC fallback names.
        command = [mig, '-arch', 'arm64', '-novouchers', '-cc', compiler, '-isysroot', sdk,
                   '-DKOBJECT_SERVER', '-I' + str(ROOT / 'osfmk'), '-header', overlay / 'mach' / (name + '_internal.h'),
                   '-user', user, '-server', out / (name + 'Server.c'), original]
        proc = run(command, name + '-mig', True)
        after, missing = deps(run(pp + ['-M', original], name + '-mig-after-deps').stdout)
        if missing or after != before: raise ValueError('MIG source closure changed')
        migrations.append(dict(name=name, generated=proc.returncode == 0, input_dependencies=before))
        if proc.returncode == 0: generated_sources.append((user, name + '-mig-user', flags))
    thread = ROOT / 'build/rpi5/apple-libpthread-main-candidate-20261013/src/pthread_asm.s'
    assembly_flags = [compiler, '-isysroot', sdk, '-target', 'arm64-apple-darwin', '-mcpu=cortex-a76',
                      '-x', 'assembler-with-cpp', '-D__ASSEMBLER__=1', '-I', str(overlay),
                      '-I', str(TARGET / 'include'), '-I', str(ROOT / 'libsyscall')]
    sources = [(ROOT / 'libsyscall/mach' / (name + '.c'), name, flags) for name in
               ('mach_legacy', 'mach_port', 'mach_init')]
    sources += [(ROOT / 'libsyscall/wrappers/_libkernel_init.c', 'libkernel-init', flags),
                (thread, 'pthread-asm', assembly_flags),
                (ROOT / 'libsyscall/mach/mach_traps.s', 'mach-traps', assembly_flags), *generated_sources]
    # Install only uniquely resolved original missing headers before any TU is
    # compiled; no declarations, layouts, or success implementations fabricated.
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
                    ROOT / 'libsyscall', ROOT / 'libsyscall/mach') if (root / rel).is_file()]
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
        if label in ('pthread-asm', 'mach-traps'):
            proc = run(selected + ['-E', '-P', '-MD', '-MF', dep, source], label + '-preprocess', True)
            if proc.returncode == 0:
                asm = out / (label + '.s'); asm.write_text(proc.stdout.replace('%%', '\n').replace(';', '\n'))
                proc = run([compiler, '-target', 'arm64-apple-darwin', '-mcpu=cortex-a76', '-x', 'assembler', '-c', asm, '-o', obj], label + '-assemble', True)
        else:
            proc = run(selected + ['-MD', '-MF', dep, '-c', source, '-o', obj], label + '-compile', True)
        actual = deps(dep.read_text())[0] if dep.exists() else None
        if proc.returncode == 0:
            if missing or actual != before: raise ValueError('Actual dependency mismatch for ' + label)
            objects.append(obj)
        units.append(dict(label=label, source=str(source), compiled=proc.returncode == 0, object=str(obj) if not proc.returncode else None,
                          missing_headers=missing, actual_headers_sha256=actual, preprocessor_headers_sha256=before,
                          diagnostics=[l for l in proc.stderr.splitlines() if 'error:' in l or 'warning:' in l]))
    archive = out / 'libapple-pthread-mach-partial.a'
    run(['xcrun', 'ar', 'rcs', archive, *objects], 'partial-archive')
    link = next(list(c['command']) for c in base['commands'] if c['stdout'].endswith('/init-live-link.stdout'))
    link[link.index('-o') + 1] = str(out / 'NOT_RUN_init-live')
    link[link.index('-map') + 1] = str(out / 'init-live.map')
    link += [str(archive), '-u', '___libkernel_init']
    attempt = run(link, 'init-live-link', True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', attempt.stderr, re.M)))
    duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", attempt.stderr)))
    for path, digest in {**pins, **headers}.items():
        if sha(path) != digest: raise ValueError('Input drift: ' + path)
    report = dict(profile='original-apple-mach-thread-and-libkernel-provider-inventory-v1',
        source_inputs_sha256=pins, headers_sha256=headers, commands=commands, units=units, migrations=migrations,
        original_header_installations=installations, target_archive=str(archive), target_archive_sha256=sha(archive),
        compiled_units=sum(u['compiled'] for u in units), attempted_units=len(units),
        target_missing_symbols=missing, target_duplicate_symbols=duplicates, target_link_complete=not attempt.returncode,
        real_libkernel_init_forced_live=True, real_pthread_init_forced_live=True,
        original_implementation_bodies_unchanged=True, source_configuration_weakened=False,
        target_startup_created=False, target_main_thread_initialized=False,
        native_runtime_tested=False, accepted_runtime_modified=False, pi_executed=False,
        generated_sha256={str(p): sha(p) for p in out.rglob('*') if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), compiled=report['compiled_units'], attempted=len(units),
        failures={u['label']:u['diagnostics'][:4] for u in units if not u['compiled']}, missing=missing, duplicates=duplicates), indent=2))
    return out, report


if __name__ == '__main__': build()
