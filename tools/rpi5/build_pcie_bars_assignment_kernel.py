#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct guarded BAR relocation/restore plus pure map-candidate kernel."""
import argparse
import json
from pathlib import Path
import re
from tools.rpi5 import build_pcie_link_elapsed_kernel as engine
from tools.rpi5 import build_pcie_id_trace_package as private
from tools.rpi5 import rp1_bars_assignment_profile as profile
ROOT,audit=engine.ROOT,engine.audit
BASE=profile.FROZEN.parent
BASE_SHA='89792a4b0c86fec83d9123cf9f92247bf92257c9e19439ae7383bd65fe34b71c'
C_PARENT=ROOT/'build/rpi5/rp1-all-bars-kernel-20261013-checked'
C_PARENT_SHA='1402041446cde952c27b18e6ce10894bd7f0845df1a5a6c152ceb3b99a4ec14e'
PROFILE='pcie-bars-assignment-restoration-no-decode-kernel-v1'
TEST=ROOT/'tools/rpi5/tests/test_pcie_bars_assignment_kernel.py'


def inputs():
    pins={};parent=None
    for folder,digest in ((BASE,BASE_SHA),(C_PARENT,C_PARENT_SHA)):
        if audit.sha(folder/'manifest.json')!=digest:raise ValueError('Frozen assignment constituent changed')
        manifest=json.loads((folder/'manifest.json').read_text())
        if folder==BASE:parent=manifest
        for name,value in (manifest['inputs_sha256']|manifest['generated_sha256']|{str(folder/'manifest.json'):digest}).items():
            if name in pins and pins[name]!=value:raise ValueError('Assignment ancestry conflict')
            pins[name]=value
    for path in (Path(__file__).resolve(),Path(profile.__file__).resolve(),TEST,
        ROOT/'loader/rpi5/rp1_bars_assign.c',ROOT/'loader/rpi5/rp1_bars_assign.h',
        ROOT/'tools/rpi5/tests/test_rp1_bars_assign.py',ROOT/'tools/rpi5/tests/rp1_bars_assign_host.c',
        ROOT/'tools/rpi5/tests/test_rp1_bars_assignment_transport.py',
        ROOT/'build/rpi5/pcie-guard-composition-serial-20261013/serial.bin'):
        value=audit.sha(path)
        if str(path) in pins and pins[str(path)]!=value:raise ValueError('Assignment source conflict')
        pins[str(path)]=value
    engine.verify(pins);return parent,parent,pins


def objects(output):
    original=[Path(p) for p in (BASE/'kernel.rp1-config.filelist').read_text().splitlines()]
    found=[p for p in original if p.name=='BCM2712PCIePHYTransport.cpp.o']
    if len(found)!=1 or len(original)!=len(set(original)) or any(p.name=='rp1_bars_assign.c.o' for p in original):
        raise ValueError('Exact transport replacement plus new assignment object required')
    changes={found[0]:output/found[0].name}
    return original,[changes.get(p,p) for p in original]+[output/'rp1_bars_assign.c.o'],changes


def compile_args(parent,source):
    if source.suffix=='.cpp':
        command=parent['compiles'][0]['command'];old=BASE/'overlay'/source.name
    elif source.name=='rp1_bars_assign.c':
        ancestor=json.loads((C_PARENT/'manifest.json').read_text())
        command=next(r['command'] for r in ancestor['bar_compiles'] if r['log'].endswith('/rp1_bars_probe-compile.log'))
        old=ROOT/'loader/rpi5/rp1_bars_probe.c'
    else:raise ValueError('Unexpected assignment source')
    if command.count(str(old))!=1:raise ValueError('Exact ancestor compile changed')
    stop=command.index('-MD') if '-MD' in command else command.index('-o')
    result=[str(source) if a==str(old) else a for a in command[:stop]]
    if source.suffix=='.c':result[1:1]=['-iquote',str(ROOT/'loader/rpi5')]
    return result


def contract():
    return dict(same_boot_live_owner_callback=True,source_callback_scope='Fresh in-memory owner/thread/phase and exact owned objects, not hardware authority',
        every_transport_access_guarded=True,fresh_config_lifecycle_checks=True,
        all_six_bar_inventory_required=True,supported_type='MEM32 non-prefetch only',
        exact_outbound_software_plan_reconciled=True,provider_fresh_outbound_readback_required=True,
        config_transfer_bound=76,endpoint_write_bound=12,
        exact_successful_restore_required=True,failure_partial_state_quarantined=True,failure_cleanup=False,retry=False,
        mapping_geometry_only=True,mapping_performed=False,memory_decode_enabled=False,
        command_writes=False,endpoint_device_access=False,bus_master_enabled=False,irq_delivery_enabled=False,
        dma_enabled=False,ethernet_proven=False,owner_limits_and_deadlines_unchanged=True,
        expected_pi_present=7,expected_pi_assignment_transfers=58,expected_pi_assignment_writes=6)


def build(output):
    b=private.load_private(Path(engine.__file__).resolve(),'_bars_assignment_kernel_engine')
    b.BASE=BASE;b.BASE_SHA=BASE_SHA;b.PROFILE=PROFILE;b.TEST=TEST;b.profile=profile
    b.inputs=inputs;b.objects=objects;b.compile_args=compile_args
    result=b.build(output);changes=result.pop('elapsed_object_replacements')
    parent=json.loads((BASE/'manifest.json').read_text())
    for key in ('elapsed_object_replacements','link_trace_fields','link_trace_call_steps','link_trace_core_steps'):
        result[key]=parent[key]
    result.pop('hardware_failure_receipt',None)
    result.pop('bar_assignment_performed',None)
    symbols=engine.base.full.symbols((output/'kernel.symbols').read_text())
    names=['_rpi5_rp1_bars_assign','_rpi5_rp1_bars_restore','_rpi5_rp1_bars_mapping_candidate','_rpi5_rp1_assignment_write_allowed']
    for name in names:
        if len(symbols.get(name,[]))!=1:raise ValueError('Missing exact assignment implementation: '+name)
    assembly=(output/'BCM2712PCIePHYTransport.cpp.s').read_text()
    guard=re.search(r'^__ZN\d+BCM2712PCIePHYTransport5guardEv:[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.M|re.S)[1]
    calls=re.findall(r'\tbl\t(_pe_rpi5_\w+)',guard)
    if calls!=parent['guard_emitted_owner_calls']:raise ValueError('Fresh owner composition changed')
    actual=(output/'overlay/BCM2712PCIeIDTrialProgress.inc').read_text()
    formats=re.findall(r'kprintf\("([^"\n]+)"',actual)
    if len(formats)!=23 or not formats[-1].startswith('RPI5XNU:PCIEID:END '):raise ValueError('Exact bounded diagnostic sequence required')
    raw=(output/'kernel.rp1-config').read_bytes()
    for fmt in formats:
        decoded=fmt.replace('\\n','\n')
        if raw.count(decoded.encode()+b'\0')!=1:raise ValueError('Exact assignment logging row missing')
    before,after,_=objects(output)
    result.update(assignment_contract=contract(),assignment_object_replacements=changes,
        assignment_added_objects=[str(output/'rp1_bars_assign.c.o')],assignment_required_implementations=names,
        assignment_record_formats=[fmt.replace('\\n','\n') for fmt in formats],
        unchanged_parent_objects=len(before)-1,guard_emitted_owner_calls=calls,
        controller_caller_unchanged=False,passive_trace_unchanged=False,owner_client_core_secure_objects_unchanged=True,
        candidate_performs_bar_assignment=True,candidate_restores_original_bars=True,bar_candidate_plan_only=False,
        bar_memory_decode_enabled=False,bar_mmio_mapped=False,command_writes=False,
        logging_calls=23,logging_max_scalar_arguments=15,
        endpoint_write_values='Existing all-ones size probe/exact original plus exact bounded assignment and original restoration for live selected MEM32 BAR',
        assignment_source_context='Exact current transport-owned config/FDT/probe/size objects, thread/phase/provider/claims every use',
        physical_sizing_capture_sha256=audit.sha(ROOT/'build/rpi5/pcie-guard-composition-serial-20261013/serial.bin'),
        physical_success_proven=False,physical_trial_admitted=False,
        required_next_evidence='Clean zero-TX bounded same-boot assignment and exact restoration followed by independent Linux recovery',
        trial_scope='All-six size/restore, bounded exact MEM32 relocation, pure unmapped Device geometry, exact original BAR restoration; no memory decode, device access, IRQ delivery, DMA or Ethernet')
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True)
    m=build(parser.parse_args().output_dir.resolve())
    print(json.dumps({key:m[key] for key in ('profile','kernel','kernel_sha256','kernel_bytes')}))
