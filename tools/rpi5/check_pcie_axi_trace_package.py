#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact C1-aware passive trace pair; no hardware access or execution claim."""
import argparse
import json
from pathlib import Path
try:
    from . import build_pcie_axi_trace_package as source
except ImportError:
    import build_pcie_axi_trace_package as source


def inspect(package):
    package=package.resolve();adapted=source.configured_source();builder=adapted.configured_builder()
    checker=adapted.load_private(adapted.PRIOR_CHECKER,'_rpi5_private_c1_trace_checker')
    checker.builder=builder;result=checker.inspect(package)
    m=json.loads((package/'manifest.json').read_text())
    trace=json.loads(json.dumps(adapted.trace_contract()));axi=source.axi_contract()
    checks=dict(actual_end_telemetry=m.get('trace_contract')==trace,
        actual_native_loader=m.get('native_loader_comparison')==adapted.native_comparison(package),
        retained_fdt_not_overlapped=max(row['address']+row['memory_size'] for row in m['loads'])<0xb000000,
        failed_id_preserved=m.get('failed_id_package_manifest_sha256')==adapted.PRIOR_MANIFEST_SHA,
        failed_passive_trace_preserved=m.get('previous_passive_trace_manifest_sha256')==source.PRIOR_SHA,
        exact_axi_correction=m.get('axi_correction')==axi,
        distinct_c1_trace_tag=result['marker'].startswith('RPI5XNU:BL33:PCIE_ID_AXI_TRACE_TRIAL TAG='))
    if not all(checks.values()):raise ValueError('C1 AXI trace package refused: '+repr([k for k,v in checks.items() if not v]))
    result.update(axi_trace_checks=checks,trace_contract=trace,axi_correction=axi,
        native_loader_comparison=m['native_loader_comparison'])
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path)
    print(json.dumps(inspect(p.parse_args().package),indent=2,sort_keys=True))
