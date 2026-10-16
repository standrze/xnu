# SPDX-License-Identifier: BSD-2-Clause
"""Actual retained IOKit methods, disabled-route admission and fixed CPU batches."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import gem_dma_batch_profile as profile
from tools.rpi5 import gem_dma_rings_profile as word
from tools.rpi5.tests import test_gem_dma_rings as prior
ROOT=profile.ROOT
def host_source(header,body):
    source=prior.host_source(header.replace('BCM2712GEMDMABatch','BCM2712GEMDMARings'),
        body.replace('BCM2712GEMDMABatch','BCM2712GEMDMARings'))
    source=source.replace('BCM2712GEMDMARings','BCM2712GEMDMABatch')
    source=profile.change(source,'w.state=RPI5_PCIE_WINDOWS_COMPLETE;',
        'w.state=RPI5_PCIE_WINDOWS_COMPLETE;for(unsigned i=0;i<3;i++)w.plan.inbound[i].bar_lo&=~31u;')
    source=source.replace('total==2564','total==164')
    source=source.replace('1u,2u,3u,256u,512u,1024u,1282u,2048u,2563u,2564u',
        '1u,2u,3u,16u,32u,64u,82u,128u,163u,164u')
    source=source.replace('1u,1282u,2564u','1u,82u,164u')
    source=source.replace('    unsigned faults=0;', '''    unsigned faults=0;
    /* Reject every enabled inbound encoding, and drift in any of the three
     * route domains; no hardware read happens on malformed metadata. */
    for(unsigned slot=0;slot<3;slot++)for(unsigned mode=0;mode<4;mode++) {
        setup(w,r);BCM2712GEMDMABatch m;active=&m;assert(m.prepare());
        if(mode==0)r.expected.inbound[slot].bar_lo|=1;
        if(mode==1)r.expected.inbound[slot].bar_hi^=1;
        if(mode==2)r.expected.inbound[slot].remap_hi^=1;
        if(mode==3)r.expected.inbound[slot].size^=0x4000;
        memset(&geometry,0xa5,sizeof geometry);auto before_geometry=geometry;
        assert(!m.qualify(&r,&geometry) && m.state()==BCM2712GEMDMABatch::Quarantined);
        assert(!memcmp(&geometry,&before_geometry,sizeof geometry) && !model.reads);faults++;
    }
''')
    return source.replace('DMA_RINGS_REAL_METHODS_PASS','DMA_BATCH_REAL_METHODS_PASS')
class GEMDMABatchTests(unittest.TestCase):
    def test_pure_predecessor_recipe_exact_all_outputs(self):
        with tempfile.TemporaryDirectory(prefix='ring-recipe-') as d:
            folder=Path(d)/'overlay';word.emit(folder)
            actual={p.name:p.read_bytes() for p in folder.iterdir()}
            self.assertEqual(actual,profile.prior.derive())

    def test_actual_retained_methods_lifecycle_disabled_routes_and_batches(self):
        with tempfile.TemporaryDirectory(prefix='dma-batch-host-') as d:
            folder=Path(d);hp,cp=profile.emit(folder/'overlay')
            host=folder/'host.cpp';host.write_text(host_source(hp.read_text(),cp.read_text()))
            sources=['iokit/Kernel/rpi5_gem_dma_route.c','iokit/Kernel/rpi5_gem_ring_batch.c',
                'loader/rpi5/pcie_windows.c','loader/rpi5/pcie_released_windows.c','loader/rpi5/rp1_gem_capabilities.c',
                'loader/rpi5/rp1_gem_identify.c','loader/rpi5/reservation_record.c','loader/rpi5/ranges.c','loader/rpi5/reservations.c',
                'osfmk/arm64/rpi5_reservation_kernel.c']
            objects=[]
            for relative in sources:
                source=ROOT/relative;obj=folder/(source.name+'.o');objects.append(obj)
                subprocess.run(['xcrun','clang','-std=c11','-O1','-g','-fsanitize=address,undefined',
                    '-I',str(ROOT),'-c',str(source),'-o',str(obj)],check=True,timeout=60)
            exe=folder/'host';p=subprocess.run(['xcrun','clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(folder/'overlay'),'-I',str(ROOT),'-I',str(ROOT/'osfmk'),'-I',str(ROOT/'iokit/Kernel'),'-I',str(ROOT/'loader/rpi5'),
                str(host),*map(str,objects),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stderr)
            for repetition in range(5):
                p=subprocess.run([exe],capture_output=True,text=True,timeout=60)
                self.assertEqual(p.returncode,0,f'repetition={repetition}: '+p.stderr)
                self.assertIn('DMA_BATCH_REAL_METHODS_PASS',p.stdout)
            print('REPEATED5 '+p.stdout,end='')

    def test_actual_iokit_a76_no_calls_in_fixed_access_loops(self):
        args,cwd=prior.predecessor.target_command()
        with tempfile.TemporaryDirectory(prefix='dma-batch-target-') as d:
            folder=Path(d);hp,cp=profile.emit(folder/'overlay');obj=folder/'batch.o'
            args=[str(cp) if a==str(prior.predecessor.PROVIDER) else a for a in args]
            args[1:1]=['-I'+str(ROOT),'-I'+str(ROOT/'osfmk'),'-I'+str(ROOT/'iokit/Kernel'),'-I'+str(ROOT/'loader/rpi5')]
            p=subprocess.run(args+['-fstack-usage','-o',str(obj)],cwd=cwd,capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'')
            asm=subprocess.check_output(['xcrun','llvm-objdump','-d',obj],text=True)
            self.assertIn('dsb\tosh',asm);self.assertIn('s1e1r',asm);self.assertIn('s1e1w',asm)
            self.assertNotIn('smc\t',asm);self.assertNotIn('hvc\t',asm)
            src=(ROOT/'iokit/Kernel/BCM2712GEMDMABatchAccess.inc').read_text()
            self.assertEqual(src[src.index('    for(unsigned i=0;i<16;i+=4)'):src.index('    return 0;')],
                '    for(unsigned i=0;i<16;i+=4) {\n        dst[i+2]=values[i+2];dst[i+3]=values[i+3];\n        dst[i+1]=values[i+1];dst[i]=values[i];\n    }\n')
            self.assertIn('for(unsigned i=0;i<16;i++)values[i]=src[i];',src)
if __name__=='__main__':unittest.main()
