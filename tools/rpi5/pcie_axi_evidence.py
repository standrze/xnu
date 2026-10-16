#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact corrected AXI capture, independent return, and explicit dual restoration."""
import argparse
import json
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import pcie_trace_evidence as original
import stage_pcie_axi_trial as stage
import serial_pcie_axi_trial as recorder
import pcie_axi_serial_core as protocol


def return_source_pins():
    paths=(Path(__file__).resolve(),stage.ROOT/'tools/rpi5/capture_pcie_axi_linux_return.py',
        Path(original.__file__).resolve(),stage.ROOT/'tools/rpi5/capture_pcie_trace_linux_return.py',
        Path(stage.base.MODULES[0].__file__).resolve(),Path(stage.base.reference.__file__).resolve())
    return {str(p):stage.sha(p) for p in paths}


_bindings=dict(original.__dict__,stage=stage,recorder=recorder,protocol=protocol,
    return_source_pins=return_source_pins,__file__=__file__,__doc__=__doc__)
for _name in ('same','zoned','number','receive_journal','inspect_capture','inspect_return','local_child','archived_sources','load_capture'):
    _fn=getattr(original,_name)
    _bindings[_name]=types.FunctionType(_fn.__code__,_bindings,_name,_fn.__defaults__)
    globals()[_name]=_bindings[_name]


def inspect(installation,capture,restoration):
    installation,capture,restoration=map(local_child,(installation,capture,restoration))
    plan,installed,observations=load_capture(installation,capture)
    return_paths=[p for p in (capture/'linux-return.json',capture/'failed-linux-return.json') if p.exists()]
    if len(return_paths)!=1:raise ValueError('One unambiguous independent return receipt required')
    return_path=return_paths[0];returned=json.loads(return_path.read_text())
    if return_path.name=='failed-linux-return.json':
        bounds={n:stage.sha(capture/n) for n in ('armed.json','state.json','serial.bin','receive-events.jsonl')}
        if (observations['diagnostic']['rp1_id_trial_pass'] is not False or
            returned.get('status')!='failed_trace_independent_linux_return_verified' or
            returned.get('rp1_id_trial_pass') is not False or returned.get('zero_serial_tx') is not True or
            returned.get('independent_normal_nvme_linux_return_verified') is not True or
            not same(returned.get('trial_failure'),observations['diagnostic']) or
            not same(returned.get('failed_capture_sha256'),bounds) or
            returned.get('failed_collector_sha256')!=stage.sha(stage.ROOT/'tools/rpi5/capture_pcie_axi_failed_return.py')):
            raise ValueError('Failed diagnostic return witness differs from actual failed trace')
        returned=returned['observation']
    boot=inspect_return(returned,plan,installed,observations)
    restore_plan=json.loads((restoration/'plan.json').read_text());result=json.loads((restoration/'result.json').read_text())
    if restore_plan['profile']!=stage.RESTORE:raise ValueError('Explicit dual-pair restore receipt required')
    stage.validate_result(result,restore_plan);archived_sources(restoration,restore_plan)
    ancestry=dict(directory=str(installation),hashes={n:stage.sha(installation/n) for n in ('plan.json','result.json')})
    if (not same(restore_plan['ancestry'],ancestry) or restore_plan['linux_boot_id']!=boot or
        result['identity']['boot_id']!=boot or len(restore_plan['nvme_backups'])!=123):
        raise ValueError('Restoration not bound to this exact trial/new Linux return')
    paths=(*[d/n for d in (installation,restoration) for n in ('plan.json','result.json')],
        *[capture/n for n in ('armed.json','state.json','serial.bin','receive-events.jsonl')],return_path)
    return dict(trace_return_restore_evidence_pass=True,rp1_id_trial_pass=observations['diagnostic']['rp1_id_trial_pass'],capture=observations,
        independent_normal_nvme_linux_return_proven=True,working_firmware_and_zsh_restored=True,
        returned_linux_boot_id=boot,restored_pair_sha256=result['pair_sha256'],
        next_inherited_artifact_count=len(stage.inherited(restore_plan,result,128)),
        files_sha256={str(p):stage.sha(p) for p in paths},
        verifier_source_sha256={str(Path(__file__).resolve()):stage.sha(Path(__file__))},
        controller_initialization_admitted=False,power_domain_ownership_proven=False,
        xnu_pe_runtime_proven=False,ethernet_proven=False,durability=False,
        scope='Exact controller/link/RP1 trace observations, bounded reset, independent normal Linux return and dual restoration; not full production ownership, IRQ delivery, DMA, GEM, packets or durable storage')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--installation',type=Path,required=True);p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--restoration',type=Path,required=True);a=p.parse_args()
    print(json.dumps(inspect(a.installation,a.capture,a.restoration),indent=2,sort_keys=True))
