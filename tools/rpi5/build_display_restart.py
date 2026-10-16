#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct linked HDMI + genuine syscall55 restart candidate; never execute it."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid
from . import build_display_xnu_console as display
from . import check_display_xnu_console as formats
from . import build_psci_restart_candidate as reset
from . import psci_restart_candidate_profile as policy
from . import root_capacity_profile as rootfs
from . import payload_container, prepare_pid1

ROOT=display.ROOT
BASE=ROOT/'build/rpi5/display-xnu-console-5cd94fg_'
BASE_SHA='d1c6ce8f6b7ed198a237d367ed821e636f0e073fdf97be8d41212afed497a165'
RUNTIME=ROOT/'build/rpi5/apple-pthread-static-complete-gm82fjkz'
RUNTIME_SHA='4a22b183000378e842d59c643ed1f8a80a520e1e77d62370880a7c095adfc35a'
RESET=ROOT/'build/rpi5/psci-restart-candidate-pdjka9li'
RESET_SHA='5339d6c36ae832b58fb285968630b1af44f4e1b0662a6c021d1c5b896ce67fb8'
JOIN=ROOT/'build/rpi5/apple-pthread-join-wait-ri8lyyub'
BOOT='serial=3 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 bcm2712_cpu_on_all=1 bcm2712_terminal_watchdog=1'
MARKER='RPI5XNU:DISPLAYRESTART:ENTRY TAG='

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def document(p):return json.loads(Path(p).read_text())
def derive_main(raw):
    old='command_line = "'+BOOT+'";'
    if raw.count(old)!=1 or raw.count('RPI5XNU:DISPLAYXNU:ENTRY TAG=')!=1:raise ValueError('Exact accepted main required')
    return raw.replace(old,'command_line = "'+BOOT+' rpi5_psci_restart=1";').replace('RPI5XNU:DISPLAYXNU:ENTRY TAG=',MARKER)

def source_paths():
    return [Path(__file__),ROOT/'tools/rpi5/check_display_restart.py',
        ROOT/'tools/rpi5/tests/test_display_restart.py',ROOT/'tools/rpi5/tests/reboot_cli_host.c',
        ROOT/'tools/rpi5/user/reboot_cli.c',ROOT/'tools/rpi5/display_restart_native.py',
        ROOT/'tools/rpi5/root_capacity_native.py',ROOT/'tools/rpi5/compare_native_macho.py',
        ROOT/'tools/rpi5/audit_macho.py',ROOT/'tools/rpi5/prepare_handoff.py',ROOT/'tools/rpi5/build_probe.py',Path(display.__file__),Path(formats.__file__),
        Path(reset.__file__),Path(policy.__file__),Path(rootfs.__file__),Path(payload_container.__file__),Path(prepare_pid1.__file__)]

def build():
    pins={};headers={};scans={};commands=[]
    def pin(path,expected=None):
        path=str(Path(path).absolute());value=sha(path)
        if expected is not None and expected!=value:raise ValueError('Input changed '+path)
        if path in pins and pins[path]!=value:raise ValueError('Conflicting input '+path)
        pins[path]=value
    parents={}
    for directory,digest in ((BASE,BASE_SHA),(RUNTIME,RUNTIME_SHA),(RESET,RESET_SHA)):
        pin(directory/'manifest.json',digest);m=document(directory/'manifest.json');parents[directory]=m
        for key in ('inputs_sha256','source_inputs_sha256','headers_sha256','generated_sha256'):
            for name,value in m.get(key,{}).items():pin(name,value)
    for path in source_paths():pin(path)
    for path in [ROOT/'libsyscall/xcodescripts/create-syscalls.pl',ROOT/'bsd/kern/syscalls.master',
        ROOT/'libsyscall/Platforms/syscall.map',ROOT/'libsyscall/Platforms/MacOSX/arm64/syscall.map',*sorted((ROOT/'libsyscall/custom').glob('*'))]:
        if path.is_file():pin(path)
    for name in ('clang','ld','strip','llvm-nm','llvm-objdump'):
        pin(subprocess.check_output(['xcrun','--find',name],text=True).strip())
    pin('/usr/bin/perl')
    out=Path(tempfile.mkdtemp(prefix='display-restart-',dir=ROOT/'build/rpi5'));print('OUTPUT='+str(out),flush=True)
    tag=uuid.uuid4().hex
    def run(args,label,cwd=ROOT,env=None):
        args=list(map(str,args));r=subprocess.run(args,cwd=cwd,env=env,capture_output=True,text=True,timeout=120)
        log=out/(label+'.log');log.write_text(r.stdout+r.stderr)
        commands.append(dict(label=label,command=args,cwd=str(cwd),returncode=r.returncode,log=str(log),log_sha256=sha(log)))
        if r.returncode:raise ValueError(label+': '+r.stderr[-5000:])
        warnings=[line for line in r.stderr.splitlines() if 'warning:' in line]
        if label=='kernel-link':
            if warnings!=[line for line in (BASE/'kernel-link.log').read_text().splitlines() if 'warning:' in line]:raise ValueError('Kernel warnings changed')
        elif label=='platform-compile':
            if len(warnings)!=1 or "warning: variable 'i' set but not used" not in warnings[0]:raise ValueError('Platform warning changed')
        elif warnings:raise ValueError('Unexpected warning '+label)
        return r.stdout
    def compile_(flags,source,label,cwd=ROOT):
        pin(source);pre=out/(label+'.scan.d');post=out/(label+'.actual.d');obj=out/(label+'.o')
        run([*flags,'-M','-MF',pre,source],label+'-scan',cwd)
        names=display.dependencies(pre,cwd)
        for p in names:pin(p);headers[p]=pins[p]
        run([*flags,'-c','-MD','-MF',post,source,'-o',obj],label+'-compile',cwd)
        if names!=display.dependencies(post,cwd):raise ValueError('Header set drift '+label)
        for p in names:pin(p,headers[p])
        scans[label]=sorted(names);return obj
    print('PHASE=original-userland-wrapper-and-generated-syscall',flush=True)
    rt=parents[RUNTIME];cmd=next(r['command'] for r in rt['commands'] if r['stdout'].endswith('/smoke-compile.stdout'))
    uf=display.compiler_flags(cmd,ROOT/'tools/rpi5/user/pthread_smoke.c')
    cli=compile_(uf,ROOT/'tools/rpi5/user/reboot_cli.c','cli')
    wrapper=compile_(uf,ROOT/'libsyscall/wrappers/reboot.c','apple-reboot-wrapper')
    generated=out/'generated';generated.mkdir()
    run(['/usr/bin/perl',ROOT/'libsyscall/xcodescripts/create-syscalls.pl',ROOT/'bsd/kern/syscalls.master',ROOT/'libsyscall/custom',
        ROOT/'libsyscall/Platforms','MacOSX',generated],'original-syscall-generator',env=dict(os.environ,ARCHS='arm64'))
    pin(JOIN/'manifest.json');jm=document(JOIN/'manifest.json')
    template=next(r['command'] for r in jm['commands'] if r['stdout'].endswith('/create-trap-preprocess.stdout'))
    af=template[:template.index('-E')];src=generated/'___reboot.s';pin(src)
    if 'SYSCALL_NONAME(reboot, 2, cerror_nocancel)' not in src.read_text():raise ValueError('Genuine reboot trap shape')
    pre=out/'syscall.scan.d';post=out/'syscall.actual.d'
    run([*af,'-M','-MF',pre,src],'syscall-scan');names=display.dependencies(pre,ROOT)
    for p in names:pin(p);headers[p]=pins[p]
    assembly=run([*af,'-E','-P','-MD','-MF',post,src],'syscall-preprocess')
    if names!=display.dependencies(post,ROOT):raise ValueError('Syscall dependencies drift')
    scans['syscall']=sorted(names)
    asm=out/'syscall.s';asm.write_text(assembly.replace('%%','\n').replace(';','\n'))
    trap=out/'syscall.o';run([af[0],'-target','arm64-apple-darwin','-mcpu=cortex-a76','-x','assembler','-c',asm,'-o',trap],'syscall-assemble')
    run(['xcrun','llvm-objdump','-d','-r',trap],'syscall-disassembly')
    if run(['xcrun','nm','-ju',trap],'syscall-undefined').split()!=['_cerror_nocancel']:raise ValueError('Syscall error owner')
    link=next(r['command'] for r in rt['commands'] if r['stdout'].endswith('/target-link.stdout'))
    cli_target=out/'NOT_RUN_reboot';changes={str(RUNTIME/'smoke.o'):str(cli),rt['target']:str(cli_target),str(RUNTIME/'target.map'):str(out/'cli.map')}
    if any(link.count(k)!=1 for k in changes):raise ValueError('Runtime exact replacement')
    args=[changes.get(a,a) for a in link]+[str(wrapper),str(trap)]
    run(args,'cli-link');cli_shape=prepare_pid1.inspect(cli_target.read_bytes())
    if run(['xcrun','nm','-ju',cli_target],'cli-undefined').strip():raise ValueError('CLI unresolved')
    run(['xcrun','llvm-objdump','-d',cli_target],'cli-disassembly')
    print('PHASE=full-HDMI-kernel-exact-platform-replacement',flush=True)
    rows=document(display.DATABASE)
    row=next(r for r in rows if r['file']==str(policy.ORIGINAL))
    kflags=display.compiler_flags(row['arguments'],policy.ORIGINAL)+['-I',str(ROOT),'-iquote',str(policy.ORIGINAL.parent),'-DRPI5_PSCI_RESTART_CANDIDATE=1','-DRPI5_FIRMWARE_FDT_HANDOFF=1']
    source=out/'IOPlatformExpert.restart.cpp';source.write_text(policy.derive(policy.ORIGINAL.read_text()))
    platform=compile_(kflags,source,'platform',Path(row['directory']))
    crow=next(r for r in rows if r['file']==str(ROOT/'pexpert/arm/pe_fiq.c'))
    cflags=display.compiler_flags(crow['arguments'],Path(crow['file']))+['-I',str(ROOT/'loader/rpi5')]
    pobj=compile_(cflags,ROOT/'loader/rpi5/psci_restart_candidate.c','policy',Path(crow['directory']))
    # Real kernel target/include/optimization flags, only the language changes.
    sflags=[a for a in cflags if a!='-xc']+['-x','assembler-with-cpp']
    sobj=compile_(sflags,ROOT/'osfmk/arm64/rpi5_psci_restart_candidate.S','smc',Path(crow['directory']))
    run(['xcrun','llvm-objdump','-d','-r',pobj,sobj],'restart-disassembly')
    old=display.OBJ/'iokit/DEVELOPMENT/IOPlatformExpert.cpo';original=(BASE/'kernel.display.filelist').read_text().splitlines()
    if original.count(str(old))!=1 or len(original)!=len(set(original)):raise ValueError('Exact original kernel object boundary')
    new=[str(platform) if p==str(old) else p for p in original]+[str(pobj),str(sobj)]
    filelist=out/'kernel.restart.filelist';filelist.write_text(''.join(p+'\n' for p in new))
    for p in original:pin(p)
    kernel=out/'kernel.display-restart';klink=next(r['command'] for r in parents[BASE]['commands'] if r['log'].endswith('/kernel-link.log'))
    changes={str(BASE/'kernel.display.filelist'):str(filelist),str(BASE/'kernel.unstripped'):str(out/'kernel.unstripped'),
        '-Wl,-map,'+str(BASE/'kernel.map'):'-Wl,-map,'+str(out/'kernel.map')}
    if any(klink.count(k)!=1 for k in changes):raise ValueError('Kernel link boundary')
    run([changes.get(a,a) for a in klink],'kernel-link')
    run(['xcrun','strip','-S',out/'kernel.unstripped','-o',kernel],'kernel-strip')
    if run(['xcrun','nm','-ju',kernel],'kernel-undefined').strip():raise ValueError('Unresolved full kernel')
    formats.macho(kernel.read_bytes())
    print('PHASE=root33-and-tagged-retained-HDMI-loader',flush=True)
    import struct
    old_payload=(BASE/'payload.bin').read_bytes();root_offset,root_bytes=struct.unpack_from('<QQ',old_payload,136)
    old_root=old_payload[root_offset:root_offset+root_bytes]
    if hashlib.sha256(old_root).hexdigest()!=display.ROOT_SHA:raise ValueError('Original root mismatch')
    files=rootfs.files_from(old_root)
    if '/sbin/reboot' in files:raise ValueError('Existing path cannot be overwritten')
    files['/sbin/reboot']=(cli_target.read_bytes(),0o555)
    new_root,catalog=rootfs.build(files)
    if catalog!=rootfs.inspect(new_root):raise ValueError('Rebuilt root inspection differs')
    if len(catalog['entries'])!=33:raise ValueError('Expected exact additional root node')
    (out/'ramdisk.bin').write_bytes(new_root);(out/'root-catalog.json').write_text(json.dumps(catalog,indent=2,sort_keys=True)+'\n')
    packed=out/'payload.bin';packed.write_bytes(payload_container.encode(kernel.read_bytes(),new_root))
    main=out/'probe_main.c';main.write_text(derive_main((BASE/'probe_main.c').read_text()))
    record=next(r['command'] for r in parents[BASE]['commands'] if r['log'].endswith('/loader-probe_main-compile.log'))
    lf=display.compiler_flags(record,BASE/'probe_main.c')
    lf=[a if not a.startswith('-DRPI5_DISPLAY_XNU_TAG=') else '-DRPI5_DISPLAY_XNU_TAG="'+tag+'"' for a in lf]
    mainobj=compile_(lf,main,'loader-main')
    payload_s=out/'payload.S';payload_s.write_text('.section .payload,"a"\n.balign 64\n.incbin "'+str(packed)+'"\n')
    payload_o=compile_(lf,payload_s,'loader-payload')
    llink=next(r['command'] for r in parents[BASE]['commands'] if r['log'].endswith('/loader-link.log'))
    elf=out/'display_restart.elf';image=out/'probe.bin'
    changes={str(BASE/'loader-probe_main.o'):str(mainobj),str(BASE/'loader-payload.o'):str(payload_o),str(BASE/'display_xnu.elf'):str(elf)}
    if any(llink.count(k)!=1 for k in changes):raise ValueError('Loader replacement boundary')
    run([changes.get(a,a) for a in llink],'loader-link');run([ROOT/'tools/rpi5/tfa-objcopy','-O','binary',elf,image],'loader-objcopy')
    if run(['xcrun','llvm-nm','--undefined-only',elf],'loader-undefined').strip():raise ValueError('Loader imports')
    symbols=formats.elf(elf.read_bytes(),image.read_bytes())
    if symbols['__stack_top'][0]-symbols['__bss_end'][0]!=32768:raise ValueError('Loader stack changed')
    if image.read_bytes().count((MARKER+tag+' SAME_BOOT OWNED_FRAMEBUFFER_CONSOLE_V1').encode())!=1:raise ValueError('Actual unique entry marker')
    body=image.read_bytes();offset=body.find(packed.read_bytes())
    if offset<0 or offset%64 or body.find(packed.read_bytes(),offset+1)>=0:raise ValueError('Actual embedded payload')
    # Main control flow is unchanged apart from literal values; require actual
    # compiler stack frames identical to the accepted main, not an estimate.
    def frames(p):return sorted(tuple(line.split('\t')[1:])+(line.split('\t')[0].rsplit(':',1)[-1],) for line in p.read_text().splitlines())
    if frames(out/'loader-main.su')!=frames(BASE/'loader-probe_main.su'):raise ValueError('Loader stack frames changed')
    for p,h in pins.items():
        if sha(p)!=h:raise ValueError('Input changed during build '+p)
    report=dict(profile='rpi5-display-original-reboot-syscall-full-composition-v1',tag=tag,
        kernel=str(kernel),kernel_sha256=sha(kernel),image=str(image),image_sha256=sha(image),image_bytes=image.stat().st_size,
        cli=str(cli_target),cli_sha256=sha(cli_target),cli_macho=cli_shape,root_sha256=hashlib.sha256(new_root).hexdigest(),root_bytes=len(new_root),root_nodes=33,
        root_only_added='/sbin/reboot',old_socket_catalog_not_extended=True,boot_argument='rpi5_psci_restart=1',
        kernel_replaced={str(old):str(platform)},kernel_added=[str(pobj),str(sobj)],payload_offset=offset,
        original_shutdown_permission_path_unchanged=True,original_watchdog_seconds=180,hardware_watchdog_seconds=15,
        existing_display_objects_unchanged=True,firmware=reset.firmware_proof(),
        scope=dict(target_executed=False,physical_restart_proven=False,poweroff_supported=False,staged=False,
            panic_enum_modes_excluded=True,all_panic_contexts_excluded=False,full_apple_reboot_utility=False),
        commands=commands,inputs_sha256=pins,headers_sha256=headers,compiler_scans=scans,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(directory=str(out),manifest_sha256=sha(out/'manifest.json'),image_sha256=sha(image)),indent=2))
    return out

if __name__=='__main__':build()
