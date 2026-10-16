#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only ownership/ring composition audit; no compiler, device or shell calls."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from tools.rpi5 import build_gem_dma_rings_package as b
from tools.rpi5 import check_display_xnu_console as binary
def exact(a,c):return json.dumps(a,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(c,sort_keys=True,separators=(',',':'),allow_nan=False)
def inspect(package,expected_manifest_sha256):
    package=Path(package).resolve();mp=package/'manifest.json'
    if package.parent!=b.ROOT/'build/rpi5' or not package.name.startswith('gem-dma-rings-'):raise ValueError('Distinct package required')
    if not re.fullmatch('[a-f0-9]{64}',expected_manifest_sha256) or b.sha(mp)!=expected_manifest_sha256:raise ValueError('Separately retained manifest pin differs')
    m=json.loads(mp.read_text());pins=m['inputs_sha256'];generated=m['generated_sha256']
    actual={str(p) for p in package.rglob('*') if p.is_file() and p!=mp}
    if set(generated)!=actual:raise ValueError('Complete generated closure differs')
    for path,digest in list(pins.items())+list(generated.items()):
        if not re.fullmatch('[a-f0-9]{64}',digest) or b.sha(path)!=digest:raise ValueError('Changed consumed bytes: '+path)
    required=[*b.sources(),Path(__file__).resolve(),b.BASE/'manifest.json',b.TEMPLATE/'manifest.json',b.SELECTED]
    if any(pins.get(str(p))!=b.sha(p) for p in required):raise ValueError('Required source is missing')
    if pins[str(b.BASE/'manifest.json')]!=b.BASE_SHA or pins[str(b.TEMPLATE/'manifest.json')]!=b.TEMPLATE_SHA:raise ValueError('Exact accepted parents differ')
    parent=json.loads((b.BASE/'manifest.json').read_text())
    for key in ('inputs_sha256','actual_headers_sha256','generated_sha256'):
        if any(pins.get(p)!=h for p,h in parent[key].items()):raise ValueError('Inherited closure omitted')
    for name,transform in [('arm_init',b.boot.arm),('probe_main',b.record.loader),('firmware_seed_tree',b.record.seed)]:
        if (package/(name+'.c')).read_text()!=transform((b.BASE/(name+'.c')).read_text()):raise ValueError('Exact owner overlay differs: '+name)
    if not re.fullmatch('[a-f0-9]{32}',m['tag']):raise ValueError('Unique tag required')
    rows=m['commands'];labels=[Path(r['log']).stem for r in rows]
    if len(labels)!=len(set(labels)):raise ValueError('Duplicate command identity')
    for row in rows:
        if not exact(row['returncode'],0) or row['log']!=str(package/(Path(row['log']).stem+'.log')) or row['log_sha256']!=b.sha(row['log']):raise ValueError('Build completion differs')
    headers={}
    for name,paths in m['compiler_scans'].items():
        row=next(r for r in rows if r['log']==str(package/(name+'-compile.log')))
        before=b.display.dependencies(package/(name+'.scan.d'),row['cwd']);after=b.display.dependencies(package/(name+'.d'),row['cwd'])
        if before!=after or sorted(before)!=paths:raise ValueError('Actual compiler dependency set differs')
        if row['command'][-2:]!=['-o',str(package/(name+'.o'))] or '-mcpu=cortex-a76' not in row['command']:raise ValueError('Actual target object differs')
        for path in before:
            if path not in pins:raise ValueError('Unpinned compiler header')
            headers[path]=pins[path]
    if not exact(headers,m['actual_headers_sha256']):raise ValueError('Complete header map differs')
    original=(b.BASE/'kernel.display.filelist').read_text().splitlines();oldarm=str(b.BASE/'arm_init.o')
    replacements={oldarm:str(package/'arm_init.o')}
    expected_added=[str(package/'dma-rings.o')]+[str(package/('kernel-'+name+'.o')) for name in (
        'rpi5_gem_dma_route','rpi5_gem_ring_stage','rpi5_reservation_kernel','reservation_record','ranges','reservations',
        'pcie_released_windows','rp1_gem_capabilities','rp1_gem_identify','firmware_seed_fdt')]
    expected_objects=[replacements.get(p,p) for p in original]+expected_added
    if original.count(oldarm)!=1 or not exact(m['replaced_objects'],replacements) or not exact(m['added_objects'],expected_added) or \
        (package/'kernel.filelist').read_text().splitlines()!=expected_objects or len(expected_objects)!=len(set(expected_objects)):
        raise ValueError('Exact kernel composition differs')
    kernel=package/'kernel.owned-rings';rawkernel=kernel.read_bytes();symbols,segments=binary.macho(rawkernel)
    for name in ('_rpi5_boot_reservation_record','_rpi5_reservation_kernel_validate','_rpi5_reservation_record_validate_fdt',
        '_rpi5_gem_ring_stage','_rpi5_display_xnu_mapping_verify','_rpi5_display_xnu_video_admit','_initialize_screen'):
        if name not in symbols:raise ValueError('Actual implementation missing: '+name)
    if not any('stageCPUOwned' in p for p in symbols):raise ValueError('Genuine retained ring member missing')
    mapped=(package/'kernel.map').read_text(errors='surrogateescape')
    if oldarm in mapped or any(p not in mapped for p in [*replacements.values(),*expected_added]):raise ValueError('Actual kernel linkmap differs')
    image=package/'probe.bin';raw=image.read_bytes();elf=binary.elf((package/'owned_rings.elf').read_bytes(),raw)
    if {name:v[0] for name,v in elf.items()}!=m['loader_symbols']:raise ValueError('Actual ELF symbol values differ')
    for name in ('rpi5_reservation_record_finalize','rpi5_reservation_record_make','rpi5_reservation_record_tree_commit'):
        if name not in elf:raise ValueError('Actual loader owner absent')
    if elf['__probe_end'][0]>=0xb000000 or elf['__stack_top'][0]-elf['__bss_end'][0]!=32768:raise ValueError('FDT/stack geometry differs')
    marker=('RPI5XNU:DISPLAYXNU:ENTRY TAG='+m['tag']+' SAME_BOOT OWNED_FRAMEBUFFER_CONSOLE_V1').encode()
    if raw.count(marker)!=1 or raw.count(b'rpi5-resolved-reservations-v1')<1:raise ValueError('Actual linked identity absent')
    packed=(package/'payload.bin').read_bytes()
    if packed[:8]!=b'RPI5XNU\0' or struct.unpack_from('<II',packed,8)!=(1,64) or struct.unpack_from('<I',packed,24)[0]!=2:raise ValueError('Payload framing differs')
    for i in range(2):
        kind,flags,off,size,digest,zero=struct.unpack_from('<IIQQ32sQ',packed,64+i*64);data=packed[off:off+size]
        if (kind,flags,zero)!=(i+1,0,0) or off%64 or len(data)!=size or hashlib.sha256(data).digest()!=digest:raise ValueError('Actual payload record differs')
        if i==0 and data!=rawkernel:raise ValueError('Embedded kernel differs')
        if i==1 and (size!=parent['root_bytes'] or digest.hex()!=parent['root_sha256']):raise ValueError('Accepted root changed')
    if struct.unpack_from('<Q',packed,16)[0]!=len(packed) or hashlib.sha256(packed[64:192]).digest()!=packed[32:64]:raise ValueError('Payload envelope differs')
    offset=m['payload_offset']
    if type(offset) is not int or offset%64 or raw[offset:offset+len(packed)]!=packed or raw.find(packed)!=offset or raw.find(packed,offset+1)>=0:raise ValueError('Payload not uniquely embedded')
    stackfiles={name:package/(('loader-' if name in ('reservation_record','reservation_record_tree') else 'stack-')+name+'.su') for name in b.record.STACK_UNITS}
    budget=b.record.stack_budget(stackfiles,package/'loader-probe_main.su',package/'loader-firmware_seed_tree.su')
    checks=dict(exact_profile=m['profile']==b.PROFILE,complete_input_and_output_closure=True,
        exact_kernel_delta=True,actual_sameboot_loader_kernel_abi=True,original_hdmi_root_preserved=True,
        exact_kernel=m['kernel']==str(kernel) and m['kernel_sha256']==b.sha(kernel) and exact(m['kernel_bytes'],len(rawkernel)),
        exact_image=m['image']==str(image) and m['image_sha256']==b.sha(image) and exact(m['image_bytes'],len(raw)),
        exact_record=m['reservation_property']=='rpi5-resolved-reservations-v1' and exact(m['reservation_wire_bytes'],1056),
        exact_reservation_stack=exact(budget,m['reservation_stack_budget']),
        no_activation_or_hardware_claim=all(m[k] is False for k in ('driver_live_owner_installed','dma_enabled',
            'queue_registers_written','irq_enabled','packets','hardware_executed','staged','deadline_extended')),
        actual_ownership_not_receipts=all(m[k] is True for k in ('reservation_consumed_seed_zero_before_hash',
            'reservation_sameboot_kernel_ready_after_vm','resolved_claims_replayed_from_actual_fdt','unresolved_window_not_declared_free',
            'ring_provider_default_off','real_apple_allocator_and_dma_command','ring_descriptor_cpu_only','old_phy_budget_unchanged')),
        unchanged_deadlines=exact(m['terminal_watchdog_seconds'],180) and exact(m['watchdog_countdown_seconds'],15))
    if not all(checks.values()):raise ValueError('Ring ownership checks failed: '+','.join(k for k,v in checks.items() if not v))
    return dict(profile=b.PROFILE,package=str(package),manifest_sha256=expected_manifest_sha256,
        image_sha256=b.sha(image),kernel_sha256=b.sha(kernel),checks=checks,
        result='SOFTWARE_COMPOSITION_ONLY',live_dma_authority=False,hardware_admission=False,
        remaining=m['remaining'])
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path);p.add_argument('--expected-manifest-sha256',required=True)
    a=p.parse_args();print(json.dumps(inspect(a.package,a.expected_manifest_sha256),sort_keys=True,indent=2))
