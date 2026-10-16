#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Non-executing forced-provider clock link against the genuine case contract."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from tools.rpi5 import prepare_pid1

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'build/rpi5/apple-ssh-case-signal-z9p6dj86'
BASE_SHA = '6536a620946ddf6cd2f497dfcec784d7e759b07a95c0ab1f9cfe04f40fe31599'
CLOCK = ROOT / 'build/rpi5/apple-clock-checked-acrq3vpm'
CLOCK_SHA = 'a2db7650517f1a30ba7374f9737ed18965c92fd4ec2126596e85febe193b7a52'
FORCE = ('_clock_gettime', '_clock_gettime_nsec_np', '_clock_getres', '_clock_settime',
         '_mach_boottime_usec', '_mach_approximate_time',
         '_mach_continuous_approximate_time', '___thread_selfusage')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit():
    pins = {str(Path(__file__).resolve()): sha(__file__),
            str(Path(prepare_pid1.__file__).resolve()): sha(prepare_pid1.__file__)}
    manifests = []
    for directory, expected in ((BASE, BASE_SHA), (CLOCK, CLOCK_SHA)):
        path = directory / 'manifest.json'
        if sha(path) != expected:
            raise ValueError('Exact static-contract input manifest required')
        pins[str(path)] = expected
        manifest = json.loads(path.read_text())
        manifests.append(manifest)
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, digest in manifest[key].items():
                if name in pins and pins[name] != digest:
                    raise ValueError('Inherited source pin conflict: ' + name)
                pins[name] = digest

    def verify():
        for name, digest in pins.items():
            if sha(name) != digest:
                raise ValueError('Static-contract input drift: ' + name)

    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-clock-static-contract-', dir=ROOT / 'build/rpi5'))
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
        return result

    original = next(c['command'] for c in manifests[0]['commands']
                    if c['stdout'].endswith('/contract-link.stdout'))
    link = list(original)
    target, mapping = out / 'NOT_RUN_clock_contract', out / 'contract.map'
    link[link.index('-o') + 1] = str(target)
    link[link.index('-map') + 1] = str(mapping)
    link += [manifests[1]['target_archive']]
    for symbol in FORCE:
        link += ['-u', symbol]
    result = run(link, 'contract-link')
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', result.stderr, re.M)))
    duplicate = sorted(set(re.findall(r"duplicate symbol '([^']+)'", result.stderr)))
    inspected, owners = None, {}
    if not result.returncode:
        undefined = run(['xcrun', 'nm', '-ju', target], 'undefined')
        if undefined.returncode or undefined.stdout:
            raise ValueError('Linked contract contains undefined symbols')
        inspected = prepare_pid1.inspect(target.read_bytes())
        run(['xcrun', 'llvm-objdump', '-d', target], 'disassembly')
        text = mapping.read_text()
        objects = {int(n): path for n, path in re.findall(r'(?m)^\[\s*(\d+)\]\s+(.+)$', text)}
        for symbol in (*FORCE, '_mach_continuous_time', '_mach_absolute_time', '_mach_timebase_info',
                       '_gettimeofday', '_getrusage', '_settimeofday', '_sysctlbyname'):
            matches = re.findall(r'(?m)^0x[0-9a-fA-F]+\s+0x[0-9a-fA-F]+\s+\[\s*(\d+)\]\s+' + re.escape(symbol) + '$', text)
            if len(matches) != 1:
                raise ValueError('Exact live provider required: ' + symbol)
            owners[symbol] = objects[int(matches[0])]
        if re.search(r'(fixture_|__asan|__ubsan|___udivti3)', text):
            raise ValueError('Host fixture/runtime helper leaked into target')
    verify()
    report = dict(profile='apple-clock-forced-static-provider-contract-v1',
        source_inputs_sha256=pins, base_link_command=original, commands=commands,
        target=str(target), forced_symbols=list(FORCE), linked=result.returncode == 0,
        missing_symbols=missing, duplicate_symbols=duplicate, live_symbol_owners=owners,
        static_inspection=inspected, target_executed=False, clock_setting_executed=False,
        native_callbacks_linked=False, full_ssh_client_qualified=False,
        generated_sha256={str(p): sha(p) for p in out.iterdir() if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(output=str(out), manifest_sha256=sha(out / 'manifest.json'),
                          linked=report['linked'], missing=missing, duplicate=duplicate)))
    return out, report


if __name__ == '__main__':
    audit()
