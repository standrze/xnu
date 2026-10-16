#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One transport object; unchanged freshly checked PE/secure owners and bounds."""
import argparse
import json
from pathlib import Path
import re
from tools.rpi5 import build_pcie_link_elapsed_kernel as engine
from tools.rpi5 import build_pcie_id_trace_package as private
from tools.rpi5 import pcie_guard_composition_profile as profile
ROOT,audit=engine.ROOT,engine.audit
BASE=profile.FROZEN.parent
BASE_SHA='1ad80e436eee43e77d605d81578c84e9f2b2286af19a8b763ff108a6a63d3ba1'
PROFILE='pcie-fresh-nested-guard-composition-kernel-v1'
TEST=ROOT/'tools/rpi5/tests/test_pcie_guard_composition_kernel.py'


def inputs():
    if audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Exact owner-trace predecessor changed')
    parent=json.loads((BASE/'manifest.json').read_text())
    pins=parent['inputs_sha256']|parent['generated_sha256']|{str(BASE/'manifest.json'):BASE_SHA}
    for path in (Path(__file__).resolve(),Path(profile.__file__).resolve(),TEST,
        ROOT/'tools/rpi5/tests/test_pcie_full_owner_accounting.py',ROOT/'tools/rpi5/tests/test_pcie_guard_composition.py',
        ROOT/'build/rpi5/pcie-owner-trace-serial-20261013/serial.bin'):
        digest=audit.sha(path)
        if str(path) in pins and pins[str(path)]!=digest:raise ValueError('Guard successor input conflict')
        pins[str(path)]=digest
    engine.verify(pins);return parent,parent,pins


def objects(output):
    before=[Path(p) for p in (BASE/'kernel.rp1-config.filelist').read_text().splitlines()]
    matches=[p for p in before if p.name=='BCM2712PCIePHYTransport.cpp.o']
    if len(matches)!=1 or len(set(before))!=len(before):raise ValueError('Unique exact old transport required')
    changes={matches[0]:output/matches[0].name}
    return before,[changes.get(p,p) for p in before],changes


def compile_args(parent,source):
    if source.name!='BCM2712PCIePHYTransport.cpp':raise ValueError('Only transport compile allowed')
    command=parent['compiles'][0]['command'];old=str(BASE/'overlay'/source.name)
    if command.count(old)!=1:raise ValueError('Exact previous compile required')
    return [str(source) if value==old else value for value in command[:command.index('-MD')]]


def build(output):
    b=private.load_private(Path(engine.__file__).resolve(),'_fresh_nested_guard_kernel')
    b.BASE=BASE;b.BASE_SHA=BASE_SHA;b.PROFILE=PROFILE;b.TEST=TEST;b.profile=profile
    b.inputs=inputs;b.objects=objects;b.compile_args=compile_args
    result=b.build(output);changes=result.pop('elapsed_object_replacements')
    parent=json.loads((BASE/'manifest.json').read_text())
    for key in ('elapsed_object_replacements','link_trace_fields','link_trace_call_steps','link_trace_core_steps'):
        result[key]=parent[key]
    result.pop('hardware_failure_receipt',None)
    assembly=(output/'BCM2712PCIePHYTransport.cpp.s').read_text()
    guard=re.search(r'^__ZN\d+BCM2712PCIePHYTransport5guardEv:[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.M|re.S)[1]
    calls=re.findall(r'\tbl\t(_pe_rpi5_\w+)',guard)
    if calls.count('_pe_rpi5_pcie_fw_check')!=2 or calls.count('_pe_rpi5_watchdog_check_pcie')!=1 or '_pe_rpi5_pcie_irq_check' in calls:
        raise ValueError('Actual linked guard does not match fresh nested composition')
    before,after,_=objects(output)
    for p,q in zip(before,after):
        if p!=q and p.name!='BCM2712PCIePHYTransport.cpp.o':raise ValueError('Owner/core object changed')
    result.update(guard_composition=profile.unchanged_contract(),
        guard_composition_object_replacements=changes,guard_emitted_owner_calls=calls,
        unchanged_parent_objects=len(before)-1,controller_caller_unchanged=True,
        passive_trace_unchanged=True,firmware_guard_unchanged=False,
        guard_predicates_and_call_order_unchanged=False,
        transport_common_owner_predicates_unchanged=True,transport_mmio_guard_sites_unchanged=True,
        fresh_pm_irq_firmware_checks_retained=True,owner_client_core_secure_objects_unchanged=True,
        observed_pm_limit_receipt=str(ROOT/'build/rpi5/pcie-owner-trace-serial-20261013/serial.bin'),
        observed_pm_limit_raw_sha256=audit.sha(ROOT/'build/rpi5/pcie-owner-trace-serial-20261013/serial.bin'),
        physical_failure_cause_proven=True,physical_success_proven=False,
        physical_trial_admitted=False,required_next_evidence='Contained BAR completion and full clean runtime recovery under nested fresh guard composition',
        trial_scope='Same contained six-BAR trial; remove redundant outer owner checks already performed inside each of two fresh firmware checks, not MMIO guard sites or deadlines')
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',required=True,type=Path)
    value=build(parser.parse_args().output_dir.resolve())
    print(json.dumps({k:value[k] for k in ('profile','kernel','kernel_sha256','kernel_bytes')}))
