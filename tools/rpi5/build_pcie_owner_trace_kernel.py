#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Two-object passive owner diagnosis on the actually exercised BAR kernel."""
import argparse
import json
from pathlib import Path
import re
from tools.rpi5 import build_pcie_link_elapsed_kernel as engine
from tools.rpi5 import build_pcie_id_trace_package as private
from tools.rpi5 import pcie_owner_trace_profile as profile
ROOT,audit=engine.ROOT,engine.audit
BASE=profile.BASE
BASE_SHA='67bc091bb7a0712c132229dd02e206b4b6063553b2116379ff89c10c21735164'
PROFILE='pcie-passive-owner-trace-bars-kernel-v1'
TEST=ROOT/'tools/rpi5/tests/test_pcie_owner_trace_kernel.py'


def inputs():
    if audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen BAR kernel changed')
    parent=json.loads((BASE/'manifest.json').read_text())
    pins=parent['inputs_sha256']|parent['generated_sha256']|{str(BASE/'manifest.json'):BASE_SHA}
    for path in (Path(__file__).resolve(),Path(profile.__file__).resolve(),profile.HEADER,TEST,
        ROOT/'tools/rpi5/tests/test_pcie_owner_composition.py',ROOT/'tools/rpi5/tests/pcie_owner_composition_env.inc',
        ROOT/'tools/rpi5/tests/pcie_owner_composition_secure.c',ROOT/'tools/rpi5/tests/test_pcie_owner_trace.py',
        ROOT/'tools/rpi5/tests/test_pcie_owner_budget_boundary.py',ROOT/'build/rpi5/rp1-bars-root-serial-20261013/serial.bin'):
        digest=audit.sha(path)
        if str(path) in pins and pins[str(path)]!=digest:raise ValueError('Conflicting new owner input')
        pins[str(path)]=digest
    engine.verify(pins);return parent,parent,pins


def objects(output):
    original=[Path(p) for p in (BASE/'kernel.rp1-config.filelist').read_text().splitlines()]
    if len(original)!=len(set(original)):raise ValueError('Unique original objects required')
    replacements={}
    for name in ('BCM2712PCIePHYTransport.cpp','pe_fiq.c'):
        matches=[p for p in original if p.name==name+'.o']
        if len(matches)!=1:raise ValueError('One exact owner/transport object required')
        replacements[matches[0]]=output/(name+'.o')
    return original,[replacements.get(p,p) for p in original],replacements


def compile_args(parent,source):
    if source.suffix=='.cpp':
        command=parent['compiles'][0]['command'];old=BASE/'overlay'/source.name
    else:
        manifest=json.loads((profile.PE.parent/'manifest.json').read_text())
        command=next(r['command'] for r in manifest['compiles'] if r['log'].endswith('/pe_fiq.c-compile.log'))
        old=profile.PE
    if command.count(str(old))!=1:raise ValueError('Exact original compile source changed')
    stop=command.index('-MD') if '-MD' in command else command.index('-o')
    return [str(source) if a==str(old) else a for a in command[:stop]]


def build(output):
    b=private.load_private(Path(engine.__file__).resolve(),'_owner_trace_kernel_engine')
    b.BASE=BASE;b.BASE_SHA=BASE_SHA;b.PROFILE=PROFILE;b.TEST=TEST;b.profile=profile
    b.inputs=inputs;b.objects=objects;b.compile_args=compile_args
    result=b.build(output)
    replacements=result.pop('elapsed_object_replacements')
    parent=json.loads((BASE/'manifest.json').read_text())
    for key in ('elapsed_object_replacements','link_trace_fields','link_trace_call_steps','link_trace_core_steps'):
        result[key]=parent[key]
    result.pop('hardware_failure_receipt',None)
    listing=(output/'kernel.symbols').read_text();symbols=engine.base.full.symbols(listing)
    if len(symbols.get('_pe_rpi5_pcie_owner_trace',[]))!=1:raise ValueError('Exact diagnostic API not linked')
    assembly=(output/'BCM2712PCIePHYTransport.cpp.s').read_text()
    entry=re.search(r'^_rpi5_pcie_id_trial_start:[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.M|re.S)[1]
    if len(re.findall(r'\tbl\t_pe_rpi5_pcie_owner_trace\b',entry))!=1:raise ValueError('One final diagnostic snapshot required')
    actual=(output/'overlay/BCM2712PCIeIDTrialProgress.inc').read_text()
    if actual.count('kprintf(')!=19:raise ValueError('Exact nineteen bounded diagnostic records required')
    result.update(owner_trace_object_replacements={str(p):str(q) for p,q in replacements.items()},
        owner_trace_fields={name:fmt for name,fmt,_ in profile.ROWS},owner_trace_snapshot_calls=1,
        owner_trace_reads_memory_only=True,owner_trace_adds_mmio=False,owner_trace_adds_smc=False,
        owner_trace_adds_counter_reads=False,owner_trace_releases_or_reloads=False,
        fw_client_object_unchanged=True,secure_firmware_unchanged=True,
        irq_mask_object_unchanged=True,pm_lease_object_unchanged=True,
        guard_predicates_and_call_order_unchanged=True,owner_failure_quarantine_unchanged=True,
        logging_calls=19,logging_max_scalar_arguments=15,
        cumulative_pm_limit=65536,cumulative_fw_limit=65536,ns_fw_deadline_seconds=9,
        secure_fw_deadline_seconds=10,pm_access_deadline_seconds=12,hardware_reset_seconds=15,
        observed_failure_raw_sha256=audit.sha(ROOT/'build/rpi5/rp1-bars-root-serial-20261013/serial.bin'),
        physical_failure_cause_proven=False,controller_caller_unchanged=True,
        physical_trial_admitted=False,required_next_evidence='Existing bounded BAR operation plus exact passive owner-failure state; no policy change',
        trial_scope='Unchanged contained six-BAR trial; passive final owner state distinguishes client, firmware, IRQ and PM rejection')
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',required=True,type=Path)
    r=build(parser.parse_args().output_dir.resolve())
    print(json.dumps({k:r[k] for k in ('profile','kernel','kernel_sha256','kernel_bytes')}))
