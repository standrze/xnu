#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Byte-only actual CPU-ring composition checker; no compiler or hardware."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import struct
from tools.rpi5 import build_gem_dma_batch_trial as b
from tools.rpi5 import check_display_xnu_console as binary
from tools.rpi5 import gem_dma_batch_completeness_v1 as canonical
from tools.rpi5 import gem_dma_batch_contract as contract
same=binary.exact
def inspect_image(package,expected_manifest_sha256):
    package=Path(package).resolve();mp=package/'manifest.json'
    if package.parent!=b.ROOT/'build/rpi5' or not package.name.startswith('gem-dma-batch-trial-'):
        raise ValueError('Exact distinct batch trial package required')
    if not re.fullmatch('[a-f0-9]{64}',expected_manifest_sha256) or b.sha(mp)!=expected_manifest_sha256:
        raise ValueError('Separately retained manifest digest differs')
    m=json.loads(mp.read_bytes());pins=m['inputs_sha256'];generated=m['generated_sha256']
    if set(generated)!={str(p) for p in package.rglob('*') if p.is_file() and p!=mp}:raise ValueError('Complete generated closure differs')
    for path,digest in [*pins.items(),*generated.items()]:
        if not re.fullmatch('[a-f0-9]{64}',digest) or b.sha(path)!=digest:raise ValueError('Consumed bytes changed: '+path)
    for p in b.sources():
        if pins.get(str(p.resolve()))!=b.sha(p):raise ValueError('Required source recipe omitted')
    parent,cap=b.parents()
    for directory,value in ((b.BASE,parent),(b.CAP,cap)):
        if pins.get(str(directory/'manifest.json'))!=b.sha(directory/'manifest.json'):raise ValueError('Parent pin omitted')
        for key in ('inputs_sha256','actual_headers_sha256','generated_sha256'):
            if any(pins.get(p)!=h for p,h in value.get(key,{}).items()):raise ValueError('Inherited source closure omitted')
    if pins.get(str(b.secure.FIRMWARE_BIN))!=b.secure.FIRMWARE_SHA or pins.get(str(b.secure.FIRMWARE/'manifest.json'))!=b.secure.FIRMWARE_MANIFEST_SHA:
        raise ValueError('Exact secure owner firmware missing')
    if not re.fullmatch('[a-f0-9]{32}',m['tag']):raise ValueError('Unique tag required')
    completeness=canonical.inspect(package,m)
    objects,replacements,extras,added=b.kernel_objects(package)
    mapped=(package/'kernel.map').read_text(errors='surrogateescape')
    if any(p not in mapped for p in [*replacements.values(),*extras,*added]) or any(p in mapped for p in replacements):
        raise ValueError('Actual linked object ownership differs')
    kernel=package/'kernel.cpu-rings';rawkernel=kernel.read_bytes();symbols,segments=binary.macho(rawkernel)
    required=('_rpi5_boot_reservation_record','_rpi5_reservation_kernel_validate','_rpi5_reservation_record_validate_fdt',
        '_rpi5_gem_ring_batch','_rpi5_pcie_id_trial_start','_rpi5_display_xnu_mapping_verify','_rpi5_console_mirror_publish')
    if any(p not in symbols for p in required) or not any('prepareCPUOwnedRings' in s for s in symbols) or not any('stageCPUOwned' in s for s in symbols):
        raise ValueError('Actual genuine ownership/caller/ring implementation absent')
    formats=re.findall(r'kprintf\("([^"\n]+)"',b.profile.derive()['BCM2712PCIeIDTrialProgress.inc'].decode())
    if (len(formats)!=52 or any(rawkernel.count(ast.literal_eval('"'+fmt+'"').encode()+b'\0')!=1 for fmt in formats) or
        any(len(re.findall(r'%(?!%)',fmt))>16 for fmt in formats) or
        any(len(re.findall(r'%(?!%)',fmt))>8 for fmt in formats[-6:-1])):
        raise ValueError('Actual complete bounded52-row encoder formats differ')
    if not same(b.leaf.inspect((package/'provider.o').read_bytes()),m['actual_batch_leaf']) or \
        not same(b.leaf.allocation_guard((package/'transport.o').read_bytes()),m['actual_nullable_new']):
        raise ValueError('Actual fixed batch or OOM control flow differs')
    oldpayload=(b.BASE/'payload.bin').read_bytes();off,n=struct.unpack_from('<QQ',oldpayload,136);root=oldpayload[off:off+n]
    payload=b.old.payload_container.encode(rawkernel,root)
    raw=(package/'probe.bin').read_bytes();elf=binary.elf((package/'cpu_rings.elf').read_bytes(),raw)
    # llvm-nm omits ELF STT_FILE records and ARM mapping symbols, not code/data.
    named={k:v[0] for k,v in elf.items() if (v[2]&15)!=4 and not k.startswith('$')}
    if not same(named,m['loader_symbols']) or 'rpi5_psci_cpu_on' in elf:
        raise ValueError('Actual loader symbol or CPU_ON scope differs')
    marker=b.profile.marker(m['tag'])
    if raw.count(marker.encode())!=1 or raw.count((b.profile.BOOTARGS+'\0').encode())!=1 or b'bcm2712_cpu_on_all=1' in raw:
        raise ValueError('Actual unique single-CPU image identity differs')
    for name in ('rpi5_reservation_record_finalize','rpi5_reservation_record_make','rpi5_reservation_record_tree_commit',
                 'rpi5_rp1_device_handoff'):
        if name not in elf:raise ValueError('Actual loader record producer absent')
    if raw.count((contract.DEVICE+'\r\n\0').encode())!=1:raise ValueError('Exact six-page RP1 declaration absent')
    page,size,_=elf['display_pages'];end=elf['__probe_end'][0]
    if page%4096 or size!=16384 or not 0x9000000<=page<page+size<=end<0xb000000 or elf['__stack_top'][0]-elf['__bss_end'][0]!=32768:
        raise ValueError('Actual loader/display/retained-FDT geometry differs')
    # Compare immutable architectural transition bytes to accepted linked EL2
    # owner. This includes HCR.RW with VM/DC/E2H clear and VTTBR0, not merely
    # EL1 SCTLR. The two boundary symbols include only unchanged entry assembly.
    accepted=(b.BASE/'probe.bin').read_bytes();aelf=binary.elf((b.BASE/'display_xnu.elf').read_bytes(),accepted)
    for begin,finish in (('probe_enter_el1','probe_el1_entry'),):
        start,stop=elf[begin][0]-0x9000000,elf[finish][0]-0x9000000
        oldstart,oldstop=aelf[begin][0]-0x9000000,aelf[finish][0]-0x9000000
        if raw[start:stop]!=accepted[oldstart:oldstop]:raise ValueError('Actual EL2-to-EL1 architecture differs')
    at=m['payload_offset']
    if type(at) is not int or at%64 or raw.find(payload)!=at or raw[at:at+len(payload)]!=payload or raw.find(payload,at+1)>=0:
        raise ValueError('Actual payload embedding differs')
    stackfiles={name:package/(('loader-' if name in ('reservation_record','reservation_record_tree') else 'stack-')+name+'.su') for name in b.old.record.STACK_UNITS}
    stack=b.old.record.stack_budget(stackfiles,package/'loader-probe_main.su',package/'loader-firmware_seed_tree.su')
    true=('sameboot_loader_kernel_reservation','real_sleepable_apple_preparation','real_fresh_controller_caller',
        'cpu_owned_descriptors_only','all_inbound_windows_disabled','candidate_addresses_not_dma_authority','native_model_not_hardware_guarantee')
    false=('queue_publication','bme_enable','dma_activation','irq_activation','hardware_executed','staged')
    exact={'profile':b.PROFILE,'trial_marker':marker,'bootargs':b.profile.BOOTARGS,'parent_manifest_sha256':b.BASE_SHA,
        'capability_manifest_sha256':b.CAP_SHA,'kernel':str(kernel),'kernel_sha256':b.sha(kernel),'kernel_bytes':len(rawkernel),
        'image':str(package/'probe.bin'),'image_sha256':b.sha(package/'probe.bin'),'image_bytes':len(raw),
        'root_bytes':len(root),'root_sha256':hashlib.sha256(root).hexdigest(),'firmware':str(b.secure.FIRMWARE_BIN),
        'firmware_sha256':b.secure.FIRMWARE_SHA,'reservation_stack_budget':stack,
        'owner_check_limit':65536,'modeled_owner_checks':64940,'modeled_firmware_sequence':16233,
        'firmware_guard_seconds':10,'ns_guard_seconds':9,'pm_guard_seconds':12,'watchdog_seconds':15,
        'copy_max_renewals':2,'copy_outer_seconds':60,'ring_deadline_us':500000,
        'ring_expected_writes':640,'ring_expected_reads':640,'ring_expected_current':164}
    if any(m.get(k) is not True for k in true) or any(m.get(k) is not False for k in false) or any(not same(m.get(k),v) for k,v in exact.items()):
        raise ValueError('Exact typed CPU-only trial contract differs')
    envelope=max(va+memory for va,memory,_,_,_ in segments)-min(va for va,memory,_,_,_ in segments if memory)
    args_pa=(0x7004000+envelope+16383)&~16383;root_pa=args_pa+0x8000
    if root_pa+len(root)>0x9000000 or end>=0xb000000:raise ValueError('Live kernel/root/loader/FDT overlap')
    root_marker=f'RPI5XNU:BL33:RAMDISK_MATERIALIZED PA={root_pa:016x} BYTES={len(root):016x} VERIFIED'
    kernel_marker=f'RPI5XNU:BL33:KERNEL_MATERIALIZED BYTES={envelope:016x} FULL_ENVELOPE_VERIFIED NO_BOOT_ARGS_WRITTEN NO_TRANSFER'
    return dict(profile=b.PROFILE,package=str(package),manifest_sha256=expected_manifest_sha256,
        image_sha256=m['image_sha256'],kernel_sha256=m['kernel_sha256'],firmware_sha256=b.secure.FIRMWARE_SHA,
        image_bytes=len(raw),tag=m['tag'],marker=marker,trial_marker=marker,bootargs=b.profile.BOOTARGS,
        kernel_copy_marker=kernel_marker,root_copy_marker=root_marker,
        boot_markers=[marker,contract.HOST,contract.DEVICE,contract.FDT,root_marker,kernel_marker],
        cpu_ring_contract=contract.contract(),inherited_capability_contracts=contract.inherited(),
        actual_loader_end=end,loader_stack=stack['conservative_bytes'],source_members=len(pins),generated_members=len(generated),
        canonical_commands=completeness['canonical_commands'],canonical_compiles=completeness['canonical_compile_labels'],cpu_owned_only=True,
        dma_reachability_qualified=False,queue_publication=False,hardware_execution=False,
        kernel_live_stack_audit_required=True,early_kernel_stack_audit_required=True)

def inspect(package,expected_manifest_sha256,qualification,qualification_sha256):
    from tools.rpi5 import qualify_gem_dma_batch_trial as stack
    result=inspect_image(package,expected_manifest_sha256)
    receipt=stack.inspect(package,expected_manifest_sha256,qualification,qualification_sha256)
    result.update(target_stack=receipt,qualification=str(Path(qualification).resolve()),
        qualification_sha256=qualification_sha256,kernel_live_stack_audit_required=False,
        early_kernel_stack_audit_required=False,software_trial_qualified=True,
        physical_execution_proven=False)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path);p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--qualification',type=Path,required=True);p.add_argument('--qualification-sha256',required=True)
    p.add_argument('--report',type=Path)
    a=p.parse_args();result=inspect(a.package,a.manifest_sha256,a.qualification,a.qualification_sha256)
    if a.report:
        target=a.report.resolve()
        if b.ROOT/'build/rpi5' not in target.parents or a.package.resolve() in target.parents:
            raise ValueError('Separate project build report required')
        with target.open('x') as output:output.write(json.dumps(result,sort_keys=True,indent=2)+'\n')
        print(json.dumps(dict(report=str(target),report_sha256=b.sha(target),software_trial_qualified=True)))
    else:print(json.dumps(result,sort_keys=True,indent=2))
