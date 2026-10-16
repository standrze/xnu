#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct zero-input trace loader paired with the C1-aware AXI kernel."""
import argparse
import json
from pathlib import Path
try:
    from . import build_pcie_id_trace_package as ancestor
except ImportError:
    import build_pcie_id_trace_package as ancestor

ROOT=ancestor.ROOT
BUILDER=ROOT/'tools/rpi5/build_pcie_id_trace_package.py'
BUILDER_SHA='2f25f7e7bf1cc77b58786693c8f8ee86f9cff8e226f9b035d4280908e48ceda9'
PRIOR_PACKAGE=ROOT/'build/rpi5/pcie-id-trial-zyw6ujf_'
PRIOR_SHA='ec55c6f2a24fcbc274e708d55ea7bc0fb7cd986b1f5f8d842acd62a77699dc0f'
KERNEL_PACKAGE=ROOT/'build/rpi5/pcie-axi-trace-kernel-20261013-v2'
KERNEL_SHA='4eab9039392a0fe027f8ee02330d3969c0f9d7a7d48c7297b94aa9052306b78c'
KERNEL_MANIFEST_SHA='fa38950c85264d4a635f1b20b511071f7af9d564f53c9600756312dc6924d644'
PROFILE='pcie-id-c1-axi-passive-trace-single-cpu-loader-v1'
CHECKER=ROOT/'tools/rpi5/check_pcie_axi_trace_package.py'
TEST=ROOT/'tools/rpi5/tests/test_pcie_axi_trace_package.py'


def configured_source():
    source=ancestor.load_private(BUILDER,'_rpi5_private_c1_trace_loader')
    source.KERNEL_PACKAGE=KERNEL_PACKAGE;source.KERNEL_SHA=KERNEL_SHA
    source.KERNEL_MANIFEST_SHA=KERNEL_MANIFEST_SHA;source.PROFILE=PROFILE
    source.CHECKER=CHECKER;source.TEST=TEST
    original=source.configured_builder
    def configured_builder():
        b=original()
        if b.sha(BUILDER)!=BUILDER_SHA or b.sha(PRIOR_PACKAGE/'manifest.json')!=PRIOR_SHA:
            raise ValueError('Frozen passive-trace loader changed')
        old_inputs,old_marker=b.inputs,b.marker
        def inputs():
            pins,reports=old_inputs();previous=json.loads((PRIOR_PACKAGE/'manifest.json').read_text())
            inherited=previous['inputs_sha256']|previous['headers_sha256']|previous['generated_sha256']
            inherited[str(PRIOR_PACKAGE/'manifest.json')]=PRIOR_SHA
            for p in (Path(__file__).resolve(),CHECKER,TEST):inherited[str(p)]=b.sha(p)
            for name,digest in inherited.items():
                if name in pins and pins[name]!=digest:raise ValueError('AXI trace pin conflict: '+name)
                pins[name]=digest
            b.verify(pins);return pins,reports
        b.inputs=inputs
        b.marker=lambda tag:old_marker(tag).replace('PCIE_ID_TRACE_TRIAL ','PCIE_ID_AXI_TRACE_TRIAL ')
        return b
    source.configured_builder=configured_builder
    return source


def axi_contract():
    source=configured_source();b=source.configured_builder()
    if b.sha(KERNEL_PACKAGE/'manifest.json')!=KERNEL_MANIFEST_SHA:
        raise ValueError('Corrected trace kernel manifest changed')
    m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    if (m.get('profile')!='pcie-id-passive-trace-c1-axi-kernel-v1' or
        m.get('axi_supported_fix_fields')!=[0x3800,0x2800,0] or
        m.get('axi_fallback_max_outstanding')!=15 or
        not all(m.get(k) is True for k in ('axi_unrelated_bits_preserved','axi_fallback_readback_exact',
            'controller_caller_unchanged','firmware_guard_unchanged','watchdog_unchanged','passive_trace_unchanged')) or
        len(m.get('axi_object_replacements',{}))!=3):
        raise ValueError('Exact three-core AXI correction contract changed')
    return dict(kernel_manifest_sha256=KERNEL_MANIFEST_SHA,replaced_objects=m['axi_object_replacements'],
        supported_fix_fields=[0x3800,0x2800,0],fallback_max_outstanding=15,
        unrelated_bits_preserved=True,exact_fallback_readback=True,
        observed_old_axi=0x60,expected_c1_fallback_axi=0x4f,
        previous_trace_package_manifest_sha256=PRIOR_SHA,
        same_caller_firmware_watchdog_and_trace=True,
        additional_mappings=False,endpoint_writes=False,dma_enabled=False,
        physical_correction_verified=False)


def build():
    source=configured_source();contract=axi_contract()
    p,m=source.build();m.update(axi_correction=contract,previous_passive_trace_manifest_sha256=PRIOR_SHA)
    (p/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    return p,m


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();p,m=build()
    print(json.dumps({k:m[k] for k in ('image','image_sha256','image_bytes','marker','kernel_sha256')},indent=2))
