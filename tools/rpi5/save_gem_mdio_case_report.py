#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Save one real package audit and fixed case data, never prepare or publish."""
import hashlib
import json
import os
from pathlib import Path
import time
from tools.rpi5 import check_pcie_gem_mdio_package as checker

ROOT=Path(__file__).resolve().parents[2]
PACKAGE=ROOT/'build/rpi5/pcie-id-trial-qthzh5e7'
MANIFEST_SHA='6c18b4c7b24346fdd08cda0f8e187d502b694e5f8d0bb8f79973641d24a44173'
IMAGE_SHA='181e58ee6326b625b3c58a1d2c288d16db0e0c1498fdf4f9ed8bb965e7436026'
MARKER='RPI5XNU:BL33:PCIE_GEM_MDIO_TRIAL TAG=bff69a28a78d4f3087da5f4ac6ec8b22 CPUS=1 NO_CPU_ON NO_INIT ZERO_SERIAL_INPUT'
FIRMWARE_SHA='dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b'
REPORT_DIR=ROOT/'build/rpi5/gem-mdio-controller-report-20261014'
CASE_DIR=ROOT/'build/rpi5/pcie-gem-mdio-case-20261014'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    with path.open('x') as handle:
        handle.write(json.dumps(value,indent=2,sort_keys=True)+'\n')
        handle.flush();os.fsync(handle.fileno())


def main():
    if REPORT_DIR.exists() or CASE_DIR.exists():raise ValueError('Fresh report and case destinations required')
    if sha(PACKAGE/'manifest.json')!=MANIFEST_SHA or sha(PACKAGE/'probe.bin')!=IMAGE_SHA:
        raise ValueError('Exact frozen capability image required')
    paths=[ROOT/'tools/rpi5'/name for name in (
        'check_pcie_gem_mdio_package.py','build_pcie_gem_mdio_package.py',
        'pcie_gem_mdio_serial_core.py','pcie_gem_mdio_trace_profile.py','pcie_gem_mdio_id_profile.py',
        'build_pcie_gem_mdio_kernel.py','build_pcie_gem_mdio_id_kernel.py','rp1_gem_mdio_profile.py',
        'tests/test_pcie_gem_mdio_package.py','tests/test_pcie_gem_mdio_serial.py',
        'tests/test_pcie_gem_mdio_kernel.py','tests/test_pcie_gem_mdio_id.py','tests/test_rp1_gem_mdio.py',
        'tests/rp1_gem_mdio_host.c','rp1_gem_mdio_sources.json')]
    paths += [ROOT/'loader/rpi5/rp1_gem_mdio.c',ROOT/'loader/rpi5/rp1_gem_mdio.h',Path(__file__).resolve()]
    pins={str(path):sha(path) for path in paths}
    started=time.monotonic()
    report=checker.inspect(PACKAGE)
    elapsed=time.monotonic()-started
    if (report['manifest_sha256']!=MANIFEST_SHA or report['image_sha256']!=IMAGE_SHA or
        report['image_bytes']!=18193720 or report['marker']!=MARKER or
        report['firmware_sha256']!=FIRMWARE_SHA or not all(report['checks'].values()) or
        not all(report['mdio_package_checks'].values())):
        raise ValueError('Actual complete checker report differs from frozen case')
    for name,value in pins.items():
        if sha(name)!=value:raise ValueError('Case source changed during audit')
    descriptor=dict(format='rpi5-zero-tx-pcie-case-v3',name='pcie-gem-mdio-20261014',
        adapter='pcie-gem-mdio',package=str(PACKAGE),package_manifest_sha256=MANIFEST_SHA,
        checker='tools.rpi5.check_pcie_gem_mdio_package',
        protocol='tools.rpi5.pcie_gem_mdio_serial_core',source_sha256=pins,
        marker=MARKER,firmware_sha256=FIRMWARE_SHA,hardware_allowed=True)
    REPORT_DIR.mkdir();save(REPORT_DIR/'checker-report.json',report)
    CASE_DIR.mkdir();save(CASE_DIR/'descriptor.json',descriptor)
    result=dict(checker_invocations=1,checker_seconds=elapsed,
        report=str(REPORT_DIR/'checker-report.json'),report_sha256=sha(REPORT_DIR/'checker-report.json'),
        descriptor=str(CASE_DIR/'descriptor.json'),descriptor_sha256=sha(CASE_DIR/'descriptor.json'),
        source_members=len(pins),hardware_executed=False,trial_prepared=False,
        note='Real offline package audit; no live controller or hardware admission')
    save(REPORT_DIR/'validation.json',result)
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=='__main__':main()
