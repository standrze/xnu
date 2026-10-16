#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Offline-only existing all-BAR cores plus elapsed timing and RP1 telemetry."""
import argparse
import json
from pathlib import Path
import re
try:
    from . import build_rp1_config_trace_kernel as previous
    from . import rp1_bars_elapsed_profile as profile
except ImportError:
    import build_rp1_config_trace_kernel as previous
    import rp1_bars_elapsed_profile as profile

ROOT,audit,base=previous.ROOT,previous.audit,previous.base
BASE=ROOT/'build/rpi5/rp1-config-trace-kernel-20261013-final'
BASE_SHA='f34a66ee8d0cb26c99f54d5d1b9a03c2efe42574e7dce9c101ad916f495c8e33'
BARS=ROOT/'build/rpi5/rp1-all-bars-kernel-20261013-checked'
BARS_SHA='1402041446cde952c27b18e6ce10894bd7f0845df1a5a6c152ceb3b99a4ec14e'
PROFILE='rp1-all-bars-elapsed-config-trace-kernel-v1'
TEST=ROOT/'tools/rpi5/tests/test_rp1_bars_elapsed_kernel.py'
verify=previous.verify


def inputs():
    pins={};parents=[]
    for folder,digest in ((BASE,BASE_SHA),(BARS,BARS_SHA)):
        if audit.sha(folder/'manifest.json')!=digest:raise ValueError('Frozen constituent manifest changed')
        m=json.loads((folder/'manifest.json').read_text());parents.append(m)
        more=m['inputs_sha256']|m['generated_sha256']|{str(folder/'manifest.json'):digest}
        for name,value in more.items():
            if name in pins and pins[name]!=value:raise ValueError('BAR/config ancestor conflict')
            pins[name]=value
    for p in (Path(__file__).resolve(),Path(profile.__file__).resolve(),TEST,
        ROOT/'tools/rpi5/tests/test_rp1_bars_elapsed.py'):
        pins[str(p)]=audit.sha(p)
    verify(pins)
    trace=json.loads((previous.previous.previous.BASE/'manifest.json').read_text())
    return parents[0],trace,pins


def objects(output):
    original=[Path(p) for p in (BASE/'kernel.rp1-config.filelist').read_text().splitlines()]
    old=[p for p in original if p.name=='BCM2712PCIePHYTransport.cpp.o']
    if len(old)!=1:raise ValueError('Exact old transport required')
    replacements={old[0]:output/'BCM2712PCIePHYTransport.cpp.o'}
    bars=[Path(p) for p in (BARS/'kernel.rp1-config.filelist').read_text().splitlines()
        if Path(p).name in ('rp1_bars_probe.c.o','rp1_bars_plan.c.o')]
    if len(bars)!=2 or len(set(original+bars))!=len(original)+2:raise ValueError('Exact two existing BAR cores required')
    return original,[replacements.get(p,p) for p in original]+bars,replacements


def build(output):
    source=previous.loader.load_private(previous.BUILDER,'_rpi5_private_allbars_elapsed_kernel')
    source.BASE=BASE;source.BASE_SHA=BASE_SHA;source.PROFILE=PROFILE;source.TEST=TEST
    source.profile=profile;source.inputs=inputs;source.objects=objects
    source.compile_args=previous.previous.compile_args
    result=source.build(output)
    parent=json.loads((BASE/'manifest.json').read_text());bars=json.loads((BARS/'manifest.json').read_text())
    names=base.full.symbols((output/'kernel.symbols').read_text())
    required=bars['bar_required_implementations']
    for name in required:
        if len(names.get(name,[]))!=1 or not any(s['initprot']&4 and s['vmaddr']<=names[name][0]<s['vmaddr']+s['filesize']
            for s in result['link']['macho']['segments']):raise ValueError('BAR implementation not uniquely executable')
    assembly=(output/'BCM2712PCIePHYTransport.cpp.s').read_text()
    name=next(n for n in required if 'rp1BarsWrite' in n)
    body=re.search(re.escape(name)+r':[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.S)
    if not body or not re.search(r'\tdmb\tosh\n.*?\tstr\tw\d+, \[x\d+(?:, [^\]]+)?\].*?\tdsb\tsy',body[1],re.S):
        raise ValueError('Actual ordered BAR numeric32 write missing')
    name=next(n for n in names if n.startswith('__ZN23BCM2712PCIePHYTransport') and 'runControllerAndObserveRP1' in n and '.' not in n)
    body=re.search(re.escape(name)+r':[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.S)
    calls=re.findall(r'\tbl\t(_rpi5_rp1_[^\s;]+)',body[1] if body else '')
    if calls!=['_rpi5_rp1_config_snapshot_trace','_rpi5_rp1_bars_probe','_rpi5_rp1_bars_assignment_plan']:
        raise ValueError('Actual guarded config-trace/BAR/plan caller order missing')
    replacements=result.pop('elapsed_object_replacements')
    for key in ('link_trace_fields','link_trace_call_steps','link_trace_core_steps','elapsed_object_replacements'):
        result[key]=parent[key]
    result.pop('hardware_failure_receipt',None)
    original,current,_=objects(output)
    result.update(bars_transport_replacements=replacements,bars_added_objects=[str(p) for p in current if p not in original and p not in map(Path,replacements.values())],
        unchanged_parent_objects=len(original)-1,bar_required_implementations=required,
        bar_parent_manifest_sha256=BARS_SHA,bar_trace_fields=profile.FIELDS,
        endpoint_config_writes_max=12,endpoint_config_reads_max=69,selector_writes_max=81,
        endpoint_config_writes=12,endpoint_header_reads=32,selector_writes=81,
        command_writes=0,bar_assignment_performed=False,bar_memory_decode_enabled=False,
        bar_mmio_mapped=False,bar_config_transactions_max=49,bar_candidate_plan_only=True,
        link_object_unchanged=True,controller_caller_unchanged=True,config_core_unchanged=True,
        bar_probe_and_plan_objects_unchanged=True,emitted_all_bar_caller_sequence=calls,
        config_write_scope_extended=True,trace_changes_permissions=False,
        bar_failure_semantics=bars['bar_failure_semantics'],
        loader_created=False,physical_trial_admitted=False,physical_id_receipt_required_before_trial=True,
        required_next_evidence='Fresh controller/link/RP1 ID success before any BAR sizing hardware trial',
        trial_scope='Offline all-six-BAR size/restore and pure allocation candidate; no COMMAND, assignment, BAR MMIO, IRQ delivery, DMA, network or hardware admission',
        installed=False,pi_executed=False,ethernet_proven=False)
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',required=True,type=Path)
    r=build(p.parse_args().output_dir.resolve())
    print(json.dumps({k:r[k] for k in ('profile','kernel','kernel_bytes','kernel_sha256')}))
