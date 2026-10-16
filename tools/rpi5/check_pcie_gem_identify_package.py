#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Native full-FDT/Device handoff and exact guarded clock/MID image audit."""
import argparse
import json
from pathlib import Path
from tools.rpi5 import build_pcie_gem_identify_package as source
def same(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)


def inspect(package):
    package=package.resolve();adapted=source.configured_source();builder=adapted.configured_builder()
    checker=adapted.load_private(adapted.PRIOR_CHECKER,'_gem_loader_checker');checker.builder=builder
    result=checker.inspect(package);m=json.loads((package/'manifest.json').read_text())
    previous=json.loads((source.PRIOR_PACKAGE/'manifest.json').read_text())
    checks=dict(exact_gem=same(m.get('gem_contract'),source.gem_contract()),
        exact_decode=same(m.get('decode_contract'),source.decode_contract()),
        exact_assignment=same(m.get('assignment_contract'),source.assignment_contract()),
        exact_guard=same(m.get('guard_composition'),source.guard_contract()),
        exact_owner=same(m.get('owner_trace'),source.owner_contract()),exact_logging=same(m.get('trace_contract'),source.trace_contract()),
        exact_historical_components=all(same(m.get(n),previous[n]) for n in ('bars_contract','link_elapsed','rp1_config_trace','root_route','rp1_device_handoff')),
        exact_predecessor=m.get('previous_decode_package_manifest_sha256')==source.PRIOR_SHA,
        actual_native_loader=same(m.get('native_loader_comparison'),adapted.native_comparison(package)),
        retained_fdt_not_overlapped=max(row['address']+row['memory_size'] for row in m['loads'])<0xb000000,
        scoped_components=m.get('prior_component_contracts_are_scoped_not_whole_trial') is True,
        endpoint_reads_only=m.get('endpoint_register_access') is True and m.get('endpoint_register_writes') is False,
        actual_rp1_helper_linked='rpi5_rp1_device_handoff' in builder.symbols_for(package/'probe.elf'),
        distinct_tag=result['marker'].startswith('RPI5XNU:BL33:PCIE_GEM_IDENTIFY_TRIAL TAG='))
    if not all(checks.values()):raise ValueError('GEM package refused: '+repr([k for k,v in checks.items() if not v]))
    result.update(gem_package_checks=checks,prior_component_contracts_are_scoped_not_whole_trial=True,
        endpoint_register_access=True,endpoint_register_writes=False)
    for name in ('gem_contract','decode_contract','assignment_contract','guard_composition','owner_trace','bars_contract',
        'trace_contract','link_elapsed','rp1_config_trace','root_route','native_loader_comparison','rp1_device_handoff'):
        result[name]=m[name]
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('package',type=Path)
    print(json.dumps(inspect(parser.parse_args().package),indent=2,sort_keys=True))
