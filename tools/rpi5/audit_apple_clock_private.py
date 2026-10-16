#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compile genuine clock providers with private declarations; not admission.

Keeps the failed public-header inventory and all accepted runtime archives.
This reports actual dependencies of the whole Apple clock TU and original
Mach helpers without pretending compiler success is runtime qualification.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import audit_apple_clock_provider as predecessor

base = predecessor.base
ROOT, sha = base.ROOT, base.sha
LOG = ROOT / 'build/rpi5/apple-pthread-log-clock-m3ct69va'
SYSCALLS = ROOT / 'build/rpi5/apple-ssh-libc-prereqs-crebas6n'


def audit():
    prior_path = predecessor.PREDECESSOR / 'manifest.json'
    if sha(prior_path) != predecessor.PREDECESSOR_SHA:
        raise ValueError('Exact47-import predecessor required')
    prior = json.loads(prior_path.read_text())
    pins = {str(prior_path): sha(prior_path), str(Path(__file__).resolve()): sha(__file__)}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
        pins.update(prior[key])
    for directory in (LOG, SYSCALLS):
        path = directory / 'manifest.json'
        # These manifests must already belong to the accepted predecessor.
        if str(path) not in pins or pins[str(path)] != sha(path):
            raise ValueError('Inherited actual provider manifest required')
    log = json.loads((LOG / 'manifest.json').read_text())
    syscalls = json.loads((SYSCALLS / 'manifest.json').read_text())
    private = ROOT / 'osfmk/mach/mach_time_private.h'
    clock = base.LIBC / 'gen/clock_gettime.c'
    mach = [ROOT / 'libsyscall/wrappers' / n for n in
            ('mach_boottime.c', 'mach_approximate_time.c')]
    thread = SYSCALLS / 'generated/___thread_selfusage.s'
    for path in (private, clock, *mach, thread):
        pins[str(path)] = sha(path)
    if subprocess.check_output(['git', '-C', str(base.LIBC), 'show',
                                'HEAD:gen/clock_gettime.c']) != clock.read_bytes():
        raise ValueError('Unchanged whole Apple clock source required')
    for path in (private, *mach):
        if subprocess.check_output(['git', 'show', 'HEAD:' + str(path.relative_to(ROOT))],
                                   cwd=ROOT) != path.read_bytes():
            raise ValueError('Unchanged original XNU provider required')

    def verify():
        for name, digest in pins.items():
            if sha(name) != digest:
                raise ValueError('Input drift: ' + name)

    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-clock-private-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands, headers, records = [], {}, {}

    def run(args, label):
        args = list(map(str, args))
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=90)
        for stream in ('stdout', 'stderr'):
            (out / (label + '.' + stream)).write_text(getattr(result, stream))
        commands.append(dict(command=args, label=label, returncode=result.returncode))
        return result

    def deps(path):
        words = shlex.split(path.read_text().replace('\\\n', ' ').partition(':')[2])
        return {str(Path(p).resolve()): sha(Path(p).resolve()) for p in words}

    def compile_(flags, source, label, assembly=False):
        scan = out / (label + '.scan.d')
        if run([*flags, '-M', '-MF', scan, source], label + '-scan').returncode:
            return None
        before = deps(scan)
        headers.update(before)  # Failed compilations retain the scanned closure too.
        obj, dep = out / (label + '.o'), out / (label + '.actual.d')
        if assembly:
            text = run([*flags, '-E', '-P', '-MD', '-MF', dep, source], label + '-preprocess')
            if text.returncode:
                return None
            asm = out / (label + '.s')
            asm.write_text(text.stdout.replace('%%', '\n').replace(';', '\n'))
            result = run([flags[0], '-target', 'arm64-apple-darwin', '-mcpu=cortex-a76',
                          '-x', 'assembler', '-c', asm, '-o', obj], label + '-assemble')
        else:
            result = run([*flags, '-MD', '-MF', dep, '-c', source, '-o', obj], label + '-compile')
        actual = deps(dep) if dep.exists() else None
        if actual is not None and actual != before:
            raise ValueError('Consumed header closure changed')
        records[label] = dict(scanned_sha256=before, consumed_sha256=actual,
                              compile_returncode=result.returncode)
        return obj if not result.returncode else None

    old = next(c['command'] for c in prior['commands']
               if c['stdout'].endswith('/target-strcasestr-compile.stdout'))
    target = old[:old.index('-MD')] + ['-include', str(private)]
    old = next(c['command'] for c in log['commands']
               if c['stdout'].endswith('/continuous-time-compile.stdout'))
    wrapper_flags = old[:old.index('-MD')]
    old = next(c['command'] for c in syscalls['commands']
               if c['stdout'].endswith('/target-initgroups-preprocess.stdout'))
    assembly_flags = old[:old.index('-E')]
    objects = [compile_(target, clock, 'clock')]
    objects += [compile_(wrapper_flags, p, p.stem) for p in mach]
    objects += [compile_(assembly_flags, thread, 'thread-selfusage', True)]
    missing, duplicates = None, None
    if all(objects):
        archive = out / 'UNQUALIFIED-clock-private.a'
        if run(['xcrun', 'ar', 'rcs', archive, *objects], 'archive').returncode:
            raise ValueError('Archive failed')
        run(['xcrun', 'nm', '-g', archive], 'symbols')
        run(['xcrun', 'llvm-objdump', '-d', '-r', *objects], 'disassembly')
        link = list(next(c['command'] for c in prior['commands']
                         if c['stdout'].endswith('/target-link.stdout')))
        link[link.index('-o') + 1] = str(out / 'NOT_RUN_ssh')
        link[link.index('-map') + 1] = str(out / 'target.map')
        linked = run([*link, archive], 'target-link')
        missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', linked.stderr, re.M)))
        duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", linked.stderr)))
    verify()
    for name, digest in headers.items():
        if sha(name) != digest:
            raise ValueError('Header changed during compilation')
    report = dict(profile='unchanged-apple-clock-private-dependency-inventory-v2',
        source_inputs_sha256=pins, headers_sha256=headers, dependency_records=records,
        commands=commands, objects=[str(p) if p else None for p in objects],
        whole_original_clock_tu_unchanged=True, original_mach_provider_bodies_unchanged=True,
        private_declaration_source=str(private), previous_missing_count=47,
        target_missing_symbols=missing, target_duplicate_symbols=duplicates,
        closed_symbols=sorted(set(prior['target_missing_symbols'])-set(missing)) if missing is not None else [],
        newly_reachable_symbols=sorted(set(missing)-set(prior['target_missing_symbols'])) if missing is not None else [],
        provider_admitted=False, native_clock_calls_executed=False, target_executed=False,
        clock_setting_executed=False, accepted_runtime_modified=False,
        known_original_error_paths_unqualified=True,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    return out, report


if __name__ == '__main__':
    output, report = audit()
    print(json.dumps(dict(output=str(output), manifest_sha256=sha(output/'manifest.json'),
        compiled=sum(p is not None for p in report['objects']), closed=report['closed_symbols'],
        new=report['newly_reachable_symbols'], missing=report['target_missing_symbols'],
        duplicates=report['target_duplicate_symbols'], provider_admitted=False)))
