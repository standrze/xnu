#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct Fixed32 allocation/verification standalone BL33; build only, never publishes or uses hardware."""
import ast
import hashlib
import importlib
import json
import re
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import uuid
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/rpi5'))
elf_inspector=importlib.import_module('build_probe')
BASE=0x9000000
PROFILE='pi5-display-compact-standalone-v1'
SOURCES=tuple(ROOT/'loader/rpi5'/s for s in ('probe_entry.S','probe_display_compact_main.c',
    'display_allocate_zero_adapter.c','display_compact_adapter.c','display_compact_patch.c','display_allocation_retained.c','display_compact_arch.S','display_query_arch.S','display_allocate_wire.c','display_mailbox_fdt.c',
    'display_allocate_transaction.c','access_mmio.S','uart.c','psci.S','fdt.c','fdt_reg.c','ranges.c','memory.S'))+(ROOT/'osfmk/console/iso_font.c',)
FILES=tuple(ROOT/p for p in ('tools/rpi5/build_display_compact_package.py','tools/rpi5/check_display_compact_package.py',
    'tools/rpi5/display_compact_serial.py','tools/rpi5/display_allocate_zero_serial.py','tools/rpi5/tests/test_display_compact_package.py',
    'tools/rpi5/tests/test_display_compact_serial.py','tools/rpi5/tests/test_display_allocate_zero_adapter.py',
    'tools/rpi5/tests/display_allocate_zero_adapter_host.c','tools/rpi5/tests/test_display_compact_patch.py','tools/rpi5/tests/display_compact_patch_host.c','tools/rpi5/tests/test_display_compact_adapter.py','tools/rpi5/tests/display_compact_adapter_host.c','tools/rpi5/tests/test_display_mailbox_fdt.py',
    'tools/rpi5/tests/test_pcie_fdt.py','tools/rpi5/tests/test_display_allocate_wire.py','tools/rpi5/tests/display_allocate_wire_host.c',
    'tools/rpi5/tests/test_display_mailbox_transaction.py','tools/rpi5/tests/display_mailbox_transaction_host.c',
    'loader/rpi5/display_query.ld','tools/rpi5/tfa-lld','tools/rpi5/tfa-objcopy','tools/rpi5/loader-toolchain.lock.json',
    'tools/rpi5/tfa.lock.json'))
FALSE_FIELDS=('physical_execution','installed','xnu_transfer','kernel_embedded','root_embedded','cpu_on_called',
    'framebuffer_access','framebuffer_allocation','framebuffer_mapping','drawing','mirror_enabled',
    'framebuffer_ownership_proven','scanout_cache_contract_proven','hardware_recovery_proven','reset_destination_proven')
FW=ROOT/'build/rpi5/tfa-candidate'
FW_REVISION='332b62e0443b004287d2cfc032a70bba6fb86f35'
FW_SHA='413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46'
def authority_inputs():
    result=[]
    for name in ('display_mailbox_get_sources.json','display_mailbox_fdt_sources.json','display_mailbox_transaction_sources.json','display_allocate_zero_sources.json'):
        path=ROOT/'tools/rpi5'/name;result.append(path)
        data=json.loads(path.read_text())
        for row in data['sources']:
            p=ROOT/data.get('directory',data.get('preserved_source_directory',''))/row['path']
            if sha(p)!=row['sha256'] or ('bytes' in row and p.stat().st_size!=row['bytes']):raise ValueError('Primary source bytes differ')
            result.append(p)
    if subprocess.check_output(['git','-C',str(FW),'rev-parse','HEAD'],text=True).strip()!=FW_REVISION or \
       subprocess.check_output(['git','-C',str(FW),'status','--porcelain'],text=True).strip():raise ValueError('Normal TF-A source lineage changed')
    binary=FW/'build/rpi5/debug/bl31.bin'
    if sha(binary)!=FW_SHA:raise ValueError('Normal firmware differs')
    names=subprocess.check_output(['git','-C',str(FW),'ls-files','-z']).decode().split('\0')[:-1]
    result.extend(FW/n for n in names if (FW/n).is_file())
    result.extend(p for p in (FW/'build/rpi5/debug').rglob('*') if p.is_file() and p.suffix in ('.o','.a','.d','.bin','.elf','.map'))
    make=(FW/'plat/rpi/rpi5/platform.mk').read_text()
    common=(FW/'plat/rpi/common/rpi3_common.c').read_text()
    if any(re.findall(r'^'+key+r'\s*:=\s*(\d+)\s*$',make,re.M)!=[value] for key,value in
        (('RESET_TO_BL31','1'),('COLD_BOOT_SINGLE_CPU','0'),('RPI3_DIRECT_LINUX_BOOT','1'))):raise ValueError('Firmware reset entry differs')
    if 'rpi3_mbox' in make or 'rpi_mbox' in make:raise ValueError('Unexpected firmware property mailbox client')
    image31=common[common.index('#ifdef IMAGE_BL31'):common.index('/*******************************************************************************')]
    if 'MAP_NS_DRAM0,' in image31:raise ValueError('Unexpected secure cached DRAM alias')
    maptext=(FW/'build/rpi5/debug/bl31/bl31.map').read_text()
    if any(x in maptext for x in ('rpi3_mbox','rpi_mbox_board','bcm2835_mailbox')):raise ValueError('Linked firmware mailbox client')
    return sorted(set(result))
def contract():
    return dict(normal_firmware_sha256=FW_SHA,normal_firmware_revision=FW_REVISION,
        direct_reset_to_bl31_required=True,original_x0_fdt_required=True,
        no_prior_arm_mailbox_client_lineage_required=True,empty_fifo_is_not_prior_request_proof=True,
        other_cores_off_required=True,interrupts_masked=True,no_cpu_on=True,
        el1_identity_mmu_dcache_icache_off=True,el2_hcr_exact=0x80000000,vttbr_el2=0,
        page_bytes=4096,page_count=4,cpu_cache_line_bytes=64,buffer_limit_exclusive=1<<32,
        exclude_entire_secure_fdt_mapping_bytes=0x400000,
        explicit_cache_operations='initial IVAC, publish CVAC, acquire IVAC; full4096B and DSB SY',
        mailbox_channel=8,max_tx=4,max_polls=512,max_callbacks=4096,deadline_us=1000000,
        sequence=['GET COUNT+SETTINGS0','SET DISPLAY0','fixed SET+ALLOCATE+GET pitch','GET complete verification'],
        live_preboot_width=1920,live_preboot_height=1080,live_preboot_depth=32,live_preboot_pitch=7680,
        configuration_requirement='Separately reviewed preboot framebuffer_depth=32; no runtime16-to32 fallback',
        requested_pixel_order=0,requested_alpha_mode=2,requested_alignment=16384,
        source_backed_alias_mask=0xc0000000,accepted_alias=0,address_representation='matched-allocate-reply-top-bits-zero-only',
        allocation_range='Fresh lowRAM end to1GiB hole, exact allocate extent; no fixed/live overlap',
        peek_before_matching_pop=True,foreign_reply_never_popped=True,no_retry=True,no_release=True,
        buffer_lifetime='entire image and possible framebuffer allocation retained until reset on every outcome',
        framebuffer_memory_access=False,drawing=False,xnu_handoff=False,
        allocation_requests_authored=True,physical_allocation_proven=False,
        caveat='Reported geometry/format/extent only; no independent scanout, alpha or mapping proof')
def visible_contract():
    return dict(x=16,y=16,width=96,height=8,stride=7680,stores=768,store_bits=32,
        framebuffer_reads=0,draw_deadline_us=500000,global_software_deadline_required=True,
        zero_opaque_alpha_halves=True,pixel_layout='PI5 glyphs24px + RGB strips3x8px in each48px half',font_row_step=2,font='unchanged Apple osfmk/console/iso_font.c',
        same_boot_allocator_required=True,fresh_fdt_required=True,mmu_cache_off_required=True,
        no_mapping=True,no_retry=True,no_release=True,retain_full_allocation_until_reset=True,
        physical_visual_confirmation_required=True,xnu_handoff=False)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def deps(p):
    tokens=shlex.split(Path(p).read_text().replace('\\\n',' '))
    if not tokens or not tokens[0].endswith(':'):raise ValueError('Invalid actual dependency document')
    return sorted({str((ROOT/t).resolve()) for t in tokens[1:]})
def imported():
    # Fixed source graph of the actual reused ELF inspector. Other unrelated
    # modules loaded by a caller never expand this package's authority/closure.
    todo=[ROOT/'tools/rpi5/build_probe.py'];found=set()
    while todo:
        path=todo.pop().resolve()
        if str(path) in found:continue
        found.add(str(path))
        for node in ast.walk(ast.parse(path.read_text())):
            names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.module else []
            for name in names:
                candidate=ROOT/'tools/rpi5'/(name+'.py')
                if candidate.is_file():todo.append(candidate)
    return sorted(found)
def tools():
    return dict(clang=subprocess.check_output(['xcrun','--find','clang'],text=True).strip(),
        nm=subprocess.check_output(['xcrun','--find','llvm-nm'],text=True).strip(),
        objdump=subprocess.check_output(['xcrun','--find','llvm-objdump'],text=True).strip(),
        linker=str(ROOT/'tools/rpi5/tfa-lld'),objcopy=str(ROOT/'tools/rpi5/tfa-objcopy'),
        zig=str(ROOT/'build/rpi5/zig-aarch64-macos-0.16.0/zig'))
def commands(out,tag,t):
    rows=[];objects=[]
    for source in SOURCES:
        label=source.stem;obj=out/(label+'.o');objects.append(obj)
        flags=[t['clang'],'--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align','-ffreestanding',
            '-fno-builtin','-fno-stack-protector','-mgeneral-regs-only','-O2','-Wall','-Wextra','-Werror',
            '-ffunction-sections','-fdata-sections',f'-DRPI5_DISPLAY_COMPACT_TAG="{tag}"']
        if source.suffix=='.c':flags+=['-std=c11','-fstack-usage']
        rows.extend([(label+'-scan',[*flags,'-M','-MF',str(out/(label+'.scan.d')),str(source)]),
            (label+'-compile',[*flags,'-c','-MD','-MF',str(out/(label+'.actual.d')),str(source),'-o',str(obj)])])
    rows.extend([('link',[t['linker'],'--gc-sections',f'--defsym=LOADER_BASE={hex(BASE)}','-T',str(ROOT/'loader/rpi5/display_query.ld'),
        *map(str,objects),'-o',str(out/'probe.elf')]),('objcopy',[t['objcopy'],'-O','binary',str(out/'probe.elf'),str(out/'probe.bin')]),
        ('symbols',[t['nm'],'--defined-only','--format=posix',str(out/'probe.elf')]),
        ('disassembly',[t['objdump'],'-d',str(out/'probe.elf')])])
    return rows
def stack(out):
    symbols={r.split()[0] for r in (out/'symbols.log').read_text().splitlines() if len(r.split())>=2 and r.split()[1] in ('t','T')}
    frames=[]
    for s in SOURCES:
        # The unchanged Apple font TU contains only its4096-byte data array;
        # clang emits no .su for a translation unit with no functions.
        if s.suffix!='.c' or s==ROOT/'osfmk/console/iso_font.c':continue
        for line in (out/(s.stem+'.su')).read_text().splitlines():
            loc,size,kind=line.split('\t')
            if loc.rsplit(':',1)[-1] not in symbols:continue
            if kind!='static' or int(size)<0:raise ValueError('Unbounded stack frame')
            frames.append(dict(location=loc,bytes=int(size),kind=kind))
    total=sum(f['bytes'] for f in frames)
    if not frames or total+512>=32768:raise ValueError('Conservative nonrecursive stack bound rejected '+str(total))
    return frames,dict(conservative_bytes=total,stack_bytes=32768,required_margin=512)
def build():
    out=Path(tempfile.mkdtemp(prefix='display-compact-',dir=ROOT/'build/rpi5'));tag=uuid.uuid4().hex;t=tools()
    pins={};headers={};scans={};records=[]
    def pin(p):
        p=str(Path(p).resolve());v=sha(p)
        if p in pins and pins[p]!=v:raise ValueError('Changed pinned input '+p)
        pins[p]=v
    for p in (*SOURCES,*FILES,*authority_inputs(),*imported(),*t.values()):pin(p)
    for label,command in commands(out,tag,t):
        r=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=60)
        log=out/(label+'.log');log.write_bytes(r.stdout+r.stderr)
        records.append(dict(label=label,command=command,cwd=str(ROOT),returncode=r.returncode))
        if r.returncode or b'warning:' in r.stderr:raise ValueError('Build failed; retained '+str(log))
        if label.endswith('-scan'):
            name=label.removesuffix('-scan');found=deps(out/(name+'.scan.d'));scans[name]=found
            for p in found:pin(p);headers[p]=pins[str(Path(p).resolve())]
        elif label.endswith('-compile'):
            name=label.removesuffix('-compile')
            if deps(out/(name+'.actual.d'))!=scans[name]:raise ValueError('Header set changed at compile')
            for p in scans[name]:pin(p)
    report=elf_inspector.inspect((out/'probe.elf').read_bytes(),(out/'probe.bin').read_bytes(),BASE)
    frames,budget=stack(out)
    for p,v in pins.items():
        if sha(p)!=v:raise ValueError('Source changed '+p)
    generated={str(p):sha(p) for p in sorted(out.iterdir()) if p.is_file()}
    report.update(profile=PROFILE,tag=tag,image=str(out/'probe.bin'),image_sha256=sha(out/'probe.bin'),
        image_bytes=(out/'probe.bin').stat().st_size,inputs_sha256=pins,headers_sha256=headers,source_scan=scans,
        generated_sha256=generated,commands=records,tool_paths=t,stack_frames=frames,stack_budget=budget,
        watchdog=dict(already_active_required=True,countdown_write_once_seconds=15,software_output_seconds=8,
            reset_route_writes=False,reload_after_arm=False),output_limit_bytes=32768,scope='Authored fixed store-only visible patch after same-boot allocation; no reads or XNU handoff; physical visibility unproven',
        allocation_contract=contract(),allocation_contract_scope='frozen allocator component only; visible_contract separately authorizes store phase',
        visible_contract=visible_contract(),mailbox_requests_authored=True,framebuffer_stores_authored=True,
        **{key:False for key in FALSE_FIELDS})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),manifest_sha256=sha(out/'manifest.json'),image_sha256=report['image_sha256'],
        image_bytes=report['image_bytes'],tag=tag,stack_budget=budget),indent=2));return report
if __name__=='__main__':build()



