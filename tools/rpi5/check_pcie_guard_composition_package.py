#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact emitted loader plus truthful changed-composition/passive-owner contract."""
import argparse
import json
from pathlib import Path
from tools.rpi5 import build_pcie_guard_composition_package as source
def same(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)


def inspect(package):
    package=package.resolve();adapted=source.configured_source();builder=adapted.configured_builder()
    checker=adapted.load_private(adapted.PRIOR_CHECKER,'_guard_loader_checker');checker.builder=builder
    result=checker.inspect(package);m=json.loads((package/'manifest.json').read_text());bars=source.prior.prior
    checks=dict(exact_guard_composition=same(m.get('guard_composition'),source.guard_contract()),
        truthful_owner_contract=same(m.get('owner_trace'),source.owner_contract()),
        owner_guard_policy_changed=m['owner_trace']['guard_policy_unchanged'] is False,
        exact_passive_logging=same(m.get('trace_contract'),source.trace_contract()),
        unchanged_bars=same(m.get('bars_contract'),bars.bars_contract()),
        exact_elapsed=same(m.get('link_elapsed'),bars.route.previous.previous.elapsed_contract()),
        exact_config=same(m.get('rp1_config_trace'),bars.route.previous.config_contract()),
        exact_root_route=same(m.get('root_route'),bars.route.root_contract()),
        exact_owner_predecessor=m.get('previous_owner_package_manifest_sha256')==source.PRIOR_OWNER_SHA,
        actual_native_loader=same(m.get('native_loader_comparison'),adapted.native_comparison(package)),
        retained_fdt_not_overlapped=max(row['address']+row['memory_size'] for row in m['loads'])<0xb000000,
        scoped_component_contracts=m.get('prior_component_contracts_are_scoped_not_whole_trial') is True,
        distinct_guard_tag=result['marker'].startswith('RPI5XNU:BL33:PCIE_GUARD_COMPOSITION_TRIAL TAG='))
    if not all(checks.values()):raise ValueError('Guard package refused: '+repr([k for k,v in checks.items() if not v]))
    result.update(guard_package_checks=checks,prior_component_contracts_are_scoped_not_whole_trial=True)
    for key in ('guard_composition','owner_trace','bars_contract','trace_contract','link_elapsed','rp1_config_trace','root_route','native_loader_comparison'):result[key]=m[key]
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path)
    print(json.dumps(inspect(p.parse_args().package),indent=2,sort_keys=True))
