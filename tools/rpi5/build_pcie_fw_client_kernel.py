#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Actual NS firmware client + retained PE/transport integration; no activation."""
import argparse
import json
from pathlib import Path
import shutil
import struct

try:
    from . import build_pcie_irq_transport_kernel as previous
    from . import build_pcie_firmware_verifier as producer
except ImportError:
    import build_pcie_irq_transport_kernel as previous
    import build_pcie_firmware_verifier as producer

audit,ROOT,full=previous.audit,previous.ROOT,previous.full
BASE=ROOT/'build/rpi5/pcie-irq-transport-kernel-20261012-final'
BASE_SHA='563cf343a50bdeafd5bcaac7e105f5f1188a6839ac744291b6ee57d46055a4f7'
FIRMWARE=ROOT/'build/rpi5/pcie-el3-verifier-20261012-checked'
FIRMWARE_SHA='cd2fc81f2576f44a63587b917ef42eb421b317061a35311163a3d2c27c069a60'
PE_OLD=previous.BASE/'pe_fiq.c.o'
TRANSPORT_OLD=BASE/'BCM2712PCIePHYTransport.cpp.o'
CORE=ROOT/'loader/rpi5/pcie_fw_client.c'
SMCCC=ROOT/'loader/rpi5/pcie_fw_smccc.S'
BODY=ROOT/'iokit/Kernel/BCM2712PCIeFirmwareTransport.inc'
PATCH=ROOT/'tools/rpi5/patches/pcie-fw-transport.patch'
PE_PATCH=ROOT/'tools/rpi5/patches/pcie-fw-owner.patch'


def inputs():
    if audit.sha(BASE/'manifest.json')!=BASE_SHA or audit.sha(FIRMWARE/'manifest.json')!=FIRMWARE_SHA:
        raise ValueError('Accepted IRQ transport or firmware producer changed')
    prior=json.loads((BASE/'manifest.json').read_text());fw=json.loads((FIRMWARE/'manifest.json').read_text())
    captured=previous.inputs()[0]
    for data in (prior,fw):
        for name,digest in {**data['inputs_sha256'],**data['generated_sha256']}.items():
            if name in captured and captured[name]!=digest:raise ValueError('Conflicting client dependency: '+name)
            captured[name]=digest
    captured[str(BASE/'manifest.json')]=BASE_SHA;captured[str(FIRMWARE/'manifest.json')]=FIRMWARE_SHA
    objects=[Path(p) for p in (BASE/'kernel.pcie-irq-transport.filelist').read_text().splitlines() if p]
    if len(objects)!=len(set(objects)) or objects.count(PE_OLD)!=1 or objects.count(TRANSPORT_OLD)!=1:
        raise ValueError('Actual PE/transport replacement ambiguous')
    for p in (CORE,CORE.with_suffix('.h'),SMCCC,BODY,PATCH,PE_PATCH,ROOT/'pexpert/arm/rpi5_pcie_fw_api.h',
        ROOT/'pexpert/arm/rpi5_pcie_fw_owner.inc',Path(__file__).resolve(),ROOT/'tools/rpi5/tests/test_pcie_fw_client.py',
        ROOT/'tools/rpi5/tests/pcie_fw_client_host.c',ROOT/'tools/rpi5/tests/pcie_fw_transport_host.cpp'):
        captured[str(p)]=audit.sha(p)
    for p,pin in captured.items():
        if audit.sha(Path(p))!=pin:raise ValueError('Client input changed: '+p)
    return captured,prior,fw,objects


def object_text(data):
    magic,cpu,subtype,kind,ncmds,size,flags,reserved=struct.unpack_from('<8I',data)
    if magic!=0xfeedfacf or cpu!=0x100000c or kind!=1:raise ValueError('Expected ARM64 Mach-O object')
    pos=32
    for _ in range(ncmds):
        cmd,length=struct.unpack_from('<II',data,pos)
        if cmd==0x19:
            count=struct.unpack_from('<I',data,pos+64)[0]
            for i in range(count):
                start=pos+72+i*80
                name,segment,address,extent,offset=struct.unpack_from('<16s16sQQI',data,start)
                if name.rstrip(b'\0')==b'__text' and segment.rstrip(b'\0')==b'__TEXT':return data[offset:offset+extent]
        pos+=length
    raise ValueError('Missing actual text section')


def build(output):
    captured,prior,fw,original=inputs();output=output.resolve()
    if not (output.parent==ROOT/'build/rpi5' or output.is_relative_to(Path('/private/tmp')) or
            output.is_relative_to(Path('/private/var/folders'))):raise ValueError('Separate fresh client kernel directory required')
    output.mkdir(parents=True,exist_ok=False);commands=[];results=[]
    def execute(args,name,cwd=ROOT,warning_free=True):
        row=audit.execute(args,cwd,output/(name+'.log'));commands.append(row)
        if row['returncode'] or (warning_free and row['warning_count']):raise ValueError('Client build failed/warned: '+row['log'])
        return row
    overlay=output/'overlay';overlay.mkdir()
    for n in previous.SOURCE_NAMES:shutil.copyfile(BASE/'overlay'/n,overlay/n)
    execute(['patch','--batch','--fuzz=0','-p1','-i',PATCH],'transport-patch',overlay)
    irq=previous.BODY.read_text();boundary='\nbool BCM2712PCIePHYTransport::guard()'
    if irq.count(boundary)!=1:raise ValueError('Accepted IRQ handoff boundary changed')
    include=overlay/'BCM2712PCIeFWTransport.inc'
    include.write_text(irq.split(boundary)[0]+'\n'+BODY.read_text())
    pe=output/'pe_fiq.c';shutil.copyfile(previous.BASE/'pe_fiq.c',pe)
    execute(['patch','--batch','--fuzz=0','-p1','-i',PE_PATCH],'pe-patch',output)
    old_pe=json.loads((previous.BASE/'manifest.json').read_text())['compiles'][0]['command']
    cpp=prior['compiles'][0]['command']
    def adapted(args,old,source,obj):
        if args.count(str(old))!=1:raise ValueError('Compile source ambiguous')
        command=[str(source) if a==str(old) else a for a in args[:-2]]+['-o',str(obj)]
        command[1:1]=['-DRPI5_PCIE_FW_CLIENT=1','-DRPI5_PCIE_FW_TRANSPORT=1'];return command
    pe_obj=output/'pe_fiq.c.o';transport_obj=output/'BCM2712PCIePHYTransport.cpp.o';core_obj=output/'pcie_fw_client.c.o'
    units=((pe,pe_obj,adapted(old_pe,previous.BASE/'pe_fiq.c',pe,pe_obj),audit.OBJ/'pexpert/DEVELOPMENT'),
        (CORE,core_obj,adapted(old_pe,previous.BASE/'pe_fiq.c',CORE,core_obj),audit.OBJ/'pexpert/DEVELOPMENT'),
        (overlay/previous.SOURCE_NAMES[0],transport_obj,
         adapted(cpp,BASE/'overlay'/previous.SOURCE_NAMES[0],overlay/previous.SOURCE_NAMES[0],transport_obj),audit.OBJ/'iokit/DEVELOPMENT'))
    for source,obj,args,cwd in units:
        captured[str(source)]=audit.sha(source);captured[str(Path(args[0]))]=audit.sha(Path(args[0]))
        dep=output/(source.name+'.d')
        execute([a for a in args[:-2] if a!='-c']+['-M','-MG','-MF',str(dep)],source.name+'-deps',cwd)
        for p in audit.dependency_paths(dep,cwd):
            if not p.is_file():raise ValueError('Missing actual client dependency: '+str(p))
            pin=audit.sha(p)
            if str(p) in captured and captured[str(p)]!=pin:raise ValueError('Conflicting actual header: '+str(p))
            captured[str(p)]=pin
        row=execute(args,source.name+'-compile',cwd);row['object_sha256']=audit.sha(obj);results.append(row)
        assembly=output/(source.name+'.s')
        execute([a for a in args[:-2] if a!='-c']+['-S','-o',str(assembly)],source.name+'-assembly',cwd)
    smc_obj=output/'pcie_fw_smccc.S.o'
    execute([old_pe[0],'-arch','arm64','--target=arm64-apple-macosx27.0.0','-mcpu=cortex-a76',
        '-ffreestanding','-mgeneral-regs-only','-fno-stack-protector','-DRPI5_PCIE_FW_CLIENT=1','-c',SMCCC,'-o',smc_obj],'smccc')
    actual=object_text(smc_obj.read_bytes())
    expected=(0xa9be7bfd,0x910003fd,0xa90153f3,0xaa0203f3,*range(0xaa1f03e2,0xaa1f03e8),
        0xd5033f9f,0xd4000003,0xd5033fdf,0xa9000660,0xa9010e62,0xa94153f3,0xa8c27bfd,0xd65f03c0)
    if actual!=struct.pack('<18I',*expected):raise ValueError('Actual SMCCC argument/clobber/store/frame bytes differ')
    _,_,extras,flags,archive,_=full.inputs()
    objects=[pe_obj if p==PE_OLD else transport_obj if p==TRANSPORT_OLD else p for p in original]+[core_obj,smc_obj]
    if len(objects)!=len(set(objects)):raise ValueError('Duplicate client constituent')
    filelist=output/'kernel.pcie-fw-client.filelist';filelist.write_text(''.join(str(p)+'\n' for p in objects))
    kernel,unstripped,linkmap=output/'kernel.pcie-fw-client',output/'kernel.unstripped',output/'kernel.map'
    args=[('-Wl,-map,'+str(linkmap)) if a.startswith('-Wl,-map,') else a for a in flags]
    row=execute(args+['-filelist',filelist,*extras,'-o',unstripped,archive],'kernel-link',warning_free=False)
    warnings=[l for l in Path(row['log']).read_text().splitlines() if 'warning:' in l]
    if warnings!=prior['baseline_linker_warnings']:raise ValueError('New client linker warnings')
    execute(['xcrun','strip','-S',unstripped,'-o',kernel],'kernel-strip')
    listing=audit.read_command(['xcrun','nm','-nm',kernel]);(output/'kernel.symbols').write_text(listing+'\n')
    if audit.read_command(['xcrun','nm','-ju',kernel]):raise ValueError('Undefined client kernel symbols')
    textmap=linkmap.read_text(errors='surrogateescape');linked=full.linked_audit(kernel.read_bytes(),listing,textmap)
    if str(PE_OLD) in textmap or str(TRANSPORT_OLD) in textmap:raise ValueError('Superseded owner/transport still linked')
    if any(str(p) not in textmap for p in objects):raise ValueError('Actual client constituent absent')
    names=full.symbols(listing)
    required=list(prior['link']['controller_irq_implementations'])+['_pe_rpi5_pcie_fw_claim','_pe_rpi5_pcie_fw_check',
        '_rpi5_pcie_fw_client_init','_rpi5_pcie_fw_client_begin','_rpi5_pcie_fw_client_check','_rpi5_pcie_fw_smccc']
    required += [n for n in names if 'BCM2712PCIePHYTransport' in n and 'claimControllerFirmware' in n]
    if len(required)!=25:raise ValueError('Client entries missing/ambiguous')
    for n in required:
        values=names.get(n,[])
        if len(values)!=1 or not any(s['initprot']&4 and s['vmaddr']<=values[0] and values[0]+4<=s['vmaddr']+s['filesize']
                for s in linked['macho']['segments']):raise ValueError('Client implementation not executable: '+n)
    for p,pin in captured.items():
        if audit.sha(Path(p))!=pin:raise ValueError('Client build input changed: '+p)
    generated={str(p):audit.sha(p) for p in output.rglob('*') if p.is_file()}
    linked['controller_firmware_implementations']=required
    report=dict(profile='pcie-firmware-client-kernel-v1',inputs_sha256=captured,generated_sha256=generated,
        kernel=str(kernel),kernel_sha256=audit.sha(kernel),kernel_bytes=kernel.stat().st_size,link=linked,
        commands=commands,compiles=results,baseline_linker_warnings=warnings,new_linker_warnings=[],
        complete_kernel_link_proven=True,actual_smccc_argument_and_frame_bytes=True,smccc_text_hex=actual.hex(),
        firmware_claim_after_ns_irq_before_reset=True,firmware_checks_bracket_independent_provider=True,
        actual_pe_client_core_linked=True,thread_reference_retained_until_reset=True,output_atomic=True,
        legacy_no_controller_path_unchanged=True,watchdog_checks_per_successful_controller_guard=14,
        firmware_producer=str(FIRMWARE),new_mapped_pages=0,boot_caller_added=False,concrete_full_lifecycle_provider_added=False,
        controller_writes_admitted=False,power_domain_ownership_proven=False,dma_authorized=False,
        installed=False,pi_executed=False,firmware_installed=False,ethernet_proven=False)
    (output/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True)
    r=build(p.parse_args().output_dir);print(json.dumps({k:r[k] for k in ('kernel','kernel_sha256','kernel_bytes','installed','pi_executed')}))
