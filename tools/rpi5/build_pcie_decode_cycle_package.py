#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""MEM-only map/revoke loader with exact two-range RP1 Device handoff."""
import json
from pathlib import Path
from tools.rpi5 import build_pcie_bars_assignment_package as prior
from tools.rpi5 import build_pcie_decode_cycle_kernel as kernel
from tools.rpi5 import pcie_decode_handoff_contract as handoff
ROOT,private=prior.ROOT,prior.private
KERNEL_PACKAGE=ROOT/'build/rpi5/pcie-decode-cycle-kernel-20261013-v1'
KERNEL_SHA='dd82a79c56f8fddb4cb32138a139b0b3cad2e645a2acb6180d8362f1206175a5'
KERNEL_MANIFEST_SHA='4742e761b800d7ffc68cb0a5683cfd3f315a890390fb1c10b1333b8259302468'
PRIOR_PACKAGE=ROOT/'build/rpi5/pcie-id-trial-_w3ajzlm'
PRIOR_SHA='9275fbd5741bd4365a6f0461dd9d74fc2980fc6517a85a416bbc6f4fdb20f3f0'
PROFILE='pcie-mem-only-device-map-revoke-single-cpu-loader-v1'
CHECKER=ROOT/'tools/rpi5/check_pcie_decode_cycle_package.py'
TEST=ROOT/'tools/rpi5/tests/test_pcie_decode_cycle_package.py'
PROTOCOL=ROOT/'tools/rpi5/pcie_decode_cycle_serial_core.py'
SERIAL_TEST=ROOT/'tools/rpi5/tests/test_pcie_decode_cycle_serial.py'
DEVICE_MARKER='RPI5XNU:BL33:RP1_DEVICE_HANDOFF RANGES=2 PAGES=6 GEM_CLOCK_ONLY DECLARATIONS_ONLY RP1_MMIO=0'
assignment_contract,guard_contract=prior.assignment_contract,prior.guard_contract


def decode_contract():
    if kernel.audit.sha(KERNEL_PACKAGE/'manifest.json')!=KERNEL_MANIFEST_SHA:raise ValueError('Exact decode kernel changed')
    m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    if (m['profile']!=kernel.PROFILE or m['kernel_sha256']!=KERNEL_SHA or m['decode_contract']!=kernel.contract() or
        len(m['decode_object_replacements'])!=1 or len(m['decode_added_objects'])!=1 or m['logging_calls']!=25 or
        m['owner_client_core_secure_objects_unchanged'] is not True):raise ValueError('Exact guarded decode kernel required')
    return dict(m['decode_contract'],kernel_manifest_sha256=KERNEL_MANIFEST_SHA,
        object_replacements=m['decode_object_replacements'],added_objects=m['decode_added_objects'])


def owner_contract():
    result=prior.owner_contract();old=result.pop('object_replacements');added=result.pop('added_objects')
    current=decode_contract()
    result.update(kernel_manifest_sha256=KERNEL_MANIFEST_SHA,object_replacements=current['object_replacements'],
        added_objects=current['added_objects'],predecessor_assignment_object_replacements=old,
        predecessor_assignment_added_objects=added,decode_sequence_added=True,
        scope='Same passive owners and fresh nested guards; temporary MEM-only command transition and exact private Device-map/revoke cycle added')
    return result


def trace_contract():
    result=prior.trace_contract();m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    raw=(KERNEL_PACKAGE/'kernel.rp1-config').read_bytes()
    for fmt in m['decode_record_formats']:
        if raw.count(fmt.encode()+b'\0')!=1:raise ValueError('Exact decode format missing')
    result.update(record_formats=m['decode_record_formats'],terminal_kprintf_count=25,
        scope='Twenty-three inherited bounded records plus two decode cycle rows; END last; whole capture health required')
    return result


def configured_source():
    a=private.load_private(Path(prior.__file__).resolve(),'_decode_assignment_loader')
    for name in ('KERNEL_PACKAGE','KERNEL_SHA','KERNEL_MANIFEST_SHA','PROFILE','CHECKER','TEST','PROTOCOL','SERIAL_TEST'):
        setattr(a,name,globals()[name])
    a.assignment_contract=assignment_contract;a.owner_contract=owner_contract;a.trace_contract=trace_contract
    source=a.configured_source();factory=source.configured_builder
    def configured_builder():
        b=factory();inputs,marker,derive,markers,stack=b.inputs,b.marker,b.derive_main,b.boot_markers,b.stack_for
        def complete_inputs():
            pins,reports=inputs()
            if b.sha(PRIOR_PACKAGE/'manifest.json')!=PRIOR_SHA:raise ValueError('Frozen assignment package changed')
            m=json.loads((PRIOR_PACKAGE/'manifest.json').read_text())
            more=m['inputs_sha256']|m['headers_sha256']|m['generated_sha256']|{str(PRIOR_PACKAGE/'manifest.json'):PRIOR_SHA}
            for path in (Path(__file__).resolve(),Path(handoff.__file__).resolve(),
                ROOT/'loader/rpi5/rp1_device_handoff.c',ROOT/'loader/rpi5/rp1_device_handoff.h',
                ROOT/'tools/rpi5/tests/test_rp1_device_handoff.py',ROOT/'tools/rpi5/tests/rp1_device_handoff_host.c'):
                more[str(path)]=b.sha(path)
            for path,value in more.items():
                if path in pins and pins[path]!=value:raise ValueError('Decode loader source conflict: '+path)
                pins[path]=value
            b.verify(pins);return pins,reports
        def derived(tag):
            original,text=derive(tag)
            # Compile the new pure helper into this actual main TU, preserving
            # the original link/object list and actual dependency scanner.
            text=kernel.profile.util.once(text,'#include "pcie_device_handoff.h"',
                '#include "pcie_device_handoff.h"\n#include "'+str(ROOT/'loader/rpi5/rp1_device_handoff.c')+'"')
            text=kernel.profile.util.once(text,'    types=pcie_types;','''    static struct rpi5_memory_types rp1_types;
    if (rpi5_rp1_device_handoff((const void *)fdt_pa,fdt_length,&pcie_types,&rp1_types)) return 0;
    types=rp1_types;''')
            anchor='    if (!text("RPI5XNU:BL33:FIRMWARE_FDT RETAINED_DESCRIPTOR_ONLY'
            text=kernel.profile.util.once(text,anchor,
                '    if (!text("'+DEVICE_MARKER+'\\r\\n")) return 0;\n'+anchor)
            return original,text
        def boot_markers(tag):
            result=markers(tag);result.insert(2,DEVICE_MARKER);return result
        def stack_for(package,old):
            frames,budgets=stack(package,old)
            extra=[row for row in frames if row['location'].split(':')[-1]=='rpi5_rp1_device_handoff']
            if not extra:raise ValueError('Actual RP1 helper stack frame missing')
            # Conservatively add every new helper frame to all existing path
            # budgets even though host-bank/RP1 handoffs execute sequentially.
            added=sum(row['bytes'] for row in extra)
            top=max(0x4000-v['minimum_remaining_bytes'] for v in budgets.values())+added
            if top+512>=0x4000:raise ValueError('RP1 handoff stack exceeds retained16KiB bound')
            budgets['rp1_device']=dict(conservative_bytes=top,minimum_remaining_bytes=0x4000-top,
                added_helper_frames=added,exact_pages=6)
            return frames,budgets
        b.inputs=complete_inputs;b.marker=lambda tag:marker(tag).replace('PCIE_BARS_ASSIGNMENT_TRIAL ','PCIE_DECODE_CYCLE_TRIAL ')
        b.derive_main=derived;b.boot_markers=boot_markers;b.handoff_contract=handoff;b.stack_for=stack_for
        return b
    source.configured_builder=configured_builder;return source


def build():
    source=configured_source();package,m=source.build()
    previous=json.loads((PRIOR_PACKAGE/'manifest.json').read_text())
    for name in ('link_elapsed','rp1_config_trace','root_route','bars_contract','guard_composition'):
        m[name]=previous[name]
    m.update(decode_contract=decode_contract(),assignment_contract=assignment_contract(),owner_trace=owner_contract(),
        previous_assignment_package_manifest_sha256=PRIOR_SHA,prior_component_contracts_are_scoped_not_whole_trial=True,
        assignment_contract_scope='Unchanged size/assignment/restore component; inserted map/decode phase specified separately',
        rp1_device_handoff=dict(marker=DEVICE_MARKER,ranges=decode_contract()['map_ranges'],pages=6,
            declaration_only=True,eth_cfg_not_declared=True,no_loader_mmio=True))
    (package/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');return package,m


if __name__=='__main__':
    p,m=build();print(json.dumps(dict(image=str(p/'probe.bin'),image_sha256=m['image_sha256'],image_bytes=m['image_bytes'],marker=m['marker']),indent=2))
