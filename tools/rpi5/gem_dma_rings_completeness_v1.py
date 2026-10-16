# SPDX-License-Identifier: BSD-2-Clause
"""Byte-only canonical recipe completion for the INACTIVE word-ring prototype.

This is not a compiler replay, historical semantic audit, transport admission,
or authority for a future real controller/batch profile. The outer package
checker must separately verify its retained manifest pin, closure and binaries.
"""
import hashlib
import json
from pathlib import Path
import re
from tools.rpi5 import gem_dma_rings_recipe_v1 as recipe
PROFILE='bcm2712-gem-owned-rings-resolved-reservations-default-off-v1'
def same(a,b):return json.dumps(a,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(b,sort_keys=True,separators=(',',':'),allow_nan=False)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def command_plan(package,tag):
    from tools.rpi5 import build_gem_dma_rings_package as b
    package=Path(package).resolve()
    if not re.fullmatch('[a-f0-9]{32}',tag) or b.PROFILE!=PROFILE:raise ValueError('Exact inactive prototype identity required')
    for path,pin in ((b.BASE/'manifest.json','d1c6ce8f6b7ed198a237d367ed821e636f0e073fdf97be8d41212afed497a165'),
                     (b.TEMPLATE/'manifest.json','0dafc8e47ab3226833c36c9aab2a2da1116abb2ca4c814e1a81a852e372c0fb8')):
        if sha(path)!=pin:raise ValueError('Exact recipe parent changed')
    parent=json.loads((b.BASE/'manifest.json').read_bytes());template=json.loads((b.TEMPLATE/'manifest.json').read_bytes())
    rows={};scans={}
    def row(label,args,cwd=b.ROOT):
        if label in rows:raise ValueError('Duplicate canonical operation')
        rows[label]=dict(command=list(map(str,args)),cwd=str(cwd))
    def unit(flags,source,label,cwd=b.ROOT):
        source=Path(source);row(label+'-scan',[*flags,'-M','-MF',package/(label+'.scan.d'),source],cwd)
        row(label+'-compile',[*flags,'-c','-MD','-MF',package/(label+'.d'),source,'-o',package/(label+'.o')],cwd)
        scans[label]=dict(cwd=str(cwd),source=str(source))
    armrow=next(r for r in parent['commands'] if r['log'].endswith('/arm_init-compile.log'))
    armflags=b.display.compiler_flags(armrow['command'],b.BASE/'arm_init.c')+['-I',str(b.ROOT),'-I',str(b.ROOT/'osfmk'),'-fstack-usage']
    unit(armflags,package/'arm_init.c','arm_init',armrow['cwd'])
    row('arm-assembly',[*armflags,'-S',package/'arm_init.c','-o',package/'arm_init.s'],armrow['cwd'])
    def flags(name):
        record=next(r for r in template['compiles'] if r['command'][-1].endswith(name+'.o'))
        original=next(a for a in record['command'] if a.endswith('/overlay/'+name))
        result=b.display.compiler_flags(record['command'],original)
        result[1:1]=['-I'+str(b.ROOT),'-I'+str(b.ROOT/'osfmk'),'-I'+str(b.ROOT/'iokit/Kernel'),'-I'+str(b.ROOT/'loader/rpi5')]
        result+=['-fstack-usage']
        return result,b.display.OBJ/('iokit/DEVELOPMENT' if name.endswith('.cpp') else 'pexpert/DEVELOPMENT')
    cpp,cppcwd=flags('BCM2712PCIePHYTransport.cpp');c,ccwd=flags('rp1_gem_mdio.c')
    unit(cpp,package/'overlay/BCM2712GEMDMARings.cpp','dma-rings',cppcwd)
    row('dma-rings-assembly',[*cpp,'-S',package/'overlay/BCM2712GEMDMARings.cpp','-o',package/'dma-rings.s'],cppcwd)
    cores=[b.ROOT/'iokit/Kernel'/p for p in ('rpi5_gem_dma_route.c','rpi5_gem_ring_stage.c')]
    cores+=[b.ROOT/'osfmk/arm64/rpi5_reservation_kernel.c']
    cores+=[b.ROOT/'loader/rpi5'/p for p in ('reservation_record.c','ranges.c','reservations.c','pcie_released_windows.c','rp1_gem_capabilities.c')]
    cores+=[b.SELECTED,b.ROOT/'loader/rpi5/firmware_seed_fdt.c']
    for source in cores:unit(c,source,'kernel-'+source.stem,ccwd)
    oldlink=next(r['command'] for r in parent['commands'] if r['log'].endswith('/kernel-link.log'))
    changes={str(b.BASE/'kernel.display.filelist'):str(package/'kernel.filelist'),str(b.BASE/'kernel.unstripped'):str(package/'kernel.unstripped'),
        '-Wl,-map,'+str(b.BASE/'kernel.map'):'-Wl,-map,'+str(package/'kernel.map')}
    if any(oldlink.count(p)!=1 for p in changes):raise ValueError('Canonical predecessor link changed')
    row('kernel-link',[changes.get(p,p) for p in oldlink])
    row('kernel-strip',['xcrun','strip','-S',package/'kernel.unstripped','-o',package/'kernel.owned-rings'])
    row('kernel-undefined',['xcrun','nm','-ju',package/'kernel.owned-rings'])
    row('kernel-symbols',['xcrun','nm','-nm',package/'kernel.owned-rings'])
    for name in ['dma-rings',*['kernel-'+source.stem for source in cores]]:row(name+'-symbols',['xcrun','nm',package/(name+'.o')])
    loaderrow=next(r for r in parent['commands'] if r['log'].endswith('/loader-probe_main-compile.log'))
    loader=b.display.compiler_flags(loaderrow['command'],b.BASE/'probe_main.c')
    loader=[a for a in loader if not a.startswith('-DRPI5_DISPLAY_XNU_TAG=')]+['-DRPI5_DISPLAY_XNU_TAG="'+tag+'"']
    for name,source in [('probe_main',package/'probe_main.c'),('firmware_seed_tree',package/'firmware_seed_tree.c'),('payload',package/'payload.S'),
                        ('reservation_record',b.ROOT/'loader/rpi5/reservation_record.c'),('reservation_record_tree',b.ROOT/'loader/rpi5/reservation_record_tree.c')]:
        unit(loader,source,'loader-'+name)
    stack={name:b.ROOT/'loader/rpi5'/(name+'.c') for name in sorted(b.record.STACK_UNITS)}
    bear=b.ROOT/'build/rpi5/bearssl-candidate/src'
    stack.update(sha2small=bear/'hash/sha2small.c',dec32be=bear/'codec/dec32be.c',enc32be=bear/'codec/enc32be.c')
    for name,source in stack.items():
        if name not in ('reservation_record','reservation_record_tree'):unit(loader,source,'stack-'+name)
    link=next(r['command'] for r in parent['commands'] if r['log'].endswith('/loader-link.log'))
    changes={str(b.BASE/('loader-'+name+'.o')):str(package/('loader-'+name+'.o')) for name in ('probe_main','firmware_seed_tree','payload')}
    if any(link.count(p)!=1 for p in changes):raise ValueError('Canonical loader predecessor changed')
    vector=[changes.get(a,a) for a in link];vector[vector.index('-o')+1]=str(package/'owned_rings.elf')
    vector[vector.index('-o'):vector.index('-o')]=[str(package/'loader-reservation_record.o'),str(package/'loader-reservation_record_tree.o')]
    row('loader-link',vector)
    row('loader-objcopy',[b.ROOT/'tools/rpi5/tfa-objcopy','-O','binary',package/'owned_rings.elf',package/'probe.bin'])
    row('loader-undefined',['xcrun','llvm-nm','--undefined-only',package/'owned_rings.elf'])
    row('loader-symbols',['xcrun','llvm-nm','-n',package/'owned_rings.elf'])
    return rows,scans
def command_bindings(package,manifest):
    from tools.rpi5 import build_gem_dma_rings_package as b
    package=Path(package).resolve();m=manifest
    if package.parent!=b.ROOT/'build/rpi5' or not package.name.startswith('gem-dma-rings-') or m.get('profile')!=PROFILE:
        raise ValueError('Wrong exact inactive package profile')
    expected,scans=command_plan(package,m['tag']);observed={}
    for r in m['commands']:
        label=Path(r['log']).stem
        if label in observed or r['log']!=str(package/(label+'.log')) or not same(r['returncode'],0) or sha(r['log'])!=r['log_sha256']:
            raise ValueError('Ambiguous/incomplete canonical operation')
        observed[label]=dict(command=r['command'],cwd=r['cwd'])
    if not same(observed,expected):raise ValueError('Complete actual compiler/link/utility vectors or cwd differ')
    if set(m['compiler_scans'])!=set(scans):raise ValueError('Complete canonical scan label set differs')
    return scans
def canonical_sources(package,pins):
    from tools.rpi5 import build_gem_dma_rings_package as b
    package=Path(package).resolve()
    required=[*b.sources(),Path(__file__).resolve(),Path(recipe.__file__).resolve(),
        b.ROOT/'tools/rpi5/tests/test_gem_dma_rings_completeness_v1.py']
    if any(pins.get(str(p))!=sha(p) for p in required):raise ValueError('Canonical source recipe input omitted')
    for name,data in recipe.derive().items():
        if (package/'overlay'/name).read_bytes()!=data:raise ValueError('Canonical private provider output differs: '+name)
    for name,transform in [('arm_init',b.boot.arm),('probe_main',b.record.loader),('firmware_seed_tree',b.record.seed)]:
        if (package/(name+'.c')).read_bytes()!=transform((b.BASE/(name+'.c')).read_text()).encode():raise ValueError('Canonical owner source differs: '+name)
def canonical_payload(package):
    from tools.rpi5 import build_gem_dma_rings_package as b
    package=Path(package).resolve()
    kernel=(package/'kernel.owned-rings').read_bytes();original=(b.BASE/'payload.bin').read_bytes()
    # Decode the accepted root from the independently pinned predecessor; do
    # not trust any newly supplied offset/hash as the root identity.
    import struct
    root_offset,root_bytes=struct.unpack_from('<QQ',original,136);root=original[root_offset:root_offset+root_bytes]
    if (package/'payload.bin').read_bytes()!=b.payload_container.encode(kernel,root):raise ValueError('Canonical payload header/offset/padding/root differs')
    assembly='.section .payload,"a"\n.balign 64\n.incbin "'+str(package/'payload.bin')+'"\n'
    if (package/'payload.S').read_bytes()!=assembly.encode():raise ValueError('Canonical embedded payload source differs')
def inspect(package,manifest):
    from tools.rpi5 import build_gem_dma_rings_package as b
    package=Path(package).resolve();m=manifest;scans=command_bindings(package,m)
    headers={};pins=m['inputs_sha256']
    for label,record in scans.items():
        before=b.display.dependencies(package/(label+'.scan.d'),record['cwd'])
        after=b.display.dependencies(package/(label+'.d'),record['cwd'])
        if before!=after or sorted(before)!=m['compiler_scans'][label] or record['source'] not in before:
            raise ValueError('Exact actual compile dependency closure differs: '+label)
        for path in before:
            if pins.get(path)!=sha(path):raise ValueError('Required compiler input omitted/changed')
            headers[path]=pins[path]
    if not same(headers,m['actual_headers_sha256']):raise ValueError('Canonical complete header map differs')
    canonical_sources(package,pins);canonical_payload(package)
    return dict(profile=PROFILE,canonical_commands=len(m['commands']),canonical_compile_labels=len(scans),
        header_members=len(headers),provider_outputs=4,compiler_replayed=False,hardware_admission=False)
