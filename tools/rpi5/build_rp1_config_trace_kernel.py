#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Two-object passive RP1 config trace on the physically exercised link image."""
import argparse
import json
from pathlib import Path
try:
    from . import build_pcie_link_elapsed_kernel as previous
    from . import build_pcie_id_trace_package as loader
    from . import rp1_config_trace_profile as profile
except ImportError:
    import build_pcie_link_elapsed_kernel as previous
    import build_pcie_id_trace_package as loader
    import rp1_config_trace_profile as profile

ROOT,audit,base=previous.ROOT,previous.audit,previous.base
BUILDER=ROOT/'tools/rpi5/build_pcie_link_elapsed_kernel.py'
BASE=ROOT/'build/rpi5/pcie-link-elapsed-kernel-20261013-final'
BASE_SHA='cfdeadb0288642aa978a50c470ef73c00842757a5101753e948a2a57d02aba0d'
PROFILE='rp1-config-passive-trace-kernel-v1'
TEST=ROOT/'tools/rpi5/tests/test_rp1_config_trace_kernel.py'
verify=previous.verify


def inputs():
    if audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Actual link image changed')
    parent=json.loads((BASE/'manifest.json').read_text())
    pins=parent['inputs_sha256']|parent['generated_sha256']|{str(BASE/'manifest.json'):BASE_SHA}
    for p in (Path(__file__).resolve(),TEST,Path(profile.__file__).resolve(),
        ROOT/'tools/rpi5/tests/test_rp1_config_trace.py'):
        pins[str(p)]=audit.sha(p)
    verify(pins)
    trace=json.loads((previous.previous.BASE/'manifest.json').read_text())
    return parent,trace,pins


def objects(output):
    original=[Path(p) for p in (BASE/'kernel.rp1-config.filelist').read_text().splitlines()]
    if len(original)!=len(set(original)):raise ValueError('Duplicate original object')
    replacements={}
    for name in ('BCM2712PCIePHYTransport.cpp','rp1_config_snapshot_checked.c'):
        found=[p for p in original if p.name==name+'.o']
        if len(found)!=1:raise ValueError('Ambiguous RP1 trace replacement')
        replacements[found[0]]=output/(name+'.o')
    return original,[replacements.get(p,p) for p in original],replacements


def build(output):
    # Private reuse of the frozen compile/dependency/link engine. Its exact
    # source is itself in the parent's complete content-hash closure.
    source=loader.load_private(BUILDER,'_rpi5_private_rp1_trace_kernel')
    source.BASE=BASE;source.BASE_SHA=BASE_SHA;source.PROFILE=PROFILE;source.TEST=TEST
    source.profile=profile;source.inputs=inputs;source.objects=objects
    source.compile_args=previous.compile_args
    result=source.build(output)
    parent=json.loads((BASE/'manifest.json').read_text())
    kernel=Path(result['kernel']);listing=(output/'kernel.symbols').read_text()
    required=base.full.symbols(listing)
    name='_rpi5_rp1_config_snapshot_trace'
    if len(required.get(name,[]))!=1:raise ValueError('Missing/ambiguous new snapshot implementation')
    if not any(s['initprot']&4 and s['vmaddr']<=required[name][0]<s['vmaddr']+s['filesize']
        for s in result['link']['macho']['segments']):raise ValueError('Non-executable snapshot implementation')
    if kernel.read_bytes().count(previous.profile.FIELDS.encode())!=1:raise ValueError('Original link telemetry lost')
    replacements=result.pop('elapsed_object_replacements')
    for key in ('link_trace_fields','link_trace_call_steps','link_trace_core_steps','elapsed_object_replacements'):
        result[key]=parent[key]
    result.update(rp1_trace_object_replacements=replacements,
        link_object_unchanged=True,controller_caller_unchanged=True,
        rp1_trace_fields=profile.FIELDS,rp1_snapshot_abi_unchanged=True,
        config_core_unchanged=True,endpoint_header_reads=32,selector_writes=32,
        endpoint_config_writes=0,rp1_trace_adds_mmio=False,
        required_rp1_trace_implementations=[name],
        rp1_call_steps={1:'guard-before',2:'config-init',3:'snapshot',4:'guard-after',5:'complete'},
        rp1_core_steps={1:'entry',2:'transfer',3:'compare',4:'profile',5:'complete'},
        hardware_failure_receipt='build/rpi5/link-v2-serial-20261013',
        passive_trace_unchanged=False,installed=False,pi_executed=False)
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True)
    r=build(p.parse_args().output_dir.resolve())
    print(json.dumps({k:r[k] for k in ('profile','kernel','kernel_sha256','kernel_bytes')}))
