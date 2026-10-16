#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Strict byte-only checker for the complete ring-only retry image."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import struct
from tools.rpi5 import build_gem_cpu_ring_retry_trial as b
from tools.rpi5 import check_display_xnu_console as binary
from tools.rpi5 import gem_cpu_ring_retry_completeness_v1 as canonical
from tools.rpi5 import gem_dma_batch_contract as contract

same=b.base.binary.exact if hasattr(b.base,'binary') else lambda a,c: json.dumps(a,sort_keys=True)==json.dumps(c,sort_keys=True)

def _read_json(path,pin):
    path=Path(path).resolve()
    if not re.fullmatch('[0-9a-f]{64}',pin) or b.sha(path)!=pin:raise ValueError('Exact retained JSON pin differs')
    return json.loads(path.read_bytes())

def inspect_image(package,expected_manifest_sha256):
    b.configure();package=Path(package).resolve();mp=package/'manifest.json'
    if package.parent!=b.ROOT/'build/rpi5' or not package.name.startswith('gem-cpu-ring-retry-trial-'):
        raise ValueError('Exact distinct retry package required')
    m=_read_json(mp,expected_manifest_sha256);pins=m['inputs_sha256'];generated=m['generated_sha256']
    members={str(p) for p in package.rglob('*') if p.is_file() and p!=mp}
    if set(generated)!=members:raise ValueError('Complete generated closure differs')
    for path,digest in [*pins.items(),*generated.items()]:
        if not re.fullmatch('[0-9a-f]{64}',digest) or b.sha(path)!=digest:raise ValueError('Consumed bytes changed: '+path)
    for path in b.sources():
        if pins.get(str(path.resolve()))!=b.sha(path):raise ValueError('Required source omitted: '+str(path))
    if (m.get('qualification'),m.get('qualification_sha256'))!=(str(b.QUALIFICATION),b.QUALIFICATION_SHA):raise ValueError('Retry qualification not bound')
    q=_read_json(b.QUALIFICATION,b.QUALIFICATION_SHA)
    if (q.get('profile')!='rpi5-gem-ring-only-allocation-retry-v1' or q.get('allocation_bytes')!=0x8000 or
        q.get('packet_memory') is not False or q.get('hardware_executed') is not False or q.get('dma') is not False or q.get('irq') is not False):
        raise ValueError('Qualified retry contract differs')
    for relative,digest in q['source_sha256'].items():
        path=b.ROOT/relative
        if b.sha(path)!=digest or pins.get(str(path.resolve()))!=digest:raise ValueError('Qualified final source differs: '+relative)
    if (m.get('failed_capture'),m.get('failed_capture_sha256'))!=(str(b.FAILED_CAPTURE),b.FAILED_CAPTURE_SHA):raise ValueError('Actual failure evidence not bound')
    failure=_read_json(b.FAILED_CAPTURE,b.FAILED_CAPTURE_SHA)
    if failure.get('diagnostic',{}).get('cpu_ring_owner')!=q['actual_failure_evidence']['cpu_ring_owner']:raise ValueError('Actual failure diagnosis drift')
    completeness=canonical.inspect(package,m)
    objects,replaced,extras,added=b.kernel_objects(package);mapped=(package/'kernel.map').read_text(errors='surrogateescape')
    if any(p not in mapped for p in [*replaced.values(),*extras,*added]) or any(p in mapped for p in replaced):raise ValueError('Linked object ownership differs')
    rawkernel=(package/'kernel.cpu-rings').read_bytes()
    if struct.unpack_from('<II',rawkernel)[:2]!=(0xfeedfacf,0x0100000c):raise ValueError('Actual Cortex-A76 arm64 kernel required')
    symbols,segments=binary.macho(rawkernel)
    required=('_rpi5_gem_ring_only_batch','_rpi5_boot_reservation_record','_rpi5_reservation_kernel_validate',
        '_rpi5_pcie_id_trial_start','_rpi5_display_xnu_mapping_verify','_rpi5_console_mirror_publish')
    if any(name not in symbols for name in required) or '_rpi5_gem_ring_batch' in symbols:raise ValueError('Exact ring-only implementation absent')
    formats=re.findall(r'kprintf\("([^"\n]+)"',b.derived_sources()['overlay/BCM2712PCIeIDTrialProgress.inc'].decode())
    if (len(formats)!=53 or not any('DMA_PREP STEP=%u ERROR=%d BYTES=%llu PACKETS=0' in f for f in formats) or
        any(rawkernel.count(ast.literal_eval('"'+f+'"').encode()+b'\0')!=1 for f in formats) or
        any(len(re.findall(r'%(?!%)',f))>16 for f in formats) or any(len(re.findall(r'%(?!%)',f))>8 for f in formats[-7:-1])):
        raise ValueError('Complete bounded 53-row encoder differs')
    raw=(package/'probe.bin').read_bytes();elf=binary.elf((package/'cpu_rings.elf').read_bytes(),raw)
    if struct.unpack_from('<H',(package/'cpu_rings.elf').read_bytes(),18)[0]!=183 or 'rpi5_psci_cpu_on' in elf:raise ValueError('Actual AArch64 single-CPU loader required')
    marker=b.retry.trial.marker(m['tag'])
    if raw.count(marker.encode())!=1 or raw.count((b.retry.trial.BOOTARGS+'\0').encode())!=1:raise ValueError('Unique image identity differs')
    true=('sameboot_loader_kernel_reservation','real_sleepable_apple_preparation','real_fresh_controller_caller',
        'cpu_owned_descriptors_only','preferred_ram_route_only','native_model_not_hardware_guarantee')
    false=('all_inbound_windows_disabled','queue_publication','bme_enable','dma_activation','irq_activation',
        'packet_mapping','dma_completion_proven','hardware_executed','staged')
    exact={'profile':b.PROFILE,'trial_marker':marker,'bootargs':b.retry.trial.BOOTARGS,'qualification_sha256':b.QUALIFICATION_SHA,
        'failed_capture_sha256':b.FAILED_CAPTURE_SHA,'allocation_bytes':32768,'descriptor_pages':2,'packet_spans':0,
        'preparation_steps':17,'ring_expected_packets':0,'ring_expected_writes':640,'ring_expected_reads':640,
        'ring_expected_current':164,'watchdog_seconds':15,'kernel_sha256':b.sha(package/'kernel.cpu-rings'),
        'image_sha256':b.sha(package/'probe.bin')}
    if any(m.get(k) is not True for k in true) or any(m.get(k) is not False for k in false) or any(type(m.get(k)) is not type(v) or m.get(k)!=v for k,v in exact.items()):
        raise ValueError('Typed retry trial contract differs')
    oldpayload=(b.base.BASE/'payload.bin').read_bytes();off,n=struct.unpack_from('<QQ',oldpayload,136);root=oldpayload[off:off+n]
    envelope=max(va+memory for va,memory,_,_,_ in segments)-min(va for va,memory,_,_,_ in segments if memory)
    args_pa=(0x7004000+envelope+16383)&~16383;root_pa=args_pa+0x8000
    root_marker=f'RPI5XNU:BL33:RAMDISK_MATERIALIZED PA={root_pa:016x} BYTES={len(root):016x} VERIFIED'
    kernel_marker=f'RPI5XNU:BL33:KERNEL_MATERIALIZED BYTES={envelope:016x} FULL_ENVELOPE_VERIFIED NO_BOOT_ARGS_WRITTEN NO_TRANSFER'
    return dict(profile=b.PROFILE,package=str(package),manifest_sha256=expected_manifest_sha256,
        image_sha256=m['image_sha256'],kernel_sha256=m['kernel_sha256'],image_bytes=len(raw),tag=m['tag'],marker=marker,
        trial_marker=marker,bootargs=b.retry.trial.BOOTARGS,root_copy_marker=root_marker,kernel_copy_marker=kernel_marker,
        boot_markers=[marker,contract.HOST,contract.DEVICE,contract.FDT,root_marker,kernel_marker],
        cpu_ring_contract=contract.contract(),inherited_capability_contracts=contract.inherited(),
        source_members=len(pins),generated_members=len(generated),canonical_commands=completeness['canonical_commands'],
        canonical_compiles=completeness['canonical_compile_labels'],qualification_sha256=b.QUALIFICATION_SHA,
        allocation_bytes=32768,preparation_steps=17,packet_spans=0,expected_writes=640,expected_readbacks=640,
        preferred_ram_route_only=True,bme=False,dma=False,irq=False,queues=False,packets=False,
        complete_capture_health_required=True,automatic_watchdog_return_required=True,physical_execution_proven=False)

def inspect(package,manifest_sha,qualification,qualification_sha):
    from tools.rpi5 import qualify_gem_cpu_ring_retry_trial as stack
    result=inspect_image(package,manifest_sha);result['target_stack']=stack.inspect(package,manifest_sha,qualification,qualification_sha)
    result.update(qualification=str(Path(qualification).resolve()),target_stack_qualification_sha256=qualification_sha,
        software_trial_qualified=True,physical_execution_proven=False)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path);p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--qualification',type=Path,required=True);p.add_argument('--qualification-sha256',required=True);p.add_argument('--report',type=Path)
    a=p.parse_args();result=inspect(a.package,a.manifest_sha256,a.qualification,a.qualification_sha256)
    if a.report:
        with a.report.resolve().open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps(result,sort_keys=True))
