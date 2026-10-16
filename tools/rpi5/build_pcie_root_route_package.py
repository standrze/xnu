#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""No-input retained-FDT loader for the fixed root0 -> RP1 bus1 route."""
import argparse
import json
from pathlib import Path
try:
    from . import build_rp1_config_trace_package as previous
    from . import pcie_root_route_profile as profile
except ImportError:
    import build_rp1_config_trace_package as previous
    import pcie_root_route_profile as profile

ROOT=previous.ROOT
BUILDER=ROOT/'tools/rpi5/build_rp1_config_trace_package.py'
BUILDER_SHA='535381f64fae5448be64bbf8fe8ade80f708f711ddf67bb13090796eae7936a4'
PRIOR_PACKAGE=ROOT/'build/rpi5/pcie-id-trial-ukgc_lll'
PRIOR_SHA='b781b3db8369d01d4cf162694ea51bd4ebad7d25b6f24b295038a852192f2d9e'
KERNEL_PACKAGE=ROOT/'build/rpi5/pcie-root-route-kernel-20261013-v3'
KERNEL_SHA='be374699c3b93dd7425b12920e22f50eceb18d36d9e10b6ca51d4749dc19fbc7'
KERNEL_MANIFEST_SHA='753ba1093e852d46a61f6b4804c69537279cc91390eb33af6b10f1e25896a355'
PROFILE='pcie-root-bus-route-single-cpu-loader-v1'
CHECKER=ROOT/'tools/rpi5/check_pcie_root_route_package.py'
TEST=ROOT/'tools/rpi5/tests/test_pcie_root_route_package.py'
TRACE_END=previous.TRACE_END[:-1]+' '+profile.FIELDS+'\n'


def configured_source():
    name=(previous.__package__+'.' if previous.__package__ else '')+'_rpi5_private_root_route_loader'
    frozen=previous.previous.ancestor.load_private(BUILDER,name)
    frozen.KERNEL_PACKAGE=KERNEL_PACKAGE;frozen.KERNEL_SHA=KERNEL_SHA
    frozen.KERNEL_MANIFEST_SHA=KERNEL_MANIFEST_SHA;frozen.PROFILE=PROFILE
    frozen.CHECKER=CHECKER;frozen.TEST=TEST;frozen.TRACE_END=TRACE_END
    frozen.PRIOR_PACKAGE=PRIOR_PACKAGE;frozen.PRIOR_SHA=PRIOR_SHA
    source=frozen.configured_source();original=source.configured_builder
    def configured_builder():
        b=original()
        if b.sha(BUILDER)!=BUILDER_SHA:raise ValueError('Frozen config loader engine changed')
        old_inputs,old_marker=b.inputs,b.marker
        def inputs():
            pins,reports=old_inputs()
            for p in (Path(__file__).resolve(),CHECKER,TEST,
                ROOT/'tools/rpi5/pcie_root_route_serial_core.py',ROOT/'tools/rpi5/tests/test_pcie_root_route_serial.py'):
                digest=b.sha(p)
                if str(p) in pins and pins[str(p)]!=digest:raise ValueError('Root-route package source conflict')
                pins[str(p)]=digest
            b.verify(pins);return pins,reports
        b.inputs=inputs;b.marker=lambda tag:old_marker(tag).replace('RP1_CONFIG_TRACE_TRIAL ','PCIE_ROOT_ROUTE_TRIAL ')
        return b
    source.configured_builder=configured_builder
    return source


def root_contract():
    b=configured_source().configured_builder()
    if b.sha(KERNEL_PACKAGE/'manifest.json')!=KERNEL_MANIFEST_SHA:raise ValueError('Root-route kernel changed')
    m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    if (m.get('profile')!='pcie-root-bus-route-kernel-v1' or m.get('root_route_fields')!=profile.FIELDS or
        len(m.get('root_route_object_replacements',{}))!=2 or
        tuple(m.get(k) for k in ('root_config_identity','root_header_type','root_primary_bus','root_secondary_bus',
            'root_subordinate_bus','root_config_write_offset','root_low24_value','root_config_reads_max',
            'root_config_writes_max','endpoint_config_writes','command_writes'))!=
            (0x271214e4,1,0,1,1,0x18,0x010100,6,1,0,0) or
        any(m.get(k) is not True for k in ('root_upper_byte_preserved','root_route_post_link_readback',
            'root_write_before_perst_release','link_object_unchanged','config_core_unchanged',
            'snapshot_object_unchanged','root_config_state_and_observation_abi_unchanged','firmware_guard_unchanged',
            'watchdog_unchanged','root_route_permissions_extended','source_corrective_change')) or
        any(m.get(k) is not False for k in ('controller_caller_unchanged','trace_changes_deadlines','physical_cause_proven'))):
        raise ValueError('Exact root routing contract changed')
    return dict(kernel_manifest_sha256=KERNEL_MANIFEST_SHA,replaced_objects=m['root_route_object_replacements'],
        end_fields=profile.FIELDS,steps=m['root_route_steps'],root_id=0x271214e4,header_type=1,
        primary_bus=0,secondary_bus=1,subordinate_bus=1,root_write_offset=0x18,low24_value=0x010100,
        root_reads_max=6,root_writes_max=1,endpoint_writes=0,command_writes=0,
        preserve_latency_byte=True,immediate_and_final_readbacks=True,post_link_readback=True,
        write_before_perst_release=True,exact_write_value_guard=True,
        source_corrective_change=True,root_permissions_extended=True,
        link_clock_config_snapshot_cores_unchanged=True,firmware_and_watchdogs_unchanged=True,
        bar_sizing_or_assignment=False,changed_deadlines=False,physical_cause_proven=False,physical_id_verified=False)


def build():
    source=configured_source();contract=root_contract();p,m=source.build()
    m.update(link_elapsed=previous.previous.elapsed_contract(),rp1_config_trace=previous.config_contract(),
        root_route=contract,previous_config_package_manifest_sha256=PRIOR_SHA)
    (p/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    return p,m


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();p,m=build()
    print(json.dumps({k:m[k] for k in ('image','image_sha256','image_bytes','marker','kernel_sha256')},indent=2))
