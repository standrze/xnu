#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Isolated GPIO32 reset + fresh bounded C22 reader, unchanged owner ceiling."""
import argparse
import json
from pathlib import Path
import re
from tools.rpi5 import build_pcie_phy_gpio_kernel as prior
from tools.rpi5 import pcie_phy_reset_trace_profile as profile
ROOT,audit,engine,private=prior.ROOT,prior.audit,prior.engine,prior.private
BASE=profile.FROZEN.parent
BASE_SHA='f21c594fe01371c85b2957988fac679b1d19dbad52231584996868def48724d1'
PROFILE='pcie-phy-reset-timed-mdio-kernel-v1'
TEST=ROOT/'tools/rpi5/tests/test_pcie_phy_reset_kernel.py'


def contract():
    return dict(fresh_original_fdt_gpio32_active_low_5ms_required=True,
        actual_no_aspm_halfword_read_offset=0xbc,no_aspm_mask=0x103,
        sole_pre_iokit_cpu_and_owner_thread_required=True,competing_root_config_writers_excluded_by_owner=True,
        no_historical_reset_state_authority=True,gpio_page_offsets=[0xd4000,0xe4000,0xf4000],
        exact_inherited_device_map_identity_and_extent=True,three_maps_then_one_action_then_reverse_revoke=True,
        duplicate_raw_gpio_observer_reads_removed=True,
        ctrl_known_mask=0xf09f,filter_encodings_admitted=[0,0x80],filter_preserved_all_writes=True,
        irq_inputoverride_reserved_and_reset_ctrl_bits_refused=True,pad_known_rw_mask=0xff,
        rio_alias_write_values=[0x10],rio_alias_offsets=[0x2000,0x3000,0x2004,0x3004],
        gpio_initial_inte_pin_bit_refused=0x10,reset_window_us=40000,assert_min_us=5000,
        assert_wait_max_us=6000,max_delay_chunks=5,max_chunk_us=1000,
        gpio_success_reads=19,gpio_write_limit=12,original_gpio_fields_exactly_restored=True,
        inherited_original_gpio_restore_may_reassert_reset=True,
        fresh_c22_register_reads=[2,3,0,1,1],fresh_mid_and_capabilities_required=True,
        mdiopolls=32,mdio_deadline_us=20000,mdio_max_reads=46,mdio_max_writes=9,mdio_guarded_time_callbacks=2,
        every_actual_mmio_retains_fresh_pre_and_post_owner_guards=True,
        monotonic_timestamps_inside_access_owner_envelope=True,expired_writes_rejected_before_side_effect=True,
        post_access_failure_does_not_claim_no_side_effect=True,inner_completion_not_outer_acceptance=True,
        any_failure_quarantines_without_cleanup_retry_or_forced_restore=True,
        no_mdio_phy_writes_advertisement_dma_irq_packet_activation=True,
        pm_limit_unchanged=65536,native32poll_fixture_pm_checks=65244,native32poll_fixture_firmware_sequence=16309,
        native32poll_fixture_guards=8154,native32poll_fixture_headroom=292,
        native_counts_not_all_possible_board_timings=True,guards_may_fail_closed_if_finite_budget_exhausted=True,
        primary_gpio_sources=json.loads((ROOT/'tools/rpi5/rp1_phy_gpio_sources.json').read_text()),
        primary_mdio_sources=json.loads((ROOT/'tools/rpi5/rp1_gem_mdio_sources.json').read_text()))


def inputs():
    if audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen GPIO kernel changed')
    parent=json.loads((BASE/'manifest.json').read_text())
    mdio=profile.core.timed.FROZEN.parent;mdio_sha='67d614b3324db922eb8d155236155002851f2096a78df583f94d009040ddafd1'
    if audit.sha(mdio/'manifest.json')!=mdio_sha:raise ValueError('Frozen corrected MDIO source changed')
    old=json.loads((mdio/'manifest.json').read_text())
    pins=parent['inputs_sha256']|parent['generated_sha256']|{str(BASE/'manifest.json'):BASE_SHA}
    additions=old['inputs_sha256']|old['generated_sha256']|{str(mdio/'manifest.json'):mdio_sha}
    paths=[Path(__file__).resolve(),Path(profile.__file__).resolve(),Path(profile.core.__file__).resolve(),TEST,
        Path(profile.core.timed.__file__).resolve(),Path(prior.__file__).resolve(),
        ROOT/'loader/rpi5/rp1_phy_reset_cycle.c',ROOT/'loader/rpi5/rp1_phy_reset_cycle.h',
        ROOT/'tools/rpi5/tests/test_rp1_phy_reset_cycle.py',ROOT/'tools/rpi5/tests/rp1_phy_reset_cycle_host.c',
        ROOT/'tools/rpi5/tests/test_rp1_gem_mdio_timed.py',ROOT/'tools/rpi5/tests/test_rp1_phy_reset_transport.py']
    for path in paths:additions[str(path)]=audit.sha(path)
    for path,value in additions.items():
        if path in pins and pins[path]!=value:raise ValueError('Reset dependency conflict: '+path)
        pins[path]=value
    engine.verify(pins);return parent,parent,pins


def objects(output):
    original=[Path(v) for v in (BASE/'kernel.rp1-config.filelist').read_text().splitlines()]
    if len(original)!=len(set(original)):raise ValueError('Duplicate original object')
    delta={}
    for name in ('BCM2712PCIePHYTransport.cpp.o','rp1_phy_gpio_observe.c.o'):
        found=[p for p in original if p.name==name]
        if len(found)!=1:raise ValueError('Exact reset transport/map-holder replacements required')
        delta[found[0]]=output/name
    extra=[output/(n+'.c.o') for n in ('rp1_gem_mdio','rp1_phy_reset_cycle')]
    if any(p.name==q.name for p in original for q in extra):raise ValueError('Reset core already linked')
    return original,[delta.get(p,p) for p in original]+extra,delta


def compile_args(parent,source):
    original,_,_=objects(source.parent.parent)
    name='BCM2712PCIePHYTransport.cpp' if source.suffix=='.cpp' else 'rp1_gem_capabilities.c'
    owner=next(p.parent for p in original if p.name==name+'.o');old=owner/'overlay'/name
    rows=[r['command'] for r in json.loads((owner/'manifest.json').read_text())['compiles'] if str(old) in r['command']]
    if len(rows)!=1:raise ValueError('Exact previous compile command required')
    args=rows[0];stop=args.index('-MD') if '-MD' in args else args.index('-o')
    return [str(source) if a==str(old) else a for a in args[:stop]]


def build(output):
    b=private.load_private(Path(engine.__file__).resolve(),'_phy_reset_kernel_engine')
    for name in ('BASE','BASE_SHA','PROFILE','TEST','profile','inputs','objects','compile_args'):setattr(b,name,globals()[name])
    result=b.build(output);delta=result.pop('elapsed_object_replacements');parent=json.loads((BASE/'manifest.json').read_text())
    result['elapsed_object_replacements']=parent['elapsed_object_replacements'];result.pop('hardware_failure_receipt',None)
    assembly=(output/'BCM2712PCIePHYTransport.cpp.s').read_text()
    guard=re.search(r'^__ZN\d+BCM2712PCIePHYTransport5guardEv:[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.M|re.S)[1]
    calls=re.findall(r'\tbl\t(_pe_rpi5_\w+)',guard)
    if calls!=parent['guard_emitted_owner_calls']:raise ValueError('Actual owner guard changed')
    formats=re.findall(r'kprintf\("([^"\n]+)"',(output/'overlay/BCM2712PCIeIDTrialProgress.inc').read_text())
    if len(formats)!=59 or not formats[-1].startswith('RPI5XNU:PCIEID:END '):raise ValueError('59 bounded records required')
    raw=(output/'kernel.rp1-config').read_bytes()
    for fmt in formats:
        if raw.count(fmt.replace('\\n','\n').encode()+b'\0')!=1:raise ValueError('Unique reset trace required')
    symbols=engine.base.full.symbols((output/'kernel.symbols').read_text())
    for name in ('_rpi5_phy_gpio_action_run','_rpi5_phy_reset_run','_rpi5_gem_mdio_run',
        '_rpi5_phy_reset_read_allowed','_rpi5_phy_reset_write_allowed','_rpi5_phy_gpio_fdt'):
        if len(symbols.get(name,[]))!=1:raise ValueError('Unique reset/MDIO/map-holder implementation required')
    if symbols.get('_rpi5_phy_gpio_run') or symbols.get('_rpi5_phy_gpio_read_allowed'):raise ValueError('Old observer implementation remained')
    result.update(reset_contract=contract(),reset_object_replacements=delta,
        reset_added_objects=[str(output/(n+'.c.o')) for n in ('rp1_gem_mdio','rp1_phy_reset_cycle')],
        reset_record_formats=[s.replace('\\n','\n') for s in formats],predecessor_gpio_manifest_sha256=BASE_SHA,
        gpio_contract_scope='Historical read-only observer predecessor only; replaced by distinct held-map reset action',
        gpio_object_replacements_scope='Historical predecessor delta, not this link',
        gpio_added_objects_scope='Historical predecessor object replaced in this link',
        prior_component_contracts_scoped_not_whole_trial=True,transport_object_unchanged=False,
        owner_client_core_secure_objects_unchanged=True,guard_emitted_owner_calls=calls,
        logging_calls=59,total_endpoint_read_bound=113,total_endpoint_write_bound=21,
        unchanged_parent_objects=len(objects(output)[0])-2,physical_success_proven=False,physical_trial_admitted=False,
        trial_scope='Bounded GPIO32 reset plus fresh C22 ID/control/status reads, then exact GPIO/GEM/maps/root/BAR restore; no packets')
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True)
    r=build(p.parse_args().output_dir.resolve());print(json.dumps({k:r[k] for k in ('profile','kernel','kernel_sha256','kernel_bytes')}))
