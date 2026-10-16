#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Connect actual BAR1 sizing/restoration after the contained RP1-ID path."""
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
CORE=ROOT/'loader/rpi5/rp1_bar1_probe.c'
BODY=ROOT/'iokit/Kernel/BCM2712RP1BARTransport.inc'


def overlay_sources(cpp):
    parent=cpp.parent;replace=previous.previous.base.replace_once
    header=parent/'BCM2712PCIePHYTransport.h'
    text=replace(header.read_text(),'extern "C" {','extern "C" {\n#include "../../loader/rpi5/rp1_bar1_probe.h"')
    text=replace(text,'    struct rpi5_rp1_config_snapshot endpoint;',
        '    struct rpi5_rp1_config_snapshot endpoint;\n    struct rpi5_rp1_bar1_size bar1;')
    text=replace(text,'    struct rpi5_pcie_config rp1Config = {};',
        '    struct rpi5_rp1_bar1_probe barProbe={};\n'
        '    static int rp1BarAuthorize(void *,const struct rpi5_pcie_config_request *);\n'
        '    static int rp1BarWrite(void *,uint32_t,uint32_t,uint32_t);\n'
        '    struct rpi5_pcie_config rp1Config = {};')
    text=replace(text,'    unsigned trialPhase() const { return getPhase(); }',
        '    unsigned trialPhase() const { return getPhase(); }\n'
        '    unsigned barTransactions() const { return barProbe.transactions; }\n'
        '    unsigned barWritesStarted() const { return barProbe.writes_started; }')
    header.write_text(text)
    transport=(ROOT/'iokit/Kernel/BCM2712RP1ConfigTransport.inc').read_text()
    transport=replace(transport,'rp1DenyWrite,rp1Read,rp1Write,order',
        'rp1BarAuthorize,rp1Read,rp1BarWrite,order')
    transport=replace(transport,'    setPhase(BCM2712_PHY_COMPLETE);\n    *out = result;',
        '    if(rpi5_rp1_bar1_probe(&barProbe,&rp1Config,&result.endpoint,&result.bar1) || !guard()) {\n'
        '        rp1Config.state=RPI5_PCIE_CONFIG_QUARANTINED;fail();return false;\n    }\n'
        '    setPhase(BCM2712_PHY_COMPLETE);\n    *out = result;')
    (parent/'BCM2712RP1ConfigTransport.inc').write_text(transport)
    cpp.write_text(cpp.read_text()+'\n#include "BCM2712RP1BARTransport.inc"\n')
    return cpp


def build(output):
    output=output.resolve();base=previous.previous.base
    if audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Accepted ID-progress kernel changed')
    report=json.loads((BASE/'manifest.json').read_text())
    pins={**report['inputs_sha256'],**report['generated_sha256'],str(BASE/'manifest.json'):BASE_SHA}
    for name,digest in pins.items():
        if audit.sha(Path(name))!=digest:raise ValueError('BAR ancestor input changed: '+name)
    for source in (CORE,CORE.with_suffix('.h'),BODY,Path(__file__).resolve(),
                   ROOT/'tools/rpi5/tests/rp1_bar1_probe_host.c',ROOT/'tools/rpi5/tests/test_rp1_bar1_probe.py',
                   ROOT/'tools/rpi5/tests/test_rp1_bar1_transport.py'):
        pins[str(source)]=audit.sha(source)
    prepared=output.parent/(output.name+'-bar-inputs');prepared.mkdir(exist_ok=False)
    old_inputs,old_overlay,old_transform=base.inputs,previous.previous.overlay,previous.transform_body
    inherited,prior,objects=old_inputs()
    args=[str(CORE) if a==str(base.previous.CORE) else a for a in prior['compiles'][1]['command'][:-2]]
    obj=prepared/'rp1_bar1_probe.c.o';args+=['-o',str(obj)]
    dep=prepared/'rp1_bar1_probe.c.d'
    for command,name in (([a for a in args[:-2] if a!='-c']+['-M','-MG','-MF',str(dep)],'deps'),(args,'compile')):
        row=audit.execute(command,audit.OBJ/'pexpert/DEVELOPMENT',prepared/(name+'.log'))
        if row['returncode'] or row['warning_count']:raise ValueError('BAR compile failed: '+row['log'])
    for path in audit.dependency_paths(dep,audit.OBJ/'pexpert/DEVELOPMENT'):
        pins[str(path)]=audit.sha(path)
    for path in prepared.iterdir():
        if path.is_file():pins[str(path)]=audit.sha(path)
    def inputs():
        more,prior,current=old_inputs()
        for name,digest in pins.items():
            if name in more and more[name]!=digest:raise ValueError('BAR input conflict: '+name)
            more[name]=digest
        return more,prior,current+[obj]
    def overlay(directory):return overlay_sources(old_overlay(directory))
    def body(text):
        text=old_transform(text).replace('RPI5XNU:PCIEID:','RPI5XNU:PCIEBAR:')
        text=base.replace_once(text,'GEN=%u LANES=%u\\n',
            'GEN=%u LANES=%u MASK=%08x SIZE=%08x TXNS=%u WRITES=%u\\n')
        return base.replace_once(text,'observed.controller.link.generation,observed.controller.link.lanes);',
            'observed.controller.link.generation,observed.controller.link.lanes,observed.bar1.mask,observed.bar1.size,\n'
            '        transport?transport->barTransactions():0,transport?transport->barWritesStarted():0);')
    base.inputs=inputs;previous.previous.overlay=overlay;previous.transform_body=body
    try:result=previous.build(output)
    finally:base.inputs=old_inputs;previous.previous.overlay=old_overlay;previous.transform_body=old_transform
    names=base.full.symbols((output/'kernel.symbols').read_text())
    required=['_rpi5_rp1_bar1_probe','_rpi5_rp1_bar1_write_allowed']
    required += [name for name in names if name.startswith('__ZN23BCM2712PCIePHYTransport') and '.' not in name and
                 any(part in name for part in ('rp1BarAuthorize','rp1BarWrite'))]
    if len(required)!=4 or any(len(names.get(name,[]))!=1 for name in required):
        raise ValueError('Actual BAR core/transport not linked uniquely')
    for name in required:
        if not any(seg['initprot']&4 and seg['vmaddr']<=names[name][0]<seg['vmaddr']+seg['filesize']
                   for seg in result['link']['macho']['segments']):raise ValueError('BAR symbol is not executable')
    emitted=(output/'transport.s').read_text();name=next(name for name in required if 'rp1BarWrite' in name)
    body=re.search(re.escape(name)+r':[^\n]*\n(.*?)Lfunc_end\d+:',emitted,re.S)
    if not body or not re.search(r'\tdmb\tosh\n.*?\tstr\tw\d+, \[x\d+(?:, [^\]]+)?\].*?\tdsb\tsy',body[1],re.S):
        raise ValueError('BAR write lacks actual ordered numeric32 store')
    result.update(profile='rp1-bar1-size-restore-kernel-v1',bar_required_implementations=required,
        endpoint_config_writes=2,endpoint_write_offsets=[0x14],command_writes=0,
        bar_assignment_performed=False,bar_memory_decode_enabled=False,bar_mmio_mapped=False,
        bar_config_transactions=13,bar_sizing_writes=2,
        trial_scope='Contained controller/link/RP1 ID plus BAR1 size mask and exact restoration; no command, assignment, mapped BAR, DMA or Ethernet',
        candidate_only=True,physical_id_receipt_required_before_trial=True)
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    r=build(parser.parse_args().output_dir)
    print(json.dumps({k:r[k] for k in ('kernel','kernel_sha256','kernel_bytes','profile')}))
