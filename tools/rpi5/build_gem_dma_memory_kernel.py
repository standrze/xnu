#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Separate, inactive genuine Apple DMA-memory provider link; never a boot package."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from tools.rpi5 import build_pcie_phy_reset_kernel as baseline
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'build/rpi5/pcie-phy-reset-kernel-20261014-v2'
BASE_SHA='0dafc8e47ab3226833c36c9aab2a2da1116abb2ca4c814e1a81a852e372c0fb8'
PROFILE='bcm2712-gem-apple-dma-memory-default-off-v1'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def build(output):
    output=output.resolve()
    if output.parent!=ROOT/'build/rpi5' or output.exists():raise ValueError('New distinct build directory required')
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Exact frozen kernel required')
    parent=json.loads((BASE/'manifest.json').read_text())
    sources=[ROOT/'iokit/Kernel/BCM2712GEMDMAMemory.cpp',ROOT/'iokit/Kernel/rpi5_gem_dma_route.c']
    pins=parent['inputs_sha256']|parent['generated_sha256']|{str(BASE/'manifest.json'):BASE_SHA}
    extra=[Path(__file__).resolve(),*sources,*(p.with_suffix('.h') for p in sources),
        ROOT/'tools/rpi5/tests/test_gem_dma_memory.py',ROOT/'tools/rpi5/tests/gem_dma_memory_host.cpp',
        ROOT/'tools/rpi5/tests/gem_dma_route_host.c',ROOT/'tools/rpi5/gem_dma_memory_sources.json']
    provenance=json.loads((ROOT/'tools/rpi5/gem_dma_memory_sources.json').read_text())
    for row in provenance['sources']:
        path=ROOT/row['path']
        if sha(path)!=row['sha256'] or path.stat().st_size!=row['bytes']:raise ValueError('Primary source bytes changed')
        extra.append(path)
    for path in extra:
        digest=sha(path)
        if str(path) in pins and pins[str(path)]!=digest:raise ValueError('Do not replace a frozen input')
        pins[str(path)]=digest
    baseline.engine.verify(pins)
    output.mkdir()
    commands=[];objects=[]
    def run(args,name,cwd=ROOT):
        row=baseline.audit.execute(list(map(str,args)),cwd,output/(name+'.log'));commands.append(row)
        if row['returncode']:raise ValueError('Failed: '+row['log'])
        return row
    for source in sources:
        name='BCM2712PCIePHYTransport.cpp' if source.suffix=='.cpp' else 'rp1_gem_mdio.c'
        rows=[r['command'] for r in parent['compiles'] if r['command'][-1].endswith(name+'.o')]
        if len(rows)!=1:raise ValueError('Exact predecessor compiler required')
        args=rows[0][:rows[0].index('-MD')]
        old=next(a for a in args if a.endswith('/overlay/'+name))
        args=[str(source) if a==old else a for a in args]
        cwd=baseline.audit.OBJ/('iokit/DEVELOPMENT' if source.suffix=='.cpp' else 'pexpert/DEVELOPMENT')
        dep=output/(source.name+'.d');obj=output/(source.name+'.o');objects.append(obj)
        row=run(args+['-MD','-MF',dep,'-o',obj],source.name+'-compile',cwd)
        if row['warning_count']:raise ValueError('New provider compile warnings')
        for path in baseline.audit.dependency_paths(dep,cwd):
            digest=sha(path)
            if str(path) in pins and pins[str(path)]!=digest:raise ValueError('Dependency drift: '+str(path))
            pins[str(path)]=digest
        run([a for a in args if a!='-c']+['-S','-o',output/(source.name+'.s')],source.name+'-assembly',cwd)
    original=(BASE/'kernel.rp1-config.filelist').read_text().splitlines()
    if len(original)!=len(set(original)) or set(original)&set(map(str,objects)):raise ValueError('Object duplication')
    filelist=output/'kernel.filelist';filelist.write_text('\n'.join(original+list(map(str,objects)))+'\n')
    link=next(r['command'] for r in parent['commands'] if r['log'].endswith('/link.log'))
    changes={str(BASE/'kernel.rp1-config.filelist'):str(filelist),str(BASE/'kernel.unstripped'):str(output/'kernel.unstripped'),
        '-Wl,-map,'+str(BASE/'kernel.map'):'-Wl,-map,'+str(output/'kernel.map')}
    if any(link.count(x)!=1 for x in changes):raise ValueError('Exact linker paths required')
    row=run([changes.get(a,a) for a in link],'link')
    warnings=[line for line in Path(row['log']).read_text().splitlines() if 'warning:' in line]
    if warnings!=parent['baseline_linker_warnings']:raise ValueError('Unexpected link warnings')
    kernel=output/'kernel.dma-memory'
    run(['xcrun','strip','-S',output/'kernel.unstripped','-o',kernel],'strip')
    symbols=subprocess.check_output(['xcrun','nm','-nm',kernel],text=True)
    (output/'kernel.symbols').write_text(symbols)
    if subprocess.check_output(['xcrun','nm','-ju',kernel],text=True).strip():raise ValueError('Unresolved provider')
    # Use the actual compiler's mangled name, not a hand-counted class length.
    provided=subprocess.check_output(['xcrun','nm','-jg',objects[0]],text=True).splitlines()
    if not any('7prepareEv' in n for n in provided) or not any('7qualifyE' in n for n in provided):raise ValueError('Provider body absent')
    for name in ['_rpi5_gem_dma_route',*provided]:
        if name not in symbols:raise ValueError('Missing linked implementation: '+name)
    text=(output/'kernel.map').read_text(errors='surrogateescape')
    if any(str(p) not in text for p in objects):raise ValueError('Provider object absent from link map')
    baseline.engine.verify(pins)
    result=dict(profile=PROFILE,parent_manifest_sha256=BASE_SHA,kernel=str(kernel),kernel_sha256=sha(kernel),
        kernel_bytes=kernel.stat().st_size,added_objects=list(map(str,objects)),replaced_objects=[],
        unchanged_predecessor_objects=len(original),inputs_sha256=pins,commands=commands,
        complete_kernel_link_proven=True,default_off=True,boot_caller_added=False,
        constructor_added=False,loader_created=False,staged=False,hardware_executed=False,
        real_apple_allocators_and_command_linked=True,one_physical_gen64_segment_required=True,
        primary_source_references=provenance,
        descriptor_mapper_none=True,command_unmapped_null_mapper=True,allocation_bytes=0x48000,
        cpu_cache_policy='Actual VA and physmap S1E1R/W PAR ATTR=0x44 plus managed WCOMB state',
        fresh_original_fdt_required=True,fresh_released_window_reads=90,
        unresolved_dynamic_reservation_windows_fully_excluded=True,
        retained_on_admitted_failure=True,ring_caller_added=False,dma_enabled=False,irq_enabled=False,packets=False,
        remaining_integration='New sleepable allocation caller and separate bounded live hardware-owner lifecycle; no reuse/reset of PHY-test lease',
        generated_sha256={str(p):sha(p) for p in output.iterdir() if p.is_file()})
    (output/'manifest.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True)
    m=build(p.parse_args().output_dir)
    print(json.dumps({k:m[k] for k in ('profile','kernel','kernel_sha256','kernel_bytes','default_off')}))
