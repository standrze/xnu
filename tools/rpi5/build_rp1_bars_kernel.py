#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct contained all-BAR inventory kernel; no hardware or decode enable."""
import argparse
import json
from pathlib import Path
import re
try:
    from . import build_pcie_id_progress_kernel as previous
except ImportError:
    import build_pcie_id_progress_kernel as previous

ROOT,audit=previous.ROOT,previous.previous.audit
BASE=ROOT/'build/rpi5/pcie-id-progress-kernel-20261013-final'
BASE_SHA='d57393c77dffea0a55249756c034becd04e5257222f6afe891f1bbc89aa2dd5e'
CORE=ROOT/'loader/rpi5/rp1_bars_probe.c'
PLAN=ROOT/'loader/rpi5/rp1_bars_plan.c'
BODY=ROOT/'iokit/Kernel/BCM2712RP1BarsTransport.inc'


def transport_source(text):
    replace=previous.previous.base.replace_once
    text=replace(text,'rp1DenyWrite,rp1Read,rp1Write,order',
        'rp1BarsAuthorize,rp1Read,rp1BarsWrite,order')
    return replace(text,'    setPhase(BCM2712_PHY_COMPLETE);\n    *out = result;',
        '    if(rpi5_rp1_bars_probe(&barsProbe,&rp1Config,&result.endpoint,&result.bars) || !guard() ||\n'
        '        rpi5_rp1_bars_assignment_plan(&binding,&barsProbe,&result.bars,&result.barsPlan) || !guard()) {\n'
        '        rp1Config.state=RPI5_PCIE_CONFIG_QUARANTINED;fail();return false;\n    }\n'
        '    setPhase(BCM2712_PHY_COMPLETE);\n    *out = result;')


def overlay_sources(cpp):
    parent=cpp.parent;replace=previous.previous.base.replace_once
    header=parent/'BCM2712PCIePHYTransport.h'
    text=replace(header.read_text(),'extern "C" {','extern "C" {\n#include "../../loader/rpi5/rp1_bars_plan.h"')
    text=replace(text,'    struct rpi5_rp1_config_snapshot endpoint;',
        '    struct rpi5_rp1_config_snapshot endpoint;\n    struct rpi5_rp1_bars_size bars;\n'
        '    struct rpi5_rp1_bars_plan barsPlan;')
    text=replace(text,'    struct rpi5_pcie_config rp1Config = {};',
        '    struct rpi5_rp1_bars_probe barsProbe={};\n'
        '    static int rp1BarsAuthorize(void *,const struct rpi5_pcie_config_request *);\n'
        '    static int rp1BarsWrite(void *,uint32_t,uint32_t,uint32_t);\n'
        '    struct rpi5_pcie_config rp1Config = {};')
    text=replace(text,'    unsigned trialPhase() const { return getPhase(); }',
        '    unsigned trialPhase() const { return getPhase(); }\n'
        '    unsigned barsTransactions() const { return barsProbe.transactions; }\n'
        '    unsigned barsWritesStarted() const { return barsProbe.writes_started; }\n'
        '    unsigned barsSelected() const { return barsProbe.selected; }')
    header.write_text(text)
    transport=transport_source((ROOT/'iokit/Kernel/BCM2712RP1ConfigTransport.inc').read_text())
    (parent/'BCM2712RP1ConfigTransport.inc').write_text(transport)
    cpp.write_text(cpp.read_text()+'\n#include "BCM2712RP1BarsTransport.inc"\n')
    return cpp


def build(output):
    output=output.resolve();base=previous.previous.base
    if audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Accepted ID-progress kernel changed')
    report=json.loads((BASE/'manifest.json').read_text())
    pins={**report['inputs_sha256'],**report['generated_sha256'],str(BASE/'manifest.json'):BASE_SHA}
    for name,digest in pins.items():
        if audit.sha(Path(name))!=digest:raise ValueError('BAR ancestor input changed: '+name)
    for source in (CORE,CORE.with_suffix('.h'),PLAN,PLAN.with_suffix('.h'),BODY,Path(__file__).resolve(),
                   ROOT/'tools/rpi5/tests/rp1_bars_probe_host.c',ROOT/'tools/rpi5/tests/test_rp1_bars_probe.py',
                   ROOT/'tools/rpi5/tests/rp1_bars_plan_host.c',
                   ROOT/'tools/rpi5/tests/test_rp1_bars_transport.py'):
        pins[str(source)]=audit.sha(source)
    prepared=output.parent/(output.name+'-bars-inputs');prepared.mkdir(exist_ok=False)
    old_inputs,old_overlay,old_transform=base.inputs,previous.previous.overlay,previous.transform_body
    inherited,prior,objects=old_inputs()
    added=[];compiles=[]
    for source in (CORE,PLAN):
        args=[str(source) if a==str(base.previous.CORE) else a for a in prior['compiles'][1]['command'][:-2]]
        obj=prepared/(source.name+'.o');args+=['-o',str(obj)];added.append(obj)
        dep=prepared/(source.name+'.d')
        for command,name in (([a for a in args[:-2] if a!='-c']+['-M','-MG','-MF',str(dep)],'deps'),(args,'compile')):
            row=audit.execute(command,audit.OBJ/'pexpert/DEVELOPMENT',prepared/(source.stem+'-'+name+'.log'))
            if row['returncode'] or row['warning_count']:raise ValueError('All-BAR compile failed: '+row['log'])
            compiles.append(row)
        for path in audit.dependency_paths(dep,audit.OBJ/'pexpert/DEVELOPMENT'):
            pins[str(path)]=audit.sha(path)
    for path in prepared.iterdir():
        if path.is_file():pins[str(path)]=audit.sha(path)
    def inputs():
        more,prior,current=old_inputs()
        for name,digest in pins.items():
            if name in more and more[name]!=digest:raise ValueError('All-BAR input conflict: '+name)
            more[name]=digest
        return more,prior,current+added
    def overlay(directory):return overlay_sources(old_overlay(directory))
    def body(text):
        text=old_transform(text).replace('RPI5XNU:PCIEID:','RPI5XNU:PCIEBARS:')
        text=base.replace_once(text,'GEN=%u LANES=%u\\n',
            'GEN=%u LANES=%u PRESENT=%02x SIZES=%08x,%08x,%08x,%08x,%08x,%08x PLAN=%08x,%08x,%08x,%08x,%08x,%08x SLOT=%u TXNS=%u WRITES=%u\\n')
        return base.replace_once(text,'observed.controller.link.generation,observed.controller.link.lanes);',
            'observed.controller.link.generation,observed.controller.link.lanes,observed.bars.present,\n'
            '        observed.bars.bar[0].size,observed.bars.bar[1].size,observed.bars.bar[2].size,\n'
            '        observed.bars.bar[3].size,observed.bars.bar[4].size,observed.bars.bar[5].size,\n'
            '        observed.barsPlan.pci_base[0],observed.barsPlan.pci_base[1],observed.barsPlan.pci_base[2],\n'
            '        observed.barsPlan.pci_base[3],observed.barsPlan.pci_base[4],observed.barsPlan.pci_base[5],\n'
            '        transport?transport->barsSelected():0,transport?transport->barsTransactions():0,\n'
            '        transport?transport->barsWritesStarted():0);')
    base.inputs=inputs;previous.previous.overlay=overlay;previous.transform_body=body
    try:result=previous.build(output)
    finally:base.inputs=old_inputs;previous.previous.overlay=old_overlay;previous.transform_body=old_transform
    names=base.full.symbols((output/'kernel.symbols').read_text())
    required=['_rpi5_rp1_bars_probe','_rpi5_rp1_bars_write_allowed','_rpi5_rp1_bars_assignment_plan']
    required += [name for name in names if name.startswith('__ZN23BCM2712PCIePHYTransport') and '.' not in name and
                 any(part in name for part in ('rp1BarsAuthorize','rp1BarsWrite'))]
    if len(required)!=5 or any(len(names.get(name,[]))!=1 for name in required):
        raise ValueError('Actual all-BAR core/transport not linked uniquely')
    for name in required:
        if not any(seg['initprot']&4 and seg['vmaddr']<=names[name][0]<seg['vmaddr']+seg['filesize']
                   for seg in result['link']['macho']['segments']):raise ValueError('All-BAR symbol not executable')
    emitted=(output/'transport.s').read_text();name=next(name for name in required if 'rp1BarsWrite' in name)
    assembly=re.search(re.escape(name)+r':[^\n]*\n(.*?)Lfunc_end\d+:',emitted,re.S)
    if not assembly or not re.search(r'\tdmb\tosh\n.*?\tstr\tw\d+, \[x\d+(?:, [^\]]+)?\].*?\tdsb\tsy',assembly[1],re.S):
        raise ValueError('All-BAR write lacks actual ordered numeric32 store')
    caller=next(name for name in names if name.startswith('__ZN23BCM2712PCIePHYTransport') and
                'runControllerAndObserveRP1' in name and '.' not in name)
    body=re.search(re.escape(caller)+r':[^\n]*\n(.*?)Lfunc_end\d+:',emitted,re.S)
    calls=re.findall(r'\tbl\t(_rpi5_rp1_[^\s;]+)',body[1] if body else '')
    if calls!=['_rpi5_rp1_config_snapshot','_rpi5_rp1_bars_probe','_rpi5_rp1_bars_assignment_plan']:
        raise ValueError('Actual snapshot, all-BAR size/restore, candidate-plan caller sequence missing')
    result.update(profile='rp1-all-bars-size-restore-candidate-plan-kernel-v1',bar_required_implementations=required,
        endpoint_config_writes=12,endpoint_write_offsets=[0x10,0x14,0x18,0x1c,0x20,0x24],command_writes=0,
        endpoint_config_reads=69,selector_writes=81,
        bar_assignment_performed=False,bar_memory_decode_enabled=False,bar_mmio_mapped=False,
        bar_config_transactions=49,bar_sizing_writes=12,
        bar_compiles=compiles,bar_candidate_plan_only=True,emitted_all_bar_caller_sequence=calls,
        bar_failure_semantics='Terminal quarantine, no cleanup/retry; the selected BAR may retain its size-probe request after a posted access failure. Only success proves restoration.',
        trial_scope='Contained controller/link/RP1 ID plus six-slot BAR sizes, exact success restoration and pure candidate allocation; no command, assignment, mapped BAR, DMA or Ethernet',
        candidate_only=True,physical_id_receipt_required_before_trial=True)
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    r=build(parser.parse_args().output_dir)
    print(json.dumps({k:r[k] for k in ('kernel','kernel_sha256','kernel_bytes','profile')}))
