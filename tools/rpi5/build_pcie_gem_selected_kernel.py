#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One C object correction: narrow SYS selected-source register admission."""
import argparse
import json
from pathlib import Path
from tools.rpi5 import build_pcie_root_forward_kernel as prior
from tools.rpi5 import rp1_gem_selected_clock_profile as profile
ROOT,audit,engine,private=prior.ROOT,prior.audit,prior.engine,prior.private
BASE=profile.FROZEN.parent
BASE_SHA='7c09e045e6d04e33bb11d43a4875b4cc17333374858bcda8412c9be172ae6f45'
PROFILE='pcie-gem-sys-selected-register-profile-kernel-v1'
TEST=ROOT/'tools/rpi5/tests/test_pcie_gem_selected_kernel.py'
REFERENCE=ROOT/'build/rpi5/gem-clock-primary-80d4218-20261013/clk-rp1.c'
REFERENCE_SHA='49f4dd543187f0799b7a545b4a60680b1b2473f904de94e36b2e4e58b8e5aeaf'
CAPTURE=ROOT/'build/rpi5/pcie-root-forward-serial-20261013/serial.bin'
CAPTURE_SHA='e907497c3882c08ecf41de83aa58e6f7777731c6f81fcdf8d4ccc3af4867a265'


def contract():
    return dict(sys_ctrl_exact_values=[2,0x802],sys_selected_exact=4,
        sys_parent='PLL_SYS: parent index2 of three standard parents; SRC mask3',
        register_profile_admission_not_independent_clock_readiness=True,
        generic_upstream_is_on_still_tests_enable11=True,sys_bit11_reserved_or_always_on_claim=False,
        physical_frequency_or_gate_measurement=False,eth_tsu_predicates_unchanged=True,
        pll_predicates_and_exact_rational_rates_unchanged=True,
        all_register_offsets_read_counts_order_and_transport_guards_unchanged=True,
        same_boot_fresh_maps_and_exact_owner_thread_phase_required=True,
        entire_before_after_clock_snapshots_identical_required=True,endpoint_read_bound=32,
        no_clock_reset_phy_ncr_writes=True,bme_dma_irq_activation=False,
        unchanged_pm_limit=65536,native_modeled_pm_checks=63372,
        native_modeled_firmware_sequence=15841,native_modeled_guards=7920,
        native_counts_not_board_timing_or_future_guarantees=True,
        primary_source=dict(path=str(REFERENCE),sha256=REFERENCE_SHA,
            url='https://github.com/raspberrypi/linux/blob/80d4218cb877ccb07d09a9f21f0678e78d8b36f5/drivers/clk/clk-rp1.c',
            sections=['rp1_clock_get_parent','clk_sys_parents','clk_sys_desc','rp1_clock_is_on'],
            scope='Selected-source decode only; no complete per-bit SYS register table claimed'),
        prior_rejection_capture=dict(path=str(CAPTURE),sha256=CAPTURE_SHA,
            role='Historical observed register bytes and original rejection, never live authority'))


def inputs():
    if audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen root-forward kernel changed')
    parent=json.loads((BASE/'manifest.json').read_text())
    pins=parent['inputs_sha256']|parent['generated_sha256']|{str(BASE/'manifest.json'):BASE_SHA}
    for path,expected in ((REFERENCE,REFERENCE_SHA),(CAPTURE,CAPTURE_SHA)):
        if audit.sha(path)!=expected:raise ValueError('Exact selected-profile evidence changed')
    for path in (Path(__file__).resolve(),Path(profile.__file__).resolve(),TEST,REFERENCE,CAPTURE,
        ROOT/'tools/rpi5/tests/test_rp1_gem_selected_clock.py'):
        value=audit.sha(path)
        if str(path) in pins and pins[str(path)]!=value:raise ValueError('Selected-profile input conflict')
        pins[str(path)]=value
    engine.verify(pins);return parent,parent,pins


def objects(output):
    original=[Path(v) for v in (BASE/'kernel.rp1-config.filelist').read_text().splitlines()]
    found=[p for p in original if p.name=='rp1_gem_identify.c.o']
    if len(found)!=1 or len(original)!=len(set(original)):raise ValueError('Exactly one GEM decoder object required')
    changes={found[0]:output/found[0].name}
    return original,[changes.get(p,p) for p in original],changes


def compile_args(parent,source):
    if source.name!='rp1_gem_identify.c':raise ValueError('Only GEM decoder may be rebuilt')
    original,_,changes=objects(source.parent.parent);owner=next(iter(changes)).parent
    manifest=json.loads((owner/'manifest.json').read_text())
    rows=[row for row in manifest['compiles'] if str(owner/'overlay/rp1_gem_identify.c') in row['command']]
    if len(rows)!=1:raise ValueError('Exact original GEM compile required')
    command=rows[0]['command'];old=str(owner/'overlay/rp1_gem_identify.c')
    if command.count(old)!=1:raise ValueError('Ambiguous original GEM source')
    stop=command.index('-MD') if '-MD' in command else command.index('-o')
    return [str(source) if arg==old else arg for arg in command[:stop]]


def build(output):
    b=private.load_private(Path(engine.__file__).resolve(),'_gem_selected_kernel_engine')
    b.BASE=BASE;b.BASE_SHA=BASE_SHA;b.PROFILE=PROFILE;b.TEST=TEST;b.profile=profile
    b.inputs=inputs;b.objects=objects;b.compile_args=compile_args
    original,current,changes=objects(output)
    transport=[p for p in current if p.name=='BCM2712PCIePHYTransport.cpp.o']
    if len(transport)!=1 or transport[0] not in original:raise ValueError('Unchanged transport required')
    def retained_layout(current,unused,mapped):
        result=engine.class_layout_audit(current,transport[0],mapped)
        result.update(constructors_allocators_vtable_and_methods_recompiled=False,
            unchanged_existing_transport_object=str(transport[0]),transport_class_layout_unchanged=True)
        return result
    b.class_layout_audit=retained_layout
    result=b.build(output);delta=result.pop('elapsed_object_replacements')
    parent=json.loads((BASE/'manifest.json').read_text())
    result['elapsed_object_replacements']=parent['elapsed_object_replacements']
    result.pop('hardware_failure_receipt',None)
    symbols=engine.base.full.symbols((output/'kernel.symbols').read_text())
    for name in ('_rpi5_gem_identify_run','_rpi5_gem_read_allowed','_rpi5_gem_clock_profile'):
        if len(symbols.get(name,[]))!=1:raise ValueError('Exact linked GEM implementation required')
    result.update(selected_clock_contract=contract(),selected_clock_object_replacements=delta,
        selected_clock_added_objects=[],unchanged_parent_objects=len(original)-1,
        predecessor_root_forward_manifest_sha256=BASE_SHA,
        root_forward_object_replacements_scope='Unchanged predecessor root-forward component delta, not this link',
        root_forward_added_objects_scope='Unchanged predecessor root-forward component objects, not new additions',
        root_forward_contract_scope='Unchanged root forwarding component; selected_clock_contract supersedes its unchanged-GEM statement',
        gem_and_decode_core_objects_unchanged=False,decode_core_unchanged=True,
        transport_object_unchanged=True,controller_caller_unchanged=True,passive_trace_unchanged=True,
        owner_client_core_secure_objects_unchanged=True,logging_calls=42,
        physical_success_proven=False,physical_trial_admitted=False,
        required_next_evidence='Clean42rows with selected-source profile, repeated MID, full root/endpoint/maps/BAR restore and independent Linux return',
        trial_scope='Only SYS clock predicate changes to exact2/0x802 plus liveSEL4; no gate/frequency proof or register-write expansion')
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path,required=True)
    result=build(parser.parse_args().output_dir.resolve())
    print(json.dumps({k:result[k] for k in ('profile','kernel','kernel_sha256','kernel_bytes')}))
