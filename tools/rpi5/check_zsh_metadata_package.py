#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct corrective-kernel zsh/raw-stat profile, with storage disabled.

Never changes the original diagnostic's kernel pin or claims a physical fix.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_statprobe_package as previous
import check_metadata_storage_guard as guard
from audit_macho import inspect as inspect_macho
from audit_statprobe_metadata import CORRECTED as KERNEL, PINS
from check_hfs_stats_package import linked_getter

ROOT = previous.ROOT
KERNEL_SHA = PINS[KERNEL]
BUILD = ROOT / 'build/rpi5-xcode27/run-obi6gw3d/manifest.json'
BUILD_SHA = '743181872d06e338a295229e9dabe26a4093fa1f18cc41e56077bdc84b67b181'


def inspect(package):
    report = previous._inspect_with_kernel(package, KERNEL, KERNEL_SHA)
    build = json.loads(BUILD.read_text())
    raw = KERNEL.read_bytes()
    if previous.terminal.sha256(KERNEL) != KERNEL_SHA:
        raise ValueError('Preserved corrective kernel changed')
    segments = inspect_macho(raw)['segments']
    symbols = subprocess.check_output(['xcrun','nm','-nm',str(KERNEL)],text=True,timeout=30)
    wiring = linked_getter(raw, segments, symbols, (ROOT/'bsd/sys/mount.h').read_text())
    storage_guard = guard.inspect(raw, segments, symbols)
    image = (package/'probe.bin').read_bytes()
    exact_command = previous.terminal.TERMINAL_COMMAND + b'\0'
    checks = report['checks']
    del checks['proven_kernel_unchanged']
    checks.update(
        corrective_kernel_exact_pin=report['kernel_sha256'] == KERNEL_SHA,
        corrective_build_receipt_pinned=previous.terminal.sha256(BUILD) == BUILD_SHA,
        corrective_build_succeeded=type(build.get('exit_code')) is int and build['exit_code'] == 0,
        corrective_build_source_stable=build.get('source_unchanged_during_build') is True
            and build.get('source') == build.get('source_at_finish'),
        corrective_build_fresh_output=build.get('fresh_kernel_outputs') is True
            and KERNEL == Path(build['output_root'])/'obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712',
        actual_mount_stat_getter_wired=bool(wiring),
        actual_sd_start_requires_opt_in=storage_guard['absent_or_not_one_returns_false'] is True,
        actual_sd_write_provider_absent=storage_guard['write_provider_absent'] is True,
        exact_storage_off_runtime_command=image.count(exact_command) == 1,
    )
    report.update(preflight_pass=all(checks.values()), corrected_metadata_kernel=True,
                  kernel_build_manifest=str(BUILD), kernel_build_manifest_sha256=BUILD_SHA,
                  linked_mount_stat_getter=wiring, linked_storage_entry_guard=storage_guard,
                  script_file_acceptance=False, abi_root_cause_proven=False, pi_executed=False,
                  scope='Distinct storage-off corrected-kernel package; physical metadata/zsh success unproven')
    if not report['preflight_pass']:
        raise ValueError('Corrective package refused: ' + repr([k for k,v in checks.items() if not v]))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path)
    parser.add_argument('--report',type=Path)
    args = parser.parse_args()
    report = inspect(args.package.resolve())
    encoded = json.dumps(report,indent=2) + '\n'
    if args.report:
        with args.report.open('x') as output: output.write(encoded)
    print(encoded,end='')


if __name__ == '__main__':
    main()
