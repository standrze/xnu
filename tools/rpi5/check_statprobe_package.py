#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preflight one isolated raw-file diagnostic package; no device access."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_serial_terminal_package as terminal
from build_probe import inspect as inspect_elf
from check_zsh_trial_package import profile_checks, KERNEL, KERNEL_SHA, BASELINE, ROOT
from pcie_stack import check as stack_check
from prepare_statprobe_root import prepare, ACCEPTED_ROOT, ROOT_PIN

INIT = ROOT / 'build/rpi5/statprobe-root-20261012-v2/ramdisk.bin'
INIT_SHA = '5644490c8969d930ad706101ab0656dcfafac78846aca51933f2eb3ec128cc23'
PROBE_SHA = 'a5f7121221bc2ffafb91b599bf2bcc1a6003e8c88da00cc855b398a38fa47917'


def _inspect_with_kernel(package, kernel, kernel_sha):
    package = package.resolve()
    if not package.is_relative_to(ROOT / 'build/rpi5'):
        raise ValueError('Separate local build/rpi5 package required')
    report = terminal.inspect(package, kernel, INIT, BASELINE, shell_trial=True)
    manifest = json.loads((package / 'manifest.json').read_text())
    root_manifest = json.loads(INIT.with_name('manifest.json').read_text())
    diagnostic = INIT.with_name('statprobe').read_bytes()
    reconstructed, preservation = prepare(ACCEPTED_ROOT.read_bytes(), diagnostic, ROOT_PIN)
    raw = (package / 'probe.bin').read_bytes()
    loads = inspect_elf((package / 'probe.elf').read_bytes(), raw, 0x9000000)
    checks = report['checks']
    checks.update(profile_checks(manifest))
    checks.update(
        proven_kernel_unchanged=report['kernel_sha256'] == kernel_sha,
        diagnostic_root_pinned=report['init_sha256'] == INIT_SHA,
        diagnostic_binary_pinned=terminal.sha256(INIT.with_name('statprobe')) == PROBE_SHA,
        exact_additive_root=reconstructed == INIT.read_bytes(),
        recovery_and_frozen_zsh_preserved=preservation['preserved_files_sha256']
            == root_manifest.get('preserved_files_sha256'),
        exact_root_extent=root_manifest.get('output_bytes') == 1441792
            and root_manifest.get('output_nodes') == 25
            and root_manifest.get('output_sha256') == INIT_SHA,
        expected_loader_entry=loads['entry'] == manifest.get('entry') == 0x9000000,
        diagnostic_markers_embedded=all(marker in raw for marker in (
            b'STATPROBE:BEGIN:RAW_DARWIN_STAT64_V1', b'STATPROBE:END:DIAGNOSTIC_ONLY',
            b'/etc/statprobe-missing', b'/etc/zsh-smoke.zsh')),
        root_sources_and_sdk_unchanged=all(
            mapping and all(terminal.sha256(Path(name)) == value for name, value in mapping.items())
            for mapping in (root_manifest.get('source_inputs_sha256', {}),
                            root_manifest.get('sdk_headers_sha256', {}))),
        loader_sources_and_outputs_unchanged=bool(manifest.get('sha256')) and all(
            terminal.sha256(ROOT / name) == value for name, value in manifest['sha256'].items()),
        stack_budget_matches=stack_check(manifest['stack_frames'])
            == manifest.get('gate5_pcie_topology_stack_budget'),
    )
    report.update(preflight_pass=all(checks.values()), image_bytes=len(raw),
                  loader_manifest_sha256=terminal.sha256(package / 'manifest.json'),
                  root_manifest_sha256=terminal.sha256(INIT.with_name('manifest.json')),
                  root_mount_marker='RPI5XNU:RAMROOT:MOUNT NODES=25 BYTES=1441792 READONLY',
                  scope='Raw stat/open/fcntl package preflight only; no Pi result',
                  pi_executed=False, script_file_acceptance=False,
                  abi_root_cause_proven=False, networking=False, durability=False,
                  sd_actions=0, serial_actions=0, reboots=0)
    if not report['preflight_pass']:
        raise ValueError('Diagnostic package refused: ' + repr([k for k, ok in checks.items() if not ok]))
    return report


def inspect(package):
    # Preserve the original diagnostic's exact historical public profile.
    return _inspect_with_kernel(package, KERNEL, KERNEL_SHA)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--report', type=Path, help='New local report only')
    args = parser.parse_args()
    report = inspect(args.package)
    encoded = json.dumps(report, sort_keys=True, indent=2) + '\n'
    if args.report:
        with args.report.open('x') as output:
            output.write(encoded)
    print(encoded, end='')


if __name__ == '__main__':
    main()
