#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""No-compiler, exact source/command/object/root closure for the opt-in image."""
import json
from pathlib import Path
import re
import struct
from . import build_display_console_records as b
from . import check_display_restart_late_framed as parent
from .check_apple_pthread_kernel_contract import MachO

def same(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)

def frames(path, inherited_bti=False):
    result={}
    for line in path.read_text().splitlines():
        field,size,kind=line.split('\t')
        name=field.rsplit(':',1)[-1]
        # The unchanged original BTI-failure decoder has a variable frame;
        # this is not in any new console path and is NOT claimed bounded64.
        if kind!='static' and not (inherited_bti and name=='handle_bti_fail' and kind=='dynamic' and size=='64'):
            raise ValueError('Static new stack frames required')
        result[name]=int(size)
    return result

def inspect(package,expected=None):
    p=Path(package).resolve();mp=p/'manifest.json'
    if p.parent!=b.ROOT/'build/rpi5' or not p.name.startswith('display-console-records-'):raise ValueError('Distinct console package')
    if expected is not None and b.sha(mp)!=expected:raise ValueError('Manifest pin')
    m=b.document(mp);pins=m['inputs_sha256'];generated=m['generated_sha256']
    if set(generated)!={str(f) for f in p.iterdir() if f.is_file() and f!=mp}:raise ValueError('Generated closure')
    for n,h in {**pins,**generated}.items():
        if not re.fullmatch('[a-f0-9]{64}',h) or b.sha(n)!=h:raise ValueError('Changed closure '+n)
    for directory,digest in [(b.BASE,b.BASE_SHA),(b.KERNEL,b.KERNEL_SHA),(b.profile.INIT,b.profile.INIT_SHA)]:
        if pins.get(str(directory/'manifest.json'))!=digest:raise ValueError('Parent pin')
        for key in ('inputs_sha256','source_inputs_sha256','headers_sha256','generated_sha256'):
            if any(pins.get(n)!=v for n,v in b.document(directory/'manifest.json').get(key,{}).items()):raise ValueError('Inherited closure omission')
    for source in [*b.sources(),*b.profile.PINS]:
        if pins.get(str(source))!=b.sha(source):raise ValueError('Required source omission')
    for name,raw in b.generated(p).items():
        if (p/name).read_text()!=raw:raise ValueError('Actual derived source '+name)
    tag=m['tag']
    if not re.fullmatch('[a-f0-9]{32}',tag):raise ValueError('Unique tag')
    plan=b.command_plan(p,tag)
    if len(plan)!=len(m['commands']):raise ValueError('Command set')
    scans={};headers={}
    for row,want in zip(m['commands'],plan):
        if any(not same(row.get(k),v) for k,v in want.items()) or not same(row.get('returncode'),37 if want['label']=='host-negative' else 0):raise ValueError('Command flags/cwd/result')
        label=want['label']
        if row['log']!=str(p/(label+'.log')) or row['log_sha256']!=b.sha(row['log']):raise ValueError('Retained log')
        if label.endswith('-scan'):
            name=label[:-5];before=sorted(b.compiler.dependencies(p/(name+'.scan.d'),Path(row['cwd'])))
            after=sorted(b.compiler.dependencies(p/(name+'.actual.d'),Path(row['cwd'])))
            if before!=after:raise ValueError('Actual dependency disagreement')
            scans[name]=before;headers.update({n:pins[n] for n in before})
    if not same(scans,m['compiler_scans']) or not same(headers,m['headers_sha256']):raise ValueError('Header closure')
    replaced=b.replacements(p);old=(b.KERNEL/'kernel.filelist').read_text().splitlines()
    if any(old.count(n)!=1 for n in replaced) or (p/'kernel.filelist').read_text().splitlines()!=[replaced.get(n,n) for n in old] or not same(m['kernel_replacements'],replaced):raise ValueError('Six exact kernel replacements')
    kernel=(p/'kernel.display-restart').read_bytes();symbols,segments=b.diagnostic.original.formats.macho(kernel)
    required=('_rpi5_console_kprintf_record','_rpi5_console_write_record','_rpi5_terminal_console_thread_owner',
        '_rpi5_restart_diagnostic_ready','_rpi5_restart_diagnostic_reset','_rpi5_restart_psci_reset')
    if any(n not in symbols for n in required):raise ValueError('Actual linked providers')
    # Exact fixed original PSCI leaf bytes remain, not inferred from names.
    fixed=b.diagnostic.original.reset.macho.MachO(b.diagnostic.BASE/'smc.o')
    for name in ('_rpi5_restart_current_el','_rpi5_restart_psci_version','_rpi5_restart_psci_feature','_rpi5_restart_psci_reset'):
        fn=fixed.function(name);address=symbols[name];size=fn['bytes']
        span=[(va,off) for va,mem,off,backed,flags in segments if va<=address and address+size<=va+backed]
        if len(span)!=1:raise ValueError('Unique linked leaf extent')
        va,off=span[0]
        if kernel[off+address-va:off+address-va+size]!=fixed.at(fixed.names[name]['address'],size):raise ValueError('Fixed SMC changed')
    # Emitted branch bindings in the real objects (host doubles are separate).
    def calls(label,name):return {r[2] for r in MachO(p/(label+'.o')).function(name)['relocations']}
    if '_rpi5_console_kprintf_record' not in calls('kprintf','_kprintf'):raise ValueError('Missing normal dispatch')
    if '_rpi5_console_write_record' not in calls('policy','_rpi5_restart_diagnostic_ready'):raise ValueError('Missing normal readiness owner')
    if '_rpi5_restart_diag_uart' in calls('policy','_rpi5_restart_diagnostic_ready'):raise ValueError('Raw boot readiness')
    reset=calls('policy','_rpi5_restart_diagnostic_reset')
    if '_rpi5_restart_diag_uart' not in reset or '_rpi5_console_write_record' in reset:raise ValueError('Changed post-halt route')
    serial=MachO(p/'serial.o');leaf=serial.function('_rpi5_console_uart_try')
    words=struct.unpack('<'+'I'*(leaf['bytes']//4),serial.at(serial.names['_rpi5_console_uart_try']['address'],leaf['bytes']))
    if sum((v&0xffe0fc00)==0x88e07c00 for v in words)!=1:raise ValueError('Exact one inline CASA acquire')
    if any(isinstance(n,str) and any(x in n for x in ('lck_','console_write','vcputc','thread_block','uart_wait')) for n in calls('serial','_rpi5_console_uart_try')):raise ValueError('Blocking operation inside FIFO guard')
    selected_frames={name:frames(p/(name+'.su'),name=='sleh') for name in ('kprintf','console','serial','sleh','watchdog','policy')}
    for label,name in [('console','rpi5_console_kprintf_record'),('console','rpi5_console_write_record'),('serial','rpi5_console_uart_try'),('sleh','rpi5_terminal_console_thread_owner')]:
        if name not in selected_frames[label] or selected_frames[label][name]>512:raise ValueError('Bounded new frame')
    oldfiles=b.rootfs.files_from((b.BASE/'ramdisk.bin').read_bytes());root=(p/'ramdisk.bin').read_bytes();new=b.rootfs.files_from(root)
    if oldfiles.keys()!=new.keys() or [n for n in oldfiles if oldfiles[n]!=new[n]]!=['/sbin/launchd']:raise ValueError('Only PID1 label root delta')
    if new['/sbin/launchd']!=((p/'NOT_RUN_launchd').read_bytes(),oldfiles['/sbin/launchd'][1]):raise ValueError('Actual launchd bytes/mode')
    catalog=b.rootfs.inspect(root)
    if not same(catalog,b.document(p/'root-catalog.json')) or len(catalog['entries'])!=33:raise ValueError('Actual root33 namespace')
    if not same(b.prepare_pid1.inspect(new['/sbin/launchd'][0]),m['target_inspection']):raise ValueError('Real static init')
    for name in ('kernel','target','loader'):
        if (p/(name+'-undefined.log')).read_text().strip():raise ValueError('Unexpected imports')
    if 'INIT_SHUTDOWN_LATE PASS CASES=205 ' not in (p/'host-run.log').read_text():raise ValueError('Actual native PID1 policy evidence')
    payload=b.payload_container.encode(kernel,root);raw=(p/'probe.bin').read_bytes();offset=m['payload_offset']
    if payload!=(p/'payload.bin').read_bytes() or type(offset)is not int or offset%64 or raw.find(payload)!=offset or raw.find(payload,offset+1)>=0:raise ValueError('Actual embedded root/kernel')
    marker=b.MARKER+tag+' SAME_BOOT OWNED_FRAMEBUFFER_CONSOLE_V1'
    if raw.count(marker.encode())!=1:raise ValueError('Actual unique marker')
    elf=b.diagnostic.original.formats.elf((p/'display_restart.elf').read_bytes(),raw)
    if elf['__stack_top'][0]-elf['__bss_end'][0]!=32768 or frames(p/'loader-main.su')!=frames(b.BASE/'loader-main.su'):raise ValueError('Unchanged loader flow/stack')
    wanted=dict(profile=b.PROFILE,parent=str(b.BASE),parent_manifest_sha256=b.BASE_SHA,kernel_parent=str(b.KERNEL),kernel_parent_manifest_sha256=b.KERNEL_SHA,
        init_parent=str(b.profile.INIT),init_parent_manifest_sha256=b.profile.INIT_SHA,
        image=str(p/'probe.bin'),image_sha256=b.sha(p/'probe.bin'),image_bytes=len(raw),kernel_sha256=b.sha(p/'kernel.display-restart'),
        root_sha256=b.sha(p/'ramdisk.bin'),root_bytes=len(root),root_nodes=33,launchd_sha256=b.sha(p/'NOT_RUN_launchd'),
        init_shutdown_ready_marker=b.profile.READY,init_shutdown_ready_max_reports=3,console_record_contract=b.CONTRACT)
    if any(not same(m.get(k),v) for k,v in wanted.items()):raise ValueError('Exact truthful current contract')
    report=parent.inspect(b.BASE,b.BASE_SHA)
    # Prior proofs retain COMPONENT scope; no stale unchanged-kernel claims.
    historical={k:report.pop(k) for k in ('checks','diagnostic_checks','copy_phase_checks','init_shutdown_checks','inherited_component_checks') if k in report}
    report['inherited_component_checks']=historical
    report.pop('root_only_replaced',None)
    report.pop('init_package',None);report.pop('init_manifest_sha256',None)
    report['copy_phase_contract']={**report['copy_phase_contract'],'kernel_unchanged':False,'kernel_root_payload_unchanged':False}
    envelope=max(va+mem for va,mem,off,backed,flags in segments)-min(va for va,mem,off,backed,flags in segments if mem)
    root_pa=((0x7004000+envelope+16383)&~16383)+0x8000
    report.update(wanted,package=str(p),manifest_sha256=b.sha(mp),tag=tag,trial_marker=marker,
        root_catalog=str(p/'root-catalog.json'),root_catalog_sha256=b.sha(p/'root-catalog.json'),
        root_ready_marker=f'RPI5XNU:TERMINAL:ROOT_READY SECONDS=180 NODES=33 BYTES={len(root)} READONLY',
        root_mount_marker=f'RPI5XNU:RAMROOT:MOUNT NODES=33 BYTES={len(root)} READONLY',
        root_copy_marker=f'RPI5XNU:BL33:RAMDISK_MATERIALIZED PA={root_pa:016x} BYTES={len(root):016x} VERIFIED',
        kernel_copy_marker=f'RPI5XNU:BL33:KERNEL_MATERIALIZED BYTES={envelope:016x} FULL_ENVELOPE_VERIFIED NO_BOOT_ARGS_WRITTEN NO_TRANSFER',
        actual_loader_end=elf['__probe_end'][0],kernel_stack_frames=selected_frames,
        inherited_dynamic_stack_functions=['handle_bti_fail'],source_members=len(pins),generated_members=len(generated),
        checks=dict(exact_six_kernel_owners=True,original_record_buffer=True,actual_inline_fifo_casa=True,
            terminal_callout_only=True,original_deadline_epoch_and_limits=True,raw_presmc_unchanged=True,
            only_pid1_label_root_delta=True,complete_source_command_header_closure=True),
        report_scope='safe-normal-console-current-with-explicit-historical-components-v1',target_executed=False)
    return report
