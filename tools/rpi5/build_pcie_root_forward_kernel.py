#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Root-bridge MEM-only forwarding/window cycle around unchanged GEM reads."""
import argparse
import json
from pathlib import Path
import re
from tools.rpi5 import build_pcie_gem_known_kernel as prior
from tools.rpi5 import pcie_root_forward_profile as profile
ROOT,audit,engine,private=prior.ROOT,prior.audit,prior.engine,prior.private
BASE=profile.FROZEN.parent
BASE_SHA='090697cffdd4fb1604ae9fadef792e04261b565b756b6bdbccb984aacb13a624'
PROFILE='pcie-root-mem-forwarding-around-gem-kernel-v1'
TEST=ROOT/'tools/rpi5/tests/test_pcie_root_forward_kernel.py'
REFERENCE=ROOT/'build/rpi5/root-forward-primary-80d4218'
REVISION='80d4218cb877ccb07d09a9f21f0678e78d8b36f5'
REFERENCE_ROWS=(
    ('setup-bus.c','drivers/pci/setup-bus.c','7e47c40e3878f794a6eb89de64ab7d0970fd7f461bffdaa92b888d8733d9f900','pci_setup_bridge_mmio'),
    ('setup-res.c','drivers/pci/setup-res.c','ce6853d72eacd5c47374bcea1bd40cf11e814759605aaeb5fd5b63213a80bbef','pci_enable_resources'),
    ('pci.c','drivers/pci/pci.c','5764e746194f2144911f006f1c491ad976494ce0c724f8f06d24402f37277761','pci_enable_bridge'),
    ('pcie-brcmstb.c','drivers/pci/controller/pcie-brcmstb.c','212ec09ab522c2e7b81638be3db833bb7e3ad62b201a08f9858092f6130ec787','brcm_pcie_map_bus'),
    ('pci_regs.h','include/uapi/linux/pci_regs.h','2c366db9fca301457193d5f2782500243f30cde8ba2f32c1087a21433701f512','PCI_MEMORY_RANGE_MASK'))


def references():
    result=[]
    for name,upstream,digest,symbol in REFERENCE_ROWS:
        path=REFERENCE/name
        if audit.sha(path)!=digest or symbol not in path.read_text():raise ValueError('Pinned primary source changed: '+name)
        result.append(dict(path=str(path),sha256=digest,symbol=symbol,
            url='https://raw.githubusercontent.com/raspberrypi/linux/'+REVISION+'/'+upstream,
            scope='Read-only primary reference; not compiled or a hardware observation'))
    return result


def inputs():
    if audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen GEM kernel changed')
    parent=json.loads((BASE/'manifest.json').read_text())
    pins=parent['inputs_sha256']|parent['generated_sha256']|{str(BASE/'manifest.json'):BASE_SHA}
    for reference in references():pins[reference['path']]=reference['sha256']
    for path in (Path(__file__).resolve(),Path(profile.__file__).resolve(),TEST,
        ROOT/'loader/rpi5/pcie_root_forward.c',ROOT/'loader/rpi5/pcie_root_forward.h',
        ROOT/'tools/rpi5/tests/test_pcie_root_forward.py',ROOT/'tools/rpi5/tests/pcie_root_forward_host.c',
        ROOT/'tools/rpi5/tests/test_pcie_root_forward_transport.py',
        ROOT/'build/rpi5/pcie-gem-identify-serial-20261013/serial.bin'):
        value=audit.sha(path)
        if str(path) in pins and pins[str(path)]!=value:raise ValueError('Root-forward source conflict: '+str(path))
        pins[str(path)]=value
    engine.verify(pins);return parent,parent,pins


def objects(output):
    original=[Path(v) for v in (BASE/'kernel.rp1-config.filelist').read_text().splitlines()]
    found=[p for p in original if p.name=='BCM2712PCIePHYTransport.cpp.o']
    if len(found)!=1 or len(original)!=len(set(original)) or any(p.name=='pcie_root_forward.c.o' for p in original):
        raise ValueError('Exact one transport replacement plus new root-forwarding core required')
    changes={found[0]:output/found[0].name}
    return original,[changes.get(p,p) for p in original]+[output/'pcie_root_forward.c.o'],changes


def compile_args(parent,source):
    index=0 if source.suffix=='.cpp' else 2
    old=BASE/'overlay'/('BCM2712PCIePHYTransport.cpp' if not index else 'rp1_gem_identify.c')
    if index and source.name!='pcie_root_forward.c':raise ValueError('Unexpected root-forward source')
    command=parent['compiles'][index]['command']
    if command.count(str(old))!=1:raise ValueError('Exact parent compile changed')
    stop=command.index('-MD') if '-MD' in command else command.index('-o')
    return [str(source) if a==str(old) else a for a in command[:stop]]


def contract():
    return dict(same_boot_actual_assignment_and_held_device_maps=True,fresh_exact_owner_thread_phase_required=True,
        direct_root_registers_not_endpoint_ecam=True,root_identity=0x271214e4,root_header_type=1,root_bus_route=0x10100,
        initial_root_io_mem_bme_clear=True,root_command_offset=4,root_command_write_width=16,
        root_command_changed_bits=2,status_w1c_never_written=True,root_window_offset=0x20,root_window_write_width=32,
        window_granularity=0x100000,minimal_window_covers_all_live_assigned_bars=True,root_window_encoding_mask=0xfff0fff0,
        all_ten_outbound_registers_exact_before_live_after=True,root_read_bound=79,root_write_bound=4,
        root_config_before_live_after_qualified=True,readback_after_every_write=True,
        existing_gem_clock_and_mid_core_unchanged=True,gem_callback_only_while_root_forwarding_live=True,
        root_original_command_and_window_restored_before_endpoint_unmap=True,
        all_original_endpoint_command_and_bars_restored_on_success=True,
        failure_quarantined_without_compensation_or_retry=True,output_unchanged_on_failure=True,
        existing_owner_client_secure_objects_guards_limits_deadlines_unchanged=True,
        no_io_bme_dma_irq_or_clock_reset_phy_writes=True,endpoint_register_writes=False,ethernet_proven=False,
        native_modeled_pm_checks=63372,native_modeled_firmware_sequence=15841,native_modeled_guards=7920,
        native_counts_not_board_timing_or_cause_proof=True,
        primary_source_revision='raspberrypi/linux@80d4218cb877ccb07d09a9f21f0678e78d8b36f5')


def build(output):
    b=private.load_private(Path(engine.__file__).resolve(),'_root_forward_kernel_engine')
    b.BASE=BASE;b.BASE_SHA=BASE_SHA;b.PROFILE=PROFILE;b.TEST=TEST;b.profile=profile
    b.inputs=inputs;b.objects=objects;b.compile_args=compile_args
    result=b.build(output);changes=result.pop('elapsed_object_replacements')
    parent=json.loads((BASE/'manifest.json').read_text())
    for name in ('elapsed_object_replacements','link_trace_fields','link_trace_call_steps','link_trace_core_steps'):
        result[name]=parent[name]
    result.pop('hardware_failure_receipt',None)
    symbols=engine.base.full.symbols((output/'kernel.symbols').read_text())
    required=['_rpi5_root_forward_run','_rpi5_root_forward_access_allowed']
    for name in required:
        if len(symbols.get(name,[]))!=1:raise ValueError('Missing exact root-forward implementation: '+name)
    assembly=(output/'BCM2712PCIePHYTransport.cpp.s').read_text()
    guard=re.search(r'^__ZN\d+BCM2712PCIePHYTransport5guardEv:[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.M|re.S)[1]
    calls=re.findall(r'\tbl\t(_pe_rpi5_\w+)',guard)
    if calls!=parent['guard_emitted_owner_calls']:raise ValueError('Fresh owner composition changed')
    formats=re.findall(r'kprintf\("([^"\n]+)"',(output/'overlay/BCM2712PCIeIDTrialProgress.inc').read_text())
    if len(formats)!=42 or not formats[-1].startswith('RPI5XNU:PCIEID:END '):raise ValueError('Exact42 bounded records required')
    raw=(output/'kernel.rp1-config').read_bytes()
    for fmt in formats:
        if raw.count(fmt.replace('\\n','\n').encode()+b'\0')!=1:raise ValueError('Exact root-forward row missing')
    original,current,_=objects(output)
    result.update(root_forward_contract=contract(),root_forward_object_replacements=changes,
        root_forward_added_objects=[str(output/'pcie_root_forward.c.o')],root_forward_required_implementations=required,
        root_forward_record_formats=[fmt.replace('\\n','\n') for fmt in formats],primary_source_references=references(),
        predecessor_gem_object_replacements=parent['gem_object_replacements'],
        predecessor_gem_added_objects=parent['gem_added_objects'],
        predecessor_gem_contract=parent['gem_contract'],predecessor_contracts_scoped_not_whole_trial=True,
        unchanged_parent_objects=len(original)-1,guard_emitted_owner_calls=calls,
        owner_client_core_secure_objects_unchanged=True,gem_and_decode_core_objects_unchanged=True,
        controller_caller_unchanged=False,passive_trace_unchanged=False,
        root_memory_forwarding_temporarily_enabled=True,root_window_temporarily_programmed=True,
        physical_gem_failure_capture_sha256=audit.sha(ROOT/'build/rpi5/pcie-gem-identify-serial-20261013/serial.bin'),
        physical_success_proven=False,physical_trial_admitted=False,logging_calls=42,
        required_next_evidence='Clean42rows root MEM/window before-live-after, repeated GEM/MID, map/endpoint/BAR restore and independent Linux return',
        trial_scope='Root MEM-only forwarding/window restoration around unchanged known-clock/MID reads; no BME, DMA, IRQ, clock, reset or PHY writes')
    # The newly linked delta is root_forward_*. Old GEM delta retains an
    # explicit predecessor name rather than masquerading as this link's delta.
    result.pop('gem_object_replacements',None);result.pop('gem_added_objects',None)
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True)
    result=build(parser.parse_args().output_dir.resolve())
    print(json.dumps({k:result[k] for k in ('profile','kernel','kernel_sha256','kernel_bytes')}))
