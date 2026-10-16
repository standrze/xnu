#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Byte-only strict root33 init replacement; unchanged original kernel/panic."""
from pathlib import Path
import re
from . import build_display_restart_late_framed as b
same=b.oldcheck.same

def inspect(package,expected=None):
    p=Path(package).resolve();mp=p/'manifest.json'
    if p.parent!=b.ROOT/'build/rpi5' or not p.name.startswith('display-restart-late-framed-'):raise ValueError('Distinct PID1 successor')
    if expected is not None and b.sha(mp)!=expected:raise ValueError('Manifest pin')
    m=b.document(mp);pins=m['inputs_sha256'];generated=m['generated_sha256']
    if set(generated)!={str(f) for f in p.iterdir() if f.is_file() and f!=mp}:raise ValueError('Generated closure')
    for n,h in {**pins,**generated}.items():
        if not re.fullmatch('[a-f0-9]{64}',h) or b.sha(n)!=h:raise ValueError('Changed file '+n)
    for directory,digest in [(b.BASE,b.BASE_SHA),(b.INIT,b.INIT_SHA)]:
        if pins.get(str(directory/'manifest.json'))!=digest:raise ValueError('Exact parent')
        for key in ('inputs_sha256','source_inputs_sha256','headers_sha256','generated_sha256'):
            if any(pins.get(n)!=v for n,v in b.document(directory/'manifest.json').get(key,{}).items()):raise ValueError('Inherited closure omission')
    for source in b.sources():
        if pins.get(str(source))!=b.sha(source):raise ValueError('New source omission')
    if (p/'probe_main.c').read_text()!=b.generated_main() or (p/'payload.S').read_text()!=b.payload_source(p):raise ValueError('Exact source derivation')
    if not re.fullmatch('[a-f0-9]{32}',m['tag']):raise ValueError('Unique tag')
    plan=b.command_plan(p,m['tag'])
    if len(m['commands'])!=len(plan):raise ValueError('Complete commands')
    for row,want in zip(m['commands'],plan):
        if any(not same(row.get(k),v) for k,v in want.items()) or not same(row.get('returncode'),0):raise ValueError('Exact linked object/flags')
        if row['log']!=str(p/(want['label']+'.log')) or row['log_sha256']!=b.sha(row['log']):raise ValueError('Exact retained log')
    scans={};headers={}
    for label in ('loader-main','loader-payload'):
        before=sorted(b.prior.prior.original.display.dependencies(p/(label+'.scan.d'),b.ROOT))
        after=sorted(b.prior.prior.original.display.dependencies(p/(label+'.actual.d'),b.ROOT))
        if before!=after:raise ValueError('Actual dependency mismatch')
        scans[label]=before;headers.update({n:pins[n] for n in before})
    if not same(scans,m['compiler_scans']) or not same(headers,m['headers_sha256']):raise ValueError('Complete header closure')
    old=b.rootfs.files_from((b.BASE/'ramdisk.bin').read_bytes());new=b.rootfs.files_from((p/'ramdisk.bin').read_bytes())
    if old.keys()!=new.keys() or [n for n in old if old[n]!=new[n]]!=['/sbin/launchd']:raise ValueError('Only launchd may change')
    if new['/sbin/launchd']!=((b.INIT/'NOT_RUN_launchd').read_bytes(),old['/sbin/launchd'][1]):raise ValueError('Exact checked PID1 bytes and mode')
    kernel=(p/'kernel.display-restart').read_bytes();root=(p/'ramdisk.bin').read_bytes()
    if kernel!=(b.BASE/'kernel.display-restart').read_bytes():raise ValueError('Kernel/panic/restart changed')
    catalog=b.rootfs.inspect(root)
    if not same(catalog,b.document(p/'root-catalog.json')) or len(catalog['entries'])!=33:raise ValueError('Actual root catalog')
    payload=b.payload_container.encode(kernel,root)
    if payload!=(p/'payload.bin').read_bytes():raise ValueError('Actual kernel/root container')
    raw=(p/'probe.bin').read_bytes();offset=m['payload_offset']
    if type(offset)is not int or offset%64 or raw.find(payload)!=offset or raw.find(payload,offset+1)>=0:raise ValueError('Actual unique payload')
    marker=b.MARKER+m['tag']+' SAME_BOOT OWNED_FRAMEBUFFER_CONSOLE_V1'
    if raw.count(marker.encode())!=1:raise ValueError('Actual unique tag')
    symbols=b.prior.prior.original.formats.elf((p/'display_restart.elf').read_bytes(),raw)
    if symbols['__stack_top'][0]-symbols['__bss_end'][0]!=32768 or (p/'loader-undefined.log').read_text().strip():raise ValueError('Stack/import contract')
    def frames(path):return sorted(tuple(r.split('\t')[1:])+(r.split('\t')[0].rsplit(':',1)[-1],) for r in path.read_text().splitlines())
    if frames(p/'loader-main.su')!=frames(b.BASE/'loader-main.su'):raise ValueError('Exact unchanged loader control stack')
    wanted=dict(profile=b.PROFILE,parent=str(b.BASE),parent_manifest_sha256=b.BASE_SHA,init_package=str(b.INIT),init_manifest_sha256=b.INIT_SHA,
        image=str(p/'probe.bin'),image_sha256=b.sha(p/'probe.bin'),image_bytes=len(raw),kernel_sha256=b.sha(p/'kernel.display-restart'),
        root_sha256=b.sha(p/'ramdisk.bin'),root_bytes=len(root),root_nodes=33,launchd_sha256=b.sha(b.INIT/'NOT_RUN_launchd'),
        root_only_replaced='/sbin/launchd',init_shutdown_ready_marker=b.init.READY,init_shutdown_ready_max_reports=3,
        init_readiness_min_successful_sleep_seconds=1,init_readiness_full_mask_revalidated=True,init_readiness_newline_framed=True,init_uart_line_atomicity_claimed=False,copy_phase_contract=b.CONTRACT)
    if any(not same(m.get(k),v) for k,v in wanted.items()):raise ValueError('Exact successor contract')
    report=b.oldcheck.inspect(b.BASE,b.BASE_SHA)
    # Historical checks retain component scope; do not claim the old root or
    # payload bytes remained unchanged in this successor.
    report['copy_phase_checks'].pop('unchanged_kernel_root_payload',None)
    report['copy_phase_checks']['unchanged_kernel_and_copy_phase_body']=True
    report.update(wanted,package=str(p),manifest_sha256=b.sha(mp),tag=m['tag'],trial_marker=marker,
        root_catalog=str(p/'root-catalog.json'),root_catalog_sha256=b.sha(p/'root-catalog.json'),
        root_mount_marker=f'RPI5XNU:RAMROOT:MOUNT NODES=33 BYTES={len(root)} READONLY',
        root_ready_marker=f'RPI5XNU:TERMINAL:ROOT_READY SECONDS=180 NODES=33 BYTES={len(root)} READONLY',
        root_copy_marker=f'RPI5XNU:BL33:RAMDISK_MATERIALIZED PA=0000000008238000 BYTES={len(root):016x} VERIFIED',
        actual_loader_end=symbols['__probe_end'][0],source_members=len(pins),generated_members=len(generated),
        init_shutdown_checks=dict(only_launchd_replaced=True,exact_original_object_source=True,real_sigprocmask_pending_wait_abi=True,
            no_signal_trampoline=True,child_exact_mask_restore=True,nonexiting_stop_after_observation=True,kernel_panic_path_unchanged=True),
        init_arrival_fork_atomicity_claimed=False,target_executed=False)
    report['inherited_component_checks']={key:dict(report[key]) for key in
        ('checks','diagnostic_checks','copy_phase_checks')}
    report['checks'].pop('root_only_added_cli')
    report['checks'].pop('exact_inherited_bytes')
    report['checks'].update(root_only_launchd_replaced=True,all_other_root_files_and_kernel_identical=True)
    report['copy_phase_checks'].pop('one_loader_owner_replaced')
    report['copy_phase_checks']['exact_main_and_payload_owner_replacements']=True
    report['diagnostic_checks'].pop('unchanged_root33_cli')
    report['diagnostic_checks']['unchanged_reboot_cli_and_diagnostic_kernel']=True
    report['report_scope']='pid1-late-framed-readiness-current-checks-with-historical-components-v1'
    report['init_shutdown_checks'].update(bounded_three_late_reports=True,fresh_mask_before_every_report=True,
        successful_sleep_only=True)
    return report


