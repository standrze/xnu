# SPDX-License-Identifier: BSD-2-Clause
"""Actual Apple TU compile and real provider bodies with explicit host doubles."""
from pathlib import Path
import json
import hashlib
import re
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]
PROVIDER=ROOT/'iokit/Kernel/BCM2712GEMDMAMemory.cpp'
HEADER=PROVIDER.with_suffix('.h')
ROUTE=ROOT/'iokit/Kernel/rpi5_gem_dma_route.c'
BASE=ROOT/'build/rpi5/pcie-phy-reset-kernel-20261014-v2'
RESERVATION_BASE=ROOT/'build/rpi5/gem-dma-rings-20261014-v2'

def target_command():
    from tools.rpi5 import build_pcie_phy_reset_kernel as baseline
    m=json.loads((BASE/'manifest.json').read_text())
    args=next(r['command'] for r in m['compiles'] if r['command'][-1].endswith('BCM2712PCIePHYTransport.cpp.o'))
    args=args[:args.index('-MD')]
    args=[str(PROVIDER) if a.endswith('/overlay/BCM2712PCIePHYTransport.cpp') else a for a in args]
    return args,baseline.audit.OBJ/'iokit/DEVELOPMENT'

class GEMDMAMemoryTests(unittest.TestCase):
    def test_primary_provider_cache_and_inbound_source_closure(self):
        metadata=json.loads((ROOT/'tools/rpi5/gem_dma_memory_sources.json').read_text())
        for row in metadata['sources']:
            raw=(ROOT/row['path']).read_bytes()
            self.assertEqual(len(raw),row['bytes']);self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])
        b=(ROOT/'iokit/Kernel/IOBufferMemoryDescriptor.cpp').read_text()
        self.assertIn('if (!(kIOMemoryMapperNone & options))',b)
        d=(ROOT/'iokit/Kernel/IODMACommand.cpp').read_text()
        self.assertIn('if (!mapper && (kUnmapped != MAPTYPE(mappingOptions)))',d)
        prepare=d.split('IODMACommand::prepare(UInt64 offset, UInt64 length, bool flushCache, bool synchronize)',1)[1]
        self.assertLess(prepare.index('if (fActive++)'),prepare.index('return kIOReturnNotAligned;'))
        mem=(ROOT/'iokit/Kernel/IOMemoryDescriptor.cpp').read_text()
        self.assertIn('[kIOWriteCombineCache] = {VM_WIMG_WCOMB, MAP_MEM_WCOMB}',mem)
        pmap=(ROOT/'osfmk/arm/pmap/pmap.c').read_text()
        self.assertIn('pmap_pte(kernel_pmap, kva)',pmap)
        self.assertIn('tmplate |= pmap_get_pt_ops(pmap)->wimg_to_pte(attributes, phys);',pmap)
        self.assertIn('flush_tlb_region_async',pmap)
        arm=(ROOT/'osfmk/arm64/proc_reg.h').read_text()
        self.assertRegex(arm,r'#define MAIR_WRITECOMB\s+0x44')
        self.assertRegex(arm,r'#define DAIF_STANDARD_DISABLE \(DAIF_ASYNCF \| DAIF_IRQF \| DAIF_FIQF\)')

    def test_actual_complete_route_bounds_and_encoding(self):
        with tempfile.TemporaryDirectory(prefix='dma-route-') as d:
            exe=Path(d)/'route'
            subprocess.run(['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(ROUTE.parent),
                str(Path(__file__).with_name('gem_dma_route_host.c')),str(ROUTE),
                str(ROOT/'loader/rpi5/pcie_windows.c'),'-o',str(exe)],check=True,timeout=60)
            p=subprocess.run([exe],capture_output=True,text=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stderr);self.assertIn('DMA_ROUTE_PASS',p.stdout);print(p.stdout,end='')

    def test_actual_provider_methods_and_actual_window_checker_faults(self):
        # Apple APIs, retrieved FDT and actual CPU translation have explicit
        # host doubles; production C++ methods and real 90-read checker remain.
        header='\n'.join(x for x in HEADER.read_text().splitlines() if not x.startswith('#include <'))
        body=PROVIDER.read_text()
        body=body[body.index('/* AT has no memory'):]
        begin=body.index('static bool translated_nc(')
        end=body.index('bool BCM2712GEMDMAMemory::context()',begin)
        body=body[:begin]+'''static bool translated_nc(uint64_t v,uint64_t p,
    uint64_t *r=nullptr,uint64_t *w=nullptr){
    if(r)*r=(UINT64_C(0x44)<<56)|(p&UINT64_C(0x0000fffffffff000));
    if(w)*w=(UINT64_C(0x44)<<56)|(p&UINT64_C(0x0000fffffffff000));
    return fake_translated_nc(v,p);
}\n'''+body[end:]
        source=Path(__file__).with_name('gem_dma_memory_host.cpp').read_text()
        self.assertEqual(source.count('/*PROVIDER_HEADER*/'),1);self.assertEqual(source.count('/*PROVIDER_BODY*/'),1)
        source=source.replace('/*PROVIDER_HEADER*/',header).replace('/*PROVIDER_BODY*/',body)
        with tempfile.TemporaryDirectory(prefix='dma-apple-host-') as d:
            folder=Path(d);host=folder/'host.cpp';host.write_text(source)
            objects=[]
            for src in (ROUTE,ROOT/'loader/rpi5/pcie_windows.c',ROOT/'loader/rpi5/pcie_released_windows.c'):
                obj=folder/(src.name+'.o');objects.append(obj)
                subprocess.run(['xcrun','clang','-std=c11','-O1','-g','-fsanitize=address,undefined','-c',str(src),'-o',str(obj)],check=True,timeout=60)
            exe=folder/'host'
            p=subprocess.run(['xcrun','clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(ROOT),'-I',str(ROOT/'iokit/Kernel'),'-I',str(ROOT/'osfmk'),
                '-I',str(ROUTE.parent),'-I',str(ROOT/'loader/rpi5'),
                str(host),*map(str,objects),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stderr)
            p=subprocess.run([exe],capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stderr);self.assertIn('NO_HARDWARE_PROOF',p.stdout);print(p.stdout,end='')

    def test_actual_iokit_a76_object_and_all_provider_imports(self):
        args,cwd=target_command()
        with tempfile.TemporaryDirectory(prefix='dma-apple-a76-') as d:
            obj=Path(d)/'provider.o'
            p=subprocess.run(args+['-o',str(obj)],cwd=cwd,capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'')
            imports=subprocess.check_output(['xcrun','nm','-ju',obj],text=True).splitlines()
            symbols=(BASE/'kernel.symbols').read_text()+(RESERVATION_BASE/'kernel.symbols').read_text()
            missing=[n for n in imports if n!='_rpi5_gem_dma_route' and not re.search(r'\b'+re.escape(n)+r'\b',symbols)]
            self.assertEqual(missing,[],'Actual existing kernel providers missing')
            self.assertIn('_pmap_cache_attributes',imports);self.assertIn('_rpi5_pcie_released_windows_check',imports)
            asm=subprocess.check_output(['xcrun','llvm-objdump','-d',obj],text=True)
            self.assertIn('s1e1r',asm);self.assertIn('s1e1w',asm);self.assertIn('PAR_EL1',asm)
            self.assertNotIn('smc\t',asm)
            observation_symbol='<__ZNK19BCM2712GEMDMAMemory21observeCPUOwnedLayoutEP34rpi5_gem_full_provider_observation>:'
            start=asm.index(observation_symbol)
            next_symbol=re.search(r'\n[0-9a-f]+ <',asm[start+len(observation_symbol):])
            end=(start+len(observation_symbol)+next_symbol.start()) if next_symbol else len(asm)
            body=asm[start:end]
            self.assertNotIn('__chkstk_darwin',body)
            self.assertNotIn('___cxx_global_var_init',subprocess.check_output(['xcrun','nm',obj],text=True))

if __name__=='__main__':unittest.main()
