#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Root bridge MEM/window cycle around the unchanged bounded GEM reads."""
import json
from pathlib import Path
from tools.rpi5 import build_pcie_gem_identify_package as prior
from tools.rpi5 import build_pcie_root_forward_kernel as kernel
ROOT,private=prior.ROOT,prior.private
KERNEL_PACKAGE=ROOT/'build/rpi5/pcie-root-forward-kernel-20261013-v1'
KERNEL_SHA='a5836576fa205bd710f8245d686f4fd206998ec260eb291d6ba9dc0df3f68c03'
KERNEL_MANIFEST_SHA='7c09e045e6d04e33bb11d43a4875b4cc17333374858bcda8412c9be172ae6f45'
PRIOR_PACKAGE=ROOT/'build/rpi5/pcie-id-trial-yjofwwhc'
PRIOR_SHA='1229ec948dff70945bbe5490728a1a40d21a9b8e1128c0fe884ee5f74757d356'
PROFILE='pcie-root-mem-forwarding-gem-single-cpu-loader-v1'
CHECKER=ROOT/'tools/rpi5/check_pcie_root_forward_package.py'
TEST=ROOT/'tools/rpi5/tests/test_pcie_root_forward_package.py'
PROTOCOL=ROOT/'tools/rpi5/pcie_root_forward_serial_core.py'
SERIAL_TEST=ROOT/'tools/rpi5/tests/test_pcie_root_forward_serial.py'
DEVICE_MARKER=prior.DEVICE_MARKER
assignment_contract,guard_contract=prior.assignment_contract,prior.guard_contract


def root_forward_contract():
    if kernel.audit.sha(KERNEL_PACKAGE/'manifest.json')!=KERNEL_MANIFEST_SHA:raise ValueError('Exact root-forward kernel changed')
    m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    if (m['profile']!=kernel.PROFILE or m['kernel_sha256']!=KERNEL_SHA or m['root_forward_contract']!=kernel.contract() or
        len(m['root_forward_object_replacements'])!=1 or len(m['root_forward_added_objects'])!=1 or m['logging_calls']!=42 or
        m['gem_and_decode_core_objects_unchanged'] is not True):raise ValueError('Exact root MEM forwarding kernel required')
    return dict(m['root_forward_contract'],kernel_manifest_sha256=KERNEL_MANIFEST_SHA,
        object_replacements=m['root_forward_object_replacements'],added_objects=m['root_forward_added_objects'],
        primary_source_references=m['primary_source_references'],
        outbound_required_mask=[0xffffffff,0xffffffff,0xfff0fff0,0xff,0xff],
        outbound_required_values=[[0,0,0xfff00000,0x1f,0x1f],[0,4,0xfff00000,0x1c,0x1e]])


def adapt_contract(factory,label):
    result=factory();old=result.pop('object_replacements');added=result.pop('added_objects');current=root_forward_contract()
    result.update(kernel_manifest_sha256=KERNEL_MANIFEST_SHA,object_replacements=current['object_replacements'],
        added_objects=current['added_objects'],predecessor_gem_object_replacements=old,
        predecessor_gem_added_objects=added,root_memory_forwarding_cycle_added=True,
        root_forward_contract_is_authoritative=True,
        native_modeled_pm_checks=63372,native_modeled_firmware_sequence=15841,native_modeled_guards=7920,
        scope=label+'; root MEM/window temporary forwarding/restoration is specified separately by root_forward_contract')
    return result


def gem_contract():return adapt_contract(prior.gem_contract,'Unchanged clock/MID core and reads')
def decode_contract():return adapt_contract(prior.decode_contract,'Unchanged endpoint decode and exact private Device maps')
def owner_contract():return adapt_contract(prior.owner_contract,'Unchanged fresh owners, guards, budgets and deadlines')


def trace_contract():
    result=prior.trace_contract();m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    raw=(KERNEL_PACKAGE/'kernel.rp1-config').read_bytes()
    for fmt in m['root_forward_record_formats']:
        if raw.count(fmt.encode()+b'\0')!=1:raise ValueError('Exact root-forward record missing')
    result.update(record_formats=m['root_forward_record_formats'],terminal_kprintf_count=42,
        scope='Thirty-five inherited records plus seven bounded root bridge rows; END last; complete original raw health scan')
    return result


def configured_source():
    p=private.load_private(Path(prior.__file__).resolve(),'_root_forward_gem_loader')
    for name in ('KERNEL_PACKAGE','KERNEL_SHA','KERNEL_MANIFEST_SHA','PROFILE','CHECKER','TEST','PROTOCOL','SERIAL_TEST','PRIOR_PACKAGE','PRIOR_SHA'):
        setattr(p,name,globals()[name])
    p.kernel=kernel;p.gem_contract=gem_contract;p.decode_contract=decode_contract;p.owner_contract=owner_contract;p.trace_contract=trace_contract
    source=p.configured_source();factory=source.configured_builder
    def configured_builder():
        b=factory();inputs,marker=b.inputs,b.marker
        def complete_inputs():
            pins,reports=inputs();path=Path(__file__).resolve();value=b.sha(path)
            if str(path) in pins and pins[str(path)]!=value:raise ValueError('Root-forward builder pin changed')
            pins[str(path)]=value;b.verify(pins);return pins,reports
        b.inputs=complete_inputs
        b.marker=lambda tag:marker(tag).replace('PCIE_GEM_IDENTIFY_TRIAL ','PCIE_ROOT_FORWARD_TRIAL ')
        return b
    source.configured_builder=configured_builder;return source


def build():
    source=configured_source();package,m=source.build()
    previous=json.loads((PRIOR_PACKAGE/'manifest.json').read_text())
    for name in ('link_elapsed','rp1_config_trace','root_route','bars_contract','guard_composition','rp1_device_handoff'):
        m[name]=previous[name]
    m.update(root_forward_contract=root_forward_contract(),gem_contract=gem_contract(),decode_contract=decode_contract(),
        assignment_contract=assignment_contract(),owner_trace=owner_contract(),
        previous_gem_package_manifest_sha256=PRIOR_SHA,prior_component_contracts_are_scoped_not_whole_trial=True,
        endpoint_register_access=True,endpoint_register_writes=False,root_config_memory_writes=True,
        root_command_changes_mem_only=True,assignment_contract_scope='Unchanged BAR component; held-map reads and root forwarding specified separately')
    (package/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');return package,m


if __name__=='__main__':
    p,m=build();print(json.dumps(dict(image=str(p/'probe.bin'),image_sha256=m['image_sha256'],image_bytes=m['image_bytes'],marker=m['marker']),indent=2))
