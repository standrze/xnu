#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct held-map C22 management loader; no device publication."""
import json
from pathlib import Path
from tools.rpi5 import build_pcie_gem_capabilities_package as prior
from tools.rpi5 import build_pcie_gem_mdio_id_kernel as kernel
from tools.rpi5.check_pcie_gem_selected_package import same
ROOT,private=prior.ROOT,prior.private
KERNEL_PACKAGE=ROOT/'build/rpi5/pcie-gem-mdio-kernel-20261014-v2'
KERNEL_SHA='ec2a37b7421a84cd0ccd2ac2d82e1e926cf44a82254be4dd2c82c8bf53886326'
KERNEL_MANIFEST_SHA='67d614b3324db922eb8d155236155002851f2096a78df583f94d009040ddafd1'
PRIOR_PACKAGE=ROOT/'build/rpi5/pcie-id-trial-s24bfjnh'
PRIOR_SHA='a8c1234b5087767af25dbe8bb8d914d754d2f58ac6824c542c122510aa318ce0'
PROFILE='pcie-held-gem-c22-mdio-single-cpu-loader-v1'
CHECKER=ROOT/'tools/rpi5/check_pcie_gem_mdio_package.py'
TEST=ROOT/'tools/rpi5/tests/test_pcie_gem_mdio_package.py'
PROTOCOL=ROOT/'tools/rpi5/pcie_gem_mdio_serial_core.py'
SERIAL_TEST=ROOT/'tools/rpi5/tests/test_pcie_gem_mdio_serial.py'
DEVICE_MARKER=prior.DEVICE_MARKER
assignment_contract,guard_contract=prior.assignment_contract,prior.guard_contract
selected_clock_contract,capabilities_contract=prior.selected_clock_contract,prior.capabilities_contract


def mdio_contract():
    if kernel.audit.sha(KERNEL_PACKAGE/'manifest.json')!=KERNEL_MANIFEST_SHA:raise ValueError('Exact MDIO kernel manifest required')
    m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    if (m['profile']!=kernel.PROFILE or m['kernel_sha256']!=KERNEL_SHA or not same(m['mdio_contract'],kernel.contract()) or
        len(m['mdio_object_replacements'])!=1 or len(m['mdio_added_objects'])!=1 or m['logging_calls']!=53 or
        m['owner_client_core_secure_objects_unchanged'] is not True):raise ValueError('Exact MDIO kernel required')
    return dict(m['mdio_contract'],kernel_manifest_sha256=KERNEL_MANIFEST_SHA,
        object_replacements=m['mdio_object_replacements'],added_objects=m['mdio_added_objects'])


def component(factory,scope):
    result=factory();current=mdio_contract()
    for name in ('object_replacements','added_objects','kernel_manifest_sha256'):
        result['predecessor_capabilities_'+name]=result.pop(name);result[name]=current[name]
    result.update(mdio_contract_is_authoritative=True,scope=scope,native_modeled_pm_checks=65420,
        native_modeled_firmware_sequence=16353,native_modeled_guards=8176)
    return result


def root_forward_contract():
    result=component(prior.root_forward_contract,'Unchanged root MEM/window restoration; bounded management inside held-map GEM interval')
    result['gem_read_sequence_and_transport_guards_unchanged']=False
    return result


def gem_contract():
    result=component(prior.gem_contract,'48 existing clock/MID/design reads plus bounded PHY management, not independent clock measurement')
    result['total_endpoint_read_bound']=94;result['endpoint_register_writes']=True
    return result


def decode_contract():return component(prior.decode_contract,'Unchanged decode/mapping lifecycle; MDIO only while exact Device maps live')
def owner_contract():return component(prior.owner_contract,'Unchanged fresh owners/limits/deadlines; each added data/time callback uses original firmware guards')


def trace_contract():
    result=prior.trace_contract();m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text());raw=(KERNEL_PACKAGE/'kernel.rp1-config').read_bytes()
    for fmt in m['mdio_record_formats']:
        if raw.count(fmt.encode()+b'\0')!=1:raise ValueError('Exact53 MDIO trace records required')
    result.update(record_formats=m['mdio_record_formats'],terminal_kprintf_count=53,
        scope='47 inherited records plus six bounded passive management records; END last; full original capture health scan')
    return result


def configured_source():
    p=private.load_private(Path(prior.__file__).resolve(),'_mdio_capability_loader')
    for name in ('KERNEL_PACKAGE','KERNEL_SHA','KERNEL_MANIFEST_SHA','PROFILE','CHECKER','TEST','PROTOCOL','SERIAL_TEST','PRIOR_PACKAGE','PRIOR_SHA','kernel'):
        setattr(p,name,globals()[name])
    for name in ('root_forward_contract','gem_contract','decode_contract','owner_contract','trace_contract'):setattr(p,name,globals()[name])
    source=p.configured_source();factory=source.configured_builder
    def configured_builder():
        b=factory();inputs,marker=b.inputs,b.marker
        def complete_inputs():
            pins,reports=inputs();path=Path(__file__).resolve();value=b.sha(path)
            if str(path) in pins and pins[str(path)]!=value:raise ValueError('MDIO builder pin conflict')
            pins[str(path)]=value;b.verify(pins);return pins,reports
        b.inputs=complete_inputs;b.marker=lambda tag:marker(tag).replace('PCIE_GEM_CAPABILITIES_TRIAL ','PCIE_GEM_MDIO_TRIAL ')
        return b
    source.configured_builder=configured_builder;return source


def build():
    source=configured_source();package,m=source.build();previous=json.loads((PRIOR_PACKAGE/'manifest.json').read_text())
    for name in ('link_elapsed','rp1_config_trace','root_route','bars_contract','guard_composition','rp1_device_handoff','selected_clock_contract','capabilities_contract'):
        m[name]=previous[name]
    m.update(mdio_contract=mdio_contract(),root_forward_contract=root_forward_contract(),gem_contract=gem_contract(),
        decode_contract=decode_contract(),assignment_contract=assignment_contract(),owner_trace=owner_contract(),
        previous_capabilities_package_manifest_sha256=PRIOR_SHA,prior_component_contracts_are_scoped_not_whole_trial=True,
        capabilities_contract_scope='Unchanged design reader only; mdio_contract defines current object set and management accesses',
        endpoint_register_access=True,endpoint_register_writes=True,phy_register_writes=False,
        root_config_memory_writes=True,root_command_changes_mem_only=True,
        selected_source_profile_not_independent_clock_measurement=True)
    (package/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');return package,m


if __name__=='__main__':
    p,m=build();print(json.dumps(dict(image=str(p/'probe.bin'),image_sha256=m['image_sha256'],image_bytes=m['image_bytes'],marker=m['marker']),indent=2))
