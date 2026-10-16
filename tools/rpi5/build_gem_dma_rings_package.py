#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""New real loader->kernel reservation ownership plus inactive retained ring provider.

This creates no live controller caller, queue publication, DMA/IRQ activation,
media write or hardware evidence. The accepted HDMI/root/watchdog objects stay
unchanged except the privately derived arm_init and post-seed loader handoff.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import uuid
from tools.rpi5 import build_display_xnu_console as display
from tools.rpi5 import gem_dma_rings_profile as rings
from tools.rpi5 import gem_dma_reservation_profile as boot
from tools.rpi5 import reservation_record_loader_profile as record
from tools.rpi5 import payload_container
ROOT=display.ROOT
BASE=ROOT/'build/rpi5/display-xnu-console-5cd94fg_'
BASE_SHA='d1c6ce8f6b7ed198a237d367ed821e636f0e073fdf97be8d41212afed497a165'
TEMPLATE=ROOT/'build/rpi5/pcie-phy-reset-kernel-20261014-v2'
TEMPLATE_SHA='0dafc8e47ab3226833c36c9aab2a2da1116abb2ca4c814e1a81a852e372c0fb8'
SELECTED=ROOT/'build/rpi5/pcie-gem-selected-kernel-20261013-v1/overlay/rp1_gem_identify.c'
PROFILE='bcm2712-gem-owned-rings-resolved-reservations-default-off-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def sources():
    paths=[Path(__file__).resolve(),Path(rings.__file__),Path(boot.__file__),*record.sources()]
    paths += [ROOT/'iokit/Kernel'/p for p in ('BCM2712GEMDMARings.inc','BCM2712GEMDMARingsLifecycle.inc',
        'BCM2712GEMDMARingsMapping.inc','BCM2712GEMDMARingsRoute.inc','rpi5_gem_dma_route.c','rpi5_gem_dma_route.h',
        'rpi5_gem_ring_stage.c','rpi5_gem_ring_stage.h')]
    paths += [ROOT/'osfmk/arm64'/p for p in ('rpi5_reservation_kernel.c','rpi5_reservation_kernel.h',
        'rpi5_reservation_api.h','rpi5_reservation_boot.inc')]
    paths += [ROOT/'tools/rpi5/tests'/p for p in ('test_gem_dma_rings.py','gem_dma_rings_host.inc',
        'test_gem_dma_reservation.py','reservation_kernel_host.c','test_reservation_record.py','reservation_record_host.c',
        'test_gem_dma_memory.py','gem_dma_memory_host.cpp','test_pcie_fdt.py')]
    paths += [ROOT/'tools/rpi5'/p for p in ('gem_dma_memory_sources.json','gem_ring_stage_sources.json')]
    paths += [ROOT/p for p in rings.PINS]
    return paths
def build(output=None):
    output=Path(tempfile.mkdtemp(prefix='gem-dma-rings-',dir=ROOT/'build/rpi5')) if output is None else Path(output).resolve()
    if output.parent!=ROOT/'build/rpi5':raise ValueError('Distinct build child required')
    if output.exists() and any(output.iterdir()):raise ValueError('Never overwrite an existing build')
    output.mkdir(exist_ok=True)
    pins={};headers={};commands=[];scans={}
    def pin(p,expected=None):
        p=str(Path(p).absolute());actual=sha(p)
        if expected is not None and actual!=expected:raise ValueError('Pinned input differs: '+p)
        if p in pins and pins[p]!=actual:raise ValueError('Input changed during composition: '+p)
        pins[p]=actual
    pin(BASE/'manifest.json',BASE_SHA);parent=json.loads((BASE/'manifest.json').read_text())
    for key in ('inputs_sha256','actual_headers_sha256','generated_sha256'):
        for p,h in parent[key].items():pin(p,h)
    pin(TEMPLATE/'manifest.json',TEMPLATE_SHA);template=json.loads((TEMPLATE/'manifest.json').read_text())
    for p in sources():pin(p)
    for metadata in ('gem_dma_memory_sources.json','gem_ring_stage_sources.json'):
        for row in json.loads((ROOT/'tools/rpi5'/metadata).read_text())['sources']:pin(ROOT/row['path'],row['sha256'])
    pin(SELECTED)
    def run(args,name,cwd=ROOT,allowed=None):
        args=list(map(str,args));p=subprocess.run(args,cwd=cwd,capture_output=True,timeout=120)
        log=output/(name+'.log');log.write_bytes(p.stdout+p.stderr)
        commands.append(dict(command=args,cwd=str(cwd),returncode=p.returncode,log=str(log),log_sha256=sha(log)))
        if p.returncode:raise ValueError('Build failed: '+str(log))
        warnings=[s for s in p.stderr.decode(errors='replace').splitlines() if 'warning:' in s]
        if allowed=='arm':
            if len(warnings)!=1 or "dyld_kernel_fixups.h:367:12: warning: variable 'cnt' set but not used" not in warnings[0]:raise ValueError('New arm warning')
        elif allowed=='link':
            expected=[s for s in (BASE/'kernel-link.log').read_text().splitlines() if 'warning:' in s]
            if warnings!=expected:raise ValueError('New linker warning')
        elif warnings:raise ValueError('Compile warning: '+str(log))
        return p.stdout.decode(errors='replace')
    def compile(flags,source,name,cwd=ROOT,allowed=None):
        source=Path(source);pin(source);obj=output/(name+'.o');dep=output/(name+'.d')
        run([*flags,'-M','-MF',output/(name+'.scan.d'),source],name+'-scan',cwd)
        found=display.dependencies(output/(name+'.scan.d'),cwd);scans[name]=sorted(found)
        for path in found:pin(path);headers[path]=pins[path]
        run([*flags,'-c','-MD','-MF',dep,source,'-o',obj],name+'-compile',cwd,allowed)
        if display.dependencies(dep,cwd)!=found:raise ValueError('Actual compiler header closure changed')
        for path in found:pin(path,headers[path])
        return obj
    overlay=output/'overlay';hp,cp=rings.emit(overlay)
    newarm=output/'arm_init.c';newarm.write_text(boot.arm((BASE/'arm_init.c').read_text()))
    armrow=next(r for r in parent['commands'] if r['log'].endswith('/arm_init-compile.log'))
    armflags=display.compiler_flags(armrow['command'],BASE/'arm_init.c')+['-I',str(ROOT),'-I',str(ROOT/'osfmk'),'-fstack-usage']
    armobj=compile(armflags,newarm,'arm_init',Path(armrow['cwd']),'arm')
    run([*armflags,'-S',newarm,'-o',output/'arm_init.s'],'arm-assembly',Path(armrow['cwd']),'arm')
    def kernel_flags(name):
        row=next(r for r in template['compiles'] if r['command'][-1].endswith(name+'.o'))
        original=next(a for a in row['command'] if a.endswith('/overlay/'+name))
        flags=display.compiler_flags(row['command'],original)
        flags[1:1]=['-I'+str(ROOT),'-I'+str(ROOT/'osfmk'),'-I'+str(ROOT/'iokit/Kernel'),'-I'+str(ROOT/'loader/rpi5')]
        flags+=['-fstack-usage']
        cwd=display.OBJ/('iokit/DEVELOPMENT' if name.endswith('.cpp') else 'pexpert/DEVELOPMENT')
        return flags,cwd
    cppflags,cppcwd=kernel_flags('BCM2712PCIePHYTransport.cpp')
    cflags,ccwd=kernel_flags('rp1_gem_mdio.c')
    added=[compile(cppflags,cp,'dma-rings',cppcwd)]
    run([*cppflags,'-S',cp,'-o',output/'dma-rings.s'],'dma-rings-assembly',cppcwd)
    corepaths=[ROOT/'iokit/Kernel/rpi5_gem_dma_route.c',ROOT/'iokit/Kernel/rpi5_gem_ring_stage.c',
        ROOT/'osfmk/arm64/rpi5_reservation_kernel.c',ROOT/'loader/rpi5/reservation_record.c',
        ROOT/'loader/rpi5/ranges.c',ROOT/'loader/rpi5/reservations.c',ROOT/'loader/rpi5/pcie_released_windows.c',
        ROOT/'loader/rpi5/rp1_gem_capabilities.c',SELECTED,ROOT/'loader/rpi5/firmware_seed_fdt.c']
    for source in corepaths:added.append(compile(cflags,source,'kernel-'+source.stem,ccwd))
    original=(BASE/'kernel.display.filelist').read_text().splitlines();oldarm=str(BASE/'arm_init.o')
    if len(original)!=len(set(original)) or original.count(oldarm)!=1:raise ValueError('Exact one-object replacement required')
    newlist=output/'kernel.filelist';newlist.write_text('\n'.join(str(armobj) if p==oldarm else p for p in original)+'\n'+'\n'.join(map(str,added))+'\n')
    oldlink=next(r['command'] for r in parent['commands'] if r['log'].endswith('/kernel-link.log'))
    changes={str(BASE/'kernel.display.filelist'):str(newlist),str(BASE/'kernel.unstripped'):str(output/'kernel.unstripped'),
        '-Wl,-map,'+str(BASE/'kernel.map'):'-Wl,-map,'+str(output/'kernel.map')}
    if any(oldlink.count(a)!=1 for a in changes):raise ValueError('Original link changed')
    run([changes.get(a,a) for a in oldlink],'kernel-link',allowed='link')
    kernel=output/'kernel.owned-rings';run(['xcrun','strip','-S',output/'kernel.unstripped','-o',kernel],'kernel-strip')
    if run(['xcrun','nm','-ju',kernel],'kernel-undefined').strip():raise ValueError('Undefined genuine provider')
    symbols=run(['xcrun','nm','-nm',kernel],'kernel-symbols');(output/'kernel.symbols').write_text(symbols)
    for symbol in ('_rpi5_boot_reservation_record','_rpi5_reservation_record_validate_fdt','stageCPUOwned',
                   '_rpi5_gem_ring_stage','_rpi5_display_xnu_mapping_verify','_rpi5_console_mirror_publish'):
        if symbol not in symbols:raise ValueError('Linked implementation absent: '+symbol)
    for name in added:
        table=run(['xcrun','nm',name],name.stem+'-symbols')
        if '___cxx_global_var_init' in table:raise ValueError('Default-off provider acquired initializer')
    # Retain the exact accepted root and all its original payload semantics.
    raw=(BASE/'payload.bin').read_bytes();root_offset,root_bytes=struct.unpack_from('<QQ',raw,136)
    root=raw[root_offset:root_offset+root_bytes]
    if len(root)!=parent['root_bytes'] or hashlib.sha256(root).hexdigest()!=parent['root_sha256']:raise ValueError('Accepted zsh root differs')
    packed=output/'payload.bin';packed.write_bytes(payload_container.encode(kernel.read_bytes(),root))
    assembly=output/'payload.S';assembly.write_text('.section .payload,"a"\n.balign 64\n.incbin "'+str(packed)+'"\n')
    tag=uuid.uuid4().hex
    loaderrow=next(r for r in parent['commands'] if r['log'].endswith('/loader-probe_main-compile.log'))
    loaderflags=display.compiler_flags(loaderrow['command'],BASE/'probe_main.c')
    loaderflags=[a for a in loaderflags if not a.startswith('-DRPI5_DISPLAY_XNU_TAG=')]+['-DRPI5_DISPLAY_XNU_TAG="'+tag+'"']
    main=output/'probe_main.c';main.write_text(record.loader((BASE/'probe_main.c').read_text()))
    seed=output/'firmware_seed_tree.c';seed.write_text(record.seed((BASE/'firmware_seed_tree.c').read_text()))
    loaderobjects={}
    for label,source in [('probe_main',main),('firmware_seed_tree',seed),('payload',assembly),
                         ('reservation_record',ROOT/'loader/rpi5/reservation_record.c'),
                         ('reservation_record_tree',ROOT/'loader/rpi5/reservation_record_tree.c')]:
        loaderobjects[label]=compile(loaderflags,source,'loader-'+label)
    # Recompile the exact reused helper bodies for measured stack frames only;
    # the actual unchanged original helper objects remain in the loader link.
    bear=ROOT/'build/rpi5/bearssl-candidate/src'
    stackpaths={name:ROOT/'loader/rpi5'/(name+'.c') for name in record.STACK_UNITS}
    for name,path in [('sha2small',bear/'hash/sha2small.c'),('dec32be',bear/'codec/dec32be.c'),('enc32be',bear/'codec/enc32be.c')]:stackpaths[name]=path
    stackfiles={}
    for name,source in stackpaths.items():
        label='loader-'+name if name in loaderobjects else 'stack-'+name
        if name not in loaderobjects:compile(loaderflags,source,label)
        stackfiles[name]=output/(label+'.su')
    stack=record.stack_budget(stackfiles,output/'loader-probe_main.su',output/'loader-firmware_seed_tree.su')
    link=next(r['command'] for r in parent['commands'] if r['log'].endswith('/loader-link.log'))
    changes={str(BASE/('loader-'+name+'.o')):str(loaderobjects[name]) for name in ('probe_main','firmware_seed_tree','payload')}
    if any(link.count(p)!=1 for p in changes):raise ValueError('Exact retained loader composition changed')
    elf=output/'owned_rings.elf';image=output/'probe.bin';args=[changes.get(a,a) for a in link]
    args[args.index('-o')+1]=str(elf)
    args[args.index('-o'):args.index('-o')]=[str(loaderobjects['reservation_record']),str(loaderobjects['reservation_record_tree'])]
    run(args,'loader-link');run([ROOT/'tools/rpi5/tfa-objcopy','-O','binary',elf,image],'loader-objcopy')
    if run(['xcrun','llvm-nm','--undefined-only',elf],'loader-undefined').strip():raise ValueError('Undefined loader')
    syms=run(['xcrun','llvm-nm','-n',elf],'loader-symbols')
    parsed={r.split()[2]:int(r.split()[0],16) for r in syms.splitlines() if len(r.split())==3}
    if parsed['__probe_end']>=0xb000000 or parsed['__stack_top']-parsed['__bss_end']!=32768:raise ValueError('Actual retained stack/FDT overlap')
    body=image.read_bytes();encoded=packed.read_bytes();offset=body.find(encoded)
    if offset<0 or offset&63 or body.find(encoded,offset+1)>=0:raise ValueError('Exact embedded payload missing')
    for path,digest in pins.items():
        if sha(path)!=digest:raise ValueError('Consumed source changed: '+path)
    report=dict(profile=PROFILE,parent_manifest_sha256=BASE_SHA,tag=tag,
        kernel=str(kernel),kernel_sha256=sha(kernel),kernel_bytes=kernel.stat().st_size,
        image=str(image),image_sha256=sha(image),image_bytes=len(body),payload_offset=offset,
        root_sha256=parent['root_sha256'],root_bytes=root_bytes,loader_symbols=parsed,
        replaced_objects={oldarm:str(armobj)},added_objects=list(map(str,added)),unchanged_kernel_objects=len(original)-1,
        commands=commands,inputs_sha256=pins,actual_headers_sha256=headers,compiler_scans=scans,
        reservation_property='rpi5-resolved-reservations-v1',reservation_wire_bytes=1056,
        reservation_consumed_seed_zero_before_hash=True,reservation_sameboot_kernel_ready_after_vm=True,
        resolved_claims_replayed_from_actual_fdt=True,unresolved_window_not_declared_free=True,
        ring_provider_default_off=True,real_apple_allocator_and_dma_command=True,
        ring_descriptor_cpu_only=True,driver_live_owner_installed=False,
        dma_enabled=False,queue_registers_written=False,irq_enabled=False,packets=False,
        hardware_executed=False,staged=False,old_phy_budget_unchanged=True,
        primary_stack_bytes=32768,reservation_stack_budget=stack,retained_display_stack_budget=parent['stack_budget'],
        terminal_watchdog_seconds=180,watchdog_countdown_seconds=15,deadline_extended=False,
        remaining='Real separate sleepable driver allocation plus fresh live controller/capability owner; no reuse of PHY-test lease',
        generated_sha256={str(p):sha(p) for p in output.rglob('*') if p.is_file()})
    (output/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return output,report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path)
    output,report=build(p.parse_args().output_dir)
    print(json.dumps(dict(directory=str(output),manifest_sha256=sha(output/'manifest.json'),kernel_sha256=report['kernel_sha256'],image_sha256=report['image_sha256'])))
