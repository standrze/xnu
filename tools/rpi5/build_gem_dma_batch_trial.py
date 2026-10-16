#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Actual one-CPU retained allocation/CPU-ring trial composition, offline only.

The same-boot loader record and real before-matching caller are installed.
Every inbound window remains disabled. No queue, BME, IRQ or DMA activation.
The complete deterministic recipe is exported for independent byte validation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import uuid
from tools.rpi5 import build_gem_dma_rings_package as old
from tools.rpi5 import build_gem_dma_batch_objects as objects
from tools.rpi5 import gem_dma_batch_trial_profile as profile
from tools.rpi5 import gem_dma_batch_leaf as leaf
from tools.rpi5 import build_pcie_id_trial_package as secure
ROOT=old.ROOT;BASE=old.BASE;CAP=objects.CAP
BASE_SHA=old.BASE_SHA
CAP_SHA='3f39456cf2d6d4b9fa7b3586b54558564addc0b25b1cdcd69c1846107f582b3e'
PROFILE='bcm2712-gem-real-cpu-owned-batch-trial-v1'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def sources():
    return list(dict.fromkeys([Path(__file__).resolve(),Path(leaf.__file__).resolve(),*old.sources(),
        *objects.sources(),*profile.sources(),ROOT/'libkern/c++/OSRuntime.cpp',
        ROOT/'tools/rpi5/tests/test_gem_dma_batch_leaf.py',
        ROOT/'tools/rpi5/gem_dma_batch_completeness_v1.py',
        ROOT/'tools/rpi5/tests/test_gem_dma_batch_completeness_v1.py',
        ROOT/'tools/rpi5/check_gem_dma_batch_trial.py',
        ROOT/'tools/rpi5/gem_dma_batch_contract.py',ROOT/'tools/rpi5/gem_dma_batch_serial.py',
        ROOT/'tools/rpi5/qualify_gem_dma_batch_trial.py',
        ROOT/'tools/rpi5/tests/test_gem_dma_batch_serial.py',ROOT/'tools/rpi5/tests/test_gem_dma_batch_loader.py',
        ROOT/'tools/rpi5/tests/test_gem_dma_batch_trial.py',
        ROOT/'tools/rpi5/tests/test_gem_dma_batch_logging.py',ROOT/'tools/rpi5/tests/test_pcie_bounded_log.py',
        ROOT/'tools/rpi5/audit_gem_batch_stack.py',ROOT/'tools/rpi5/audit_gem_batch_startup_stack.py',
        ROOT/'tools/rpi5/audit_gem_rp1_loader_stack.py',ROOT/'tools/rpi5/tests/test_gem_batch_stack_evidence.py',
        ROOT/'tools/rpi5/tests/test_gem_batch_startup_stack.py']))
def parents():
    result=[]
    for path,digest in ((BASE,BASE_SHA),(CAP,CAP_SHA)):
        if sha(path/'manifest.json')!=digest:raise ValueError('Exact immutable composition parent required')
        result.append(json.loads((path/'manifest.json').read_bytes()))
    return result
def kernel_objects(output):
    original=(BASE/'kernel.display.filelist').read_text().splitlines()
    cap=(CAP/'kernel.rp1-config.filelist').read_text().splitlines()
    byname={Path(p).name:p for p in cap}
    if len(byname)!=len(cap) or len(set(original))!=len(original):raise ValueError('Ambiguous object owner')
    replacements={str(BASE/'arm_init.o'):str(output/'arm_init.o')}
    logical={'IOStartIOKit.cpo':'IOStartIOKit.cpp.o','pe_fiq.o':'pe_fiq.c.o'}
    selected={'pcie_qos.c.o','pcie_ubus.c.o','pcie_clock.c.o','pcie_rc.c.o','pcie_link.c.o',
        'rp1_config_snapshot_checked.c.o','BCM2712PCIePHYTransport.cpp.o'}
    consumed={'arm_init.c.o'}
    for p in original:
        name=Path(p).name
        if name in logical:replacements[p]=byname[logical[name]];consumed.add(logical[name])
        elif name in selected:
            replacements[p]=str(output/'transport.o') if name=='BCM2712PCIePHYTransport.cpp.o' else byname[name]
            consumed.add(name)
        elif name in byname:consumed.add(name)
    extras=[p for p in cap if Path(p).name not in consumed]
    expected={'pcie_released_windows.c.o','pcie_root_forward.c.o','rp1_bars_assign.c.o','rp1_bars_plan.c.o',
        'rp1_bars_probe.c.o','rp1_decode_cycle.c.o','rp1_gem_capabilities.c.o','rp1_gem_identify.c.o'}
    if {Path(p).name for p in extras}!=expected or any(p not in original for p in replacements):
        raise ValueError('Exact cross-profile logical object delta changed')
    added=[output/'provider.o']+[output/('kernel-'+p.stem+'.o') for p in core_sources()]
    result=[replacements.get(p,p) for p in original]+extras+list(map(str,added))
    if len(result)!=len(set(result)):raise ValueError('Duplicate linked object')
    return result,replacements,extras,list(map(str,added))
def core_sources():
    return [ROOT/'iokit/Kernel/rpi5_gem_ring_batch.c',ROOT/'iokit/Kernel/rpi5_gem_dma_route.c',
        ROOT/'osfmk/arm64/rpi5_reservation_kernel.c',ROOT/'loader/rpi5/reservation_record.c',
        ROOT/'loader/rpi5/ranges.c',ROOT/'loader/rpi5/reservations.c',ROOT/'loader/rpi5/firmware_seed_fdt.c']
def plan(output,tag):
    parent,_=parents();rows=[];scans={}
    def row(label,args,cwd=ROOT):rows.append((label,list(map(str,args)),str(cwd)))
    def unit(flags,source,label,cwd=ROOT):
        row(label+'-scan',[*flags,'-M','-MF',output/(label+'.scan.d'),source],cwd)
        row(label+'-compile',[*flags,'-c','-MD','-MF',output/(label+'.d'),source,'-o',output/(label+'.o')],cwd)
        scans[label]=dict(source=str(source),cwd=str(cwd))
    armrow=next(r for r in parent['commands'] if r['log'].endswith('/arm_init-compile.log'))
    armflags=old.display.compiler_flags(armrow['command'],BASE/'arm_init.c')+['-I',str(ROOT),'-I',str(ROOT/'osfmk'),'-fstack-usage']
    unit(armflags,output/'arm_init.c','arm_init',armrow['cwd'])
    row('arm-assembly',[*armflags,'-S',output/'arm_init.c','-o',output/'arm_init.s'],armrow['cwd'])
    recipes=objects.recipes(output)
    for label,source,flags,cwd in recipes[:2]:unit(flags,source,label,cwd)
    cflags,ccwd=recipes[2][2:]
    for source in core_sources():unit(cflags,source,'kernel-'+source.stem,ccwd)
    original=next(r['command'] for r in parent['commands'] if r['log'].endswith('/kernel-link.log'))
    changes={str(BASE/'kernel.display.filelist'):str(output/'kernel.filelist'),str(BASE/'kernel.unstripped'):str(output/'kernel.unstripped'),
        '-Wl,-map,'+str(BASE/'kernel.map'):'-Wl,-map,'+str(output/'kernel.map')}
    if any(original.count(p)!=1 for p in changes):raise ValueError('Exact kernel link owner changed')
    row('kernel-link',[changes.get(a,a) for a in original])
    row('kernel-strip',['xcrun','strip','-S',output/'kernel.unstripped','-o',output/'kernel.cpu-rings'])
    row('kernel-undefined',['xcrun','nm','-ju',output/'kernel.cpu-rings'])
    row('kernel-symbols',['xcrun','nm','-nm',output/'kernel.cpu-rings'])
    for name in ('transport','provider'):row(name+'-disassembly',['xcrun','llvm-objdump','-dr',output/(name+'.o')])
    loaderrow=next(r['command'] for r in parent['commands'] if r['log'].endswith('/loader-probe_main-compile.log'))
    flags=old.display.compiler_flags(loaderrow,BASE/'probe_main.c')
    flags=[a for a in flags if not a.startswith(('-DRPI5_DISPLAY_XNU_TAG=','-DRPI5_GATE3_CPU_ON_ALL='))]
    flags+=['-DRPI5_DISPLAY_XNU_TAG="'+tag+'"','-DRPI5_GATE3_CPU_ON_ALL=0']
    for name,source in [('probe_main',output/'probe_main.c'),('firmware_seed_tree',output/'firmware_seed_tree.c'),
        ('payload',output/'payload.S'),('psci',output/'psci.S'),
        ('rp1_device_handoff',ROOT/'loader/rpi5/rp1_device_handoff.c'),
        ('reservation_record',ROOT/'loader/rpi5/reservation_record.c'),('reservation_record_tree',ROOT/'loader/rpi5/reservation_record_tree.c')]:
        unit(flags,source,'loader-'+name)
    stack={n:ROOT/'loader/rpi5'/(n+'.c') for n in sorted(old.record.STACK_UNITS)}
    bear=ROOT/'build/rpi5/bearssl-candidate/src'
    stack.update(sha2small=bear/'hash/sha2small.c',dec32be=bear/'codec/dec32be.c',enc32be=bear/'codec/enc32be.c')
    for name,source in stack.items():
        if name not in ('reservation_record','reservation_record_tree'):unit(flags,source,'stack-'+name)
    link=next(r['command'] for r in parent['commands'] if r['log'].endswith('/loader-link.log'))
    changes={str(BASE/('loader-'+n+'.o')):str(output/('loader-'+n+'.o')) for n in ('probe_main','firmware_seed_tree','payload')}
    psci=[a for a in link if Path(a).name=='psci.o']
    if len(psci)!=1 or any(link.count(p)!=1 for p in changes):raise ValueError('Exact loader link owner changed')
    changes[psci[0]]=str(output/'loader-psci.o')
    args=[changes.get(a,a) for a in link];args[args.index('-o')+1]=str(output/'cpu_rings.elf')
    args[args.index('-o'):args.index('-o')]=[str(output/'loader-reservation_record.o'),str(output/'loader-reservation_record_tree.o'),
        str(output/'loader-rp1_device_handoff.o')]
    row('loader-link',args);row('loader-objcopy',[ROOT/'tools/rpi5/tfa-objcopy','-O','binary',output/'cpu_rings.elf',output/'probe.bin'])
    row('loader-undefined',['xcrun','llvm-nm','--undefined-only',output/'cpu_rings.elf'])
    row('loader-symbols',['xcrun','llvm-nm','-n',output/'cpu_rings.elf'])
    if len({label for label,_,_ in rows})!=len(rows):raise ValueError('Duplicate canonical command')
    return rows,scans
def derived_sources():
    result={'overlay/'+name:data for name,data in profile.derive().items()}
    result.update({'arm_init.c':old.boot.arm((BASE/'arm_init.c').read_text()).encode(),
        'probe_main.c':profile.loader((BASE/'probe_main.c').read_text()).encode(),
        'firmware_seed_tree.c':old.record.seed((BASE/'firmware_seed_tree.c').read_text()).encode(),
        'psci.S':profile.psci((ROOT/'loader/rpi5/psci.S').read_text()).encode()})
    return result
def build(output=None):
    output=Path(tempfile.mkdtemp(prefix='gem-dma-batch-trial-',dir=ROOT/'build/rpi5')) if output is None else Path(output).resolve()
    if output.parent!=ROOT/'build/rpi5' or (output.exists() and any(output.iterdir())):raise ValueError('Distinct empty build required')
    output.mkdir(exist_ok=True);pins={};headers={};commands=[];parent,cap=parents()
    def pin(p,digest=None):
        # Preserve inherited tool aliases (clang++ is a symlink to clang); the
        # manifest names the actual consumed invocation path as well as bytes.
        p=str(Path(p).absolute());actual=sha(p)
        if digest is not None and actual!=digest:raise ValueError('Immutable input changed: '+p)
        if p in pins and pins[p]!=actual:raise ValueError('Conflicting input pin: '+p)
        pins[p]=actual
    for directory,m in ((BASE,parent),(CAP,cap)):
        pin(directory/'manifest.json')
        for key in ('inputs_sha256','actual_headers_sha256','generated_sha256'):
            for p,h in m.get(key,{}).items():pin(p,h)
    for p in sources():pin(p)
    pin(old.TEMPLATE/'manifest.json',old.TEMPLATE_SHA)
    pin(secure.FIRMWARE/'manifest.json',secure.FIRMWARE_MANIFEST_SHA);pin(secure.FIRMWARE_BIN,secure.FIRMWARE_SHA)
    for name,data in derived_sources().items():
        p=output/name;p.parent.mkdir(exist_ok=True);p.write_bytes(data)
    filelist,replacements,extras,added=kernel_objects(output)
    (output/'kernel.filelist').write_text('\n'.join(filelist)+'\n')
    tag=uuid.uuid4().hex;rows,scans=plan(output,tag)
    raw=(BASE/'payload.bin').read_bytes();root_offset,root_bytes=struct.unpack_from('<QQ',raw,136)
    root=raw[root_offset:root_offset+root_bytes]
    if len(root)!=parent['root_bytes'] or hashlib.sha256(root).hexdigest()!=parent['root_sha256']:raise ValueError('Accepted root differs')
    for label,args,cwd in rows:
        if label=='loader-probe_main-scan':
            (output/'payload.bin').write_bytes(old.payload_container.encode((output/'kernel.cpu-rings').read_bytes(),root))
            (output/'payload.S').write_text('.section .payload,"a"\n.balign 64\n.incbin "'+str(output/'payload.bin')+'"\n')
        p=subprocess.run(args,cwd=cwd,capture_output=True,timeout=120)
        log=output/(label+'.log');log.write_bytes(p.stdout+p.stderr)
        commands.append(dict(command=args,cwd=cwd,returncode=p.returncode,log=str(log),log_sha256=sha(log)))
        warnings=[s for s in p.stderr.decode(errors='replace').splitlines() if 'warning:' in s]
        if label in ('arm_init-compile','arm-assembly'):
            warning_ok=len(warnings)==1 and "dyld_kernel_fixups.h:367:12: warning: variable 'cnt' set but not used" in warnings[0]
        elif label=='kernel-link':warning_ok=warnings==[s for s in (BASE/'kernel-link.log').read_text().splitlines() if 'warning:' in s]
        else:warning_ok=not warnings
        if p.returncode or not warning_ok:raise ValueError('Actual build failed: '+str(log))
        if label.endswith('-undefined') and p.stdout.strip():raise ValueError('Undefined implementation: '+str(log))
        if label.endswith('-scan'):
            unit=label[:-5]
            for path in old.display.dependencies(output/(unit+'.scan.d'),cwd):pin(path)
        if label.endswith('-compile'):
            unit=label[:-8];before=old.display.dependencies(output/(unit+'.scan.d'),cwd)
            after=old.display.dependencies(output/(unit+'.d'),cwd)
            if before!=after:raise ValueError('Actual header scan drift')
            for path in after:pin(path);headers[path]=pins[path]
    leafproof=leaf.inspect((output/'provider.o').read_bytes());oom=leaf.allocation_guard((output/'transport.o').read_bytes())
    syms=(output/'loader-symbols.log').read_text()
    symbols={r.split()[2]:int(r.split()[0],16) for r in syms.splitlines() if len(r.split())==3}
    if 'rpi5_psci_cpu_on' in symbols or symbols['__probe_end']>=0xb000000 or symbols['__stack_top']-symbols['__bss_end']!=32768:
        raise ValueError('Loader CPU/FDT/stack admission differs')
    stackfiles={n:output/(('loader-' if n in ('reservation_record','reservation_record_tree') else 'stack-')+n+'.su') for n in old.record.STACK_UNITS}
    budget=old.record.stack_budget(stackfiles,output/'loader-probe_main.su',output/'loader-firmware_seed_tree.su')
    image=(output/'probe.bin').read_bytes();payload=(output/'payload.bin').read_bytes();at=image.find(payload)
    if at<0 or at%64 or image.find(payload,at+1)>=0:raise ValueError('Unique aligned payload absent')
    for p,h in pins.items():
        if sha(p)!=h:raise ValueError('Consumed source changed during build: '+p)
    m=dict(profile=PROFILE,tag=tag,trial_marker=profile.marker(tag),bootargs=profile.BOOTARGS,
        parent_manifest_sha256=BASE_SHA,capability_manifest_sha256=CAP_SHA,
        kernel=str(output/'kernel.cpu-rings'),kernel_sha256=sha(output/'kernel.cpu-rings'),kernel_bytes=(output/'kernel.cpu-rings').stat().st_size,
        image=str(output/'probe.bin'),image_sha256=sha(output/'probe.bin'),image_bytes=len(image),payload_offset=at,
        root_sha256=parent['root_sha256'],root_bytes=root_bytes,firmware=str(secure.FIRMWARE_BIN),firmware_sha256=secure.FIRMWARE_SHA,
        replaced_objects=replacements,inherited_extra_objects=extras,added_objects=added,
        commands=commands,compiler_scans={k:sorted(old.display.dependencies(output/(k+'.d'),r['cwd'])) for k,r in scans.items()},
        inputs_sha256=pins,actual_headers_sha256=headers,loader_symbols=symbols,reservation_stack_budget=budget,
        actual_batch_leaf=leafproof,actual_nullable_new=oom,
        sameboot_loader_kernel_reservation=True,real_sleepable_apple_preparation=True,real_fresh_controller_caller=True,
        cpu_owned_descriptors_only=True,all_inbound_windows_disabled=True,candidate_addresses_not_dma_authority=True,
        queue_publication=False,bme_enable=False,dma_activation=False,irq_activation=False,hardware_executed=False,staged=False,
        owner_check_limit=65536,modeled_owner_checks=64940,modeled_firmware_sequence=16233,
        native_model_not_hardware_guarantee=True,firmware_guard_seconds=10,ns_guard_seconds=9,
        pm_guard_seconds=12,watchdog_seconds=15,copy_max_renewals=2,copy_outer_seconds=60,
        ring_deadline_us=500000,ring_expected_writes=640,ring_expected_reads=640,ring_expected_current=164,
        generated_sha256={str(p):sha(p) for p in output.rglob('*') if p.is_file()})
    (output/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    return output,m
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=Path)
    output,m=build(parser.parse_args().output_dir)
    print(json.dumps(dict(package=str(output),manifest_sha256=sha(output/'manifest.json'),kernel_sha256=m['kernel_sha256'],image_sha256=m['image_sha256'])))
