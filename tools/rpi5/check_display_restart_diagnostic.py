#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Byte-only complete composition and nominal-only diagnostic admission."""
from pathlib import Path
import re
import struct
from . import build_display_restart_diagnostic as b
from . import restart_diagnostic_serial as protocol

same=b.oldcheck.same

def inspect(package,expected=None):
    p=Path(package).resolve();manifest=p/'manifest.json'
    if p.parent!=b.ROOT/'build/rpi5' or not p.name.startswith('display-restart-diagnostic-'):raise ValueError('Distinct diagnostic package required')
    if expected is not None and b.sha(manifest)!=expected:raise ValueError('Exact diagnostic manifest pin')
    m=b.document(manifest);pins=m['inputs_sha256'];generated=m['generated_sha256']
    if set(generated)!={str(path) for path in p.rglob('*') if path.is_file() and path!=manifest}:raise ValueError('Complete diagnostic generated closure')
    for name,value in {**pins,**generated}.items():
        if not re.fullmatch('[0-9a-f]{64}',value) or b.sha(name)!=value:raise ValueError('Diagnostic closure '+name)
    base=b.document(b.BASE/'manifest.json')
    if pins.get(str(b.BASE/'manifest.json'))!=b.BASE_SHA:raise ValueError('Frozen parent identity')
    for key in ('inputs_sha256','headers_sha256','generated_sha256'):
        if any(pins.get(name)!=value for name,value in base[key].items()):raise ValueError('Inherited parent closure omitted')
    for path in b.sources():
        if pins.get(str(path))!=b.sha(path):raise ValueError('Required new diagnostic source omitted')
    tag=m['tag']
    if not re.fullmatch('[a-f0-9]{32}',tag):raise ValueError('Unique actual loader tag')
    for name,text in b.generated_sources(p).items():
        if (p/name).read_text()!=text:raise ValueError('Actual owner derivation '+name)
    plan=b.command_plan(p,tag);commands=m['commands']
    if len(commands)!=len(plan):raise ValueError('Exact command membership')
    for observed,wanted in zip(commands,plan):
        if any(not same(observed.get(k),v) for k,v in wanted.items()) or type(observed.get('returncode')) is not int or observed['returncode']!=0:
            raise ValueError('Exact command/cwd/flags '+wanted['label'])
        if observed['log']!=str(p/(wanted['label']+'.log')) or observed['log_sha256']!=b.sha(observed['log']):raise ValueError('Actual command log')
    headers={};scans={}
    for label,(_,source,cwd) in b.units(p,tag).items():
        before=b.original.display.dependencies(p/(label+'.scan.d'),cwd)
        after=b.original.display.dependencies(p/(label+'.actual.d'),cwd)
        if before!=after:raise ValueError('Actual dependency scan changed '+label)
        scans[label]=sorted(before)
        for name in before:headers[name]=pins[name]
    if not same(headers,m['headers_sha256']) or not same(scans,m['compiler_scans']):raise ValueError('Complete actual header closure required')
    replaced=b.replacements(p);old=(b.BASE/'kernel.restart.filelist').read_text().splitlines()
    if (p/'kernel.filelist').read_text().splitlines()!=[replaced.get(name,name) for name in old] or not same(m['kernel_replaced'],replaced):
        raise ValueError('Exact four changed kernel owners required')
    kernel=(p/'kernel.display-restart').read_bytes();ks,segments=b.original.formats.macho(kernel)
    required=('_rpi5_restart_attempt','_rpi5_restart_diagnostic_reset','_rpi5_restart_diagnostic_ready',
        '_rpi5_restart_diagnostic_boot_ready','_rpi5_restart_diag_snapshot','_rpi5_restart_diag_uart','_rpi5_restart_psci_reset')
    if any(name not in ks for name in required):raise ValueError('Actual linked diagnostic providers')
    for label in ('kernel','loader'):
        if (p/(label+'-undefined.log')).read_text().strip():raise ValueError('Unresolved actual image')
    # The only reset mechanism remains the exact fixed original assembly.
    leaf=b.original.reset.macho.MachO(b.BASE/'smc.o')
    for symbol in ('_rpi5_restart_current_el','_rpi5_restart_psci_version','_rpi5_restart_psci_feature','_rpi5_restart_psci_reset'):
        shape=leaf.function(symbol);address=ks[symbol];size=shape['bytes']
        candidates=[(va,file) for va,_,file,backed,_ in segments if va<=address and address+size<=va+backed]
        if len(candidates)!=1:raise ValueError('Unique file-backed unchanged SMC')
        va,file=candidates[0]
        if kernel[file+address-va:file+address-va+size]!=leaf.at(leaf.names[symbol]['address'],size):raise ValueError('Fixed linked SMC changed')
    obj=b.original.reset.macho.MachO(p/'policy.o');fn=obj.function('_rpi5_restart_attempt')
    words=struct.unpack('<'+'I'*(fn['bytes']//4),obj.at(obj.names['_rpi5_restart_attempt']['address'],fn['bytes']))
    if sum((word&0xffe0fc00)==0x88e0fc00 for word in words)!=1:raise ValueError('Exact irreversible CASAL absent')
    names={row[2] for row in fn['relocations']}
    if '_rpi5_restart_diagnostic_reset' not in names or '_rpi5_restart_psci_reset' in names:raise ValueError('Pre-call hook must dominate actual reset')
    root=(p/'ramdisk.bin').read_bytes();payload=(p/'payload.bin').read_bytes();raw=(p/'probe.bin').read_bytes()
    if root!=(b.BASE/'ramdisk.bin').read_bytes() or (p/'root-catalog.json').read_bytes()!=(b.BASE/'root-catalog.json').read_bytes():raise ValueError('Root33/real CLI changed')
    if payload!=b.original.payload_container.encode(kernel,root):raise ValueError('Actual complete container')
    offset=m['payload_offset']
    if type(offset)is not int or offset%64 or raw.find(payload)!=offset or raw.find(payload,offset+1)>=0:raise ValueError('Actual embedded payload')
    marker=b.MARKER+tag+' SAME_BOOT OWNED_FRAMEBUFFER_CONSOLE_V1'
    if raw.count(marker.encode())!=1 or raw.count((b.original.BOOT+' rpi5_psci_restart=1').encode()+b'\0')!=1:raise ValueError('Actual tag/runtime opt-in')
    elf=b.original.formats.elf((p/'display_restart.elf').read_bytes(),raw)
    if elf['__stack_top'][0]-elf['__bss_end'][0]!=32768:raise ValueError('Existing loader stack changed')
    def frames(path):return sorted(tuple(line.split('\t')[1:])+(line.split('\t')[0].rsplit(':',1)[-1],) for line in path.read_text().splitlines())
    if frames(p/'loader-main.su')!=frames(b.BASE/'loader-main.su'):raise ValueError('Actual loader control-flow stack changed')
    contract=dict(profile=b.PROFILE,parent=str(b.BASE),parent_manifest_sha256=b.BASE_SHA,image=str(p/'probe.bin'),image_bytes=len(raw),image_sha256=b.sha(p/'probe.bin'),
        kernel_sha256=b.sha(p/'kernel.display-restart'),root_sha256=b.sha(p/'ramdisk.bin'),root_bytes=len(root),root_nodes=33,
        terminal_seconds=180,hardware_watchdog_seconds=15,watchdog_reloaded_by_diagnostic=False,watchdog_deadline_changed=False,
        watchdog_rate_bound_proven=False,physical_psci_causality_proven=False,target_executed=False,poweroff_supported=False)
    if any(not same(m.get(key),value) for key,value in contract.items()):raise ValueError('Exact diagnostic limits and truthfulness required')
    report=b.oldcheck.inspect(b.BASE,b.BASE_SHA)
    envelope=max(va+memory for va,memory,_,_,_ in segments)-min(va for va,memory,_,_,_ in segments if memory)
    root_pa=((0x7004000+envelope+16383)&~16383)+0x8000
    report.update(contract,package=str(p),manifest_sha256=b.sha(manifest),tag=tag,trial_marker=marker,
        root_catalog=str(p/'root-catalog.json'),root_catalog_sha256=b.sha(p/'root-catalog.json'),
        root_copy_marker=f'RPI5XNU:BL33:RAMDISK_MATERIALIZED PA={root_pa:016x} BYTES={len(root):016x} VERIFIED',
        kernel_copy_marker=f'RPI5XNU:BL33:KERNEL_MATERIALIZED BYTES={envelope:016x} FULL_ENVELOPE_VERIFIED NO_BOOT_ARGS_WRITTEN NO_TRANSFER',
        restart_ready_marker=protocol.READY.decode(),restart_pre_smc_prefix=protocol.PRE_PREFIX.decode(),
        diagnostic_checks=dict(actual_four_owner_replacements=True,exact_original_policy_and_casal=True,
            unchanged_fixed_smc=True,read_only_pm_snapshot=True,lock_free_bounded_uart=True,unchanged_root33_cli=True,
            unchanged_180s_service_deadline=True,nominal_not_physical_rate_claim=True,complete_byte_closure=True))
    return report
