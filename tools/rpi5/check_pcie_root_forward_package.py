#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Actual native loader/Device geometry and root MEM-forwarding package audit."""
import argparse
import json
from pathlib import Path
from tools.rpi5 import build_pcie_root_forward_package as source
def same(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)


def inspect(package):
    package=package.resolve();adapted=source.configured_source();builder=adapted.configured_builder()
    checker=adapted.load_private(adapted.PRIOR_CHECKER,'_root_forward_loader_checker');checker.builder=builder
    result=checker.inspect(package);m=json.loads((package/'manifest.json').read_text())
    previous=json.loads((source.PRIOR_PACKAGE/'manifest.json').read_text())
    checks={name:same(m.get(name),factory()) for name,factory in (
        ('root_forward_contract',source.root_forward_contract),('gem_contract',source.gem_contract),
        ('decode_contract',source.decode_contract),('assignment_contract',source.assignment_contract),
        ('guard_composition',source.guard_contract),('owner_trace',source.owner_contract),('trace_contract',source.trace_contract))}
    checks.update(exact_historical_components=all(same(m.get(n),previous[n]) for n in ('bars_contract','link_elapsed','rp1_config_trace','root_route','rp1_device_handoff')),
        exact_predecessor=m.get('previous_gem_package_manifest_sha256')==source.PRIOR_SHA,
        actual_native_loader=same(m.get('native_loader_comparison'),adapted.native_comparison(package)),
        retained_fdt_not_overlapped=max(row['address']+row['memory_size'] for row in m['loads'])<0xb000000,
        scoped_components=m.get('prior_component_contracts_are_scoped_not_whole_trial') is True,
        endpoint_reads_only=m.get('endpoint_register_access') is True and m.get('endpoint_register_writes') is False,
        root_memory_only=m.get('root_config_memory_writes') is True and m.get('root_command_changes_mem_only') is True,
        actual_rp1_helper_linked='rpi5_rp1_device_handoff' in builder.symbols_for(package/'probe.elf'),
        distinct_tag=result['marker'].startswith('RPI5XNU:BL33:PCIE_ROOT_FORWARD_TRIAL TAG='))
    if not all(checks.values()):raise ValueError('Root-forward package refused: '+repr([k for k,v in checks.items() if not v]))
    result.update(root_forward_package_checks=checks,prior_component_contracts_are_scoped_not_whole_trial=True,
        endpoint_register_access=True,endpoint_register_writes=False,root_config_memory_writes=True,root_command_changes_mem_only=True)
    for name in ('root_forward_contract','gem_contract','decode_contract','assignment_contract','guard_composition','owner_trace','bars_contract',
        'trace_contract','link_elapsed','rp1_config_trace','root_route','native_loader_comparison','rp1_device_handoff'):
        result[name]=m[name]
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('package',type=Path)
    print(json.dumps(inspect(parser.parse_args().package),indent=2,sort_keys=True))
