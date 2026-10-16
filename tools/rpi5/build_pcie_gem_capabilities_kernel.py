#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct two-object plus one-core GEM capability kernel; no hardware."""
import argparse
import json
from pathlib import Path
import re
from tools.rpi5 import build_pcie_gem_selected_kernel as prior
from tools.rpi5 import pcie_gem_capabilities_trace_profile as profile

ROOT, audit, engine, private = prior.ROOT, prior.audit, prior.engine, prior.private
BASE = profile.FROZEN.parent
BASE_SHA = '932b71ad0e5a39f2627e25c81222e3f430995503f9663c92750302c3f48d586d'
PROFILE = 'pcie-held-device-gem-capabilities-kernel-v1'
TEST = ROOT / 'tools/rpi5/tests/test_pcie_gem_capabilities_kernel.py'


def contract():
    return dict(extra_offsets=[0xfc,0x280,0x284,0x290,0x294,0x29c,0x2a4,0x2ac],
        extra_passes=2, extra_reads=16, original_clock_mid_reads=32, total_endpoint_reads=48,
        capability_phase='After second MID and before all 15 post-clock reads, with original mappings/root forwarding live',
        repeat_words_equal_required=True, mid_matches_held_identity=True,
        exact_owner_thread_phase_before_after_callbacks=True,
        transport_firmware_guard_before_after_every_extra_read=True,
        original_before_after_clock_equality_required=True,
        parent_commit_only_after_complete_restoration=True,
        any_failure_quarantines_without_retry_or_compensating_cleanup=True,
        reads_are_le32_design_configuration_only=True, endpoint_register_writes=False,
        no_status_isr_statistics_ncr_mdio_or_phy_access=True,
        no_clock_reset_dma_irq_enable=True, unknown_bus_width_retained_not_defaulted=True,
        dma64_feature_not_addressability_qualification=True,
        unchanged_pm_limit=65536, native_modeled_pm_checks=63628,
        native_modeled_firmware_sequence=15905, native_modeled_guards=7952,
        model_counts_not_physical_timing_or_guarantees=True,
        retained_watchdog_seconds=[9,10,12,15], ethernet_proven=False,
        primary_sources=json.loads((ROOT/'tools/rpi5/rp1_gem_capabilities_sources.json').read_text()))


def inputs():
    if audit.sha(BASE/'manifest.json') != BASE_SHA:
        raise ValueError('Exact accepted selected-clock kernel required')
    parent = json.loads((BASE/'manifest.json').read_text())
    pins = parent['inputs_sha256'] | parent['generated_sha256'] | {str(BASE/'manifest.json'):BASE_SHA}
    paths = [Path(__file__).resolve(), Path(profile.__file__).resolve(), Path(profile.core.__file__).resolve(), TEST,
        ROOT/'loader/rpi5/rp1_gem_capabilities.c', ROOT/'loader/rpi5/rp1_gem_capabilities.h',
        ROOT/'tools/rpi5/tests/test_rp1_gem_capabilities.py', ROOT/'tools/rpi5/tests/rp1_gem_capabilities_host.c',
        ROOT/'tools/rpi5/rp1_gem_capabilities_sources.json', ROOT/'docs/rpi5/GEM-CAPABILITY-READER.md']
    for path in paths:
        value = audit.sha(path)
        if str(path) in pins and pins[str(path)] != value:
            raise ValueError('Capability input pin conflict')
        pins[str(path)] = value
    source = json.loads((ROOT/'tools/rpi5/rp1_gem_capabilities_sources.json').read_text())
    for row in source['sources']:
        path = ROOT/row['path']
        if audit.sha(path) != row['sha256']:
            raise ValueError('Capability primary source changed')
        pins[str(path)] = row['sha256']
    engine.verify(pins)
    return parent, parent, pins


def objects(output):
    original = [Path(p) for p in (BASE/'kernel.rp1-config.filelist').read_text().splitlines()]
    changes = {}
    for name in ('BCM2712PCIePHYTransport.cpp.o','rp1_gem_identify.c.o'):
        found = [p for p in original if p.name == name]
        if len(found) != 1:
            raise ValueError('Exact capability replacement owner required')
        changes[found[0]] = output/name
    if len(original) != len(set(original)) or any(p.name=='rp1_gem_capabilities.c.o' for p in original):
        raise ValueError('Fresh capability core required')
    return original, [changes.get(p,p) for p in original] + [output/'rp1_gem_capabilities.c.o'], changes


def compile_args(parent, source):
    original, _, _ = objects(source.parent.parent)
    name = 'BCM2712PCIePHYTransport.cpp' if source.suffix=='.cpp' else 'rp1_gem_identify.c'
    owner = next(p.parent for p in original if p.name==name+'.o')
    old = owner/'overlay'/name
    manifest = json.loads((owner/'manifest.json').read_text())
    rows = [r['command'] for r in manifest['compiles'] if str(old) in r['command']]
    if len(rows) != 1:
        raise ValueError('Exact original compile command required')
    command = rows[0]
    stop = command.index('-MD') if '-MD' in command else command.index('-o')
    return [str(source) if a==str(old) else a for a in command[:stop]]


def build(output):
    b = private.load_private(Path(engine.__file__).resolve(), '_gem_capability_kernel_engine')
    for name in ('BASE','BASE_SHA','PROFILE','TEST','profile','inputs','objects','compile_args'):
        setattr(b,name,globals()[name])
    result = b.build(output)
    delta = result.pop('elapsed_object_replacements')
    parent = json.loads((BASE/'manifest.json').read_text())
    result['elapsed_object_replacements'] = parent['elapsed_object_replacements']
    result.pop('hardware_failure_receipt',None)
    assembly = (output/'BCM2712PCIePHYTransport.cpp.s').read_text()
    guard = re.search(r'^__ZN\d+BCM2712PCIePHYTransport5guardEv:[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.M|re.S)[1]
    calls = re.findall(r'\tbl\t(_pe_rpi5_\w+)',guard)
    if calls != parent['guard_emitted_owner_calls']:
        raise ValueError('Original owner guard composition changed')
    formats = re.findall(r'kprintf\("([^"\n]+)"',(output/'overlay/BCM2712PCIeIDTrialProgress.inc').read_text())
    if len(formats)!=47 or not formats[-1].startswith('RPI5XNU:PCIEID:END '):
        raise ValueError('47 bounded passive records required')
    raw=(output/'kernel.rp1-config').read_bytes()
    for fmt in formats:
        if raw.count(fmt.replace('\\n','\n').encode()+b'\0')!=1:
            raise ValueError('Exact capability trace missing from linked kernel')
    symbols=engine.base.full.symbols((output/'kernel.symbols').read_text())
    for name in ('_rpi5_gem_cap_run','_rpi5_gem_cap_read_allowed','_rpi5_gem_cap_decode'):
        if len(symbols.get(name,[]))!=1:
            raise ValueError('Unique linked capability implementation required')
    result.update(capabilities_contract=contract(),capabilities_object_replacements=delta,
        capabilities_added_objects=[str(output/'rp1_gem_capabilities.c.o')],
        capability_record_formats=[s.replace('\\n','\n') for s in formats],
        predecessor_selected_clock_manifest_sha256=BASE_SHA,
        prior_component_contracts_scoped_not_whole_trial=True,
        transport_object_unchanged=False,gem_and_decode_core_objects_unchanged=False,
        decode_core_unchanged=True,controller_caller_unchanged=False,passive_trace_unchanged=False,
        owner_client_core_secure_objects_unchanged=True,guard_emitted_owner_calls=calls,
        logging_calls=47,total_endpoint_read_bound=48,unchanged_parent_objects=len(objects(output)[0])-2,
        physical_success_proven=False,physical_trial_admitted=False,
        trial_scope='Read-only repeated GEM design words inside held root/map and original clock bracket; no packet driver')
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    result=build(parser.parse_args().output_dir.resolve())
    print(json.dumps({k:result[k] for k in ('profile','kernel','kernel_sha256','kernel_bytes')}))
