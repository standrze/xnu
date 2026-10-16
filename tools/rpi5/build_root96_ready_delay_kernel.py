#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct readiness-v2 kernel: one full post-enable interval, no extension.

The prior immediate-first-reload prototype and all accepted inputs stay intact.
The timestamp is release/acquire published independently of the legacy boolean:
a service observing an unset timestamp cannot announce readiness prematurely.
This is not arbitrary-console serialization or an assertion of SMP silence.
"""
import argparse
import json
from pathlib import Path
import re

try:
    from . import build_root96_ready_kernel as prior
except ImportError:
    import build_root96_ready_kernel as prior

ROOT, audit = prior.ROOT, prior.audit
BASE = ROOT / 'build/rpi5/root96-ready-kernel-20261013-checked'
BASE_SHA = '5c4bdc698d75197a28b12d878312bcb95d87f7d5f8428d0f930af5a56bc8dc24'
OLD_TRANSFORM = prior.transform
MARKER = prior.MARKER
ANNOUNCE = '''\tuint64_t report_after = __atomic_load_n(&rpi5_wdog_terminal_report_after, __ATOMIC_ACQUIRE);
\tif (rpi5_wdog_terminal_enabled && !rpi5_wdog_terminal_reported &&
\t    report_after != 0 && now >= report_after) {
\t\trpi5_wdog_terminal_reported = true;
\t\tkprintf("\\nRPI5XNU:TERMINAL:WATCHDOG_READY SECONDS=%u\\n",
\t\t    RPI5_TERMINAL_WDOG_SECONDS);
\t}
'''


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Readiness-v2 source boundary changed: ' + old)
    return text.replace(old, new)


def transform(source):
    text = OLD_TRANSFORM(source)
    text = replace_once(text, 'static bool rpi5_wdog_terminal_reported;\n',
        'static bool rpi5_wdog_terminal_reported;\nstatic uint64_t rpi5_wdog_terminal_report_after;\n')
    text = replace_once(text,
        '\trpi5_wdog_deadline = now + frequency * RPI5_TERMINAL_WDOG_SECONDS;\n',
        '\trpi5_wdog_deadline = now + frequency * RPI5_TERMINAL_WDOG_SECONDS;\n'
        '\t/* The checked 180-second expression also bounds this 5-second sum. */\n'
        '\t__atomic_store_n(&rpi5_wdog_terminal_report_after,\n'
        '\t    now + frequency * RPI5_WDOG_RELOAD_SECONDS, __ATOMIC_RELEASE);\n')
    return replace_once(text, prior.ANNOUNCE, ANNOUNCE)


def build(output):
    manifest = BASE / 'manifest.json'
    if audit.sha(manifest) != BASE_SHA:
        raise ValueError('Frozen readiness-v1 prototype changed')
    old = json.loads(manifest.read_text())
    pins = old['inputs_sha256'] | old['generated_sha256'] | {str(manifest): BASE_SHA}
    for path in (Path(__file__).resolve(), ROOT / 'tools/rpi5/tests/test_root96_ready_delay_kernel.py',
                 ROOT / 'tools/rpi5/tests/test_root96_ready_kernel.py'):
        pins[str(path)] = audit.sha(path)
    def verify():
        for name, digest in pins.items():
            if audit.sha(Path(name)) != digest:
                raise ValueError('Readiness-v2 input changed: ' + name)
    verify()
    old_transform = prior.transform
    prior.transform = transform
    try:
        result = prior.build(output)
    finally:
        prior.transform = old_transform
    verify()
    output = output.resolve()
    assembly = (output / 'pe_fiq.s').read_text()
    def function(name):
        start = assembly.index('_' + name + ':')
        return assembly[start:assembly.index('; -- End function', start)]
    enable = function('pe_rpi5_watchdog_enable_terminal')
    service = function('pe_rpi5_watchdog_timer_tick')
    if '_rpi5_wdog_terminal_report_after@PAGE' not in enable or not re.search(r'\bstlr\s+x\d+,', enable):
        raise ValueError('No emitted release publication of report threshold')
    if '_rpi5_wdog_terminal_report_after@PAGE' not in service or not re.search(r'\b(?:ldar|ldapr)\s+x\d+,', service):
        raise ValueError('No emitted acquire observation of report threshold')
    for name, digest in pins.items():
        if name in result['inputs_sha256'] and result['inputs_sha256'][name] != digest:
            raise ValueError('Conflicting readiness-v2 source pin')
        result['inputs_sha256'][name] = digest
    result.update(profile='root96-terminal-ready-delay-kernel-v2',
        readiness_prototype_manifest_sha256=BASE_SHA,
        first_notice_minimum_post_enable_seconds=5,
        first_notice_requires_successful_reload=True,
        readiness_timestamp_publication='ARM64 release stlr/acquire ldar-or-ldapr; zero means not published',
        watchdog_hardware_timeout_seconds=15, watchdog_service_interval_seconds=5,
        deadline_extended=False, arbitrary_console_serialization=False)
    (output / 'manifest.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    report = build(parser.parse_args().output_dir)
    print(json.dumps({k: report[k] for k in ('kernel', 'kernel_sha256', 'kernel_bytes', 'profile')}))
