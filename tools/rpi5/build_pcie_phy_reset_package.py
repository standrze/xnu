#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct59-row GPIO32 pulse + fresh C22 trial, same nine Device pages."""
import json
from pathlib import Path
from tools.rpi5 import build_pcie_phy_gpio_package as prior
from tools.rpi5 import build_pcie_phy_reset_kernel as kernel
from tools.rpi5.check_pcie_gem_selected_package import same
ROOT,private=prior.ROOT,prior.private
KERNEL_PACKAGE=ROOT/'build/rpi5/pcie-phy-reset-kernel-20261014-v2'
KERNEL_SHA='0298e440db72b8c9e6a71585373e57fe32a8c2d64e792aef98ba2e069c672fdf'
KERNEL_MANIFEST_SHA='0dafc8e47ab3226833c36c9aab2a2da1116abb2ca4c814e1a81a852e372c0fb8'
PRIOR_PACKAGE=prior.PRIOR_PACKAGE
PRIOR_SHA=prior.PRIOR_SHA
PROFILE='pcie-phy-reset-timed-mdio-single-cpu-loader-v1'
CHECKER=ROOT/'tools/rpi5/check_pcie_phy_reset_package.py'
TEST=ROOT/'tools/rpi5/tests/test_pcie_phy_reset_package.py'
PROTOCOL=ROOT/'tools/rpi5/pcie_phy_reset_serial_core.py'
SERIAL_TEST=ROOT/'tools/rpi5/tests/test_pcie_phy_reset_serial.py'
DEVICE_MARKER=prior.DEVICE_MARKER
assignment_contract,guard_contract=prior.assignment_contract,prior.guard_contract
selected_clock_contract,capabilities_contract=prior.selected_clock_contract,prior.capabilities_contract
gpio_handoff_contract=prior.gpio_handoff_contract


def reset_contract():
    if kernel.audit.sha(KERNEL_PACKAGE/'manifest.json')!=KERNEL_MANIFEST_SHA:raise ValueError('Exact reset kernel manifest required')
    m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    if (m['profile']!=kernel.PROFILE or m['kernel_sha256']!=KERNEL_SHA or not same(m['reset_contract'],kernel.contract()) or
        len(m['reset_object_replacements'])!=2 or len(m['reset_added_objects'])!=2 or m['logging_calls']!=59 or
        m['owner_client_core_secure_objects_unchanged'] is not True):raise ValueError('Exact reset kernel required')
    return dict(m['reset_contract'],kernel_manifest_sha256=KERNEL_MANIFEST_SHA,
        object_replacements=m['reset_object_replacements'],added_objects=m['reset_added_objects'])


def component(factory,scope):
    result=factory();current=reset_contract()
    for name in ('object_replacements','added_objects','kernel_manifest_sha256'):
        result['predecessor_gpio_'+name]=result.pop(name);result[name]=current[name]
    result.pop('gpio_contract_is_authoritative',None)
    result.update(reset_contract_is_authoritative=True,scope=scope,native_modeled_pm_checks=65244,
        native_modeled_firmware_sequence=16309,native_modeled_guards=8154)
    return result


def root_forward_contract():return component(prior.root_forward_contract,'Unchanged root restoration; explicit GPIO32 pulse + C22 read action inside live root/map interval')
def gem_contract():
    result=component(prior.gem_contract,'48 retained clock/MID/design reads + at most46 C22 management +19 GPIO reads; GPIO and temporary management writes')
    result.update(total_endpoint_read_bound=113,endpoint_register_writes=True,endpoint_write_bound=21)
    return result
def decode_contract():return component(prior.decode_contract,'Unchanged MEM-only decode/maps; distinct GPIO pulse and fresh C22 reads while all exact Device maps live')
def owner_contract():return component(prior.owner_contract,'Unchanged fresh owner checks and limits; timestamp samples fused inside unchanged MMIO guard envelopes')
def trace_contract():
    result=prior.prior.trace_contract();m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text());raw=(KERNEL_PACKAGE/'kernel.rp1-config').read_bytes()
    for fmt in m['reset_record_formats']:
        if raw.count(fmt.encode()+b'\0')!=1:raise ValueError('Exact59 reset trace records required')
    result.update(record_formats=m['reset_record_formats'],terminal_kprintf_count=59,
        scope='47 retained records +six MDIO +six GPIO reset records; END last; full raw post-END fault scan')
    return result


def configured_source():
    parent=private.load_private(Path(prior.__file__).resolve(),'_phy_reset_ninepage_loader')
    for name in ('KERNEL_PACKAGE','KERNEL_SHA','KERNEL_MANIFEST_SHA','PROFILE','CHECKER','TEST','PROTOCOL','SERIAL_TEST','kernel'):
        setattr(parent,name,globals()[name])
    parent.gpio_contract=reset_contract
    for name in ('root_forward_contract','gem_contract','decode_contract','owner_contract','trace_contract'):
        setattr(parent,name,globals()[name])
    source=parent.configured_source();factory=source.configured_builder
    def configured_builder():
        b=factory();inputs,marker=b.inputs,b.marker
        def complete_inputs():
            pins,reports=inputs()
            for path in (Path(__file__).resolve(),Path(prior.__file__).resolve()):
                value=b.sha(path)
                if str(path) in pins and pins[str(path)]!=value:raise ValueError('Reset loader source conflict')
                pins[str(path)]=value
            b.verify(pins);return pins,reports
        b.inputs=complete_inputs;b.marker=lambda tag:marker(tag).replace('PCIE_PHY_GPIO_TRIAL ','PCIE_PHY_RESET_TRIAL ')
        return b
    source.configured_builder=configured_builder;return source


def build():
    source=configured_source();package,m=source.build();previous=json.loads((PRIOR_PACKAGE/'manifest.json').read_text())
    for name in ('link_elapsed','rp1_config_trace','root_route','bars_contract','guard_composition','selected_clock_contract','capabilities_contract'):
        m[name]=previous[name]
    m.update(reset_contract=reset_contract(),root_forward_contract=root_forward_contract(),gem_contract=gem_contract(),
        decode_contract=decode_contract(),assignment_contract=assignment_contract(),owner_trace=owner_contract(),
        previous_capabilities_package_manifest_sha256=PRIOR_SHA,previous_gpio_package_manifest_sha256='b4b84a4ef35b1e941bced191bf294504d8388d67e0029f10353193d3fd94dad6',
        prior_component_contracts_are_scoped_not_whole_trial=True,
        capabilities_contract_scope='Unchanged design core only; reset_contract authorizes only this explicit GPIO32 pulse/restore and C22 read action',
        endpoint_register_access=True,endpoint_register_writes=True,phy_register_writes=False,gpio_reset_writes=True,
        root_config_memory_writes=True,root_command_changes_mem_only=True,
        selected_source_profile_not_independent_clock_measurement=True,
        predecessor_rp1_device_handoff=previous['rp1_device_handoff'],rp1_device_handoff=gpio_handoff_contract())
    (package/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');return package,m


if __name__=='__main__':
    p,m=build();print(json.dumps(dict(image=str(p/'probe.bin'),image_sha256=m['image_sha256'],image_bytes=m['image_bytes'],marker=m['marker']),indent=2))
