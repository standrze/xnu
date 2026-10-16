#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct two-object root-bus routing correction on the actual config trace."""
import argparse
import json
from pathlib import Path
import re
try:
    from . import build_rp1_config_trace_kernel as previous
    from . import pcie_root_route_profile as profile
except ImportError:
    import build_rp1_config_trace_kernel as previous
    import pcie_root_route_profile as profile

ROOT,audit,base=previous.ROOT,previous.audit,previous.base
BASE=ROOT/'build/rpi5/rp1-config-trace-kernel-20261013-final'
BASE_SHA='f34a66ee8d0cb26c99f54d5d1b9a03c2efe42574e7dce9c101ad916f495c8e33'
PROFILE='pcie-root-bus-route-kernel-v1'
TEST=ROOT/'tools/rpi5/tests/test_pcie_root_route_kernel.py'
verify=previous.verify


def inputs():
    if audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Actual config-trace kernel changed')
    parent=json.loads((BASE/'manifest.json').read_text())
    pins=parent['inputs_sha256']|parent['generated_sha256']|{str(BASE/'manifest.json'):BASE_SHA}
    for p in (Path(__file__).resolve(),TEST,Path(profile.__file__).resolve(),
        ROOT/'tools/rpi5/tests/test_pcie_root_route.py'):
        pins[str(p)]=audit.sha(p)
    verify(pins)
    trace=json.loads((previous.previous.previous.BASE/'manifest.json').read_text())
    return parent,trace,pins


def objects(output):
    original=[Path(p) for p in (BASE/'kernel.rp1-config.filelist').read_text().splitlines()]
    if len(original)!=len(set(original)):raise ValueError('Duplicate original object')
    replacements={}
    for name in ('BCM2712PCIePHYTransport.cpp','pcie_rc.c'):
        found=[p for p in original if p.name==name+'.o']
        if len(found)!=1:raise ValueError('Ambiguous root-route replacement')
        replacements[found[0]]=output/(name+'.o')
    return original,[replacements.get(p,p) for p in original],replacements


def build(output):
    source=previous.loader.load_private(previous.BUILDER,'_rpi5_private_root_route_kernel')
    source.BASE=BASE;source.BASE_SHA=BASE_SHA;source.PROFILE=PROFILE;source.TEST=TEST
    source.profile=profile;source.inputs=inputs;source.objects=objects
    source.compile_args=previous.previous.compile_args
    result=source.build(output)
    parent=json.loads((BASE/'manifest.json').read_text())
    symbols=base.full.symbols((output/'kernel.symbols').read_text())
    name='_rpi5_pcie_rc_configure_root_route'
    if len(symbols.get(name,[]))!=1 or not any(s['initprot']&4 and s['vmaddr']<=symbols[name][0]<s['vmaddr']+s['filesize']
        for s in result['link']['macho']['segments']):raise ValueError('New root-route implementation not uniquely executable')
    assembly=(output/'BCM2712PCIePHYTransport.cpp.s').read_text()
    n=next(n for n in symbols if n.startswith('__ZN23BCM2712PCIePHYTransport') and 'runControllerE' in n and '.' not in n)
    body=re.search(re.escape(n)+r':[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.S)
    calls=re.findall(r'\tbl\t(_rpi5_pcie_[^\s;]+)',body[1] if body else '')
    if calls.count(name)!=1 or calls.index(name)>=calls.index('_rpi5_pcie_link_train_elapsed_trace'):
        raise ValueError('Actual root-route call before link release missing')
    replacements=result.pop('elapsed_object_replacements')
    for key in ('link_trace_fields','link_trace_call_steps','link_trace_core_steps','elapsed_object_replacements'):
        result[key]=parent[key]
    result.pop('hardware_failure_receipt',None)
    result.update(root_route_object_replacements=replacements,
        root_route_required_implementations=[name],root_route_fields=profile.FIELDS,
        root_route_call_sequence=calls,root_config_identity=profile.ROOT_ID,
        root_header_type=1,root_primary_bus=0,root_secondary_bus=1,root_subordinate_bus=1,
        root_config_write_offset=0x18,root_config_writes_max=1,root_config_reads_max=6,
        root_low24_value=0x010100,root_upper_byte_preserved=True,
        root_route_post_link_readback=True,root_write_before_perst_release=True,
        root_route_steps={1:'entry',2:'root-profile',3:'read-original-route',4:'write-route',
            5:'immediate-readback',6:'independent-final-readback',7:'rc-complete',
            8:'post-link-readback',9:'complete'},
        link_object_unchanged=True,config_core_unchanged=True,snapshot_object_unchanged=True,
        controller_caller_unchanged=False,root_config_state_and_observation_abi_unchanged=True,
        root_route_permissions_extended=True,trace_adds_mmio=True,trace_changes_permissions=True,
        trace_changes_deadlines=False,source_corrective_change=True,physical_cause_proven=False,
        endpoint_header_reads=32,selector_writes=32,endpoint_config_writes=0,
        command_writes=0,bar_assignment_performed=False,root_route_only=True,
        trial_scope='Root0 to direct RP1 bus1 configuration route plus read-only ID; no BAR, COMMAND, DMA, IRQ delivery or packets',
        installed=False,pi_executed=False,ethernet_proven=False)
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True)
    r=build(p.parse_args().output_dir.resolve())
    print(json.dumps({k:r[k] for k in ('profile','kernel','kernel_sha256','kernel_bytes')}))
