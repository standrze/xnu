#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct42-row root forwarding trial with narrow SYS source selection admission."""
import json
from pathlib import Path
from tools.rpi5 import build_pcie_root_forward_package as prior
from tools.rpi5 import build_pcie_gem_selected_kernel as kernel
ROOT,private=prior.ROOT,prior.private
KERNEL_PACKAGE=ROOT/'build/rpi5/pcie-gem-selected-kernel-20261013-v1'
KERNEL_SHA='c262f59a2e34c203695ea6d1eabf1eca6f36ea1bf2df12d4eb5b17243383cc5c'
KERNEL_MANIFEST_SHA='932b71ad0e5a39f2627e25c81222e3f430995503f9663c92750302c3f48d586d'
PRIOR_PACKAGE=ROOT/'build/rpi5/pcie-id-trial-adb7yr9w'
PRIOR_SHA='2754ff2de036d035219a2a93bd85474f8095da17339b2bab40b2ae629eecc988'
PROFILE='pcie-gem-selected-source-root-forward-single-cpu-loader-v1'
CHECKER=ROOT/'tools/rpi5/check_pcie_gem_selected_package.py'
TEST=ROOT/'tools/rpi5/tests/test_pcie_gem_selected_package.py'
PROTOCOL=ROOT/'tools/rpi5/pcie_gem_selected_serial_core.py'
SERIAL_TEST=ROOT/'tools/rpi5/tests/test_pcie_gem_selected_serial.py'
DEVICE_MARKER=prior.DEVICE_MARKER
assignment_contract,guard_contract=prior.assignment_contract,prior.guard_contract


def selected_clock_contract():
    if kernel.audit.sha(KERNEL_PACKAGE/'manifest.json')!=KERNEL_MANIFEST_SHA:raise ValueError('Exact selected-source kernel changed')
    m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    if (m['profile']!=kernel.PROFILE or m['kernel_sha256']!=KERNEL_SHA or m['selected_clock_contract']!=kernel.contract() or
        len(m['selected_clock_object_replacements'])!=1 or m['selected_clock_added_objects'] or
        m['transport_object_unchanged'] is not True or m['passive_trace_unchanged'] is not True or
        m['logging_calls']!=42):raise ValueError('Exact one-object selected-source kernel required')
    return dict(m['selected_clock_contract'],kernel_manifest_sha256=KERNEL_MANIFEST_SHA,
        object_replacements=m['selected_clock_object_replacements'],added_objects=[])


def component(factory,label):
    result=factory();current=selected_clock_contract()
    result.update(predecessor_root_forward_object_replacements=result.pop('object_replacements'),
        predecessor_root_forward_added_objects=result.pop('added_objects'),
        predecessor_root_forward_kernel_manifest_sha256=result.pop('kernel_manifest_sha256'),
        kernel_manifest_sha256=KERNEL_MANIFEST_SHA,object_replacements=current['object_replacements'],added_objects=[],
        selected_clock_contract_is_authoritative=True,scope=label)
    return result


def root_forward_contract():
    result=component(prior.root_forward_contract,'Unchanged root MEM/window cycle; selected_clock_contract governs the corrected GEM predicate')
    result['existing_gem_clock_and_mid_core_unchanged']=False
    result['gem_read_sequence_and_transport_guards_unchanged']=True
    return result


def gem_contract():
    result=component(prior.gem_contract,'Selected-source register profile only; no independent physical clock/gate/frequency proof')
    result.update(register_profile_admission_not_independent_clock_readiness=True,
        sys_ctrl_exact_values=[2,0x802],sys_selected_exact=4,physical_frequency_or_gate_measurement=False)
    return result


def decode_contract():return component(prior.decode_contract,'Unchanged endpoint decode and Device mappings; only GEM predicate differs')
def owner_contract():return component(prior.owner_contract,'Unchanged fresh owners, guards, budgets and deadlines; one pure GEM predicate correction')


def trace_contract():
    result=prior.trace_contract();m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    raw=(KERNEL_PACKAGE/'kernel.rp1-config').read_bytes()
    for fmt in m['root_forward_record_formats']:
        if raw.count(fmt.encode()+b'\0')!=1:raise ValueError('Exact selected-source42-row trace required')
    result.update(gem_ready_field_means='Admitted selected-source register profile, not independently measured gating/frequency')
    return result


def configured_source():
    p=private.load_private(Path(prior.__file__).resolve(),'_gem_selected_root_loader')
    for name in ('KERNEL_PACKAGE','KERNEL_SHA','KERNEL_MANIFEST_SHA','PROFILE','CHECKER','TEST','PROTOCOL','SERIAL_TEST','PRIOR_PACKAGE','PRIOR_SHA'):
        setattr(p,name,globals()[name])
    p.kernel=kernel
    for name in ('root_forward_contract','gem_contract','decode_contract','owner_contract','trace_contract'):setattr(p,name,globals()[name])
    source=p.configured_source();factory=source.configured_builder
    def configured_builder():
        b=factory();inputs,marker=b.inputs,b.marker
        def complete_inputs():
            pins,reports=inputs();path=Path(__file__).resolve();value=b.sha(path)
            if str(path) in pins and pins[str(path)]!=value:raise ValueError('Selected-source builder pin changed')
            pins[str(path)]=value;b.verify(pins);return pins,reports
        b.inputs=complete_inputs
        b.marker=lambda tag:marker(tag).replace('PCIE_ROOT_FORWARD_TRIAL ','PCIE_GEM_SELECTED_TRIAL ')
        return b
    source.configured_builder=configured_builder;return source


def build():
    source=configured_source();package,m=source.build()
    previous=json.loads((PRIOR_PACKAGE/'manifest.json').read_text())
    for name in ('link_elapsed','rp1_config_trace','root_route','bars_contract','guard_composition','rp1_device_handoff'):
        m[name]=previous[name]
    m.update(selected_clock_contract=selected_clock_contract(),root_forward_contract=root_forward_contract(),
        gem_contract=gem_contract(),decode_contract=decode_contract(),assignment_contract=assignment_contract(),
        owner_trace=owner_contract(),previous_root_forward_package_manifest_sha256=PRIOR_SHA,
        prior_component_contracts_are_scoped_not_whole_trial=True,endpoint_register_access=True,
        endpoint_register_writes=False,root_config_memory_writes=True,root_command_changes_mem_only=True,
        selected_source_profile_not_independent_clock_measurement=True)
    (package/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');return package,m


if __name__=='__main__':
    p,m=build();print(json.dumps(dict(image=str(p/'probe.bin'),image_sha256=m['image_sha256'],image_bytes=m['image_bytes'],marker=m['marker']),indent=2))
