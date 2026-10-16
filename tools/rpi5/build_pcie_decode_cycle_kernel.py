#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct MEM-only map/revoke/restore kernel; no endpoint register access."""
import argparse
import json
from pathlib import Path
import re
from tools.rpi5 import build_pcie_bars_assignment_kernel as prior
from tools.rpi5 import rp1_decode_profile as profile
ROOT,audit,engine,private=prior.ROOT,prior.audit,prior.engine,prior.private
BASE=profile.FROZEN.parent
BASE_SHA='9c038627143bc79fc453af85996ab8e74e073a18a90f4885dc868c906f4083bc'
PROFILE='pcie-mem-only-device-map-revoke-kernel-v1'
TEST=ROOT/'tools/rpi5/tests/test_pcie_decode_cycle_kernel.py'


def inputs():
    if audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen assignment kernel changed')
    parent=json.loads((BASE/'manifest.json').read_text())
    pins=parent['inputs_sha256']|parent['generated_sha256']|{str(BASE/'manifest.json'):BASE_SHA}
    for path in (Path(__file__).resolve(),Path(profile.__file__).resolve(),TEST,
        ROOT/'loader/rpi5/rp1_decode_cycle.c',ROOT/'loader/rpi5/rp1_decode_cycle.h',
        ROOT/'tools/rpi5/tests/test_rp1_decode_cycle.py',ROOT/'tools/rpi5/tests/rp1_decode_cycle_host.c',
        ROOT/'tools/rpi5/tests/test_rp1_decode_transport.py',
        ROOT/'iokit/Kernel/IOMemoryDescriptor.cpp',ROOT/'iokit/IOKit/IOMemoryDescriptor.h',
        ROOT/'build/rpi5/pcie-bars-assignment-serial-20261013/serial.bin'):
        digest=audit.sha(path)
        if str(path) in pins and pins[str(path)]!=digest:raise ValueError('Decode source conflict: '+str(path))
        pins[str(path)]=digest
    engine.verify(pins);return parent,parent,pins


def objects(output):
    original=[Path(p) for p in (BASE/'kernel.rp1-config.filelist').read_text().splitlines()]
    found=[p for p in original if p.name=='BCM2712PCIePHYTransport.cpp.o']
    if len(found)!=1 or len(original)!=len(set(original)) or any(p.name=='rp1_decode_cycle.c.o' for p in original):
        raise ValueError('Exact transport replacement plus new decode object required')
    changes={found[0]:output/found[0].name}
    return original,[changes.get(p,p) for p in original]+[output/'rp1_decode_cycle.c.o'],changes


def compile_args(parent,source):
    index=0 if source.suffix=='.cpp' else 1
    old=BASE/'overlay'/('BCM2712PCIePHYTransport.cpp' if not index else 'rp1_bars_assign.c')
    if index and source.name!='rp1_decode_cycle.c':raise ValueError('Unexpected decode source')
    command=parent['compiles'][index]['command']
    if command.count(str(old))!=1:raise ValueError('Exact ancestor compile changed')
    stop=command.index('-MD') if '-MD' in command else command.index('-o')
    return [str(source) if a==str(old) else a for a in command[:stop]]


def contract():
    return dict(same_boot_actual_assignment_required=True,exact_current_owner_thread_phase_required=True,
        existing_transport_guards_unchanged=True,firmware_owner_client_secure_objects_unchanged=True,
        config_transfer_bound=34,command_write_bound=2,command_write_width=16,command_changed_bits=2,
        live_header_and_all_six_bars_rechecked=True,status_register_never_written=True,
        map_count=2,unmap_count=2,unmap_order=['clocks','gem'],
        map_ranges=[[0x1f00100000,0x1f00104000],[0x1f00018000,0x1f0002c000]],
        immutable_device_type_required=True,fresh_unshared_host_only_descriptor=True,
        exact_original_map_backing_identity_required=True,mapper_none=True,cache_inhibited=True,
        unique_static_reference_mapping_refused=True,exact_physical_and_virtual_geometry_checked=True,
        endpoint_memory_decode_temporarily_enabled=True,original_command_restored_before_bars=True,
        same_boot_all_bar_restore_required=True,quarantined_failure_no_cleanup=True,retry=False,
        endpoint_register_access=False,clock_reset_writes=False,bus_master_enabled=False,
        irq_delivery_enabled=False,dma_enabled=False,ethernet_proven=False,
        deadlines_and_cumulative_limits_unchanged=True,native_modeled_pm_checks=61532,
        native_modeled_firmware_sequence=15381,native_modeled_guards=7690,
        native_counts_are_not_board_timing_or_future_budget_guarantee=True)


def build(output):
    b=private.load_private(Path(engine.__file__).resolve(),'_decode_cycle_kernel_engine')
    b.BASE=BASE;b.BASE_SHA=BASE_SHA;b.PROFILE=PROFILE;b.TEST=TEST;b.profile=profile
    b.inputs=inputs;b.objects=objects;b.compile_args=compile_args
    result=b.build(output);changes=result.pop('elapsed_object_replacements')
    parent=json.loads((BASE/'manifest.json').read_text())
    for key in ('elapsed_object_replacements','link_trace_fields','link_trace_call_steps','link_trace_core_steps'):
        result[key]=parent[key]
    result.pop('hardware_failure_receipt',None)
    symbols=engine.base.full.symbols((output/'kernel.symbols').read_text())
    names=['_rpi5_rp1_decode_run','_rpi5_rp1_decode_write_allowed','_rpi5_rp1_decode_mapping_allowed']
    for name in names:
        if len(symbols.get(name,[]))!=1:raise ValueError('Missing exact decode implementation: '+name)
    assembly=(output/'BCM2712PCIePHYTransport.cpp.s').read_text()
    guard=re.search(r'^__ZN\d+BCM2712PCIePHYTransport5guardEv:[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.M|re.S)[1]
    calls=re.findall(r'\tbl\t(_pe_rpi5_\w+)',guard)
    if calls!=parent['guard_emitted_owner_calls']:raise ValueError('Fresh owner composition changed')
    actual=(output/'overlay/BCM2712PCIeIDTrialProgress.inc').read_text()
    formats=re.findall(r'kprintf\("([^"\n]+)"',actual)
    if len(formats)!=25 or not formats[-1].startswith('RPI5XNU:PCIEID:END '):raise ValueError('Exact25 bounded records required')
    raw=(output/'kernel.rp1-config').read_bytes()
    for fmt in formats:
        if raw.count(fmt.replace('\\n','\n').encode()+b'\0')!=1:raise ValueError('Exact decode logging row missing')
    before,after,_=objects(output)
    result.update(decode_contract=contract(),decode_object_replacements=changes,
        decode_added_objects=[str(output/'rp1_decode_cycle.c.o')],decode_required_implementations=names,
        decode_record_formats=[fmt.replace('\\n','\n') for fmt in formats],
        unchanged_parent_objects=len(before)-1,guard_emitted_owner_calls=calls,
        controller_caller_unchanged=False,passive_trace_unchanged=False,
        owner_client_core_secure_objects_unchanged=True,
        bar_memory_decode_enabled=True,bar_mmio_mapped=True,command_writes=True,
        endpoint_register_access=False,logging_calls=25,logging_max_scalar_arguments=15,
        physical_assignment_capture_sha256=audit.sha(ROOT/'build/rpi5/pcie-bars-assignment-serial-20261013/serial.bin'),
        assignment_contract_scope='Retained predecessor stage only; decode_contract governs inserted new phase',
        physical_success_proven=False,physical_trial_admitted=False,
        required_next_evidence='Clean25-record same-boot MEM-only Device-map/revoke/COMMAND and BAR restore plus independent Linux recovery',
        trial_scope='Repeat exact size/assign; temporary MEM-only decode, two private host-only Device maps, revoke, restore COMMAND and BARs; no endpoint register access, BME, DMA or IRQ')
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True)
    m=build(parser.parse_args().output_dir.resolve())
    print(json.dumps({key:m[key] for key in ('profile','kernel','kernel_sha256','kernel_bytes')}))
