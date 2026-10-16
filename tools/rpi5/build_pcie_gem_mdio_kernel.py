#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct one-transport plus C22 core successor; no hardware or policy lift."""
import argparse
import json
from pathlib import Path
import re
from tools.rpi5 import build_pcie_gem_capabilities_kernel as prior
from tools.rpi5 import pcie_gem_mdio_trace_profile as profile
ROOT,audit,engine,private=prior.ROOT,prior.audit,prior.engine,prior.private
BASE=profile.FROZEN.parent
BASE_SHA='3f39456cf2d6d4b9fa7b3586b54558564addc0b25b1cdcd69c1846107f582b3e'
PROFILE='pcie-held-device-gem-c22-mdio-kernel-v1'
TEST=ROOT/'tools/rpi5/tests/test_pcie_gem_mdio_kernel.py'


def contract():
    return dict(register_offsets=[0,4,8,0x34],clause22_phy_reads=[2,3,0,1,1],phy_address=1,
        fdt_mode='rgmii-id',fresh_original_fdt_reparsed_then_exact_semantic_binding=True,
        private_fdt_object_bytes_and_length_retained_every_callback=True,
        same_boot_caps_complete_and_mid_00070109_required=True,
        selected_source_200MHz_not_independently_measured=True,
        divider_field=[18,3],unsafe_divider_codes=[0,1,2,3,4],replacement_divider_code=5,
        inherited_safe_dividers=[5,6,7],mdc_divisor=96,mdc_max_hz_baseline=2500000,
        ncr_preserved_known_rw_mask=0x11180000,ncr_temporary_set_mask=0x10,
        all_unknown_ncr_command_loopback_rx_tx_mpe_initial_bits_refused=True,
        ncfgr_configuration_rmw_preserves_all_non_clk_bits=True,
        exact_config_readbacks_and_restoration_required=True,
        no_phy_write_reset_advertisement_clockcontroller_packet_dma_irq=True,
        management_deadline_us=20000,total_nsr_poll_limit=32,read_limit=46,write_limit=9,clock_limit=57,
        callbacks_have_current_source_pre_post=True,actual_data_and_time_callbacks_keep_two_fresh_firmware_guards=True,
        any_failure_quarantines_without_compensating_io_or_retry=True,
        original_pre_post_clocks_maps_bars_root_restore_remain_required=True,
        parent_output_commits_only_after_complete_restoration=True,
        unchanged_pm_limit=65536,native_modeled_pm_checks=65420,native_modeled_firmware_sequence=16353,
        native_modeled_guards=8176,native_budget_headroom=116,
        native_counts_for_explicit_complete_32poll_fixture_not_all_possible_board_timings=True,
        retained_watchdog_seconds=[9,10,12,15],phy_link_up_not_required=True,
        primary_sources=json.loads((ROOT/'tools/rpi5/rp1_gem_mdio_sources.json').read_text()))


def inputs():
    if audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen capabilities kernel changed')
    parent=json.loads((BASE/'manifest.json').read_text())
    pins=parent['inputs_sha256']|parent['generated_sha256']|{str(BASE/'manifest.json'):BASE_SHA}
    paths=[Path(__file__).resolve(),Path(profile.__file__).resolve(),Path(profile.core.__file__).resolve(),TEST,
        ROOT/'loader/rpi5/rp1_gem_mdio.c',ROOT/'loader/rpi5/rp1_gem_mdio.h',
        ROOT/'tools/rpi5/tests/test_rp1_gem_mdio.py',ROOT/'tools/rpi5/tests/rp1_gem_mdio_host.c',
        ROOT/'tools/rpi5/rp1_gem_mdio_sources.json']
    for path in paths:
        value=audit.sha(path)
        if str(path) in pins and pins[str(path)]!=value:raise ValueError('MDIO input conflict')
        pins[str(path)]=value
    for row in contract()['primary_sources']['sources']:
        path=ROOT/row['path']
        if audit.sha(path)!=row['sha256'] or path.stat().st_size!=row['bytes']:raise ValueError('MDIO primary bytes changed')
        pins[str(path)]=row['sha256']
    engine.verify(pins);return parent,parent,pins


def objects(output):
    original=[Path(v) for v in (BASE/'kernel.rp1-config.filelist').read_text().splitlines()]
    found=[p for p in original if p.name=='BCM2712PCIePHYTransport.cpp.o']
    if len(found)!=1 or len(original)!=len(set(original)) or any(p.name=='rp1_gem_mdio.c.o' for p in original):
        raise ValueError('Exactly one old transport and fresh MDIO core required')
    delta={found[0]:output/found[0].name}
    return original,[delta.get(p,p) for p in original]+[output/'rp1_gem_mdio.c.o'],delta


def compile_args(parent,source):
    original,_,_=objects(source.parent.parent)
    name='BCM2712PCIePHYTransport.cpp' if source.suffix=='.cpp' else 'rp1_gem_capabilities.c'
    owner=next(p.parent for p in original if p.name==name+'.o');old=owner/'overlay'/name
    rows=[r['command'] for r in json.loads((owner/'manifest.json').read_text())['compiles'] if str(old) in r['command']]
    if len(rows)!=1:raise ValueError('Exact previous compiler invocation required')
    args=rows[0];stop=args.index('-MD') if '-MD' in args else args.index('-o')
    return [str(source) if a==str(old) else a for a in args[:stop]]


def build(output):
    b=private.load_private(Path(engine.__file__).resolve(),'_gem_mdio_kernel_engine')
    for name in ('BASE','BASE_SHA','PROFILE','TEST','profile','inputs','objects','compile_args'):setattr(b,name,globals()[name])
    result=b.build(output);delta=result.pop('elapsed_object_replacements')
    parent=json.loads((BASE/'manifest.json').read_text());result['elapsed_object_replacements']=parent['elapsed_object_replacements']
    result.pop('hardware_failure_receipt',None)
    assembly=(output/'BCM2712PCIePHYTransport.cpp.s').read_text()
    guard=re.search(r'^__ZN\d+BCM2712PCIePHYTransport5guardEv:[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.M|re.S)[1]
    calls=re.findall(r'\tbl\t(_pe_rpi5_\w+)',guard)
    if calls!=parent['guard_emitted_owner_calls']:raise ValueError('Owner guard composition changed')
    formats=re.findall(r'kprintf\("([^"\n]+)"',(output/'overlay/BCM2712PCIeIDTrialProgress.inc').read_text())
    if len(formats)!=53 or not formats[-1].startswith('RPI5XNU:PCIEID:END '):raise ValueError('53 bounded records required')
    raw=(output/'kernel.rp1-config').read_bytes()
    for fmt in formats:
        if raw.count(fmt.replace('\\n','\n').encode()+b'\0')!=1:raise ValueError('Unique linked MDIO trace required')
    symbols=engine.base.full.symbols((output/'kernel.symbols').read_text())
    for name in ('_rpi5_gem_mdio_run','_rpi5_gem_mdio_read_allowed','_rpi5_gem_mdio_write_allowed',
        '_rpi5_gem_mdio_clock_allowed','_rpi5_gem_mdio_binding_equal','_rpi5_fdt_pcie_rp1'):
        if len(symbols.get(name,[]))!=1:raise ValueError('Unique MDIO/FDT implementation required')
    result.update(mdio_contract=contract(),mdio_object_replacements=delta,mdio_added_objects=[str(output/'rp1_gem_mdio.c.o')],
        mdio_record_formats=[s.replace('\\n','\n') for s in formats],predecessor_capabilities_manifest_sha256=BASE_SHA,
        capabilities_contract_scope='Preserved capability component; mdio_contract adds bounded management writes afterward',
        capabilities_object_replacements_scope='Historical capabilities predecessor delta, not this link',
        capabilities_added_objects_scope='Historical capabilities predecessor objects, not new additions',
        prior_component_contracts_scoped_not_whole_trial=True,transport_object_unchanged=False,
        gem_and_decode_core_objects_unchanged=True,decode_core_unchanged=True,controller_caller_unchanged=False,
        passive_trace_unchanged=False,owner_client_core_secure_objects_unchanged=True,guard_emitted_owner_calls=calls,
        logging_calls=53,total_endpoint_read_bound=94,total_endpoint_write_bound=9,
        unchanged_parent_objects=len(objects(output)[0])-1,physical_success_proven=False,physical_trial_admitted=False,
        trial_scope='C22 ID/control/basic status reads and exact temporary management config restore; no packet driver')
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True)
    r=build(p.parse_args().output_dir.resolve());print(json.dumps({k:r[k] for k in ('profile','kernel','kernel_sha256','kernel_bytes')}))
