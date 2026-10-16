#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Byte-only verifier for the distinct linked restart candidate; no execution."""
import json
from pathlib import Path
import re
import struct
from . import build_display_restart as b

def same(a,c):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(c,sort_keys=True,allow_nan=False)
def inspect(package,expected=None):
    p=Path(package).resolve();mp=p/'manifest.json'
    if p.parent!=b.ROOT/'build/rpi5' or not p.name.startswith('display-restart-'):raise ValueError('Distinct package required')
    if expected is not None and b.sha(mp)!=expected:raise ValueError('Manifest pin')
    m=b.document(mp);pins=m['inputs_sha256'];generated=m['generated_sha256']
    if set(generated)!={str(q) for q in p.rglob('*') if q.is_file() and q!=mp}:raise ValueError('Complete generated closure')
    for name,value in {**pins,**generated}.items():
        if not re.fullmatch('[0-9a-f]{64}',value) or b.sha(name)!=value:raise ValueError('Byte closure '+name)
    for path in b.source_paths():
        if pins.get(str(path))!=b.sha(path):raise ValueError('Required source omitted')
    for parent,digest in ((b.BASE,b.BASE_SHA),(b.RUNTIME,b.RUNTIME_SHA),(b.RESET,b.RESET_SHA)):
        if pins.get(str(parent/'manifest.json'))!=digest:raise ValueError('Parent pin')
        old=b.document(parent/'manifest.json')
        for key in ('inputs_sha256','source_inputs_sha256','headers_sha256','generated_sha256'):
            if any(pins.get(k)!=v for k,v in old.get(key,{}).items()):raise ValueError('Inherited closure omitted')
    if (p/'IOPlatformExpert.restart.cpp').read_text()!=b.policy.derive(b.policy.ORIGINAL.read_text()):raise ValueError('Platform overlay differs')
    if (p/'probe_main.c').read_text()!=b.derive_main((b.BASE/'probe_main.c').read_text()):raise ValueError('Loader overlay differs')
    tag=m['tag']
    if not re.fullmatch('[a-f0-9]{32}',tag):raise ValueError('Actual unique tag')
    records=m['commands'];by={r['label']:r for r in records}
    if len(by)!=len(records) or any(r['returncode']!=0 or type(r['returncode']) is not int or r['log']!=str(p/(r['label']+'.log')) or r['log_sha256']!=b.sha(r['log']) for r in records):raise ValueError('Command receipts')
    rt=b.document(b.RUNTIME/'manifest.json');base=b.document(b.BASE/'manifest.json');db=b.document(b.display.DATABASE)
    smoke=next(r['command'] for r in rt['commands'] if r['stdout'].endswith('/smoke-compile.stdout'))
    uf=b.display.compiler_flags(smoke,b.ROOT/'tools/rpi5/user/pthread_smoke.c')
    cpp=next(r for r in db if r['file']==str(b.policy.ORIGINAL));c=next(r for r in db if r['file']==str(b.ROOT/'pexpert/arm/pe_fiq.c'))
    cf=b.display.compiler_flags(c['arguments'],Path(c['file']))+['-I',str(b.ROOT/'loader/rpi5')]
    kf=b.display.compiler_flags(cpp['arguments'],b.policy.ORIGINAL)+['-I',str(b.ROOT),'-iquote',str(b.policy.ORIGINAL.parent),'-DRPI5_PSCI_RESTART_CANDIDATE=1','-DRPI5_FIRMWARE_FDT_HANDOFF=1']
    lf=b.display.compiler_flags(next(r['command'] for r in base['commands'] if r['log'].endswith('/loader-probe_main-compile.log')),b.BASE/'probe_main.c')
    lf=[a if not a.startswith('-DRPI5_DISPLAY_XNU_TAG=') else '-DRPI5_DISPLAY_XNU_TAG="'+tag+'"' for a in lf]
    expected_units={'cli':(uf,b.ROOT/'tools/rpi5/user/reboot_cli.c',b.ROOT),
        'apple-reboot-wrapper':(uf,b.ROOT/'libsyscall/wrappers/reboot.c',b.ROOT),
        'platform':(kf,p/'IOPlatformExpert.restart.cpp',Path(cpp['directory'])),
        'policy':(cf,b.ROOT/'loader/rpi5/psci_restart_candidate.c',Path(c['directory'])),
        'smc':([a for a in cf if a!='-xc']+['-x','assembler-with-cpp'],b.ROOT/'osfmk/arm64/rpi5_psci_restart_candidate.S',Path(c['directory'])),
        'loader-main':(lf,p/'probe_main.c',b.ROOT),'loader-payload':(lf,p/'payload.S',b.ROOT)}
    if set(m['compiler_scans'])!=set(expected_units)|{'syscall'}:raise ValueError('Scan membership')
    headers={};expected_order=[]
    for label in ('cli','apple-reboot-wrapper'):expected_order.extend((label+'-scan',label+'-compile'))
    expected_order += ['original-syscall-generator','syscall-scan','syscall-preprocess','syscall-assemble','syscall-disassembly','syscall-undefined','cli-link','cli-undefined','cli-disassembly']
    for label in ('platform','policy','smc'):expected_order.extend((label+'-scan',label+'-compile'))
    expected_order += ['restart-disassembly','kernel-link','kernel-strip','kernel-undefined','loader-main-scan','loader-main-compile','loader-payload-scan','loader-payload-compile','loader-link','loader-objcopy','loader-undefined']
    if [r['label'] for r in records]!=expected_order:raise ValueError('Exact command membership/order')
    def receipt(label,args,cwd=b.ROOT):
        if by[label]['command']!=list(map(str,args)) or by[label]['cwd']!=str(cwd):raise ValueError('Exact command '+label)
    for label,(flags,source,cwd) in expected_units.items():
        expected_cmd=list(map(str,[*flags,'-c','-MD','-MF',p/(label+'.actual.d'),source,'-o',p/(label+'.o')]))
        receipt(label+'-compile',expected_cmd,cwd)
        receipt(label+'-scan',[*flags,'-M','-MF',p/(label+'.scan.d'),source],cwd)
        before=b.display.dependencies(p/(label+'.scan.d'),cwd);after=b.display.dependencies(p/(label+'.actual.d'),cwd)
        if before!=after or sorted(before)!=m['compiler_scans'][label]:raise ValueError('Consumed headers '+label)
        for name in before:headers[name]=pins[name]
    if b.display.dependencies(p/'syscall.scan.d',b.ROOT)!=b.display.dependencies(p/'syscall.actual.d',b.ROOT):raise ValueError('Trap headers')
    for name in b.display.dependencies(p/'syscall.actual.d',b.ROOT):headers[name]=pins[name]
    if sorted(b.display.dependencies(p/'syscall.actual.d',b.ROOT))!=m['compiler_scans']['syscall'] or not same(headers,m['headers_sha256']):raise ValueError('Header map omission')
    join=b.document(b.JOIN/'manifest.json');at=next(r['command'] for r in join['commands'] if r['stdout'].endswith('/create-trap-preprocess.stdout'));af=at[:at.index('-E')]
    receipt('original-syscall-generator',['/usr/bin/perl',b.ROOT/'libsyscall/xcodescripts/create-syscalls.pl',b.ROOT/'bsd/kern/syscalls.master',b.ROOT/'libsyscall/custom',b.ROOT/'libsyscall/Platforms','MacOSX',p/'generated'])
    receipt('syscall-scan',[*af,'-M','-MF',p/'syscall.scan.d',p/'generated/___reboot.s'])
    receipt('syscall-preprocess',[*af,'-E','-P','-MD','-MF',p/'syscall.actual.d',p/'generated/___reboot.s'])
    receipt('syscall-assemble',[af[0],'-target','arm64-apple-darwin','-mcpu=cortex-a76','-x','assembler','-c',p/'syscall.s','-o',p/'syscall.o'])
    for label,args in {
        'syscall-disassembly':['xcrun','llvm-objdump','-d','-r',p/'syscall.o'],
        'syscall-undefined':['xcrun','nm','-ju',p/'syscall.o'],
        'cli-undefined':['xcrun','nm','-ju',p/'NOT_RUN_reboot'],
        'cli-disassembly':['xcrun','llvm-objdump','-d',p/'NOT_RUN_reboot'],
        'restart-disassembly':['xcrun','llvm-objdump','-d','-r',p/'policy.o',p/'smc.o'],
        'kernel-strip':['xcrun','strip','-S',p/'kernel.unstripped','-o',p/'kernel.display-restart'],
        'kernel-undefined':['xcrun','nm','-ju',p/'kernel.display-restart'],
        'loader-objcopy':[b.ROOT/'tools/rpi5/tfa-objcopy','-O','binary',p/'display_restart.elf',p/'probe.bin'],
        'loader-undefined':['xcrun','llvm-nm','--undefined-only',p/'display_restart.elf']}.items():receipt(label,args)
    def exact_link(label,old,changes,append=()):
        if any(old.count(key)!=1 for key in changes):raise ValueError('Ambiguous link replacement')
        receipt(label,[changes.get(a,a) for a in old]+list(map(str,append)))
    old=next(r['command'] for r in rt['commands'] if r['stdout'].endswith('/target-link.stdout'))
    exact_link('cli-link',old,{str(b.RUNTIME/'smoke.o'):str(p/'cli.o'),rt['target']:str(p/'NOT_RUN_reboot'),str(b.RUNTIME/'target.map'):str(p/'cli.map')},[p/'apple-reboot-wrapper.o',p/'syscall.o'])
    old=next(r['command'] for r in base['commands'] if r['log'].endswith('/kernel-link.log'))
    exact_link('kernel-link',old,{str(b.BASE/'kernel.display.filelist'):str(p/'kernel.restart.filelist'),str(b.BASE/'kernel.unstripped'):str(p/'kernel.unstripped'),'-Wl,-map,'+str(b.BASE/'kernel.map'):'-Wl,-map,'+str(p/'kernel.map')})
    old=next(r['command'] for r in base['commands'] if r['log'].endswith('/loader-link.log'))
    exact_link('loader-link',old,{str(b.BASE/'loader-probe_main.o'):str(p/'loader-main.o'),str(b.BASE/'loader-payload.o'):str(p/'loader-payload.o'),str(b.BASE/'display_xnu.elf'):str(p/'display_restart.elf')})
    old_object=b.display.OBJ/'iokit/DEVELOPMENT/IOPlatformExpert.cpo';old_list=(b.BASE/'kernel.display.filelist').read_text().splitlines()
    expected_list=[str(p/'platform.o') if name==str(old_object) else name for name in old_list]+[str(p/'policy.o'),str(p/'smc.o')]
    if (p/'kernel.restart.filelist').read_text().splitlines()!=expected_list or not same(m['kernel_replaced'],{str(old_object):str(p/'platform.o')}) or m['kernel_added']!=list(map(str,[p/'policy.o',p/'smc.o'])):raise ValueError('Exact kernel delta')
    raw_kernel=(p/'kernel.display-restart').read_bytes();ks,segments=b.formats.macho(raw_kernel)
    required=('_rpi5_restart_attempt','_rpi5_restart_psci_reset','_rpi5_firmware_fdt_view','_rpi5_console_mirror_publish','_initialize_screen','_reboot')
    if any(s not in ks for s in required):raise ValueError('Linked kernel owners')
    cli=(p/'NOT_RUN_reboot').read_bytes();b.prepare_pid1.inspect(cli)
    cs,_=b.formats.macho(cli)
    if any(n not in cs for n in ('_reboot','___reboot','_cerror_nocancel','_rpi5_pthread_smoke_main','_darwin_static_start')):raise ValueError('Real CLI providers')
    cli_map=(p/'cli.map').read_text();km=(p/'kernel.map').read_text(errors='surrogateescape')
    for name in ('apple-reboot-wrapper.o','syscall.o','startup.o'):
        if name not in cli_map:raise ValueError('CLI map ownership')
    if str(old_object) in km or any(str(p/name) not in km for name in ('platform.o','policy.o','smc.o')):raise ValueError('Kernel map owners')
    # Decode actual target instructions/relocations, not disassembly strings.
    MachO=b.reset.macho.MachO
    trap=MachO(p/'syscall.o');trap_body=trap.function('___reboot')
    if trap.at(trap.names['___reboot']['address'],8)!=struct.pack('<II',0xd28006f0,0xd4001001) or [r[2] for r in trap_body['relocations']]!=['_cerror_nocancel']:raise ValueError('Actual Apple syscall55/error branch')
    wrapper=MachO(p/'apple-reboot-wrapper.o')
    if [r[2] for r in wrapper.function('_reboot')['relocations']]!=['___reboot']:raise ValueError('Original wrapper target')
    leaf=MachO(p/'smc.o')
    def kernel_at(address,size):
        eligible=[(va,file) for va,_,file,backed,_ in segments if va<=address and address+size<=va+backed]
        if len(eligible)!=1:raise ValueError('Linked reset leaf is not uniquely file-backed')
        va,file=eligible[0];return raw_kernel[file+address-va:file+address-va+size]
    for symbol in ('_rpi5_restart_current_el','_rpi5_restart_psci_version','_rpi5_restart_psci_feature','_rpi5_restart_psci_reset'):
        shape=leaf.function(symbol)
        if shape['relocations'] or leaf.at(leaf.names[symbol]['address'],shape['bytes'])!=kernel_at(ks[symbol],shape['bytes']):raise ValueError('Actual linked fixed SMC leaf')
    candidate=MachO(p/'policy.o')
    imports={s['name'] for s in candidate.symbols if s['type']&1 and not s['type']&0xe}
    if imports!={'_rpi5_fdt_property','_rpi5_fdt_psci_smc','_rpi5_restart_current_el','_rpi5_restart_psci_version','_rpi5_restart_psci_feature','_rpi5_restart_psci_reset'}:raise ValueError('Policy runtime dependency')
    fn=candidate.function('_rpi5_restart_attempt');words=struct.unpack('<'+'I'*(fn['bytes']//4),candidate.at(candidate.names['_rpi5_restart_attempt']['address'],fn['bytes']))
    if sum((word&0xffe0fc00)==0x88e0fc00 for word in words)!=1:raise ValueError('Actual inline one-shot CASAL')
    raw=(p/'probe.bin').read_bytes();symbols=b.formats.elf((p/'display_restart.elf').read_bytes(),raw)
    marker=(b.MARKER+tag+' SAME_BOOT OWNED_FRAMEBUFFER_CONSOLE_V1').encode()
    if raw.count(marker)!=1 or raw.count((b.BOOT+' rpi5_psci_restart=1').encode()+b'\0')!=1:raise ValueError('Actual opt-in/tag')
    packed=(p/'payload.bin').read_bytes();root=(p/'ramdisk.bin').read_bytes()
    if packed!=b.payload_container.encode(raw_kernel,root):raise ValueError('Actual payload integrity')
    offset=m['payload_offset']
    if type(offset)is not int or offset%64 or raw.find(packed)!=offset or raw.find(packed,offset+1)>=0:raise ValueError('Embedded payload')
    old_payload=(b.BASE/'payload.bin').read_bytes();a,n=struct.unpack_from('<QQ',old_payload,136)
    oldfiles=b.rootfs.files_from(old_payload[a:a+n]);files=b.rootfs.files_from(root)
    if files!={**oldfiles,'/sbin/reboot':(cli,0o555)}:raise ValueError('Root contents changed beyond new CLI')
    catalog=b.rootfs.inspect(root)
    if len(catalog['entries'])!=33 or not same(catalog,b.document(p/'root-catalog.json')):raise ValueError('Root catalog')
    if symbols['__stack_top'][0]-symbols['__bss_end'][0]!=32768 or symbols['__probe_end'][0]>=0xb000000:raise ValueError('Loader memory bound')
    def frames(path):return sorted(tuple(line.split('\t')[1:])+(line.split('\t')[0].rsplit(':',1)[-1],) for line in path.read_text().splitlines())
    if frames(p/'loader-main.su')!=frames(b.BASE/'loader-probe_main.su'):raise ValueError('Actual main stack changed')
    if not same(m['firmware'],b.reset.firmware_proof()):raise ValueError('Exact linked normal firmware contract')
    expected_scope=dict(target_executed=False,physical_restart_proven=False,poweroff_supported=False,staged=False,panic_enum_modes_excluded=True,all_panic_contexts_excluded=False,full_apple_reboot_utility=False)
    for key,value in dict(profile='rpi5-display-original-reboot-syscall-full-composition-v1',root_nodes=33,root_bytes=len(root),root_sha256=b.sha(p/'ramdisk.bin'),
        image=str(p/'probe.bin'),image_sha256=b.sha(p/'probe.bin'),image_bytes=len(raw),kernel=str(p/'kernel.display-restart'),kernel_sha256=b.sha(p/'kernel.display-restart'),
        cli=str(p/'NOT_RUN_reboot'),cli_sha256=b.sha(p/'NOT_RUN_reboot'),original_watchdog_seconds=180,hardware_watchdog_seconds=15,
        root_only_added='/sbin/reboot',old_socket_catalog_not_extended=True,existing_display_objects_unchanged=True,
        original_shutdown_permission_path_unchanged=True,boot_argument='rpi5_psci_restart=1',scope=expected_scope).items():
        if not same(m.get(key),value):raise ValueError('Contract field '+key)
    inherited=b.formats.inspect(b.BASE,b.BASE_SHA)
    envelope=max(va+memory for va,memory,_,_,_ in segments)-min(va for va,memory,_,_,_ in segments if memory)
    root_pa=((0x7004000+envelope+16383)&~16383)+0x8000
    inherited.update(profile=m['profile'],package=str(p),manifest_sha256=b.sha(mp),image=str(p/'probe.bin'),image_bytes=len(raw),
        image_sha256=m['image_sha256'],kernel_sha256=m['kernel_sha256'],root_sha256=m['root_sha256'],
        root_nodes=33,root_bytes=len(root),tag=tag,trial_marker=marker.decode(),root_catalog=str(p/'root-catalog.json'),root_catalog_sha256=b.sha(p/'root-catalog.json'),
        root_copy_marker=f'RPI5XNU:BL33:RAMDISK_MATERIALIZED PA={root_pa:016x} BYTES={len(root):016x} VERIFIED',
        kernel_copy_marker=f'RPI5XNU:BL33:KERNEL_MATERIALIZED BYTES={envelope:016x} FULL_ENVELOPE_VERIFIED NO_BOOT_ARGS_WRITTEN NO_TRANSFER',
        root_mount_marker=f'RPI5XNU:RAMROOT:MOUNT NODES=33 BYTES={len(root)} READONLY',
        root_ready_marker=f'RPI5XNU:TERMINAL:ROOT_READY SECONDS=180 NODES=33 BYTES={len(root)} READONLY')
    return dict(inherited,restart_contract=dict(cli='/sbin/reboot',options='RB_AUTOBOOT only',opt_in='rpi5_psci_restart=1',
        poweroff_supported=False,physical_restart_proven=False),
        cli_sha256=m['cli_sha256'],
        source_members=len(pins),generated_members=len(generated),actual_loader_end=symbols['__probe_end'][0],
        target_executed=False,physical_restart_proven=False,poweroff_supported=False,
        checks=dict(exact_inherited_bytes=True,actual_headers=True,exact_compile_link_boundaries=True,real_wrapper_and_trap=True,
            full_kernel_link=True,unchanged_watchdog=True,root_only_added_cli=True,exact_embedded_payload=True))
