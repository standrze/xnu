#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build a separate actual TF-A EL3 verifier; never install/reboot."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

ROOT=Path(__file__).resolve().parents[2]
UPSTREAM=ROOT/'build/rpi5/tfa-candidate'
REVISION='332b62e0443b004287d2cfc032a70bba6fb86f35'
ORIGINAL_SHA='413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46'
NAMES=('pcie_verifier.h','pcie_verifier.c','pcie_verifier_mmio.S','pcie_verifier_sip.c')
PATCH=ROOT/'tools/rpi5/patches/pcie-fw-verifier.patch'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def tool_identity():
    result={}
    for name in ('clang','llvm-nm'):
        p=Path(subprocess.check_output(['xcrun','--find',name],text=True,timeout=30).strip())
        result[name]=dict(path=str(p),sha256=sha(p))
    p=ROOT/'build/rpi5/zig-aarch64-macos-0.16.0/zig'
    result['zig']=dict(path=str(p),sha256=sha(p));return result


def audit_elf(elf,binary):
    d=elf.read_bytes();raw=binary.read_bytes()
    if d[:7]!=b'\x7fELF\x02\x01\x01':raise ValueError('Expected LE ELF64')
    h=struct.unpack_from('<HHIQQQIHHHHHH',d,16)
    if h[:3]!=(2,183,1) or h[3]!=0x1000 or h[8]!=56 or h[10]!=64:raise ValueError('Wrong TF-A ELF ABI')
    loads=[]
    for i in range(h[9]):
        typ,perms,off,va,pa,size,mem,align=struct.unpack_from('<IIQQQQQQ',d,h[4]+i*h[8])
        if typ in (2,3):raise ValueError('Dynamic firmware forbidden')
        if typ!=1:continue
        if va!=pa or size>mem or off+size>len(d) or pa+mem>0x80000 or perms&3==3:
            raise ValueError('Invalid firmware extent')
        if size and raw[pa:pa+size]!=d[off:off+size]:raise ValueError('ELF/raw disagreement')
        loads.append(dict(address=pa,file_size=size,memory_size=mem,flags=perms))
    loads.sort(key=lambda v:v['address'])
    if not loads or loads[0]['address']!=0 or len(raw)!=max(v['address']+v['file_size'] for v in loads if v['file_size']):
        raise ValueError('Unexpected raw firmware extent')
    if any(a['address']+a['memory_size']>b['address'] for a,b in zip(loads,loads[1:])):raise ValueError('Overlapping LOADs')
    if subprocess.check_output(['xcrun','llvm-nm','--undefined-only',str(elf)],text=True,timeout=30).strip():
        raise ValueError('Undefined firmware symbol')
    listing=subprocess.check_output(['xcrun','llvm-nm','--defined-only','--format=posix',str(elf)],text=True,timeout=30)
    symbols={r[0]:r[1:4] for line in listing.splitlines() if len(r:=line.split())>=4}
    def words(name,expected):
        kind,address,size=symbols[name];offset=int(address,16)
        if kind not in ('t','T') or int(size,16)!=4*len(expected):raise ValueError('Wrong leaf extent: '+name)
        if struct.unpack_from('<'+'I'*len(expected),raw,offset)!=expected:raise ValueError('Wrong emitted leaf: '+name)
    words('rpi5_fw_load32',(0xd5033f9f,0xb9400000,0xd5033f9f,0xd65f03c0))
    words('rpi5_fw_counter',(0xd5033fdf,0xd53be020,0xd65f03c0))
    words('rpi5_fw_frequency',(0xd53be000,0xd65f03c0))
    words('rpi5_fw_unlock',(0x889ffc1f,0xd65f03c0))
    # One LDAXR/STXR attempt, only forward fail branches, no waiting/retry loop.
    words('rpi5_fw_trylock',(0x885ffc01,0x350000c1,0x52800021,0x88027c01,0x35000062,
        0x52800020,0xd65f03c0,0xd5033f5f,0x52800000,0xd65f03c0))
    descriptor=symbols['__svc_desc_rpi5_pcie_verifier'];address=int(descriptor[1],16)
    if int(descriptor[2],16)!=32 or raw[address:address+3]!=bytes((2,2,1)):
        raise ValueError('Missing actual fast SiP descriptor')
    init,handler=struct.unpack_from('<QQ',raw,address+16)
    if init or handler!=int(symbols['rpi5_pcie_sip'][1],16):raise ValueError('Wrong actual service handler')
    if sum(name.startswith('__svc_desc_') and raw[int(row[1],16):int(row[1],16)+3]==bytes((2,2,1))
           for name,row in symbols.items())!=1:raise ValueError('Conflicting SiP service owner')
    return dict(entry=h[3],loads=loads,actual_service_registered=True,ordered_read_leaves=True,
                one_attempt_lock=True,symbols=symbols)


def build(output):
    output=output.resolve()
    if output.parent!=ROOT/'build/rpi5':raise ValueError('Fresh separate build/rpi5 directory required')
    if subprocess.check_output(['git','-C',str(UPSTREAM),'rev-parse','HEAD'],text=True).strip()!=REVISION or \
            subprocess.check_output(['git','-C',str(UPSTREAM),'status','--porcelain'],text=True).strip():
        raise ValueError('Pinned original TF-A checkout changed')
    baseline=UPSTREAM/'build/rpi5/debug/bl31.bin'
    if sha(baseline)!=ORIGINAL_SHA:raise ValueError('Original installed firmware changed')
    tools=tool_identity()
    tracked=subprocess.check_output(['git','-C',str(UPSTREAM),'ls-files','-z']).decode().split('\0')[:-1]
    extra=[ROOT/'firmware/rpi5'/n for n in NAMES]+[PATCH,Path(__file__).resolve(),ROOT/'tools/rpi5/tests/test_pcie_firmware_verifier.py',
        ROOT/'tools/rpi5/tests/pcie_firmware_verifier_host.c',ROOT/'tools/rpi5/tests/fw_verifier_stubs/common/runtime_svc.h',
        ROOT/'tools/rpi5/tests/fw_verifier_stubs/smccc_helpers.h',ROOT/'tools/rpi5/tfa.lock.json',ROOT/'tools/rpi5/loader-toolchain.lock.json',
        *(ROOT/'tools/rpi5'/n for n in ('tfa-clang','tfa-lld','tfa-objcopy','tfa-ar'))]
    captured={str(p):sha(p) for p in [*(UPSTREAM/n for n in tracked),*extra,baseline] if p.is_file()}
    output.mkdir(exist_ok=False);tree=output/'source';tree.mkdir()
    for name in tracked:
        source=UPSTREAM/name
        if not source.is_file():continue
        target=tree/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    for name in NAMES:shutil.copyfile(ROOT/'firmware/rpi5'/name,tree/'plat/rpi/rpi5'/name)
    commands=[]
    def run(args,name,cwd):
        result=subprocess.run(list(map(str,args)),cwd=cwd,text=True,capture_output=True,timeout=120)
        (output/(name+'.stdout')).write_text(result.stdout);(output/(name+'.stderr')).write_text(result.stderr)
        commands.append(dict(command=list(map(str,args)),cwd=str(cwd),returncode=result.returncode))
        if result.returncode:raise ValueError(name+' failed: '+result.stderr[-2000:])
    run(['patch','--batch','--fuzz=0','-p1','-i',PATCH],'patch',tree)
    run(['make','-j4','V=1','PLAT=rpi5','DEBUG=1','RPI3_RUNTIME_UART=-1','CFLAGS=-fstack-usage',
        'BUILD_STRING=pcie-verifier-332b62e','BUILD_BASE='+str(output/'build'),
        *[f'{key}={ROOT}/tools/rpi5/{value}' for key,value in
          (('CC','tfa-clang'),('LD','tfa-lld'),('OC','tfa-objcopy'),('AR','tfa-ar'))]],'make',tree)
    binary=output/'build/rpi5/debug/bl31.bin';elf=output/'build/rpi5/debug/bl31/bl31.elf'
    report=audit_elf(elf,binary)
    frames=[]
    for p in (output/'build').rglob('pcie_verifier*.su'):
        for line in p.read_text().splitlines():
            location,size,kind=line.split('\t')
            if kind!='static':raise ValueError('Unbounded added firmware stack')
            frames.append(dict(location=location,bytes=int(size)))
    if not frames or sum(r['bytes'] for r in frames)>1024:raise ValueError('Added C frame budget refused')
    if any(sha(Path(p))!=pin for p,pin in captured.items()):raise ValueError('Build input changed')
    if tool_identity()!=tools:raise ValueError('Compiler/linker/tool changed during build')
    for name in tracked:
        if name=='plat/rpi/rpi5/platform.mk' or not (UPSTREAM/name).is_file():continue
        if sha(tree/name)!=captured[str(UPSTREAM/name)]:raise ValueError('Copied upstream source changed: '+name)
    generated={str(p):sha(p) for p in (*[tree/'plat/rpi/rpi5'/n for n in NAMES],tree/'plat/rpi/rpi5/platform.mk',binary,elf,
        *(output/'build').rglob('pcie_verifier*.o'),*(output/'build').rglob('pcie_verifier*.su'),
        output/'make.stdout',output/'make.stderr',output/'patch.stdout',output/'patch.stderr',
        *(tree/n for n in tracked if (tree/n).is_file()))}
    report.update(profile='pcie-el3-verifier-v1',firmware=str(binary),firmware_sha256=sha(binary),
        firmware_bytes=binary.stat().st_size,inputs_sha256=captured,generated_sha256=generated,commands=commands,tool_identity=tools,
        added_c_frames=frames,added_c_frame_sum=sum(r['bytes'] for r in frames),original_firmware_preserved=True,
        installed=False,pi_executed=False,controller_writes=False,dma_authorized=False,clock_power_ownership_proven=False,
        secure_dram_isolation_claimed=False,scope='Real EL3 secure-view verification service/link; not hardware execution or complete lifecycle admission')
    (output/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True)
    r=build(p.parse_args().output_dir);print(json.dumps({k:r[k] for k in ('firmware','firmware_sha256','firmware_bytes','added_c_frame_sum','installed','pi_executed')}))
