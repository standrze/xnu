#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct no-input retained-FDT loader for the complete passive RP1 read trace."""
import argparse
import json
from pathlib import Path
try:
    from . import build_pcie_link_elapsed_package as previous
    from . import rp1_config_trace_profile as profile
except ImportError:
    import build_pcie_link_elapsed_package as previous
    import rp1_config_trace_profile as profile

ROOT=previous.ROOT
BUILDER=ROOT/'tools/rpi5/build_pcie_link_elapsed_package.py'
BUILDER_SHA='a2fe880fa904df16e26315af7470b192fd800e1394cd17fb3a029995cb28c738'
PRIOR_PACKAGE=ROOT/'build/rpi5/pcie-id-trial-y60h5lfb'
PRIOR_SHA='56e3ee8a55a0f6df251d14875e7f5400da2b467b5179975a61e012db1302863d'
KERNEL_PACKAGE=ROOT/'build/rpi5/rp1-config-trace-kernel-20261013-final'
KERNEL_SHA='ac58d554e9e682c6c49694482fc27a77f1162e9636afce884971b865f36d32af'
KERNEL_MANIFEST_SHA='f34a66ee8d0cb26c99f54d5d1b9a03c2efe42574e7dce9c101ad916f495c8e33'
PROFILE='rp1-config-passive-trace-single-cpu-loader-v1'
CHECKER=ROOT/'tools/rpi5/check_rp1_config_trace_package.py'
TEST=ROOT/'tools/rpi5/tests/test_rp1_config_trace_package.py'
TRACE_END=previous.TRACE_END[:-1]+' '+profile.FIELDS+'\n'


def configured_source():
    private_name=(previous.__package__+'.' if previous.__package__ else '')+'_rpi5_private_config_loader'
    frozen=previous.ancestor.load_private(BUILDER,private_name)
    frozen.KERNEL_PACKAGE=KERNEL_PACKAGE;frozen.KERNEL_SHA=KERNEL_SHA
    frozen.KERNEL_MANIFEST_SHA=KERNEL_MANIFEST_SHA;frozen.PROFILE=PROFILE
    frozen.CHECKER=CHECKER;frozen.TEST=TEST;frozen.TRACE_END=TRACE_END
    frozen.PRIOR_PACKAGE=PRIOR_PACKAGE;frozen.PRIOR_SHA=PRIOR_SHA
    source=frozen.configured_source();original=source.configured_builder
    def configured_builder():
        b=original()
        if b.sha(BUILDER)!=BUILDER_SHA:raise ValueError('Frozen elapsed loader engine changed')
        old_inputs,old_marker=b.inputs,b.marker
        def inputs():
            pins,reports=old_inputs()
            for p in (Path(__file__).resolve(),CHECKER,TEST):
                digest=b.sha(p)
                if str(p) in pins and pins[str(p)]!=digest:raise ValueError('Config package source pin conflict')
                pins[str(p)]=digest
            b.verify(pins);return pins,reports
        b.inputs=inputs;b.marker=lambda tag:old_marker(tag).replace('PCIE_ID_LINK_ELAPSED_TRIAL ','RP1_CONFIG_TRACE_TRIAL ')
        return b
    source.configured_builder=configured_builder
    return source


def config_contract():
    b=configured_source().configured_builder()
    if b.sha(KERNEL_PACKAGE/'manifest.json')!=KERNEL_MANIFEST_SHA:raise ValueError('Config trace kernel changed')
    m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    if (m.get('profile')!='rp1-config-passive-trace-kernel-v1' or
        m.get('rp1_trace_fields')!=profile.FIELDS or len(m.get('rp1_trace_object_replacements',{}))!=2 or
        any(m.get(k) is not True for k in ('link_object_unchanged','controller_caller_unchanged',
            'config_core_unchanged','rp1_snapshot_abi_unchanged','firmware_guard_unchanged','watchdog_unchanged')) or
        m.get('endpoint_header_reads')!=32 or m.get('selector_writes')!=32 or m.get('endpoint_config_writes')!=0 or
        any(m.get(k) is not False for k in ('rp1_trace_adds_mmio','trace_changes_permissions','trace_changes_deadlines'))):
        raise ValueError('Exact passive RP1 config trace contract changed')
    return dict(kernel_manifest_sha256=KERNEL_MANIFEST_SHA,
        replaced_objects=m['rp1_trace_object_replacements'],call_steps=m['rp1_call_steps'],
        core_steps=m['rp1_core_steps'],end_fields=profile.FIELDS,
        phase14_means='RP1_INSPECTING',phase13_means='CLOCK_FINISHING',
        snapshot_reads_max=32,selector_writes_max=32,endpoint_writes=0,
        extra_mmio=False,changed_permissions=False,changed_deadlines=False,
        link_clock_and_config_cores_unchanged=True,
        source_corrective_change=False,physical_rp1_id_verified=False)


def build():
    source=configured_source();contract=config_contract()
    p,m=source.build()
    m.update(link_elapsed=previous.elapsed_contract(),rp1_config_trace=contract,
        previous_elapsed_package_manifest_sha256=PRIOR_SHA)
    (p/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    return p,m


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();p,m=build()
    print(json.dumps({k:m[k] for k in ('image','image_sha256','image_bytes','marker','kernel_sha256')},indent=2))
