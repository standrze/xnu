#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Same contained BAR trial with exact passive PE owner failure snapshots."""
import argparse
import json
from pathlib import Path
import re
from tools.rpi5 import build_rp1_bars_root_package as prior
from tools.rpi5 import build_pcie_owner_trace_kernel as kernel
ROOT=prior.ROOT
KERNEL_PACKAGE=ROOT/'build/rpi5/pcie-owner-trace-kernel-20261013-v1'
KERNEL_SHA='17faec28fbd6a27d861c7be05de7022f7649ada9d0d61e7aff54fd1272a39829'
KERNEL_MANIFEST_SHA='1ad80e436eee43e77d605d81578c84e9f2b2286af19a8b763ff108a6a63d3ba1'
PRIOR_PACKAGE=ROOT/'build/rpi5/pcie-id-trial-kbne7vjh'
PRIOR_SHA='d3b6e58f9a941d309678624b1384dfe9e8bee5e3f4eb654749f7b7770d112775'
PROFILE='pcie-passive-owner-trace-bars-single-cpu-loader-v1'
CHECKER=ROOT/'tools/rpi5/check_pcie_owner_trace_package.py'
TEST=ROOT/'tools/rpi5/tests/test_pcie_owner_trace_package.py'
PROTOCOL=ROOT/'tools/rpi5/pcie_owner_trace_serial_core.py'
SERIAL_TEST=ROOT/'tools/rpi5/tests/test_pcie_owner_trace_serial.py'


def formats():
    return prior.formats()[:-1]+['RPI5XNU:PCIEID:'+label+' '+fmt+'\n' for label,fmt,_ in kernel.profile.ROWS]+[prior.TRACE_END]


TRACE_END=prior.TRACE_END


def trace_contract():
    raw=(KERNEL_PACKAGE/'kernel.rp1-config').read_bytes()
    for fmt in formats():
        if raw.count(fmt.encode()+b'\0')!=1:raise ValueError('Actual passive owner format missing')
    result=prior.trace_contract()
    result.update(record_formats=formats(),terminal_kprintf_count=19,
        scope='Bounded logging and passive in-memory owner snapshot only; unchanged BAR operation')
    return result


def owner_contract():
    if kernel.audit.sha(KERNEL_PACKAGE/'manifest.json')!=KERNEL_MANIFEST_SHA:raise ValueError('Exact owner kernel changed')
    m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    if (m['profile']!=kernel.PROFILE or m['kernel_sha256']!=KERNEL_SHA or m['logging_calls']!=19 or
        any(m[k] is not True for k in ('owner_trace_reads_memory_only','fw_client_object_unchanged','secure_firmware_unchanged',
            'irq_mask_object_unchanged','pm_lease_object_unchanged','guard_predicates_and_call_order_unchanged','owner_failure_quarantine_unchanged')) or
        any(m[k] is not False for k in ('owner_trace_adds_mmio','owner_trace_adds_smc','owner_trace_adds_counter_reads',
            'owner_trace_releases_or_reloads','physical_failure_cause_proven'))):raise ValueError('Passive owner contract changed')
    return dict(kernel_manifest_sha256=KERNEL_MANIFEST_SHA,object_replacements=m['owner_trace_object_replacements'],
        fields=m['owner_trace_fields'],memory_only=True,added_mmio=0,added_smc=0,added_counter_reads=0,
        guard_policy_unchanged=True,deadline_seconds=[9,10,12,15],finite_limits=[65536,65536],
        existing_bar_sequence_unchanged=True,cause_proven=False,
        failure_stages={'fw':{'2':'arguments','3':'interrupt-context','4':'owner-gate','5':'thread','6':'client','7':'post-client-owner','8':'complete'},
          'rpc':{'2':'raw-argument','3':'owner-before','4':'request','5':'irq-before-smc','6':'smc-in-progress','7':'owner-after','8':'irq-after-smc','9':'complete'},
          'pm':{'2':'owner-argument','3':'interrupt-context','4':'owner-gate','5':'core-in-progress','6':'core-failed','7':'complete'},
          'irq':{'2':'arguments','3':'interrupt-context','4':'owner-gate','5':'thread','6':'pm-before','7':'irq-core','8':'pm-after','9':'complete'}},
        scope='First failing existing PE path and raw returned SMC values; no added access authority')


def configured_source():
    source=prior.engine.load_private(Path(prior.engine.__file__).resolve(),'_pcie_owner_loader')
    source.KERNEL_PACKAGE=KERNEL_PACKAGE;source.KERNEL_SHA=KERNEL_SHA;source.KERNEL_MANIFEST_SHA=KERNEL_MANIFEST_SHA
    source.PROFILE=PROFILE;source.CHECKER=CHECKER;source.TEST=TEST;source.TRACE_END=TRACE_END
    source.trace_contract=trace_contract;original=source.configured_builder
    def configured_builder():
        b=original();old_inputs,old_marker=b.inputs,b.marker
        def inputs():
            pins,reports=old_inputs()
            if b.sha(PRIOR_PACKAGE/'manifest.json')!=PRIOR_SHA:raise ValueError('Frozen BAR predecessor changed')
            m=json.loads((PRIOR_PACKAGE/'manifest.json').read_text())
            inherited=m['inputs_sha256']|m['headers_sha256']|m['generated_sha256']|{str(PRIOR_PACKAGE/'manifest.json'):PRIOR_SHA}
            for path in (Path(__file__).resolve(),CHECKER,TEST,PROTOCOL,SERIAL_TEST):inherited[str(path)]=b.sha(path)
            for name,value in inherited.items():
                if name in pins and pins[name]!=value:raise ValueError('Owner loader input conflict')
                pins[name]=value
            b.verify(pins);return pins,reports
        b.inputs=inputs;b.marker=lambda tag:old_marker(tag).replace('PCIE_ID_TRACE_TRIAL ','PCIE_OWNER_TRACE_TRIAL ')
        return b
    source.configured_builder=configured_builder;return source


def build():
    source=configured_source();contract=owner_contract();package,m=source.build()
    m.update(link_elapsed=prior.route.previous.previous.elapsed_contract(),rp1_config_trace=prior.route.previous.config_contract(),
        root_route=prior.route.root_contract(),bars_contract=prior.bars_contract(),owner_trace=contract,
        previous_bars_package_manifest_sha256=PRIOR_SHA,prior_component_contracts_are_scoped_not_whole_trial=True)
    (package/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');return package,m


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();p,m=build()
    print(json.dumps({k:m[k] for k in ('image','image_sha256','image_bytes','marker','kernel_sha256')},indent=2))
