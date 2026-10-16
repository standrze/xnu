#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Isolated one-character cursor correction to pristine Apple date-329.

Preserves the original rejected binary/source, the accepted pwd, all roots and
all kernels. Tests are native read-only formatting; never sets the clock.
"""
import difflib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

try:
    from . import build_apple_current_commands as base
except ImportError:
    import build_apple_current_commands as base

PACKAGE = base.ROOT / 'build/rpi5/apple-current-commands-qg7qd51g'
MANIFEST_SHA = '58f43461d7f9768400afe01972ad409e9c88845655e1eaeddd378c75f109a1c1'


def build():
    manifest = PACKAGE / 'manifest.json'
    if base.sha(manifest) != MANIFEST_SHA:
        raise ValueError('Current original command closure changed')
    previous = json.loads(manifest.read_text())
    pins = previous['source_inputs_sha256'] | previous['headers_sha256'] | previous['generated_sha256']
    pins[str(manifest)] = MANIFEST_SHA
    pins[str(Path(__file__).resolve())] = base.sha(Path(__file__).resolve())
    base.verify(pins)
    source = base.pristine(base.SHELL, base.SHELL_COMMIT, 'date/date.c')
    before = source.read_text()
    old = '\t\t\t\ttok = newformat + prefixlen + 9;'
    new = '\t\t\t\ttok = newformat + prefixlen + 8;'
    if before.count(old) != 1:
        raise ValueError('Expected exactly one original token cursor assignment')
    after = before.replace(old, new)
    out = Path(tempfile.mkdtemp(prefix='apple-date-cursor-', dir=base.ROOT / 'build/rpi5'))
    derived = out / 'date.c'
    derived.write_text(after)
    (out / 'date.c.diff').write_text(''.join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True), fromfile=str(source), tofile=str(derived))))
    commands, headers = [], {}

    def run(args, label, **kwargs):
        args = list(map(str, args))
        r = subprocess.run(args, cwd=base.ROOT, capture_output=True, text=True, timeout=30, **kwargs)
        stdout, stderr = out / (label + '.stdout'), out / (label + '.stderr')
        stdout.write_text(r.stdout)
        stderr.write_text(r.stderr)
        commands.append(dict(command=args, returncode=r.returncode, stdout=str(stdout), stderr=str(stderr)))
        return r

    def paths(raw):
        return {str(Path(v).resolve()): base.sha(Path(v).resolve())
                for v in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}

    linked = {}
    for flavor in ('target', 'native'):
        old_object = PACKAGE / ('date-date.o' if flavor == 'target' else 'date-native-date.o')
        matches = [r['command'] for r in previous['commands']
                   if '-c' in r['command'] and str(old_object) in r['command']]
        if len(matches) != 1:
            raise ValueError('Missing original date compile command')
        args = matches[0]
        args = args[:args.index('-MD')]
        obj = out / (flavor + '-date.o')
        args = [str(derived) if a == str(source) else str(obj) if a == str(old_object) else a for a in args]
        args += ['-I', str(source.parent)]
        scan, skip = [], False
        for token in args:
            if skip:
                skip = False
            elif token == '-o':
                skip = True
            elif token != '-c':
                scan.append(token)
        scanned = run(scan + ['-M'], flavor + '-dependencies')
        if scanned.returncode:
            raise ValueError('Date overlay dependency scan failed')
        dependency_before = paths(scanned.stdout)
        dep = out / (flavor + '.d')
        r = run(args + ['-MD', '-MF', dep], flavor + '-compile')
        if r.returncode or paths(dep.read_text()) != dependency_before:
            raise ValueError('Date overlay actual compile failed or dependencies changed')
        headers.update(dependency_before)
        label = 'date-link.stderr' if flavor == 'target' else 'date-native-link.stderr'
        old_link = [r['command'] for r in previous['commands'] if Path(r['stderr']).name == label]
        if len(old_link) != 1:
            raise ValueError('Missing original date link')
        binary = out / ('date' if flavor == 'target' else 'date-native')
        old_binary = PACKAGE / ('date' if flavor == 'target' else 'date-native')
        args = [str(obj) if a == str(old_object) else str(binary) if a == str(old_binary)
                else str(out / 'date.map') if a == str(PACKAGE / 'date.map') else a for a in old_link[0]]
        r = run(args, flavor + '-link')
        linked[flavor] = dict(returncode=r.returncode, binary=str(binary) if r.returncode == 0 else None,
                              missing_symbols=re.findall(r'^\s+"([^"]+)", referenced from:', r.stderr, re.M))
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1', LC_ALL='C', TZ='UTC0')
    env.pop('COMMAND_MODE', None)
    rejected = run([previous['programs']['date']['native_executable'], '-u', '-r', '0', '-Ins'],
                   'original-rejected-nanoseconds', env=env)
    if rejected.returncode == 0 or 'AddressSanitizer: heap-buffer-overflow' not in rejected.stderr:
        raise ValueError('Original bug did not reproduce as expected')
    program = linked['native']['binary']
    if program is None:
        raise ValueError('Corrected native date did not link')
    cases = [('ins', ['-u', '-r', '0', '-Ins'], '1970-01-01T00:00:00,000000000+00:00\n')]
    for index, (fmt, expected) in enumerate((
        ('%N', '000000000'), ('%N%N', '000000000000000000'),
        ('%N-%N', '000000000-000000000'), ('%N%%N', '000000000%N'),
        ('%%N', '%N'), ('x%N', 'x000000000'), ('%Nx', '000000000x'),
        ('%N%Y', '0000000001970'), ('%Y%N', '1970000000000'),
        ('%N%N%N', '000000000000000000000000000'),
        ('', ''), ('%Y-%m-%dT%H:%M:%SZ', '1970-01-01T00:00:00Z'),
    )):
        cases.append(('format-' + str(index), ['-u', '-r', '0', '+' + fmt], expected + '\n'))
    results = []
    for label, args, expected in cases:
        r = run([program, *args], 'fixed-' + label, env=env)
        if r.returncode or r.stdout != expected or r.stderr:
            raise ValueError('Corrected read-only date case failed: ' + label)
        results.append(dict(case=label, command=args, expected=expected, passed=True))
    base.verify(pins)
    base.verify(headers)
    report = dict(profile='apple-date329-cursor-overlay-v1',
                  original_source=str(source), original_sha256=base.sha(source),
                  derived_source=str(derived), derived_sha256=base.sha(derived),
                  exact_change='newformat + prefixlen + 9 becomes +8 before the for-loop increment',
                  reason='Resume at first suffix byte after loop increment, including the terminating NUL',
                  original_nanosecond_asan_failure_reproduced=True, fixed_native_cases=results,
                  link_results=linked, source_inputs_sha256=pins, headers_sha256=headers, commands=commands,
                  generated_sha256={str(p): base.sha(p) for p in out.iterdir() if p.is_file()},
                  static_date_accepted=False, pi_executed=False, installed=False, system_clock_set=False)
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return out, report


if __name__ == '__main__':
    out, report = build()
    print(json.dumps(dict(output=str(out), native_cases=len(report['fixed_native_cases']),
                          original_rejected=report['original_nanosecond_asan_failure_reproduced'],
                          static_target=report['link_results']['target']), indent=2))
