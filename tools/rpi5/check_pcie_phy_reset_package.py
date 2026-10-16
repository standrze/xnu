#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact reset/C22 scope plus emitted FDT/Device/geometry and actual loader audit."""
import argparse
import json
from pathlib import Path
from tools.rpi5 import build_pcie_phy_reset_package as source
from tools.rpi5.check_pcie_gem_selected_package import same


def inspect(package):
    package=package.resolve();adapted=source.configured_source();builder=adapted.configured_builder()
    checker=adapted.load_private(adapted.PRIOR_CHECKER,'_phy_reset_loader_checker');checker.builder=builder
    m=json.loads((package/'manifest.json').read_text())
    previous=json.loads((source.PRIOR_PACKAGE/'manifest.json').read_text())
    checks={name:same(m.get(name),factory()) for name,factory in (
        ('reset_contract',source.reset_contract),('capabilities_contract',source.capabilities_contract),
        ('selected_clock_contract',source.selected_clock_contract),('root_forward_contract',source.root_forward_contract),
        ('gem_contract',source.gem_contract),('decode_contract',source.decode_contract),
        ('assignment_contract',source.assignment_contract),('guard_composition',source.guard_contract),
        ('owner_trace',source.owner_contract),('trace_contract',source.trace_contract))}
    checks.update(exact_historical_components=all(same(m.get(n),previous[n]) for n in ('bars_contract','link_elapsed','rp1_config_trace','root_route')),
        exact_ninepage_device_handoff=same(m.get('rp1_device_handoff'),source.gpio_handoff_contract()),
        exact_predecessor=m.get('previous_capabilities_package_manifest_sha256')==source.PRIOR_SHA,
        retained_fdt_not_overlapped=max(row['address']+row['memory_size'] for row in m['loads'])<0xb000000,
        scoped_components=m.get('prior_component_contracts_are_scoped_not_whole_trial') is True,
        explicit_gpio_and_management_write_scope=m.get('endpoint_register_access') is True and m.get('endpoint_register_writes') is True and
            m.get('phy_register_writes') is False and m.get('gpio_reset_writes') is True,
        root_memory_only=m.get('root_config_memory_writes') is True and m.get('root_command_changes_mem_only') is True,
        no_clock_measurement_claim=m.get('selected_source_profile_not_independent_clock_measurement') is True,
        distinct_tag=isinstance(m.get('marker'),str) and m['marker'].startswith('RPI5XNU:BL33:PCIE_PHY_RESET_TRIAL TAG='))
    if not all(checks.values()):raise ValueError('Reset package refused: '+repr([k for k,v in checks.items() if not v]))
    # Cheap exact scope rejection precedes native replay; accepted candidates
    # still execute every original linked/FDT/geometry/loader check below.
    result=checker.inspect(package)
    checks.update(actual_gpio_handoff_linked='rpi5_phy_gpio_device_handoff' in builder.symbols_for(package/'probe.elf'),
        actual_native_loader=same(m.get('native_loader_comparison'),adapted.native_comparison(package)))
    if not all(checks.values()):raise ValueError('Reset package refused: '+repr([k for k,v in checks.items() if not v]))
    result.update(reset_package_checks=checks,prior_component_contracts_are_scoped_not_whole_trial=True,
        endpoint_register_access=True,endpoint_register_writes=True,phy_register_writes=False,gpio_reset_writes=True,
        root_config_memory_writes=True,root_command_changes_mem_only=True,selected_source_profile_not_independent_clock_measurement=True)
    for name in ('reset_contract','capabilities_contract','selected_clock_contract','root_forward_contract','gem_contract','decode_contract','assignment_contract',
        'guard_composition','owner_trace','bars_contract','trace_contract','link_elapsed','rp1_config_trace','root_route',
        'native_loader_comparison','rp1_device_handoff'):result[name]=m[name]
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path)
    print(json.dumps(inspect(p.parse_args().package),indent=2,sort_keys=True))
