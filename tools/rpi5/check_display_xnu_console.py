#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only linked same-boot display admission. No compiler, subprocess or hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from . import build_display_xnu_console as b
def exact(a,c):return json.dumps(a,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(c,sort_keys=True,separators=(',',':'),allow_nan=False)
def elf(data,raw):
    def get(fmt,offset):
        if offset<0 or offset+struct.calcsize(fmt)>len(data):raise ValueError('Truncated ELF')
        return struct.unpack_from(fmt,data,offset)
    if data[:7]!=b'\x7fELF\x02\x01\x01':raise ValueError('Invalid ELF identity')
    kind,machine,version,entry,phoff,shoff,flags,ehsize,phsize,phnum,shsize,shnum,names=get('<HHIQQQIHHHHHH',16)
    if (kind,machine,version,entry,ehsize,phsize,shsize)!=(2,183,1,0x9000000,64,56,64):raise ValueError('Invalid ELF ABI')
    loads=[]
    for i in range(phnum):
        typ,perms,off,va,pa,size,memory,align=get('<IIQQQQQQ',phoff+i*56)
        if typ in (2,3):raise ValueError('Dynamic ELF prohibited')
        if typ!=1:continue
        if not memory or size>memory or off+size>len(data) or va!=pa or pa<entry or pa+memory>0xb000000 or perms&3==3:raise ValueError('Invalid ELF extent')
        if size and raw[pa-entry:pa-entry+size]!=data[off:off+size]:raise ValueError('ELF/raw bytes differ')
        loads.append((pa,size,memory,perms))
    loads.sort()
    if not loads or len(raw)!=max(pa+size for pa,size,_,_ in loads if size)-entry or not any(pa<=entry<pa+size and perms&1 for pa,size,_,perms in loads):raise ValueError('Invalid raw entry/extent')
    if any(a[0]+a[2]>c[0] for a,c in zip(loads,loads[1:])):raise ValueError('ELF loads overlap')
    sections=[get('<IIQQQQIIQQ',shoff+i*64) for i in range(shnum)];symbols={}
    for section in sections:
        _,typ,_,_,off,size,link,_,_,stride=section
        if off+size>len(data) and typ!=8:raise ValueError('ELF section outside image')
        if typ in (4,9) and size:raise ValueError('ELF relocations remain')
        if typ!=2:continue
        if stride!=24 or size%24:raise ValueError('Invalid symbol table')
        string=sections[link];table=data[string[4]:string[4]+string[5]]
        for position in range(off+24,off+size,24):
            name,info,other,index,value,length=get('<IBBHQQ',position)
            if not index:raise ValueError('Undefined ELF symbol')
            label=table[name:table.index(b'\0',name)].decode();symbols[label]=(value,length,info)
    if not symbols:raise ValueError('No ELF symbols')
    return symbols
def macho(data):
    if data[:4]!=b'\xcf\xfa\xed\xfe' or struct.unpack_from('<I',data,4)[0]!=0x100000c:raise ValueError('Not AArch64 Mach-O')
    count,bytes_=struct.unpack_from('<II',data,16);offset=32;symbols={};segments=[];symtab=None
    if offset+bytes_>len(data):raise ValueError('Mach-O load commands truncated')
    for _ in range(count):
        cmd,size=struct.unpack_from('<II',data,offset)
        if size<8 or offset+size>32+bytes_:raise ValueError('Bad Mach-O command')
        if cmd==2:symtab=struct.unpack_from('<IIII',data,offset+8)
        if cmd==0x19:
            name,va,memory,file,size_,maxprot,prot,sections,flags=struct.unpack_from('<16sQQQQIIII',data,offset+8)
            if file+size_>len(data):raise ValueError('Mach-O segment truncated')
            segments.append((va,memory,file,size_,prot))
        offset+=size
    if offset!=32+bytes_ or symtab is None:raise ValueError('Missing Mach-O symbol table')
    off,count,strings,size=symtab
    if off+16*count>len(data) or strings+size>len(data):raise ValueError('Mach-O symbols truncated')
    table=data[strings:strings+size]
    for i in range(count):
        name,typ,section,desc,value=struct.unpack_from('<IBBHQ',data,off+16*i)
        if not name:continue
        label=table[name:table.index(b'\0',name)].decode(errors='surrogateescape')
        if typ&1 and not typ&0x0e:raise ValueError('Undefined Mach-O symbol '+label)
        symbols[label]=value
    return symbols,segments
def inspect(package,expected_manifest_sha256=None):
    package=Path(package).resolve();mp=package/'manifest.json'
    if package.parent!=b.ROOT/'build/rpi5' or not package.name.startswith('display-xnu-console-'):raise ValueError('Distinct linked package required')
    if expected_manifest_sha256 is not None and b.sha(mp)!=expected_manifest_sha256:raise ValueError('Manifest pin differs')
    m=json.loads(mp.read_text());pins=m.get('inputs_sha256',{});generated=m.get('generated_sha256',{})
    if not pins or not generated or set(generated)!={str(p) for p in package.iterdir() if p.is_file() and p.name!='manifest.json'}:raise ValueError('Output closure differs')
    for name,digest in {**pins,**generated}.items():
        if not re.fullmatch('[a-f0-9]{64}',digest) or b.sha(name)!=digest:raise ValueError('Consumed bytes differ '+name)
    for path in (Path(__file__),Path(b.__file__),Path(b.overlay.__file__),b.ROOT/'osfmk/arm64/rpi5_display_xnu_api.h',
        b.ROOT/'loader/rpi5/display_xnu_record.h',b.ROOT/'loader/rpi5/display_xnu_handoff.c',b.ROOT/'loader/rpi5/display_xnu_allocate.h'):
        if pins.get(str(path.resolve()))!=b.sha(path):raise ValueError('Required source absent')
    for directory,digest in ((b.KERNEL,b.KERNEL_SHA),(b.LOADER,b.LOADER_SHA)):
        parent=directory/'manifest.json'
        if pins.get(str(parent))!=digest:raise ValueError('Wrong typed parent bytes')
        report=json.loads(parent.read_text())
        for key in ('inputs_sha256','generated_sha256'):
            for name,value in report[key].items():
                if pins.get(name)!=value:raise ValueError('Inherited closure omitted '+name)
    sources=(('serial_console',b.ROOT/'osfmk/console/serial_console.c',b.overlay.serial),
        ('video_console',b.ROOT/'osfmk/console/video_console.c',b.overlay.video),
        ('pmap',b.ROOT/'osfmk/arm/pmap/pmap.c',b.overlay.pmap),('arm_init',b.overlay.ARM,b.overlay.arm),
        ('probe_main',b.overlay.LOADER,b.overlay.loader),('firmware_seed_tree',b.overlay.SEED,b.overlay.seed),
        ('display_xnu_allocate',b.overlay.ALLOCATOR,b.overlay.allocator))
    for name,original,transform in sources:
        if (package/(name+'.c')).read_text()!=transform(original.read_text()):raise ValueError('Exact source overlay differs '+name)
    tag=m.get('tag','')
    if not re.fullmatch('[a-f0-9]{32}',tag):raise ValueError('Distinct actual package tag required')
    expected_commands,expected_scans,expected_replacement=b.command_plan(package,tag)
    actual=[(Path(r['log']).stem,r['command'],r['cwd']) for r in m['commands']]
    if not exact(actual,expected_commands) or set(m['compiler_scans'])!=set(expected_scans) or not exact(m['replaced_objects'],expected_replacement):raise ValueError('Exact compiler/link command or object/scan set differs')
    if any(r['returncode']!=0 or r['log']!=str(package/(label+'.log')) or r['log_sha256']!=b.sha(r['log']) for r,(label,_,_) in zip(m['commands'],expected_commands)):raise ValueError('Actual build receipt differs')
    headers={}
    for label,names in m['compiler_scans'].items():
        row=next(r for r in m['commands'] if r['log'].endswith('/'+label+'-compile.log'))
        before=b.dependencies(package/(label+'.scan.d'),row['cwd']);after=b.dependencies(package/(label+'.actual.d'),row['cwd'])
        if before!=after or sorted(before)!=names:raise ValueError('Actual compiler dependencies differ')
        for name in before:
            if name not in pins:raise ValueError('Unpinned actual dependency')
            headers[name]=pins[name]
    if not exact(headers,m['actual_headers_sha256']):raise ValueError('Header closure omitted')
    kernel=package/'kernel.display-console';raw_kernel=kernel.read_bytes();kernel_symbols,segments=macho(raw_kernel)
    envelope=max(va+memory for va,memory,_,_,_ in segments)-min(va for va,memory,_,_,_ in segments if memory)
    args_pa=(0x7004000+envelope+16383)&~16383;root_pa=args_pa+0x8000
    for symbol in ('_rpi5_display_xnu_mapping_verify','_rpi5_display_xnu_video_admit','_rpi5_display_xnu_mirror_started',
        '_rpi5_console_mirror_publish','_initialize_screen','_iso_font'):
        if symbol not in kernel_symbols:raise ValueError('Linked kernel owner absent '+symbol)
    original_objects=(b.KERNEL/'kernel.root-confirmed.filelist').read_text().splitlines();selected=m['replaced_objects']
    if len(selected)!=4 or any(original_objects.count(s)!=1 for s in selected):raise ValueError('Kernel replacement boundary differs')
    expected=''.join(str(selected.get(p,p))+'\n' for p in original_objects)
    if (package/'kernel.display.filelist').read_text()!=expected:raise ValueError('Actual link filelist differs')
    mapped=(package/'kernel.map').read_text(errors='surrogateescape')
    if any(str(path) not in mapped for path in selected.values()) or any(path in mapped for path in selected):raise ValueError('Actual linkmap replacement differs')
    image=package/'probe.bin';raw=image.read_bytes();symbols=elf((package/'display_xnu.elf').read_bytes(),raw)
    marker=('RPI5XNU:DISPLAYXNU:ENTRY TAG='+tag+' SAME_BOOT OWNED_FRAMEBUFFER_CONSOLE_V1').encode()
    if raw.count(marker)!=1 or raw_kernel.count(b'RPI5XNU:DISPLAYXNU:MIRROR_READY NORMAL_NC NX UART_FIRST INPUT_UART ONLY_MAPPING_RETAINED_UNTIL_RESET')!=1:raise ValueError('Actual unique tagged/readiness markers differ')
    if any(symbols.get(name,(None,))[0]!=value for name,value in m['loader_symbols'].items()):raise ValueError('Actual ELF symbols differ')
    packed=(package/'payload.bin').read_bytes()
    if packed[:8]!=b'RPI5XNU\0' or struct.unpack_from('<II',packed,8)!=(1,64) or struct.unpack_from('<I',packed,24)[0]!=2:raise ValueError('Payload header differs')
    for index in range(2):
        kind,flags,off,size,digest,zero=struct.unpack_from('<IIQQ32sQ',packed,64+64*index)
        data=packed[off:off+size]
        if (kind,flags,zero)!=(index+1,0,0) or off%64 or len(data)!=size or hashlib.sha256(data).digest()!=digest:raise ValueError('Payload record differs')
        if index==0 and data!=raw_kernel:raise ValueError('Embedded kernel is not linked kernel')
        if index==1 and (size!=1916928 or digest.hex()!=b.ROOT_SHA):raise ValueError('Operational zsh root differs')
    if hashlib.sha256(packed[64:192]).digest()!=packed[32:64] or struct.unpack_from('<Q',packed,16)[0]!=len(packed):raise ValueError('Payload envelope differs')
    offset=m['payload_offset']
    if offset%64 or raw[offset:offset+len(packed)]!=packed or raw.find(packed)!=offset or raw.find(packed,offset+1)>=0:raise ValueError('Actual embedded payload differs')
    page,size,info=symbols['display_pages'];live=symbols['__probe_end'][0]
    if page%4096 or size!=16384 or not 0x9000000<=page<page+size<=live<0xb000000 or symbols['__stack_top'][0]-symbols['__bss_end'][0]!=32768:raise ValueError('Linked lifetime/storage/stack differs')
    # Exact immutable architectural leaf bytes, copied implementation only.
    leaves={'rpi5_display_query_identity':(0xd65f03c0,), 'rpi5_display_query_counter':(0xd5033fdf,0xd53be040,0xd65f03c0),
        'rpi5_display_query_read':(0xd5033f9f,0xb9400000,0xd5033f9f,0xd65f03c0),
        'rpi5_display_query_write':(0xd5033f9f,0xb9000001,0xd5033f9f,0xd65f03c0)}
    for name,words in leaves.items():
        address,size,_=symbols[name];expected=struct.pack('<'+'I'*len(words),*words)
        if size!=len(expected) or raw[address-0x9000000:address-0x9000000+size]!=expected:raise ValueError('Actual architecture leaf differs '+name)
    budget=b.stack_budget(package,json.loads((b.LOADER/'manifest.json').read_text()))
    checks=dict(exact_profile=m.get('profile')=='pi5-display-xnu-sameboot-console-v1',full_source_byte_closure=True,
        actual_headers_bound=True,exact_four_kernel_object_replacement=True,actual_kernel_and_zsh_embedded=True,
        exact_sameboot_allocation_overlay=True,exact_original_fdt_owner_and_top=True,
        fixed_managed_span=exact(m.get('managed_span'),[0x6000000,0x10000000]),
        exact_image=m.get('image')==str(image) and m.get('image_sha256')==b.sha(image) and exact(m.get('image_bytes'),len(raw)),
        exact_kernel=m.get('kernel')==str(kernel) and m.get('kernel_sha256')==b.sha(kernel),
        no_hardware_claim=all(m.get(k) is False for k in ('physical_execution','installed','scanout_proven','global_feature_macro_changed','release','loader_framebuffer_access')),
        exact_stack=exact(m.get('stack_budget'),budget),
        bounded_mapping_lifetime=m.get('published_mapping_retained_until_reset') is True and m.get('late_descriptor_or_mapping_replacement_prohibited') is True,
        normal_nc_nx_live_pte_audit='mrs %0, mair_el1' in (package/'pmap.c').read_text() and 'ARM_PTE_AP(AP_RWNA)' in (package/'pmap.c').read_text(),
        mirror_ready_after_actual_screen_acquire=m.get('mirror_enable_after_initialize_screen') is True,
        uart_first_input_unchanged=m.get('uart_first') is True and m.get('uart_input_unchanged') is True,
        no_allocator_reuse_or_release=m.get('matched_allocation_required') is True and exact(m.get('allocation_requests_max'),4))
    watchdog=b.KERNEL/'pe_fiq.o';objects=(package/'kernel.display.filelist').read_text().splitlines()
    checks['unchanged_bounded_watchdog']=objects.count(str(watchdog))==1 and str(watchdog) not in selected and \
        m.get('original_watchdog_object_unchanged') is True and exact(m.get('terminal_watchdog_seconds'),180) and \
        exact(m.get('watchdog_countdown_seconds'),15) and m.get('watchdog_deadline_extended') is False
    if not all(checks.values()):raise ValueError('Linked display checks failed '+','.join(k for k,v in checks.items() if not v))
    contract=dict(package=str(package),image=str(image),image_bytes=len(raw),tag=tag,trial_marker=marker.decode(),
        root_bytes=1916928,root_nodes=32,root_sha256=b.ROOT_SHA,
        root_catalog=str(package/'root-catalog.json'),root_catalog_sha256=b.sha(package/'root-catalog.json'),
        root_copy_marker=f'RPI5XNU:BL33:RAMDISK_MATERIALIZED PA={root_pa:016x} BYTES={1916928:016x} VERIFIED',
        kernel_copy_marker=f'RPI5XNU:BL33:KERNEL_MATERIALIZED BYTES={envelope:016x} FULL_ENVELOPE_VERIFIED NO_BOOT_ARGS_WRITTEN NO_TRANSFER',
        root_mount_marker='RPI5XNU:RAMROOT:MOUNT NODES=32 BYTES=1916928 READONLY',
        watchdog_ready_marker='RPI5XNU:TERMINAL:WATCHDOG_READY SECONDS=180',
        watchdog_ready_profile='root42-state-confirmed-watchdog-kernel-v1',terminal_watchdog_seconds=180,watchdog_hardware_timeout_seconds=15,
        root_ready_marker='RPI5XNU:TERMINAL:ROOT_READY SECONDS=180 NODES=32 BYTES=1916928 READONLY',root_ready_max_reports=3,
        root_ready_requires_mounted_readonly=True,root_ready_requires_successful_reload=True,
        mirror_ready_marker='RPI5XNU:DISPLAYXNU:MIRROR_READY NORMAL_NC NX UART_FIRST INPUT_UART ONLY_MAPPING_RETAINED_UNTIL_RESET',
        required_normal_firmware_sha256='413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46',
        handoff=dict(required_by_kernel=True,linked_loader_handoff=True,descriptor_not_confused_with_kernel_string=True,
            same_boot_owned_allocation=True,managed_span_unchanged=True,normal_nc_nx_actual_pte_verified=True,old_mapping_retained_until_reset=True),
        allocation_complete_marker='RPI5XNU:DISPLAYXNU:ALLOCATE RC=0000000000000000 COMPLETED=000000000000000f QUARANTINED=0000000000000000',
        allocation_owned_prefix='RPI5XNU:DISPLAYXNU:OWNED START=',
        display_handoff_marker='RPI5XNU:DISPLAYXNU:HANDOFF VIDEO_PHYSICAL NORMAL_NC_NX REQUIRED UART_FIRST')
    catalog=json.loads((package/'root-catalog.json').read_text())
    if catalog.get('sha256')!=b.ROOT_SHA or catalog.get('size')!=1916928 or len(catalog.get('entries',[]))!=32:raise ValueError('Root catalog differs')
    return dict(profile=m['profile'],manifest_sha256=b.sha(mp),image_sha256=b.sha(image),kernel_sha256=b.sha(kernel),
        checks=checks,source_members=len(pins),generated_members=len(generated),stack_budget=budget['conservative_bytes'],
        actual_loader_end=live,physical_visibility_proven=False,**contract)
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('package',type=Path);parser.add_argument('--manifest-sha256')
    args=parser.parse_args();print(json.dumps(inspect(args.package,args.manifest_sha256),sort_keys=True))
