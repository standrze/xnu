#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct same-boot clock-state/GEM MID read-only kernel, no clock writes."""
import argparse
import json
from pathlib import Path
import re
from tools.rpi5 import build_pcie_decode_cycle_kernel as prior
from tools.rpi5 import rp1_gem_identify_profile as profile
ROOT,audit,engine,private=prior.ROOT,prior.audit,prior.engine,prior.private
BASE=profile.FROZEN.parent
BASE_SHA='4742e761b800d7ffc68cb0a5683cfd3f315a890390fb1c10b1333b8259302468'
PROFILE='pcie-held-mapping-clock-gem-mid-kernel-v1'
TEST=ROOT/'tools/rpi5/tests/test_pcie_gem_identify_kernel.py'


def inputs():
    if audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen decode kernel changed')
    parent=json.loads((BASE/'manifest.json').read_text())
    pins=parent['inputs_sha256']|parent['generated_sha256']|{str(BASE/'manifest.json'):BASE_SHA}
    for path in (Path(__file__).resolve(),Path(profile.__file__).resolve(),TEST,
        ROOT/'loader/rpi5/rp1_gem_identify.c',ROOT/'loader/rpi5/rp1_gem_identify.h',
        ROOT/'tools/rpi5/tests/test_rp1_gem_identify.py',ROOT/'tools/rpi5/tests/rp1_gem_identify_host.c',
        ROOT/'tools/rpi5/tests/test_rp1_gem_transport.py',
        ROOT/'build/rpi5/pcie-decode-cycle-serial-20261013/serial.bin'):
        digest=audit.sha(path)
        if str(path) in pins and pins[str(path)]!=digest:raise ValueError('GEM source conflict: '+str(path))
        pins[str(path)]=digest
    engine.verify(pins);return parent,parent,pins


def objects(output):
    original=[Path(p) for p in (BASE/'kernel.rp1-config.filelist').read_text().splitlines()]
    names=('BCM2712PCIePHYTransport.cpp.o','rp1_decode_cycle.c.o')
    found=[p for p in original if p.name in names]
    if len(found)!=2 or len({p.name for p in found})!=2 or len(original)!=len(set(original)) or any(p.name=='rp1_gem_identify.c.o' for p in original):
        raise ValueError('Exact transport/decode replacements and new GEM core required')
    changes={p:output/p.name for p in found}
    return original,[changes.get(p,p) for p in original]+[output/'rp1_gem_identify.c.o'],changes


def compile_args(parent,source):
    index=0 if source.suffix=='.cpp' else 1
    old=BASE/'overlay'/('BCM2712PCIePHYTransport.cpp' if not index else 'rp1_decode_cycle.c')
    if index and source.name not in ('rp1_decode_cycle.c','rp1_gem_identify.c'):raise ValueError('Unexpected GEM source')
    command=parent['compiles'][index]['command']
    if command.count(str(old))!=1:raise ValueError('Exact ancestor compile changed')
    stop=command.index('-MD') if '-MD' in command else command.index('-o')
    return [str(source) if a==str(old) else a for a in command[:stop]]


def contract():
    return dict(same_boot_live_decode_mapped_required=True,exact_owner_thread_phase_maps_required=True,
        existing_guards_owners_clients_and_deadlines_unchanged=True,
        fresh_pre_and_post_guard_every_endpoint_read=True,clock_word_count=15,endpoint_read_bound=32,
        clock_offsets=[0x14,0x18,0x20,0x8000,0x8004,0x8008,0x800c,0x8010,0x64,0x68,0x70,0x134,0x138,0x140,0x8014],
        gem_offsets=[0xfc],read_width=32,read_endianness='little',mid_reads=2,clock_snapshot_reads=2,
        known_inherited_clock_profile_only=True,xosc_hz=50000000,system_hz=200000000,
        tx_hz=125000000,tsu_hz=50000000,pll_integer_feedback=[20,40],
        before_after_clocks_identical_required=True,mid_identical_and_gem_id_required=True,
        clock_reset_ncr_phy_register_writes=False,endpoint_register_writes=False,
        bme_dma_irq_activation=False,ethernet_proven=False,physical_clock_measurement_claimed=False,
        all_maps_command_bars_restored_on_success=True,no_cleanup_or_retry_after_failure=True,
        native_modeled_pm_checks=62044,native_modeled_firmware_sequence=15509,native_modeled_guards=7754,
        native_counts_are_not_board_timing_or_future_guarantees=True,
        primary_source_revision='raspberrypi/linux@80d4218cb877ccb07d09a9f21f0678e78d8b36f5',
        reset_scope='RP1 macb_init has no reset handler/property; no independent reset-state claim')


def build(output):
    b=private.load_private(Path(engine.__file__).resolve(),'_gem_identify_kernel_engine')
    b.BASE=BASE;b.BASE_SHA=BASE_SHA;b.PROFILE=PROFILE;b.TEST=TEST;b.profile=profile
    b.inputs=inputs;b.objects=objects;b.compile_args=compile_args
    result=b.build(output);changes=result.pop('elapsed_object_replacements')
    parent=json.loads((BASE/'manifest.json').read_text())
    for key in ('elapsed_object_replacements','link_trace_fields','link_trace_call_steps','link_trace_core_steps'):
        result[key]=parent[key]
    result.pop('hardware_failure_receipt',None)
    symbols=engine.base.full.symbols((output/'kernel.symbols').read_text())
    names=['_rpi5_gem_identify_run','_rpi5_gem_read_allowed','_rpi5_gem_clock_profile']
    for name in names:
        if len(symbols.get(name,[]))!=1:raise ValueError('Missing exact GEM implementation: '+name)
    assembly=(output/'BCM2712PCIePHYTransport.cpp.s').read_text()
    guard=re.search(r'^__ZN\d+BCM2712PCIePHYTransport5guardEv:[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.M|re.S)[1]
    calls=re.findall(r'\tbl\t(_pe_rpi5_\w+)',guard)
    if calls!=parent['guard_emitted_owner_calls']:raise ValueError('Fresh owner composition changed')
    formats=re.findall(r'kprintf\("([^"\n]+)"',(output/'overlay/BCM2712PCIeIDTrialProgress.inc').read_text())
    if len(formats)!=35 or not formats[-1].startswith('RPI5XNU:PCIEID:END '):raise ValueError('Exact35 bounded records required')
    raw=(output/'kernel.rp1-config').read_bytes()
    for fmt in formats:
        if raw.count(fmt.replace('\\n','\n').encode()+b'\0')!=1:raise ValueError('Exact GEM record missing')
    before,after,_=objects(output)
    result.update(gem_contract=contract(),gem_object_replacements=changes,
        gem_added_objects=[str(output/'rp1_gem_identify.c.o')],gem_required_implementations=names,
        gem_record_formats=[fmt.replace('\\n','\n') for fmt in formats],
        unchanged_parent_objects=len(before)-2,guard_emitted_owner_calls=calls,
        owner_client_core_secure_objects_unchanged=True,controller_caller_unchanged=False,passive_trace_unchanged=False,
        predecessor_decode_contract=parent['decode_contract'],
        predecessor_decode_contract_scope='Predecessor mapping phase; new gem_contract governs register reads inside held maps',
        bar_memory_decode_enabled=True,bar_mmio_mapped=True,command_writes=True,
        endpoint_register_access=True,endpoint_register_writes=False,logging_calls=35,logging_max_scalar_arguments=15,
        physical_decode_capture_sha256=audit.sha(ROOT/'build/rpi5/pcie-decode-cycle-serial-20261013/serial.bin'),
        physical_success_proven=False,physical_trial_admitted=False,
        required_next_evidence='Clean35-record exact clock/MID reads with maps/COMMAND/BAR restore and independent Linux recovery',
        trial_scope='Same-boot size/assign/MEM-map; inherited clocks, two MID reads, revoke/restore. No clock, reset, NCR, PHY, DMA or IRQ writes')
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True)
    m=build(parser.parse_args().output_dir.resolve())
    print(json.dumps({key:m[key] for key in ('profile','kernel','kernel_sha256','kernel_bytes')}))
