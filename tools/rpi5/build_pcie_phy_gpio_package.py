#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct held-map GPIO32 raw observer; no GPIO writes or reset claim."""
import json
from pathlib import Path
from tools.rpi5 import build_pcie_gem_capabilities_package as prior
from tools.rpi5 import build_pcie_phy_gpio_kernel as kernel
from tools.rpi5 import pcie_phy_gpio_handoff_contract as handoff
from tools.rpi5.check_pcie_gem_selected_package import same
ROOT,private=prior.ROOT,prior.private
KERNEL_PACKAGE=ROOT/'build/rpi5/pcie-phy-gpio-kernel-20261014-v1'
KERNEL_SHA='9e8c1cbf4d767110d886690cdded4b9f28b9cebff6cf73ca42b963c58cb624aa'
KERNEL_MANIFEST_SHA='f21c594fe01371c85b2957988fac679b1d19dbad52231584996868def48724d1'
PRIOR_PACKAGE=ROOT/'build/rpi5/pcie-id-trial-s24bfjnh'
PRIOR_SHA='a8c1234b5087767af25dbe8bb8d914d754d2f58ac6824c542c122510aa318ce0'
PROFILE='pcie-phy-gpio32-read-only-single-cpu-loader-v1'
CHECKER=ROOT/'tools/rpi5/check_pcie_phy_gpio_package.py'
TEST=ROOT/'tools/rpi5/tests/test_pcie_phy_gpio_package.py'
PROTOCOL=ROOT/'tools/rpi5/pcie_phy_gpio_serial_core.py'
SERIAL_TEST=ROOT/'tools/rpi5/tests/test_pcie_phy_gpio_serial.py'
DEVICE_MARKER=prior.DEVICE_MARKER.replace('RANGES=2 PAGES=6 GEM_CLOCK_ONLY','RANGES=5 PAGES=9 GEM_CLOCK_GPIO32_ONLY')
assignment_contract,guard_contract=prior.assignment_contract,prior.guard_contract
selected_clock_contract,capabilities_contract=prior.selected_clock_contract,prior.capabilities_contract


def gpio_contract():
    if kernel.audit.sha(KERNEL_PACKAGE/'manifest.json')!=KERNEL_MANIFEST_SHA:raise ValueError('Exact GPIO kernel manifest required')
    m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    if (m['profile']!=kernel.PROFILE or m['kernel_sha256']!=KERNEL_SHA or not same(m['gpio_contract'],kernel.contract()) or
        len(m['gpio_object_replacements'])!=1 or len(m['gpio_added_objects'])!=1 or m['logging_calls']!=53 or
        m['owner_client_core_secure_objects_unchanged'] is not True):raise ValueError('Exact GPIO kernel required')
    return dict(m['gpio_contract'],kernel_manifest_sha256=KERNEL_MANIFEST_SHA,
        object_replacements=m['gpio_object_replacements'],added_objects=m['gpio_added_objects'])


def component(factory,scope):
    result=factory();current=gpio_contract()
    for name in ('object_replacements','added_objects','kernel_manifest_sha256'):
        result['predecessor_capabilities_'+name]=result.pop(name);result[name]=current[name]
    result.update(gpio_contract_is_authoritative=True,scope=scope,native_modeled_pm_checks=63916,
        native_modeled_firmware_sequence=15977,native_modeled_guards=7988)
    return result


def root_forward_contract():
    result=component(prior.root_forward_contract,'Unchanged root MEM/window restoration; read-only GPIO32 snapshots inside held-map GEM interval')
    result['gem_read_sequence_and_transport_guards_unchanged']=False
    return result


def gem_contract():
    result=component(prior.gem_contract,'48 existing clock/MID/design reads plus12 GPIO32 raw reads; no PHY readiness or clock measurement')
    result['total_endpoint_read_bound']=60;result['endpoint_register_writes']=False
    return result


def decode_contract():return component(prior.decode_contract,'Unchanged decode/mapping lifecycle; GPIO observation only while exact Device maps live')
def owner_contract():return component(prior.owner_contract,'Unchanged fresh owners/limits/deadlines; each new Device map/read/unmap callback uses original firmware guards')
def gpio_handoff_contract():
    return dict(marker=DEVICE_MARKER,pages=9,
        ranges=decode_contract()['map_ranges']+[[0x1f000d4000,0x1f000d8000],[0x1f000e4000,0x1f000e8000],[0x1f000f4000,0x1f000f8000]],
        declaration_only=True,eth_cfg_not_declared=True,no_loader_mmio=True,gpio32_additional_pages=3)


def trace_contract():
    result=prior.trace_contract();m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text());raw=(KERNEL_PACKAGE/'kernel.rp1-config').read_bytes()
    for fmt in m['gpio_record_formats']:
        if raw.count(fmt.encode()+b'\0')!=1:raise ValueError('Exact53 GPIO trace records required')
    result.update(record_formats=m['gpio_record_formats'],terminal_kprintf_count=53,
        scope='47 inherited records plus six bounded passive GPIO32 records; END last; full original capture health scan')
    return result


def configured_source():
    p=private.load_private(Path(prior.__file__).resolve(),'_gpio_capability_loader')
    for name in ('KERNEL_PACKAGE','KERNEL_SHA','KERNEL_MANIFEST_SHA','PROFILE','CHECKER','TEST','PROTOCOL','SERIAL_TEST','PRIOR_PACKAGE','PRIOR_SHA','kernel'):
        setattr(p,name,globals()[name])
    for name in ('root_forward_contract','gem_contract','decode_contract','owner_contract','trace_contract'):setattr(p,name,globals()[name])
    source=p.configured_source();factory=source.configured_builder
    def configured_builder():
        b=factory();inputs,marker,derive,markers,stack=b.inputs,b.marker,b.derive_main,b.boot_markers,b.stack_for
        def complete_inputs():
            pins,reports=inputs();path=Path(__file__).resolve();value=b.sha(path)
            if str(path) in pins and pins[str(path)]!=value:raise ValueError('GPIO builder pin conflict')
            pins[str(path)]=value
            for extra in (ROOT/'loader/rpi5/phy_gpio_device_handoff.c',ROOT/'loader/rpi5/phy_gpio_device_handoff.h',
                Path(handoff.__file__),ROOT/'tools/rpi5/tests/test_phy_gpio_device_handoff.py'):
                key=str(extra.resolve());digest=b.sha(extra)
                if key in pins and pins[key]!=digest:raise ValueError('GPIO handoff source conflict')
                pins[key]=digest
            b.verify(pins);return pins,reports
        def derived(tag):
            original,text=derive(tag)
            anchor='#include "'+str(ROOT/'loader/rpi5/rp1_device_handoff.c')+'"'
            text=kernel.profile.core.util.once(text,anchor,anchor+'\n#include "'+str(ROOT/'loader/rpi5/phy_gpio_device_handoff.c')+'"')
            text=kernel.profile.core.util.once(text,
                'rpi5_rp1_device_handoff((const void *)fdt_pa,fdt_length,&pcie_types,&rp1_types)',
                'rpi5_phy_gpio_device_handoff((const void *)fdt_pa,fdt_length,&pcie_types,&rp1_types)')
            text=text.replace(prior.DEVICE_MARKER,DEVICE_MARKER)
            return original,text
        def boot_markers(tag):return [row.replace(prior.DEVICE_MARKER,DEVICE_MARKER) for row in markers(tag)]
        def stack_for(package,old):
            frames,budgets=stack(package,old)
            extra=[row for row in frames if row['location'].split(':')[-1] in ('rpi5_phy_gpio_device_handoff','phy_gpio_be32','phy_gpio_equal')]
            if not any(row['location'].split(':')[-1]=='rpi5_phy_gpio_device_handoff' for row in extra):raise ValueError('Actual GPIO handoff frame missing')
            added=sum(row['bytes'] for row in extra)
            top=max(0x4000-v['minimum_remaining_bytes'] for v in budgets.values())+added
            if top+512>=0x4000:raise ValueError('GPIO handoff stack exceeds inherited16KiB')
            budgets['phy_gpio_device']=dict(conservative_bytes=top,minimum_remaining_bytes=0x4000-top,added_helper_frames=added,exact_pages=9)
            return frames,budgets
        b.inputs=complete_inputs;b.marker=lambda tag:marker(tag).replace('PCIE_GEM_CAPABILITIES_TRIAL ','PCIE_PHY_GPIO_TRIAL ')
        b.derive_main=derived;b.boot_markers=boot_markers;b.stack_for=stack_for;b.handoff_contract=handoff
        return b
    source.configured_builder=configured_builder;return source


def build():
    source=configured_source();package,m=source.build();previous=json.loads((PRIOR_PACKAGE/'manifest.json').read_text())
    for name in ('link_elapsed','rp1_config_trace','root_route','bars_contract','guard_composition','selected_clock_contract','capabilities_contract'):
        m[name]=previous[name]
    m.update(gpio_contract=gpio_contract(),root_forward_contract=root_forward_contract(),gem_contract=gem_contract(),
        decode_contract=decode_contract(),assignment_contract=assignment_contract(),owner_trace=owner_contract(),
        previous_capabilities_package_manifest_sha256=PRIOR_SHA,prior_component_contracts_are_scoped_not_whole_trial=True,
        capabilities_contract_scope='Unchanged design reader only; gpio_contract defines current object set and GPIO reads and three separately bounded maps',
        endpoint_register_access=True,endpoint_register_writes=False,phy_register_writes=False,
        root_config_memory_writes=True,root_command_changes_mem_only=True,
        selected_source_profile_not_independent_clock_measurement=True,
        predecessor_rp1_device_handoff=previous['rp1_device_handoff'],
        rp1_device_handoff=gpio_handoff_contract())
    (package/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');return package,m


if __name__=='__main__':
    p,m=build();print(json.dumps(dict(image=str(p/'probe.bin'),image_sha256=m['image_sha256'],image_bytes=m['image_bytes'],marker=m['marker']),indent=2))
