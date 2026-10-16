#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct held-map repeated GEM design-register loader package."""
import json
from pathlib import Path
from types import SimpleNamespace
from tools.rpi5 import build_pcie_gem_selected_package as prior
from tools.rpi5 import build_pcie_gem_capabilities_kernel as kernel
ROOT,private=prior.ROOT,prior.private
KERNEL_PACKAGE=ROOT/'build/rpi5/pcie-gem-capabilities-kernel-20261013-v1'
KERNEL_SHA='7ca7d04e3eb541b83fbe68f1804156f1fbfc4da0160b736ac42f0f691f71a088'
KERNEL_MANIFEST_SHA='3f39456cf2d6d4b9fa7b3586b54558564addc0b25b1cdcd69c1846107f582b3e'
PRIOR_PACKAGE=ROOT/'build/rpi5/pcie-id-trial-vf78_802'
PRIOR_SHA='a287f869e27bd1926dfcc2147ea998e673e02dd0aff8b2f9a45816324dc90904'
PROFILE='pcie-held-gem-capabilities-single-cpu-loader-v1'
CHECKER=ROOT/'tools/rpi5/check_pcie_gem_capabilities_package.py'
TEST=ROOT/'tools/rpi5/tests/test_pcie_gem_capabilities_package.py'
PROTOCOL=ROOT/'tools/rpi5/pcie_gem_capabilities_serial_core.py'
SERIAL_TEST=ROOT/'tools/rpi5/tests/test_pcie_gem_capabilities_serial.py'
DEVICE_MARKER=prior.DEVICE_MARKER
assignment_contract,guard_contract=prior.assignment_contract,prior.guard_contract
selected_clock_contract=prior.selected_clock_contract


def capabilities_contract():
    if kernel.audit.sha(KERNEL_PACKAGE/'manifest.json')!=KERNEL_MANIFEST_SHA:
        raise ValueError('Exact capability kernel manifest required')
    m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    if (m['profile']!=kernel.PROFILE or m['kernel_sha256']!=KERNEL_SHA or
        m['capabilities_contract']!=kernel.contract() or len(m['capabilities_object_replacements'])!=2 or
        len(m['capabilities_added_objects'])!=1 or m['logging_calls']!=47 or
        m['owner_client_core_secure_objects_unchanged'] is not True):
        raise ValueError('Exact held-map capability kernel required')
    return dict(m['capabilities_contract'],kernel_manifest_sha256=KERNEL_MANIFEST_SHA,
        object_replacements=m['capabilities_object_replacements'],added_objects=m['capabilities_added_objects'])


def component(factory,scope):
    result=factory();current=capabilities_contract()
    for name in ('object_replacements','added_objects','kernel_manifest_sha256'):
        result['predecessor_selected_'+name]=result.pop(name)
        result[name]=current[name]
    result.update(capabilities_contract_is_authoritative=True,scope=scope,
        native_modeled_pm_checks=63628,native_modeled_firmware_sequence=15905,native_modeled_guards=7952)
    return result


def root_forward_contract():
    result=component(prior.root_forward_contract,'Unchanged root MEM/window restoration; read-only capability callback extends held-map GEM interval')
    result['gem_read_sequence_and_transport_guards_unchanged']=False
    result['original_guard_sites_unchanged_new_reads_same_guards']=True
    return result


def gem_contract():
    result=component(prior.gem_contract,'Original32 clock/MID reads plus16 design reads; no clock frequency/gate measurement')
    result['total_endpoint_read_bound']=48
    return result


def decode_contract():return component(prior.decode_contract,'Unchanged endpoint decode/mapping lifecycle; capability callback while exact Device maps live')
def owner_contract():return component(prior.owner_contract,'Unchanged fresh ownership/limits/deadlines; extra16 reads with existing pre/post transport guards')


def trace_contract():
    result=prior.trace_contract();m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    raw=(KERNEL_PACKAGE/'kernel.rp1-config').read_bytes()
    for fmt in m['capability_record_formats']:
        if raw.count(fmt.encode()+b'\0')!=1:raise ValueError('Exact47 capability trace records required')
    result.update(record_formats=m['capability_record_formats'],terminal_kprintf_count=47,
        scope='42 inherited records plus CAPS and four raw design-snapshot rows; END last; whole original capture health scan')
    return result


def configured_source():
    p=private.load_private(Path(prior.__file__).resolve(),'_capability_selected_loader')
    for name in ('KERNEL_PACKAGE','KERNEL_SHA','KERNEL_MANIFEST_SHA','PROFILE','CHECKER','TEST','PROTOCOL','SERIAL_TEST','PRIOR_PACKAGE','PRIOR_SHA'):
        setattr(p,name,globals()[name])
    # Existing loader derivation needs only the exact textual once() helper;
    # do not add exports to the already-pinned kernel/profile module.
    p.kernel=SimpleNamespace(**vars(kernel))
    p.kernel.profile=SimpleNamespace(**vars(kernel.profile),util=kernel.profile.core.util)
    for name in ('root_forward_contract','gem_contract','decode_contract','owner_contract','trace_contract'):
        setattr(p,name,globals()[name])
    source=p.configured_source();factory=source.configured_builder
    def configured_builder():
        b=factory();inputs,marker=b.inputs,b.marker
        def complete_inputs():
            pins,reports=inputs();path=Path(__file__).resolve();value=b.sha(path)
            if str(path) in pins and pins[str(path)]!=value:raise ValueError('Capability builder pin changed')
            pins[str(path)]=value;b.verify(pins);return pins,reports
        b.inputs=complete_inputs
        b.marker=lambda tag:marker(tag).replace('PCIE_GEM_SELECTED_TRIAL ','PCIE_GEM_CAPABILITIES_TRIAL ')
        return b
    source.configured_builder=configured_builder;return source


def build():
    source=configured_source();package,m=source.build()
    previous=json.loads((PRIOR_PACKAGE/'manifest.json').read_text())
    for name in ('link_elapsed','rp1_config_trace','root_route','bars_contract','guard_composition','rp1_device_handoff','selected_clock_contract'):
        m[name]=previous[name]
    m.update(capabilities_contract=capabilities_contract(),root_forward_contract=root_forward_contract(),
        gem_contract=gem_contract(),decode_contract=decode_contract(),assignment_contract=assignment_contract(),
        owner_trace=owner_contract(),previous_selected_package_manifest_sha256=PRIOR_SHA,
        prior_component_contracts_are_scoped_not_whole_trial=True,
        selected_clock_contract_scope='Unchanged SYS predicate only; capabilities_contract defines current object set/read sequence',
        endpoint_register_access=True,endpoint_register_writes=False,root_config_memory_writes=True,
        root_command_changes_mem_only=True,selected_source_profile_not_independent_clock_measurement=True)
    (package/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');return package,m


if __name__=='__main__':
    p,m=build();print(json.dumps(dict(image=str(p/'probe.bin'),image_sha256=m['image_sha256'],image_bytes=m['image_bytes'],marker=m['marker']),indent=2))
