#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Independent exact-target early reservation stack audit. No hardware or linking.

Recompile unchanged FDT/Apple scalar digest owners with their recorded real
kernel commands, adding only stack/dependency receipts. Require identical text
to the actual reused objects. Bound only successful reservation admission;
panic/error recovery and unrelated arm_init phases are not newly qualified.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import struct
import subprocess
from tools.rpi5 import build_display_xnu_console as display
ROOT=display.ROOT
BASE=ROOT/'build/rpi5/display-xnu-console-5cd94fg_'
PHY=ROOT/'build/rpi5/pcie-phy-transport-20261012-final'
DATABASE=display.OBJ/'compile_commands.json'
CRYPTO=('ccdigest_init','ccdigest_update','ccdigest_final_64be','ccsha256_ltc_compress','cc_clear','cc_dit','memset_s')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def text_bytes(path,section=b'__text',segments=(b'__TEXT',b'__TEXT_EXEC',b'__HIB')):
    data=Path(path).read_bytes()
    if len(data)<32 or struct.unpack_from('<I',data)[0]!=0xfeedfacf:raise ValueError('Expected real Mach-O64 object')
    count=struct.unpack_from('<I',data,16)[0];offset=32;found=[]
    for _ in range(count):
        cmd,size=struct.unpack_from('<II',data,offset)
        if size<8 or offset+size>len(data):raise ValueError('Bad Mach-O load command')
        if cmd==0x19:
            sections=struct.unpack_from('<I',data,offset+64)[0]
            for i in range(sections):
                at=offset+72+80*i
                if at+80>offset+size:raise ValueError('Bad Mach-O section')
                name=data[at:at+16].split(b'\0')[0];segment=data[at+16:at+32].split(b'\0')[0]
                n,where=struct.unpack_from('<QI',data,at+40)
                if name==section and segment in segments:
                    if where+n>len(data):raise ValueError('Bad text extent')
                    found.append(data[where:where+n])
        offset+=size
    if len(found)!=1:raise ValueError('Expected exact text owner')
    return found[0]
def frames(path):
    result={}
    for line in Path(path).read_text().splitlines():
        location,n,kind=line.rsplit('\t',2);name=location.rsplit(':',1)[-1]
        if name in result or int(n)<0:raise ValueError('Ambiguous stack receipt')
        result[name]=dict(bytes=int(n),kind=kind,location=location)
    if not result:raise ValueError('Empty stack receipt')
    return result
def audit(package,output):
    package=Path(package).resolve();output=Path(output).resolve()
    if package.parent!=ROOT/'build/rpi5' or output.parent!=ROOT/'build/rpi5' or output.exists():raise ValueError('Distinct new audit directory required')
    output.mkdir();pins={};commands=[];tables={}
    def pin(p):pins[str(p)]=sha(p)
    pin(Path(__file__).resolve());manifest=package/'manifest.json';pin(manifest);m=json.loads(manifest.read_bytes())
    if m['profile']!='bcm2712-gem-owned-rings-resolved-reservations-default-off-v1':raise ValueError('Wrong integration profile')
    def measure(name,command,cwd,original):
        original=Path(original);pin(original);obj=output/(name+'.o');dep=output/(name+'.d')
        cmd=list(command);cmd[cmd.index('-o')+1]=str(obj)
        cmd+=['-fstack-usage','-MD','-MF',str(dep)]
        p=subprocess.run(cmd,cwd=cwd,capture_output=True,timeout=60)
        log=output/(name+'.log');log.write_bytes(p.stdout+p.stderr)
        commands.append(dict(command=cmd,cwd=str(cwd),returncode=p.returncode,log=str(log),log_sha256=sha(log)))
        if p.returncode:raise ValueError('Exact target compile failed: '+str(log))
        if text_bytes(obj)!=text_bytes(original):raise ValueError('Stack measurement changed actual reused text: '+name)
        for path in display.dependencies(dep,cwd):pin(Path(path))
        tables[name]=frames(output/(name+'.su'))
    pin(PHY/'manifest.json');phy=json.loads((PHY/'manifest.json').read_bytes())
    fdtrow=next(r for r in phy['results'] if str(ROOT/'loader/rpi5/fdt.c') in r['command'] and '-c' in r['command'])
    measure('fdt',fdtrow['command'],display.OBJ/'pexpert/DEVELOPMENT',PHY/'fdt.c.o')
    pin(DATABASE);db=json.loads(DATABASE.read_bytes())
    for name in CRYPTO:
        rows=[r for r in db if r['file'].endswith('/'+name+'.c')]
        if len(rows)!=1:raise ValueError('Ambiguous original scalar/leaf owner: '+name)
        row=rows[0]
        measure(name,row['arguments'],Path(row['directory']),Path(row['directory'])/row['output'])
    # Bind the actual linked descriptor bytes, not only its source spelling.
    di=display.OBJ/'osfmk/DEVELOPMENT/ccsha256_ltc_di.o';pin(di)
    pin(ROOT/'osfmk/corecrypto/ccsha256_ltc_di.c')
    descriptor=text_bytes(di,b'__const',(b'__DATA',b'__DATA_CONST'))
    if len(descriptor)!=80 or struct.unpack_from('<QQQ',descriptor)!=(32,32,64):raise ValueError('Scalar digest descriptor changed')
    imports=subprocess.check_output(['xcrun','nm','-ju',di],text=True).splitlines()
    if set(imports)!={'_ccdigest_final_64be','_ccsha256_initial_state','_ccsha256_ltc_compress'}:raise ValueError('Scalar digest owners changed')
    filelist=BASE/'kernel.display.filelist';pin(filelist)
    owners=filelist.read_text().splitlines()
    for obj in (di,PHY/'fdt.c.o',*[display.OBJ/'osfmk/DEVELOPMENT'/(name+'.o') for name in CRYPTO]):
        if owners.count(str(obj))!=1:raise ValueError('Measured object is not exact reused kernel owner')
    for name in ('arm_init','kernel-reservation_record','kernel-reservations','kernel-rpi5_reservation_kernel','kernel-ranges','kernel-firmware_seed_fdt'):
        p=package/(name+'.su');pin(p)
        if m['generated_sha256'].get(str(p))!=sha(p):raise ValueError('Emitted stack receipt differs from package')
        tables[name]=frames(p)
    def static(table,name):
        row=tables[table][name]
        if row['kind']!='static':raise ValueError('Unbounded noncrypto stack frame: '+name)
        return row['bytes']
    arm=static('arm_init','arm_init');kernel=static('kernel-rpi5_reservation_kernel','rpi5_reservation_kernel_validate')
    rec='kernel-reservation_record'
    # Overcount all reachable FDT owners, even sequential/mutually exclusive
    # parsing calls. No recursion; all remaining emitted FDT helpers are inline
    # or zero-byte scalar leaves. phandles/cpus/PSCI/inventory are not called.
    fdt_names=('rpi5_fdt_memory','rpi5_fdt_reservation_plan','rpi5_fdt_initrd',
        'rpi5_fdt_property','rpi5_fdt_structure','rpi5_fdt_layout','be64','value_equal')
    fdt_bound=sum(static('fdt',name) for name in fdt_names)
    source=static(rec,'rpi5_reservation_record_source')+fdt_bound
    resolve=static('kernel-reservations','rpi5_resolve_reservations')+sum(
        static('kernel-ranges',name) for name in ('rpi5_ranges_subtract','rpi5_ranges_find','rpi5_ranges_validate_live'))
    validate=static(rec,'rpi5_reservation_record_validate_fdt')+max(source,resolve,
        static(rec,'rpi5_reservation_record_fixed'),static(rec,'rpi5_reservation_record_valid'))
    decode=static(rec,'rpi5_reservation_record_decode')+static(rec,'rpi5_reservation_record_valid')
    seed=static('kernel-firmware_seed_fdt','rpi5_firmware_seed_select')+fdt_bound
    # Fixed original ccsha256_ltc_di: state32+length8+block64+num4 =108,
    # cc_ctx_n rounds to8-byte units, A76 stack to16 =>112B VLA maximum.
    # No caller-controlled descriptor/selector; boot.inc directly names it.
    # Actual unchanged assembly memcpy/memmove/bzero/secure_memset each save
    # only one16-byte FP/LR pair, make no calls, and have no dynamic SP change.
    # Overcount both distinct16B leaves even though they cannot nest.
    asm_frames=0
    for name in ('bcopy','bzero'):
        obj=display.OBJ/'osfmk/DEVELOPMENT'/(name+'.o');pin(obj)
        asm=subprocess.check_output(['xcrun','llvm-objdump','-d',obj],text=True)
        if re.search(r'\bbl(?:r)?\s',asm):raise ValueError('Assembly memory owner acquired call')
        sp_lines=[' '.join(line.split()[2:]) for line in asm.splitlines() if re.search(r'\bsp\b',line)]
        allowed={'stp x29, x30, [sp, #-0x10]!','mov x29, sp','mov sp, x29','ldp x29, x30, [sp], #0x10'}
        if not sp_lines or set(sp_lines)-allowed:raise ValueError('Assembly memory stack changed: '+name)
        asm_frames+=16
    # Count every scalar/DIT/clear C frame sequentially, plus112B fixed VLA.
    # Successful path only: stack-check failure/panic are not admission paths.
    crypto=112+asm_frames
    for table in CRYPTO:
        for row in tables[table].values():
            if row['kind']!='static' and not (table=='ccdigest_final_64be' and row['kind']=='dynamic'):
                raise ValueError('Unexpected crypto stack dynamics')
            crypto+=row['bytes']
    paths=dict(canonical_fdt_admission=arm+kernel+validate+asm_frames,wire_decode=arm+kernel+decode+asm_frames,
        post_seed_guard=arm+seed+asm_frames,original_scalar_sha=arm+crypto)
    maximum=max(paths.values())
    pin(ROOT/'osfmk/arm64/start.s');pin(ROOT/'osfmk/arm/data.s');pin(ROOT/'osfmk/mach/arm/vm_param.h')
    if '#define INTSTACK_SIZE           (4*4096)' not in (ROOT/'osfmk/mach/arm/vm_param.h').read_text():raise ValueError('Startup stack contract changed')
    if maximum+512>=16384:raise ValueError('Early kernel reservation path exceeds original16KiB startup stack')
    for path,digest in pins.items():
        if sha(path)!=digest:raise ValueError('Audit input drift: '+path)
    report=dict(profile='pi5-reservation-kernel-stack-audit-v1',package_manifest_sha256=pins[str(manifest)],
        paths_conservative_bytes=paths,maximum_conservative_bytes=maximum,stack_bytes=16384,
        required_margin_bytes=512,minimum_remaining_bytes=16384-maximum,actual_reused_text_unchanged=True,
        scalar_final_vla_bound_bytes=112,actual_assembly_memory_frames_overcounted_bytes=asm_frames,
        hardware_executed=False,scope='Successful early reservation admission only; no recursion, no panic/IRQ-stack workload claim',
        frames=tables,commands=commands,inputs_sha256=pins,
        generated_sha256={str(p):sha(p) for p in output.iterdir() if p.is_file()})
    (output/'audit.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();r=audit(args.package,args.output)
    print(json.dumps(dict(audit_sha256=sha(args.output/'audit.json'),paths=r['paths_conservative_bytes'],remaining=r['minimum_remaining_bytes'])))
