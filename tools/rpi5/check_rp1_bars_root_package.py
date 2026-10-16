#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Actual emitted Device/FDT image, bounded formats and six-BAR scope checks."""
import argparse
import json
from pathlib import Path
try:
    from . import build_rp1_bars_root_package as source
except ImportError:
    import build_rp1_bars_root_package as source


def inspect(package):
    package=package.resolve();adapted=source.configured_source();builder=adapted.configured_builder()
    checker=adapted.load_private(adapted.PRIOR_CHECKER,'_rp1_bars_bounded_checker')
    checker.builder=builder;result=checker.inspect(package)
    m=json.loads((package/'manifest.json').read_text())
    trace=json.loads(json.dumps(source.trace_contract()));bars=json.loads(json.dumps(source.bars_contract()))
    checks=dict(actual_bounded_logging=m.get('trace_contract')==trace,
        actual_native_loader=m.get('native_loader_comparison')==adapted.native_comparison(package),
        retained_fdt_not_overlapped=max(row['address']+row['memory_size'] for row in m['loads'])<0xb000000,
        predecessor=m.get('previous_root_route_package_manifest_sha256')==source.PRIOR_SHA,
        exact_elapsed=m.get('link_elapsed')==source.route.previous.previous.elapsed_contract(),
        exact_config=m.get('rp1_config_trace')==source.route.previous.config_contract(),
        exact_root_route=m.get('root_route')==source.route.root_contract(),exact_bars=m.get('bars_contract')==bars,
        scoped_component_contracts=m.get('prior_component_contracts_are_scoped_not_whole_trial') is True,
        distinct_bars_tag=result['marker'].startswith('RPI5XNU:BL33:RP1_BARS_ROOT_TRIAL TAG='))
    if not all(checks.values()):raise ValueError('BAR package refused: '+repr([k for k,v in checks.items() if not v]))
    result.update(bars_package_checks=checks,trace_contract=trace,bars_contract=bars,
        link_elapsed=m['link_elapsed'],rp1_config_trace=m['rp1_config_trace'],root_route=m['root_route'],
        native_loader_comparison=m['native_loader_comparison'],prior_component_contracts_are_scoped_not_whole_trial=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path)
    print(json.dumps(inspect(p.parse_args().package),indent=2,sort_keys=True))
