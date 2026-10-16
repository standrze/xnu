#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Save one exact GPIO32 reset/C22 package audit; never prepare or publish."""
import hashlib
import json
import os
from pathlib import Path
import time

from tools.rpi5 import check_pcie_phy_reset_package as checker
from tools.rpi5.check_pcie_gem_selected_package import same

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'build/rpi5/pcie-id-trial-q5lw58tf'
MANIFEST_SHA = '0c8b015a71ce65269e4b4d2373745f399673c95db2e5e59f86b72231f658c6fb'
IMAGE_SHA = '6627559f8dc8e3a78329203300b85507403a5a32c2d4b21a473834dac44c892f'
MARKER = 'RPI5XNU:BL33:PCIE_PHY_RESET_TRIAL TAG=617795334d2b4c95a4e7712c4ac20b65 CPUS=1 NO_CPU_ON NO_INIT ZERO_SERIAL_INPUT'
FIRMWARE_SHA = 'dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b'
REPORT_DIR = ROOT / 'build/rpi5/pcie-phy-reset-qualification-20261014'
CASE_DIR = ROOT / 'build/rpi5/pcie-phy-reset-case-20261014'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=True) + '\n')
        handle.flush()
        os.fsync(handle.fileno())


def main():
    if REPORT_DIR.exists() or CASE_DIR.exists():
        raise ValueError('Fresh report and case destinations required')
    if sha(PACKAGE / 'manifest.json') != MANIFEST_SHA or sha(PACKAGE / 'probe.bin') != IMAGE_SHA:
        raise ValueError('Exact frozen GPIO32 reset package required')
    paths = [ROOT / 'tools/rpi5' / name for name in (
        'check_pcie_phy_reset_package.py', 'build_pcie_phy_reset_package.py',
        'pcie_phy_reset_serial_core.py', 'pcie_phy_reset_trace_profile.py',
        'build_pcie_phy_reset_kernel.py', 'rp1_phy_reset_transport_profile.py',
        'rp1_gem_mdio_timed_profile.py', 'rp1_phy_gpio_sources.json',
        'rp1_gem_mdio_sources.json',
        'tests/test_pcie_phy_reset_package.py', 'tests/test_pcie_phy_reset_serial.py',
        'tests/test_pcie_phy_reset_kernel.py', 'tests/test_rp1_phy_reset_transport.py',
        'tests/test_rp1_phy_reset_cycle.py', 'tests/rp1_phy_reset_cycle_host.c',
        'tests/test_rp1_gem_mdio_timed.py')]
    paths += [ROOT / 'loader/rpi5/rp1_phy_reset_cycle.c',
              ROOT / 'loader/rpi5/rp1_phy_reset_cycle.h', Path(__file__).resolve()]
    pins = {str(path): sha(path) for path in paths}
    started = time.monotonic()
    report = checker.inspect(PACKAGE)
    elapsed = time.monotonic() - started
    expected = dict(manifest_sha256=MANIFEST_SHA, image_sha256=IMAGE_SHA,
                    image_bytes=18214120, marker=MARKER, firmware_sha256=FIRMWARE_SHA)
    if not all(same(report.get(name), value) for name, value in expected.items()):
        raise ValueError('Actual complete checker report differs from frozen case')
    for field in ('checks', 'reset_package_checks'):
        if not isinstance(report.get(field), dict) or not report[field] or not all(
                value is True for value in report[field].values()):
            raise ValueError('All actual package checks must pass')
    for name, value in pins.items():
        if sha(name) != value:
            raise ValueError('Case source changed during audit')
    descriptor = dict(
        format='rpi5-zero-tx-pcie-case-v3', name='pcie-phy-reset-20261014',
        adapter='pcie-phy-reset', package=str(PACKAGE),
        package_manifest_sha256=MANIFEST_SHA,
        checker='tools.rpi5.check_pcie_phy_reset_package',
        protocol='tools.rpi5.pcie_phy_reset_serial_core', source_sha256=pins,
        marker=MARKER, firmware_sha256=FIRMWARE_SHA, hardware_allowed=True)
    REPORT_DIR.mkdir()
    save(REPORT_DIR / 'checker-report.json', report)
    CASE_DIR.mkdir()
    save(CASE_DIR / 'descriptor.json', descriptor)
    result = dict(
        checker_invocations=1, checker_seconds=elapsed,
        report=str(REPORT_DIR / 'checker-report.json'),
        report_sha256=sha(REPORT_DIR / 'checker-report.json'),
        descriptor=str(CASE_DIR / 'descriptor.json'),
        descriptor_sha256=sha(CASE_DIR / 'descriptor.json'), source_members=len(pins),
        hardware_executed=False, trial_prepared=False,
        note='Offline package audit only; no live controller or hardware admission')
    save(REPORT_DIR / 'validation.json', result)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
