#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Offline, default-off reset slice. Never links/stages/executes a boot image."""
import hashlib
import json
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile
from . import psci_restart_candidate_profile as profile
from . import check_apple_pthread_kernel_contract as macho

ROOT=profile.ROOT
FIRMWARE=ROOT/'build/rpi5/tfa-candidate'
FW_SHA='413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46'
ELF_SHA='2defa0796e74231c21956388b6621c63dce4353c00743793105228134e4c5f55'
DATABASE=ROOT/'build/rpi5-xcode27/fresh-435uage7/obj/DEVELOPMENT_ARM64_BCM2712/compile_commands.json'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def firmware_proof():
    """Actual accepted binary, not merely a similarly named platform source."""
    binary=FIRMWARE/'build/rpi5/debug/bl31.bin';elf=FIRMWARE/'build/rpi5/debug/bl31/bl31.elf'
    if sha(binary)!=FW_SHA or sha(elf)!=ELF_SHA:raise ValueError('Exact normal firmware required')
    raw=binary.read_bytes();data=elf.read_bytes()
    if data[:7]!=b'\x7fELF\x02\x01\x01' or struct.unpack_from('<HH',data,16)!=(2,183):raise ValueError('ELF identity')
    phoff=struct.unpack_from('<Q',data,32)[0];phsize,phnum=struct.unpack_from('<HH',data,54)
    if phsize!=56:raise ValueError('ELF PH size')
    matched=0
    for i in range(phnum):
        typ,flags,off,va,pa,size,memory,align=struct.unpack_from('<IIQQQQQQ',data,phoff+56*i)
        if typ==1 and size:
            if va!=pa or raw[pa:pa+size]!=data[off:off+size]:raise ValueError('Firmware load bytes differ')
            matched+=1
    if not matched:raise ValueError('No firmware loads')
    # Pinned map names + exact linked callback table and decoded B/BL targets.
    mapping=(FIRMWARE/'build/rpi5/debug/bl31/bl31.map').read_text()
    for owner in ('rpi3_pm.o:(.text.rpi3_system_reset)', 'rpi3_pm.o:(.text.rpi3_watchdog_reset)',
                  'rpi3_pm.o:(.rodata.plat_rpi3_psci_pm_ops)', 'psci_system_off.o:(.text.psci_system_reset)'):
        if owner not in mapping:raise ValueError('Actual firmware owner missing')
    if struct.unpack_from('<Q',raw,0x90f0+0x58)[0]!=0x64c8:raise ValueError('PSCI reset callback differs')
    def branch(at,target):
        op=struct.unpack_from('<I',raw,at)[0];offset=op&0x3ffffff
        if offset&0x2000000:offset-=0x4000000
        if op>>26!=0x25 or at+4*offset!=target:raise ValueError('Actual BL target differs')
    branch(0x5d80,0x5e28);branch(0x64dc,0x6550)
    # Address construction gives PM_RSTC 0x107d20001c, and stores watchdog/RSTC.
    expected=(0xd2800388,0xf2afa408,0xf2c00208,0x52800149,0x72ab4009,0xb9000909,
              0xb940010a,0x529ff9eb,0x72b4bfeb,0x0a0b014a,0x0b090149,0x11005929,
              0xb9000109,0xd503207f,0x17ffffff)
    if struct.unpack_from('<15I',raw,0x6564)!=expected:raise ValueError('Actual reset MMIO/park sequence differs')
    return dict(firmware_sha256=FW_SHA,elf_sha256=ELF_SHA,psci_version='1.1',
        service_dispatch=0x5d80,psci_system_reset=0x5e28,callback_table=0x90f0,
        callback_offset=0x58,callback=0x64c8,watchdog_reset=0x6550,
        pm_rstc=0x107d20001c,pm_wdog=0x107d200024,
        system_reset_linked=True,physical_restart_proven=False,system_off_qualified=False)


def build():
    proof=firmware_proof();pins={};headers={};commands=[];scans={}
    def pin(path,digest=None):
        path=str(Path(path).absolute());actual=sha(path)
        if digest is not None and actual!=digest:raise ValueError('Source pin drift '+path)
        if path in pins and pins[path]!=actual:raise ValueError('Source changed during build '+path)
        pins[path]=actual
    paths=[Path(__file__),Path(profile.__file__),Path(macho.__file__),DATABASE,profile.ORIGINAL,
        ROOT/'loader/rpi5/psci_restart_candidate.c',ROOT/'loader/rpi5/psci_restart_candidate.h',
        ROOT/'osfmk/arm64/rpi5_psci_restart_candidate.S',ROOT/'iokit/Kernel/rpi5_psci_restart_candidate.inc',
        ROOT/'tools/rpi5/tests/test_psci_restart_candidate.py',ROOT/'tools/rpi5/tests/psci_restart_candidate_host.c',
        ROOT/'tools/rpi5/tests/test_pcie_fdt.py',ROOT/'libsyscall/wrappers/reboot.c',
        ROOT/'bsd/kern/syscalls.master',ROOT/'bsd/kern/kern_xxx.c',ROOT/'bsd/kern/kern_shutdown.c',
        ROOT/'osfmk/kern/machine.c',ROOT/'osfmk/arm64/machine_routines.c',
        ROOT/'bsd/sys/reboot.h',ROOT/'osfmk/arm64/rpi5_firmware_fdt.inc',
        ROOT/'tools/rpi5/tfa.lock.json',ROOT/'loader/rpi5/fdt.c',ROOT/'loader/rpi5/ranges.c']
    paths += [FIRMWARE/p for p in ('plat/rpi/rpi5/platform.mk','plat/rpi/rpi5/include/rpi_hw.h',
        'plat/rpi/common/rpi3_pm.c','lib/psci/psci_main.c','lib/psci/psci_setup.c',
        'lib/psci/psci_system_off.c','include/lib/psci/psci.h','build/rpi5/debug/bl31.bin',
        'build/rpi5/debug/bl31/bl31.elf','build/rpi5/debug/bl31/bl31.map','build/rpi5/debug/bl31/rpi3_pm.d')]
    for p in paths:pin(p)
    for tool in ('clang','llvm-nm','llvm-objdump'):
        pin(subprocess.check_output(['xcrun','--find',tool],text=True).strip())
    out=Path(tempfile.mkdtemp(prefix='psci-restart-candidate-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True)
    def run(args,label,cwd=ROOT):
        args=list(map(str,args));r=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=90)
        for stream in ('stdout','stderr'):(out/(label+'.'+stream)).write_text(getattr(r,stream))
        commands.append(dict(label=label,command=args,cwd=str(cwd),returncode=r.returncode))
        if r.returncode:raise ValueError(label+': '+r.stderr[-5000:])
        return r.stdout
    def deps(path,cwd):
        text=Path(path).read_text().replace('\\\n',' ');words=shlex.split(text.partition(':')[2])
        return {str((Path(cwd)/s).resolve()):sha((Path(cwd)/s).resolve()) for s in words}
    def compile_(flags,source,label,cwd=ROOT):
        pre=out/(label+'.scan.d');post=out/(label+'.actual.d');obj=out/(label+'.o')
        run([*flags,'-M','-MF',pre,source],label+'-scan',cwd);before=deps(pre,cwd)
        for p,d in before.items():pin(p,d);headers[p]=d
        run([*flags,'-MD','-MF',post,'-c',source,'-o',obj],label+'-compile',cwd)
        if before!=deps(post,cwd):raise ValueError('Actual header closure differs')
        scans[label]=before
        return obj
    run(['python3','-m','unittest','tools.rpi5.tests.test_psci_restart_candidate','-v'],'native-tests')
    raw=profile.ORIGINAL.read_text();derived=out/'IOPlatformExpert.restart.cpp';derived.write_text(profile.derive(raw))
    row=next(r for r in json.loads(DATABASE.read_text()) if r['file']==str(profile.ORIGINAL))
    flags=[];i=0
    while i<len(row['arguments']):
        a=row['arguments'][i]
        if a in ('-o','-MF','-MT','-MQ'):i+=2;continue
        if a in ('-c','-MD','-MMD') or a==str(profile.ORIGINAL):i+=1;continue
        flags.append(a);i+=1
    flags += ['-I',str(ROOT),'-iquote',str(profile.ORIGINAL.parent)]
    old=compile_(flags,profile.ORIGINAL,'original',row['directory'])
    off=compile_(flags,derived,'default-off',row['directory'])
    enabled=compile_([*flags,'-DRPI5_PSCI_RESTART_CANDIDATE=1','-DRPI5_FIRMWARE_FDT_HANDOFF=1'],derived,'opt-in',row['directory'])
    a,b=macho.MachO(old),macho.MachO(off)
    owner=next(n for n in a.names if 'haltRestart' in n and 'IOPlatformExpert' in n)
    if a.function(owner)!=b.function(owner):raise ValueError('Default-off dispatch changed')
    if any('rpi5_restart' in s['name'] for s in b.symbols):raise ValueError('Default-off has reset provider')
    opt_imports=run(['xcrun','llvm-nm','--undefined-only',enabled],'opt-in-undefined')
    for name in ('_rpi5_restart_attempt','_rpi5_firmware_fdt_view'):
        if name not in opt_imports:raise ValueError('Actual candidate dependency absent')
    target=['xcrun','clang','-target','arm64-apple-macosx13.0','-mcpu=cortex-a76',
        '-ffreestanding','-fno-builtin','-fno-stack-protector','-O2','-Wall','-Wextra','-Werror',
        '-I',str(ROOT/'loader/rpi5')]
    policy=compile_([*target,'-std=c11'],ROOT/'loader/rpi5/psci_restart_candidate.c','policy')
    leaf=compile_(target,ROOT/'osfmk/arm64/rpi5_psci_restart_candidate.S','smc')
    leaf_disassembly=run(['xcrun','llvm-objdump','-d',leaf],'smc-disassembly')
    if leaf_disassembly.count('smc\t#0')!=3 or 'str\t' in leaf_disassembly or 'ldr\t' in leaf_disassembly:
        raise ValueError('Fixed SMC-only leaf differs')
    # No unresolved leaf imports; policy refers only to existing parsers and
    # fixed leaves. No compiler runtime/atomic fallback allowed.
    if run(['xcrun','llvm-nm','--undefined-only',leaf],'smc-undefined').strip():raise ValueError('Leaf imports')
    required=set(run(['xcrun','llvm-nm','-ju',policy],'policy-undefined').split())
    expected={'_rpi5_fdt_property','_rpi5_fdt_psci_smc','_rpi5_restart_current_el',
        '_rpi5_restart_psci_version','_rpi5_restart_psci_feature','_rpi5_restart_psci_reset'}
    if required!=expected:raise ValueError('Unexpected policy dependencies '+str(required))
    for p,d in list(pins.items()):pin(p,d)
    manifest=dict(profile='rpi5-psci-restart-default-off-software-candidate-v1',
        firmware=proof,inputs_sha256=pins,headers_sha256=headers,scanned_and_consumed=scans,
        commands=commands,default_off_dispatch=a.function(owner),policy_imports=sorted(required),
        activation=dict(compile_macro='RPI5_PSCI_RESTART_CANDIDATE=1',boot_argument='rpi5_psci_restart=1',
            platform_mode='kPERestartCPU only',existing_callback_priority=True,automatic_retry=False),
        scope=dict(kernel_linked=False,loader_built=False,hardware_access=False,target_executed=False,
            successful_reboot_proven=False,poweroff_qualified=False,original_apple_privilege_shutdown_path_unchanged=True),
        generated_sha256={str(p):sha(p) for p in sorted(out.iterdir()) if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(output=str(out),manifest_sha256=sha(out/'manifest.json'),scope=manifest['scope']),indent=2))
    return out


if __name__=='__main__':build()
