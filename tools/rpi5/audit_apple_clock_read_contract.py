#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only clock linkage; preserves the failed separately forced setter trial."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
from tools.rpi5 import audit_apple_clock_static_contract as prior

ROOT, sha = prior.ROOT, prior.sha
FAILURE = ROOT / 'build/rpi5/apple-clock-static-contract-9g46utl5'
FAILURE_SHA = 'a2c7ee6b6510e86b8447fd7c4fc41a155ac0939dc8032f89aa10f56e16364209'


def audit():
    path = FAILURE / 'manifest.json'
    if sha(path) != FAILURE_SHA:
        raise ValueError('Exact failed setter contract required')
    old = json.loads(path.read_text())
    if old['linked'] or old['missing_symbols'] != ['_settimeofday'] or old['duplicate_symbols']:
        raise ValueError('Unexpected predecessor outcome')
    pins = old['source_inputs_sha256'] | old['generated_sha256'] | {
        str(path): FAILURE_SHA, str(Path(__file__).resolve()): sha(__file__)}

    def verify():
        for name, digest in pins.items():
            if sha(name) != digest:
                raise ValueError('Clock contract input drift: ' + name)

    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-clock-read-contract-', dir=ROOT / 'build/rpi5'))
    print('OUTPUT=' + str(out), flush=True)
    commands = []

    def run(args, label):
        args = list(map(str, args))
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=90)
        for stream in ('stdout', 'stderr'):
            (out / (label + '.' + stream)).write_text(getattr(result, stream))
        commands.append(dict(command=args, returncode=result.returncode,
                             stdout=str(out / (label + '.stdout')),
                             stderr=str(out / (label + '.stderr'))))
        if result.returncode:
            raise ValueError(label + ': ' + result.stderr)
        return result

    link = list(old['commands'][0]['command'])
    if link.count('_clock_settime') != 1 or link[link.index('_clock_settime') - 1] != '-u':
        raise ValueError('Exact forced setter pair required')
    index = link.index('_clock_settime')
    del link[index - 1:index + 1]
    target, mapping = out / 'NOT_RUN_clock_read_contract', out / 'contract.map'
    link[link.index('-o') + 1] = str(target)
    link[link.index('-map') + 1] = str(mapping)
    run(link, 'contract-link')
    undefined = run(['xcrun', 'nm', '-ju', target], 'undefined')
    if undefined.stdout:
        raise ValueError('Read-only contract has undefined symbols')
    inspected = prior.prepare_pid1.inspect(target.read_bytes())
    run(['xcrun', 'llvm-objdump', '-d', target], 'disassembly')
    text = mapping.read_text()
    objects = {int(n): p for n, p in re.findall(r'(?m)^\[\s*(\d+)\]\s+(.+)$', text)}
    expected = {
        '_clock_gettime': 'libapple-clock-checked.a(target-clock.o)',
        '_clock_gettime_nsec_np': 'libapple-clock-checked.a(target-clock.o)',
        '_clock_getres': 'libapple-clock-checked.a(target-clock.o)',
        '_mach_boottime_usec': 'libapple-clock-checked.a(mach_boottime.o)',
        '_mach_approximate_time': 'libapple-clock-checked.a(mach_approximate_time.o)',
        '___thread_selfusage': 'libapple-clock-checked.a(thread-selfusage.o)',
        '_mach_continuous_approximate_time': 'libapple-pthread-log.a(continuous-time.o)',
        '_mach_continuous_time': 'libapple-pthread-log.a(continuous-time.o)',
        '_mach_absolute_time': 'libapple-pthread-log.a(absolute-time.o)',
        '_mach_timebase_info': 'private-abi-runtime.a(12-darwin_entry.o)',
    }
    owners = {}
    for symbol in (*expected, '_gettimeofday', '_getrusage', '_sysctlbyname'):
        matches = re.findall(r'(?m)^0x[0-9a-fA-F]+\s+0x[0-9a-fA-F]+\s+\[\s*(\d+)\]\s+' + re.escape(symbol) + '$', text)
        if len(matches) != 1:
            raise ValueError('Exactly one live symbol required: ' + symbol)
        owner = objects[int(matches[0])]
        if symbol in expected and not owner.endswith(expected[symbol]):
            raise ValueError('Unexpected provider for ' + symbol + ': ' + owner)
        owners[symbol] = owner
    if re.search(r'(fixture_|__asan|__ubsan|___udivti3)', text):
        raise ValueError('Host fixture or new division runtime leaked into target')
    if re.search(r'(?m)^0x.*\s(_clock_settime|_settimeofday)$', text):
        raise ValueError('Setter unexpectedly present in read contract')
    # These are explicitly host-compiled ASan/UBSan executables with deterministic
    # renamed callbacks. Never invoke the Mach-O target created above.
    for mode in ('original', 'derived'):
        result = run([prior.CLOCK / ('host-' + mode), mode], 'native-' + mode)
        if result.stdout != 'APPLE_CLOCK ' + mode.upper() + ' PASS\n' or result.stderr:
            raise ValueError('Native boundary oracle changed')
    verify()
    report = dict(profile='apple-clock-read-only-forced-static-contract-v1',
        source_inputs_sha256=pins, commands=commands, live_symbol_owners=owners,
        target=str(target), target_sha256=sha(target), static_inspection=inspected,
        undefined_symbols=[], target_executed=False, clock_setting_executed=False,
        native_boundary_tests='Original and derived host callbacks only; not target clocks',
        setter_qualified=False, setter_missing_symbol='_settimeofday',
        full_ssh_client_qualified=False, generated_sha256={str(p): sha(p) for p in out.iterdir() if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(output=str(out), manifest_sha256=sha(out / 'manifest.json'),
                          target_sha256=sha(target), undefined=0, target_executed=False)))
    return out, report


if __name__ == '__main__':
    audit()
