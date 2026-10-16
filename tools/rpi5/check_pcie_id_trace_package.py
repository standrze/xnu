#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Validate the passive ID failure-trace loader without touching hardware."""
import argparse
import json
from pathlib import Path
try:
    from . import build_pcie_id_trace_package as source
except ImportError:
    import build_pcie_id_trace_package as source


def inspect(package):
    package=package.resolve();builder=source.configured_builder()
    checker=source.load_private(source.PRIOR_CHECKER,'_rpi5_private_trace_checker')
    checker.builder=builder
    result=checker.inspect(package)
    record=json.loads((package/'manifest.json').read_text())
    # Round-trip numeric reason keys exactly as JSON serialization stores them.
    contract=json.loads(json.dumps(source.trace_contract()))
    checks=dict(actual_end_telemetry=record.get('trace_contract')==contract,
        actual_native_loader=record.get('native_loader_comparison')==source.native_comparison(package),
        retained_fdt_not_overlapped=max(row['address']+row['memory_size'] for row in record['loads'])<0xb000000,
        failed_candidate_preserved=record.get('failed_id_package_manifest_sha256')==source.PRIOR_MANIFEST_SHA,
        distinct_trace_tag=result['marker'].startswith('RPI5XNU:BL33:PCIE_ID_TRACE_TRIAL TAG='))
    if not all(checks.values()):raise ValueError('Passive trace package refused: '+repr([k for k,v in checks.items() if not v]))
    result.update(trace_checks=checks,trace_contract=contract,native_loader_comparison=record['native_loader_comparison'])
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path)
    print(json.dumps(inspect(parser.parse_args().package),indent=2,sort_keys=True))
