#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Actual loader image, passive owner contract and unchanged BAR scope."""
import argparse
import json
from pathlib import Path
from tools.rpi5 import build_pcie_owner_trace_package as source


def same(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)


def inspect(package):
    package=package.resolve();adapted=source.configured_source();builder=adapted.configured_builder()
    checker=adapted.load_private(adapted.PRIOR_CHECKER,'_owner_trace_loader_checker');checker.builder=builder
    result=checker.inspect(package);m=json.loads((package/'manifest.json').read_text());prior=source.prior
    checks=dict(actual_bounded_logging=same(m.get('trace_contract'),source.trace_contract()),
        owner_state_only=same(m.get('owner_trace'),source.owner_contract()),
        unchanged_bars=same(m.get('bars_contract'),prior.bars_contract()),
        exact_elapsed=same(m.get('link_elapsed'),prior.route.previous.previous.elapsed_contract()),
        exact_config=same(m.get('rp1_config_trace'),prior.route.previous.config_contract()),
        exact_root_route=same(m.get('root_route'),prior.route.root_contract()),
        exact_predecessor=m.get('previous_bars_package_manifest_sha256')==source.PRIOR_SHA,
        actual_native_loader=same(m.get('native_loader_comparison'),adapted.native_comparison(package)),
        retained_fdt_not_overlapped=max(row['address']+row['memory_size'] for row in m['loads'])<0xb000000,
        scoped_component_contracts=m.get('prior_component_contracts_are_scoped_not_whole_trial') is True,
        distinct_owner_tag=result['marker'].startswith('RPI5XNU:BL33:PCIE_OWNER_TRACE_TRIAL TAG='))
    if not all(checks.values()):raise ValueError('Owner package refused: '+repr([k for k,v in checks.items() if not v]))
    result.update(owner_package_checks=checks,prior_component_contracts_are_scoped_not_whole_trial=True)
    for key in ('owner_trace','bars_contract','trace_contract','link_elapsed','rp1_config_trace','root_route','native_loader_comparison'):result[key]=m[key]
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path)
    print(json.dumps(inspect(p.parse_args().package),indent=2,sort_keys=True))
