#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct tagged 41-node/ready-v2 retained-FDT loader; offline only.

Adapt the frozen corrected-root loader: replay its original object link, then
replace only the payload and a copied main with one unique serial tag. Preserve
the real four-CPU startup, storage-off command, Device/full-FDT handoff and
normal firmware. No frozen sources or physical media are modified.
"""
import argparse
import difflib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import uuid
try:
    from . import build_root96_fdt_package as base
    from . import build_pcie_id_trial_package as support
    from . import check_root96_command_package as root_check
    from . import root_capacity_profile as root_profile
    from . import root_capacity_native as native
    from . import root96_batch_handoff as handoff
    from .audit_macho import inspect as inspect_kernel
except ImportError:
    import build_root96_fdt_package as base
    import build_pcie_id_trial_package as support
    import check_root96_command_package as root_check
    import root_capacity_profile as root_profile
    import root_capacity_native as native
    import root96_batch_handoff as handoff
    from audit_macho import inspect as inspect_kernel

ROOT,sha,LOADER=base.ROOT,base.sha,base.LOADER
PROFILE='root96-ready41-retained-fdt-v1'
KERNEL_DIR=ROOT/'build/rpi5/root96-ready-delay-kernel-20261013-final'
KERNEL=KERNEL_DIR/'kernel.ready'
KERNEL_SHA='c00bc5250b5fc3c1b6b71da530a22eafcdaa61bd3d554511ceca60214b1c4336'
KERNEL_MANIFEST_SHA='73d44400c8b473d92fc186a199cce0fda908027248f1d2287a9888f62d08c23c'
ROOT_DIR=root_check.PACKAGE
WATCHDOG_MARKER='RPI5XNU:TERMINAL:WATCHDOG_READY SECONDS=180'
WATCHDOG_PROFILE='root96-terminal-ready-delay-kernel-v2'
LABELS=('baseline-link','baseline-copy','main-compile','payload-compile','batch-link','batch-copy')


def merge(pins,more):
    for name,digest in more.items():
        if name in pins and pins[name]!=digest:raise ValueError('Conflicting batch input: '+name)
        pins[name]=digest


def inputs():
    pins,old,_=base.inputs()
    root=root_check.inspect(ROOT_DIR)
    if sha(KERNEL_DIR/'manifest.json')!=KERNEL_MANIFEST_SHA or sha(KERNEL)!=KERNEL_SHA:
        raise ValueError('Exact readiness-v2 kernel required')
    km=json.loads((KERNEL_DIR/'manifest.json').read_text())
    rm=json.loads((ROOT_DIR/'manifest.json').read_text())
    for directory,record in ((KERNEL_DIR,km),(ROOT_DIR,rm)):
        merge(pins,record['inputs_sha256']);merge(pins,record['generated_sha256'])
        merge(pins,{str(directory/'manifest.json'):sha(directory/'manifest.json')})
    for path in (Path(__file__).resolve(),Path(root_check.__file__).resolve(),Path(support.__file__).resolve(),
            ROOT/'tools/rpi5/check_root96_batch_package.py',ROOT/'tools/rpi5/tests/test_root96_batch_package.py',
            Path(handoff.__file__).resolve(),Path(native.__file__).resolve(),Path(root_profile.__file__).resolve(),
            ROOT/'tools/rpi5/compare_native_macho.py',ROOT/'tools/rpi5/tests/firmware_fdt_host.c',
            ROOT/'tools/rpi5/pcie_id_handoff_contract.py',ROOT/'tools/rpi5/tests/test_pcie_fdt.py'):
        merge(pins,{str(path):sha(path)})
    if km['profile']!=WATCHDOG_PROFILE or km['node_capacity']!=96 or km['terminal_deadline_seconds']!=180 or \
       km['first_notice_minimum_post_enable_seconds']!=5 or km['boot_caller_added'] or km['controller_initialized']:
        raise ValueError('Readiness/kernel scope changed')
    files=(KERNEL_DIR/'kernel.ready.filelist').read_text().splitlines()
    arm=[p for p in files if Path(p).name in ('arm_init.c.o','arm_init.o')]
    if arm!=[str(LOADER/'arm_init.c.o')] or '_rpi5_pcie_id_trial_start' in (KERNEL_DIR/'kernel.symbols').read_text():
        raise ValueError('Kernel must keep retained-FDT arm_init, without PCIe boot caller')
    base.verify(pins)
    return pins,old,root,km


def marker(tag):
    if not isinstance(tag,str) or not re.fullmatch('[0-9a-f]{32}',tag):raise ValueError('Fresh 128-bit tag required')
    return 'RPI5XNU:BL33:ROOT96_BATCH_TRIAL TAG='+tag+' CPUS=4 ROOT_NODES=41 WATCHDOG_READY_V2'


def derive_main(tag):
    original=(LOADER/'probe_main.c').read_text()
    anchor='void probe_el1_main(uintptr_t fdt_pa)\n{\n'
    if original.count(anchor)!=1:raise ValueError('Frozen loader entry changed')
    return original,original.replace(anchor,anchor+'    if (!text("'+marker(tag)+'\\r\\n")) return;\n')


def geometry():
    parsed=inspect_kernel(KERNEL.read_bytes())
    envelope=max(s['vmaddr']+s['vmsize'] for s in parsed['segments'])-parsed['virtual_base']
    end=0x7004000+envelope;args=(end+0x3fff)&~0x3fff;root=args+0x8000
    length=(ROOT_DIR/'ramdisk.bin').stat().st_size
    return dict(kernel_header=0x7004000,kernel_end=end,kernel_envelope=envelope,
        args_pa=args,tree_pa=args+0x4000,root_pa=root,root_end=root+length,root_bytes=length,
        root_copy_marker=f'RPI5XNU:BL33:RAMDISK_MATERIALIZED PA={root:016x} BYTES={length:016x} VERIFIED',
        root_mount_marker=f'RPI5XNU:RAMROOT:MOUNT NODES=41 BYTES={length} READONLY',
        kernel_copy_marker=f'RPI5XNU:BL33:KERNEL_MATERIALIZED BYTES={envelope:016x} FULL_ENVELOPE_VERIFIED NO_BOOT_ARGS_WRITTEN NO_TRANSFER')


def commands_for(package,old):
    original=next(r['command'] for r in old['commands'] if r['log'].endswith('/firmware-fdt-link.log'))
    replay=list(original);replay[replay.index('-o')+1]=str(package/'baseline.elf')
    main=list(next(r['command'] for r in old['commands'] if r['log'].endswith('/loader-main.log')))
    main[main.index('-c')+1]=str(package/'probe_main.c');main[main.index('-o')+1]=str(package/'probe_main.o')
    payload=['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align',
        '-ffreestanding','-fno-stack-protector','-mgeneral-regs-only','-O2','-Wall','-Wextra','-Werror',
        '-c',str(package/'payload.S'),'-o',str(package/'payload.o')]
    changes={str(LOADER/'probe_main.o'):str(package/'probe_main.o')}
    objects=[x for x in original if x.endswith('/payload.o')]
    if len(objects)!=1:raise ValueError('Frozen payload object ambiguous')
    changes[objects[0]]=str(package/'payload.o')
    link=[changes.get(x,x) for x in original];link[link.index('-o')+1]=str(package/'probe.elf')
    copy=lambda name:[''+str(ROOT/'tools/rpi5/tfa-objcopy'),'-O','binary',str(package/(name+'.elf')),str(package/(name+'.bin'))]
    return [replay,copy('baseline'),main+['-MD','-MF',str(package/'main.d')],
            payload+['-MD','-MF',str(package/'payload.d')],link,copy('probe')]


def generated_names():
    return {'baseline.elf','baseline.bin','probe_main.c','probe_main.c.diff','probe_main.o','probe_main.su',
        'payload.bin','payload.S','payload.o','probe.elf','probe.bin','main.d','payload.d','main-scan.txt','payload-scan.txt'}|{s+'.log' for s in LABELS}


def header_closure(package,old):
    headers={}
    for index,label in ((2,'main'),(3,'payload')):
        command=commands_for(package,old)[index][:-3]
        scan=support.scan_command(command)
        r=subprocess.run(scan,cwd=ROOT,text=True,capture_output=True,timeout=60)
        if r.returncode or r.stderr:raise ValueError('Batch dependency scan failed')
        before=base.dependencies((package/(label+'-scan.txt')).read_text())
        actual=base.dependencies((package/(label+'.d')).read_text())
        if before!=actual or before!=base.dependencies(r.stdout):raise ValueError('Batch complete dependency closure differs')
        merge(headers,before)
    return headers


def build():
    pins,old,root,km=inputs();tools=base.tool_identity()
    package=Path(tempfile.mkdtemp(prefix='root96-batch-',dir=ROOT/'build/rpi5'));tag=uuid.uuid4().hex
    before,after=derive_main(tag);(package/'probe_main.c').write_text(after)
    (package/'probe_main.c.diff').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='accepted/probe_main.c',tofile='probe_main.c')))
    (package/'payload.bin').write_bytes(base.encode(KERNEL.read_bytes(),(ROOT_DIR/'ramdisk.bin').read_bytes()))
    (package/'payload.S').write_text('.section .payload,"a"\n.balign 64\n.incbin "'+str(package/'payload.bin')+'"\n')
    commands=[]
    for index,(command,label) in enumerate(zip(commands_for(package,old),LABELS)):
        if index in (2,3):
            scan=support.scan_command(command[:-3]);r=subprocess.run(scan,cwd=ROOT,text=True,capture_output=True,timeout=60)
            if r.returncode or r.stderr:raise ValueError('Batch precompile dependency scan failed')
            (package/(('main' if index==2 else 'payload')+'-scan.txt')).write_text(r.stdout)
        r=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=60)
        log=package/(label+'.log');log.write_text(r.stdout+r.stderr)
        commands.append(dict(command=command,returncode=r.returncode,log=str(log)))
        if r.returncode or r.stderr:raise ValueError('Batch compilation/link failed: '+str(log))
        if index==1 and sha(package/'baseline.bin')!=old['image_sha256']:raise ValueError('Frozen loader replay differs')
    headers=header_closure(package,old);frames,budgets=support.stack_for(package,old)
    raw=(package/'probe.bin').read_bytes();layout=base.retained.device.accepted.old.inspect_elf((package/'probe.elf').read_bytes(),raw,base.BASE)
    end=max(s['address']+s['memory_size'] for s in layout['loads']);g=geometry()
    if g['root_end']>base.BASE or end>=0xb000000:raise ValueError('Batch root/loader/live FDT overlap')
    contract=base.handoff_contract(package,KERNEL)
    if raw[:contract['payload_offset']].count((marker(tag)+'\r\n\0').encode())!=1:raise ValueError('Unique tag must be in real loader, not payload')
    base.verify(pins);base.verify(headers)
    if base.tool_identity()!=tools:raise ValueError('Batch tool identity changed')
    if {p.name for p in package.iterdir()}!=generated_names():raise ValueError('Unexpected batch artifact closure')
    result=dict(profile=PROFILE,tag=tag,trial_marker=marker(tag),inputs_sha256=pins,headers_sha256=headers,
        generated_sha256={str(p):sha(p) for p in package.iterdir()},commands=commands,tool_identity=tools,
        image=str(package/'probe.bin'),image_sha256=sha(package/'probe.bin'),image_bytes=len(raw),entry=base.BASE,elf=layout,
        kernel=str(KERNEL),kernel_sha256=KERNEL_SHA,kernel_manifest=str(KERNEL_DIR/'manifest.json'),kernel_manifest_sha256=KERNEL_MANIFEST_SHA,
        root=str(ROOT_DIR/'ramdisk.bin'),root_sha256=root_check.IMAGE_SHA,root_manifest=str(ROOT_DIR/'manifest.json'),root_manifest_sha256=root_check.MANIFEST_SHA,
        embedded_init=root_profile.inspect((ROOT_DIR/'ramdisk.bin').read_bytes()),handoff=contract,geometry=g,
        root_profile_audit=root,stack_frames=frames,stack_budgets=budgets,
        original_loader_reproduced=True,only_payload_and_tagged_main_replaced=True,
        original_loader_manifest_sha256=base.LOADER_SHA,terminal_bootargs=base.failed.terminal.TERMINAL_COMMAND.decode(),
        normal_firmware_sha256=base.failed.NORMAL_FIRMWARE_SHA,terminal_watchdog_seconds=180,hardware_watchdog_seconds=15,
        watchdog_ready_marker=WATCHDOG_MARKER,watchdog_ready_profile=WATCHDOG_PROFILE,
        installed=False,physical_execution=False,controller_initialized=False,networking=False)
    manifest=package/'manifest.json';manifest.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    result['native_macho']=native.compare(KERNEL,package)
    result['native_handoff']=handoff.audit(LOADER,KERNEL,g['kernel_end'],g['root_bytes'],end)
    merge(result['inputs_sha256'],result['native_handoff']['inputs_sha256'])
    base.verify(result['inputs_sha256'])
    manifest.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return package,result


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();p,r=build()
    print(json.dumps({k:r[k] for k in ('image','image_sha256','image_bytes','trial_marker','geometry')},indent=2))
