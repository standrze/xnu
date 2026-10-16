#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct no-input ID loader with bounded elapsed settling and link trace."""
import argparse
import json
from pathlib import Path
try:
    from . import build_pcie_id_trace_package as ancestor
    from . import pcie_link_elapsed_profile as profile
except ImportError:
    import build_pcie_id_trace_package as ancestor
    import pcie_link_elapsed_profile as profile

ROOT=ancestor.ROOT
BUILDER=ROOT/'tools/rpi5/build_pcie_id_trace_package.py'
BUILDER_SHA='2f25f7e7bf1cc77b58786693c8f8ee86f9cff8e226f9b035d4280908e48ceda9'
PRIOR_PACKAGE=ROOT/'build/rpi5/pcie-id-trial-v5t00fib'
PRIOR_SHA='3e21f6fa338f3b9b274befbef14630d3f8fac2c24f543f78935e52c04209d322'
KERNEL_PACKAGE=ROOT/'build/rpi5/pcie-link-elapsed-kernel-20261013-final'
KERNEL_SHA='6853562383a5e1e2d833a4990cc0cfd4d4c64a5bc4565ede7a01626b5ebf8f16'
KERNEL_MANIFEST_SHA='cfdeadb0288642aa978a50c470ef73c00842757a5101753e948a2a57d02aba0d'
PROFILE='pcie-id-link-elapsed-trace-single-cpu-loader-v1'
CHECKER=ROOT/'tools/rpi5/check_pcie_link_elapsed_package.py'
TEST=ROOT/'tools/rpi5/tests/test_pcie_link_elapsed_package.py'
TRACE_END=ancestor.TRACE_END[:-1]+' '+profile.FIELDS+'\n'


def configured_source():
    source=ancestor.load_private(BUILDER,'_rpi5_private_link_elapsed_loader')
    source.KERNEL_PACKAGE=KERNEL_PACKAGE;source.KERNEL_SHA=KERNEL_SHA
    source.KERNEL_MANIFEST_SHA=KERNEL_MANIFEST_SHA;source.PROFILE=PROFILE
    source.CHECKER=CHECKER;source.TEST=TEST;source.TRACE_END=TRACE_END
    original=source.configured_builder
    def configured_builder():
        b=original()
        if b.sha(BUILDER)!=BUILDER_SHA or b.sha(PRIOR_PACKAGE/'manifest.json')!=PRIOR_SHA:
            raise ValueError('Frozen corrected-AXI loader ancestry changed')
        old_inputs,old_marker=b.inputs,b.marker
        def inputs():
            pins,reports=old_inputs();previous=json.loads((PRIOR_PACKAGE/'manifest.json').read_text())
            inherited=previous['inputs_sha256']|previous['headers_sha256']|previous['generated_sha256']
            inherited[str(PRIOR_PACKAGE/'manifest.json')]=PRIOR_SHA
            for p in (Path(__file__).resolve(),CHECKER,TEST):inherited[str(p)]=b.sha(p)
            for name,digest in inherited.items():
                if name in pins and pins[name]!=digest:raise ValueError('Link elapsed package pin conflict: '+name)
                pins[name]=digest
            b.verify(pins);return pins,reports
        b.inputs=inputs
        b.marker=lambda tag:old_marker(tag).replace('PCIE_ID_TRACE_TRIAL ','PCIE_ID_LINK_ELAPSED_TRIAL ')
        return b
    source.configured_builder=configured_builder
    return source


def elapsed_contract():
    source=configured_source();b=source.configured_builder()
    if b.sha(KERNEL_PACKAGE/'manifest.json')!=KERNEL_MANIFEST_SHA:raise ValueError('Elapsed kernel manifest changed')
    m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    if (m.get('profile')!='pcie-id-link-elapsed-trace-kernel-v1' or
        (m.get('reset_min_us'),m.get('reset_max_us'),m.get('poll_max_us'))!=(100000,110000,100000) or
        m.get('link_trace_fields')!=profile.FIELDS or len(m.get('elapsed_object_replacements',{}))!=2 or
        not all(m.get(k) is True for k in ('axi_objects_unchanged','delay_accounts_guard_time','firmware_guard_unchanged','watchdog_unchanged')) or
        any(m.get(k) is not False for k in ('trace_adds_mmio','trace_changes_permissions','trace_changes_deadlines'))):
        raise ValueError('Exact bounded elapsed/trace kernel contract changed')
    return dict(kernel_manifest_sha256=KERNEL_MANIFEST_SHA,replaced_objects=m['elapsed_object_replacements'],
        call_steps=m['link_trace_call_steps'],core_steps=m['link_trace_core_steps'],
        reset_min_us=100000,reset_max_us=110000,poll_max_us=100000,
        delay_max_chunk_us=1000,delay_max_chunks=100,delay_accounts_guard_time=True,
        prior_c1_axi_objects_unchanged=True,firmware_guards_unchanged=True,watchdogs_unchanged=True,
        additional_mappings=False,endpoint_writes=False,dma_enabled=False,
        physical_cause_proven=False,physical_correction_verified=False,
        previous_axi_package_manifest_sha256=PRIOR_SHA)


def build():
    source=configured_source();contract=elapsed_contract()
    p,m=source.build();m.update(link_elapsed=contract,previous_axi_package_manifest_sha256=PRIOR_SHA)
    (p/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    return p,m


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();p,m=build()
    print(json.dumps({k:m[k] for k in ('image','image_sha256','image_bytes','marker','kernel_sha256')},indent=2))
