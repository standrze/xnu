#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Inventory the unchanged Apple clock TU; never admit or execute a provider."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_case_signal as base

PREDECESSOR = base.ROOT / 'build/rpi5/apple-ssh-case-signal-z9p6dj86'
PREDECESSOR_SHA = '6536a620946ddf6cd2f497dfcec784d7e759b07a95c0ab1f9cfe04f40fe31599'


def audit():
    manifest = PREDECESSOR / 'manifest.json'
    if base.sha(manifest) != PREDECESSOR_SHA:
        raise ValueError('Exact prior full-client composition required')
    previous = json.loads(manifest.read_text())
    source = base.LIBC / 'gen/clock_gettime.c'
    original = subprocess.check_output(['git', '-C', str(base.LIBC),
                                        'show', 'HEAD:gen/clock_gettime.c'])
    if original != source.read_bytes():
        raise ValueError('Unchanged complete Apple clock TU required')
    pins = {str(manifest): PREDECESSOR_SHA, str(source): base.sha(source),
            str(Path(__file__).resolve()): base.sha(__file__)}
    for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
        for name, digest in previous[key].items():
            if name in pins and pins[name] != digest:
                raise ValueError('Conflicting inherited evidence')
            pins[name] = digest
    def verify():
        for name, digest in pins.items():
            if base.sha(name) != digest:
                raise ValueError('Input drift: ' + name)
    verify()
    output = Path(tempfile.mkdtemp(prefix='apple-clock-inventory-', dir=base.ROOT / 'build/rpi5'))
    commands = []
    def run(command, label):
        command = list(map(str, command))
        result = subprocess.run(command, cwd=base.ROOT, capture_output=True,
                                text=True, timeout=90)
        for name in ('stdout', 'stderr'):
            (output / (label + '.' + name)).write_text(getattr(result, name))
        commands.append(dict(command=command, cwd=str(base.ROOT),
                             returncode=result.returncode, label=label))
        return result
    compile_command = next(c['command'] for c in previous['commands']
                           if c['stdout'].endswith('/target-strcasestr-compile.stdout'))
    flags = compile_command[:compile_command.index('-MD')]
    scan = output / 'clock.scan.d'
    scanned = run([*flags, '-M', '-MF', scan, source], 'scan')
    compiled = None
    consumed = {}
    missing = None
    duplicates = None
    if scanned.returncode == 0:
        def dependencies(path):
            raw = path.read_text().replace('\\\n', ' ').partition(':')[2]
            return {str(Path(p).resolve()): base.sha(Path(p).resolve()) for p in shlex.split(raw)}
        before = dependencies(scan)
        obj, dep = output / 'clock.o', output / 'clock.actual.d'
        compiled = run([*flags, '-MD', '-MF', dep, '-c', source, '-o', obj], 'compile')
        if compiled.returncode == 0:
            consumed = dependencies(dep)
            if consumed != before:
                raise ValueError('Actual clock dependency closure differs')
            archive = output / 'UNQUALIFIED-clock.a'
            if run(['xcrun', 'ar', 'rcs', archive, obj], 'archive').returncode:
                raise ValueError('Archive generation failed')
            run(['xcrun', 'llvm-objdump', '-d', '-r', obj], 'disassembly')
            link = list(next(c['command'] for c in previous['commands']
                             if c['stdout'].endswith('/target-link.stdout')))
            link[link.index('-o') + 1] = str(output / 'NOT_RUN_ssh')
            link[link.index('-map') + 1] = str(output / 'target.map')
            linked = run([*link, archive], 'target-link')
            missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', linked.stderr, re.M)))
            duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", linked.stderr)))
    verify()
    for name, digest in consumed.items():
        if base.sha(name) != digest:
            raise ValueError('Consumed header changed')
    report = dict(profile='apple-clock-whole-tu-dependency-inventory-v1',
        predecessor_manifest_sha256=PREDECESSOR_SHA, source_inputs_sha256=pins,
        headers_sha256=consumed, commands=commands, unchanged_original_source=True,
        scan_returncode=scanned.returncode,
        compile_returncode=compiled.returncode if compiled is not None else None,
        previous_missing_count=len(previous['target_missing_symbols']),
        target_missing_symbols=missing, target_duplicate_symbols=duplicates,
        closed_symbols=sorted(set(previous['target_missing_symbols'])-set(missing)) if missing is not None else [],
        newly_reachable_symbols=sorted(set(missing)-set(previous['target_missing_symbols'])) if missing is not None else [],
        provider_admitted=False, native_clock_calls_executed=False,
        target_executed=False, clock_setting_executed=False,
        full_client_qualified=False, accepted_runtime_modified=False,
        generated_sha256={str(p): base.sha(p) for p in output.iterdir() if p.is_file()})
    (output / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True)+'\n')
    return output, report


if __name__ == '__main__':
    output, report = audit()
    print(json.dumps(dict(output=str(output), manifest_sha256=base.sha(output / 'manifest.json'),
        scan_returncode=report['scan_returncode'], compile_returncode=report['compile_returncode'],
        closed=report['closed_symbols'], new=report['newly_reachable_symbols'],
        provider_admitted=False), sort_keys=True))
