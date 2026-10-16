#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One transport plus GPIO32 read-only core; unchanged owner lifecycle/bounds."""
import argparse
import json
from pathlib import Path
import re
from tools.rpi5 import build_pcie_gem_mdio_kernel as prior
from tools.rpi5 import pcie_phy_gpio_trace_profile as profile
ROOT,audit,engine,private=prior.ROOT,prior.audit,prior.engine,prior.private
BASE=profile.FROZEN.parent
BASE_SHA=prior.BASE_SHA
PROFILE='pcie-phy-gpio32-read-only-kernel-v1'
TEST=ROOT/'tools/rpi5/tests/test_pcie_phy_gpio_kernel.py'
def contract():
    return dict(fresh_original_fdt_reset_binding=True,reset_pin=32,reset_active_low=True,declared_reset_ms=5,
        bar1_page_offsets=[0xd4000,0xe4000,0xf4000],page_size=0x4000,
        register_offsets=[[0,0x20],[0,0x24],[1,0],[1,4],[1,8],[2,0x14]],passes=2,read_limit=12,
        actual_apple_mapper_hostonly_nomapper_cacheinhibited=True,exact_mapping_identity_and_extent=True,
        maps=3,reverse_unmaps=3,raw_only_not_reset_or_phy_readiness=True,
        no_gpio_phy_mdio_clock_dma_irq_writes=True,no_gpio32_claim_or_reset_assertion=True,
        failures_quarantine_no_retry_no_compensating_io=True,
        independent_existing_owner_guards_before_after_every_real_callback=True,
        same_boot_caps_mid_clocks_maps_root_forward_and_assignment_required=True,
        original_post_clocks_and_root_bar_restore_required=True,
        native_model_pm_checks=63916,native_model_firmware_sequence=15977,native_model_guards=7988,
        modeled_counts_not_all_possible_board_timings=True,unchanged_pm_limit=65536,
        retained_watchdog_seconds=[9,10,12,15],
        primary_sources=json.loads((ROOT/'tools/rpi5/rp1_phy_gpio_sources.json').read_text()))
def inputs():
    if audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen capability kernel changed')
    parent=json.loads((BASE/'manifest.json').read_text());pins=parent['inputs_sha256']|parent['generated_sha256']|{str(BASE/'manifest.json'):BASE_SHA}
    paths=[Path(__file__).resolve(),Path(profile.__file__).resolve(),Path(profile.core.__file__).resolve(),TEST,
        Path(prior.__file__).resolve(),ROOT/'loader/rpi5/rp1_phy_gpio_observe.c',ROOT/'loader/rpi5/rp1_phy_gpio_observe.h',
        ROOT/'tools/rpi5/rp1_phy_gpio_sources.json',ROOT/'tools/rpi5/tests/test_rp1_phy_gpio_observe.py']
    for row in contract()['primary_sources']['sources']:
        path=ROOT/row['path']
        if audit.sha(path)!=row['sha256'] or path.stat().st_size!=row['bytes']:raise ValueError('GPIO primary bytes changed')
        paths.append(path)
    for path in paths:
        value=audit.sha(path)
        if str(path) in pins and pins[str(path)]!=value:raise ValueError('GPIO dependency conflict')
        pins[str(path)]=value
    engine.verify(pins);return parent,parent,pins
def objects(output):
    original=[Path(v) for v in (BASE/'kernel.rp1-config.filelist').read_text().splitlines()]
    found=[p for p in original if p.name=='BCM2712PCIePHYTransport.cpp.o']
    if len(found)!=1 or len(original)!=len(set(original)) or any(p.name=='rp1_phy_gpio_observe.c.o' for p in original):raise ValueError('Exact fresh object delta required')
    delta={found[0]:output/found[0].name}
    return original,[delta.get(p,p) for p in original]+[output/'rp1_phy_gpio_observe.c.o'],delta
compile_args=prior.compile_args
def build(output):
    b=private.load_private(Path(engine.__file__).resolve(),'_phy_gpio_kernel_engine')
    for name in ('BASE','BASE_SHA','PROFILE','TEST','profile','inputs','objects','compile_args'):setattr(b,name,globals()[name])
    result=b.build(output);delta=result.pop('elapsed_object_replacements');parent=json.loads((BASE/'manifest.json').read_text())
    result['elapsed_object_replacements']=parent['elapsed_object_replacements'];result.pop('hardware_failure_receipt',None)
    assembly=(output/'BCM2712PCIePHYTransport.cpp.s').read_text()
    guard=re.search(r'^__ZN\d+BCM2712PCIePHYTransport5guardEv:[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.M|re.S)[1]
    calls=re.findall(r'\tbl\t(_pe_rpi5_\w+)',guard)
    if calls!=parent['guard_emitted_owner_calls']:raise ValueError('Owner guard changed')
    formats=re.findall(r'kprintf\("([^"\n]+)"',(output/'overlay/BCM2712PCIeIDTrialProgress.inc').read_text())
    if len(formats)!=53 or not formats[-1].startswith('RPI5XNU:PCIEID:END '):raise ValueError('53 bounded records required')
    raw=(output/'kernel.rp1-config').read_bytes()
    for fmt in formats:
        if raw.count(fmt.replace('\\n','\n').encode()+b'\0')!=1:raise ValueError('Unique GPIO trace required')
    symbols=engine.base.full.symbols((output/'kernel.symbols').read_text())
    for name in ('_rpi5_phy_gpio_run','_rpi5_phy_gpio_read_allowed','_rpi5_phy_gpio_map_allowed','_rpi5_phy_gpio_fdt','_rpi5_phy_gpio_pcie_equal'):
        if len(symbols.get(name,[]))!=1:raise ValueError('Unique new GPIO implementation required')
    result.update(gpio_contract=contract(),gpio_object_replacements=delta,gpio_added_objects=[str(output/'rp1_phy_gpio_observe.c.o')],
        gpio_record_formats=[s.replace('\\n','\n') for s in formats],predecessor_capabilities_manifest_sha256=BASE_SHA,
        capabilities_contract_scope='Capability component retained; GPIO observer adds separate read-only pages afterward',
        capabilities_object_replacements_scope='Historical predecessor delta, not this link',
        capabilities_added_objects_scope='Historical predecessor objects, not new additions',
        prior_component_contracts_scoped_not_whole_trial=True,transport_object_unchanged=False,
        gem_and_decode_core_objects_unchanged=True,decode_core_unchanged=True,controller_caller_unchanged=False,
        passive_trace_unchanged=False,owner_client_core_secure_objects_unchanged=True,guard_emitted_owner_calls=calls,
        logging_calls=53,total_endpoint_read_bound=60,total_endpoint_write_bound=0,
        unchanged_parent_objects=len(objects(output)[0])-1,physical_success_proven=False,physical_trial_admitted=False,
        trial_scope='GPIO32 inherited state observation, no GPIO claim/setup/reset or PHY-readiness assertion')
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True)
    r=build(p.parse_args().output_dir.resolve());print(json.dumps({k:r[k] for k in ('profile','kernel','kernel_sha256','kernel_bytes')}))
