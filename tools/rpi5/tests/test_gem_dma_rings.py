# SPDX-License-Identifier: BSD-2-Clause
"""Distinct ring-owning Apple provider: actual methods, explicit native API doubles."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import gem_dma_rings_profile as profile
from tools.rpi5.tests import test_gem_dma_memory as predecessor
ROOT=profile.ROOT

def host_source(header,body):
    header='\n'.join(x for x in header.splitlines() if not x.startswith('#include <'))
    body=body[body.index('/* AT has no memory'):]
    begin=body.index('static bool translated_nc(');end=body.index('bool BCM2712GEMDMARings::context()',begin)
    body=body[:begin]+'static bool translated_nc(uint64_t v,uint64_t p){return fake_translated_nc(v,p);}\n'+body[end:]
    body=profile.replace(body,'__asm__ volatile("dsb osh" ::: "memory");','/* Native barrier double; target object separately audited. */')
    source=(ROOT/'tools/rpi5/tests/gem_dma_memory_host.cpp').read_text().split('int main()\n',1)[0]
    source=source.replace('BCM2712GEMDMAMemory','BCM2712GEMDMARings')
    source=source.replace('pa=0x100000000,gen=0x100000000','pa=0xe000000,gen=0xe000000')
    source=source.replace('ram->start[0]=0x40000000','ram->start[0]=0')
    source=source.replace('p->request[0].size=0x4000000;',
        'p->request[0].size=0x4000000;p->request[0].alignment=1;p->request[0].node_offset=17;')
    # Pure parsers cannot call arbitrary code in production. Keep reentrancy
    # injection at real allocating/virtual/cache/owner boundaries, not inside
    # these FDT data doubles; the separate codec suite uses actual FDT parsers.
    begin=source.index('extern "C" int rpi5_pcie_profile_decode(')
    end=source.index('static bool fake_translated_nc(',begin)
    parsers=source[begin:end].replace('return event()?-1:0;','return 0;').replace('return event()?-1:1;','return 1;')
    source=source[:begin]+parsers+source[end:]
    source=source.replace('void release(){model.releases++;}','void release(){model.releases++;(void)event();}')
    source=source.replace('uint64_t getLength()const{return sizeof allocation;}','uint64_t getLength()const{(void)event();return sizeof allocation;}')
    source=source.replace('uint64_t getCapacity()const{return sizeof allocation;}','uint64_t getCapacity()const{(void)event();return sizeof allocation;}')
    source=source.replace('void *getBytesNoCopy()const{return allocation;}','void *getBytesNoCopy()const{(void)event();return allocation;}')
    source=source.replace('const void *getBytesNoCopy()const{return &fixture;}','const void *getBytesNoCopy()const{(void)event();return &fixture;}')
    source=source.replace('unsigned getLength()const{return sizeof fixture;}','unsigned getLength()const{(void)event();return sizeof fixture;}')
    # Keep native lookup callbacks observable; no production owner is supplied.
    source=source.replace('static void mutate(){released->io.context=(void *)0x4444;}','')
    provider_double='''
static struct rpi5_reservation_record kernel_record;
static bool kernel_record_ready;
extern "C" const struct rpi5_reservation_record *rpi5_boot_reservation_record(void)
{return kernel_record_ready?&kernel_record:nullptr;}
'''
    source=source.replace('/*PROVIDER_HEADER*/',header+provider_double).replace('/*PROVIDER_BODY*/',body)
    source=source.replace('    model=Model{};fixture={};','''    model=Model{};fixture={};kernel_record_ready=true;kernel_record={};
    kernel_record.managed_start=0x6000000;kernel_record.managed_end=0x10000000;
    kernel_record.loader_start=0x9000000;kernel_record.loader_end=0xa000000;
    kernel_record.kernel_start=0x7004000;kernel_record.kernel_end=0x8000000;
    kernel_record.args_pa=0x8000000;kernel_record.args_bytes=1152;
    kernel_record.tree_pa=0x8004000;kernel_record.tree_bytes=4096;
    kernel_record.fdt_pa=0xb000000;kernel_record.fdt_bytes=sizeof fixture;kernel_record.top=0xb040000;
    kernel_record.owner_counter=100;kernel_record.fdt_sha256[0]=1;
    kernel_record.fixed_count=1;kernel_record.fixed[0]={0,0x80000};kernel_record.dynamic_count=1;
    kernel_record.dynamic[0]={17,0,0x80000,0x4080000,1};''')
    return source+'\n'+(ROOT/'tools/rpi5/tests/gem_dma_rings_host.inc').read_text()

class GEMDMARingsTests(unittest.TestCase):
    def test_actual_retained_methods_lifecycle_release_reentry_and_ring_access(self):
        with tempfile.TemporaryDirectory(prefix='dma-rings-host-') as d:
            folder=Path(d);hp,cp=profile.emit(folder/'overlay')
            host=folder/'host.cpp';host.write_text(host_source(hp.read_text(),cp.read_text()))
            sources=['iokit/Kernel/rpi5_gem_dma_route.c','iokit/Kernel/rpi5_gem_ring_stage.c',
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
                self.assertIn('DMA_RINGS_REAL_METHODS_PASS',p.stdout)
            print('REPEATED5 '+p.stdout,end='')

    def test_actual_iokit_target_and_cpu_owned_store_barrier(self):
        args,cwd=predecessor.target_command()
        with tempfile.TemporaryDirectory(prefix='dma-rings-target-') as d:
            folder=Path(d);hp,cp=profile.emit(folder/'overlay');obj=folder/'rings.o'
            args=[str(cp) if a==str(predecessor.PROVIDER) else a for a in args]
            args[1:1]=['-I'+str(ROOT),'-I'+str(ROOT/'osfmk'),'-I'+str(ROOT/'iokit/Kernel'),'-I'+str(ROOT/'loader/rpi5')]
            p=subprocess.run(args+['-o',str(obj)],cwd=cwd,capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'')
            asm=subprocess.check_output(['xcrun','llvm-objdump','-d',obj],text=True)
            self.assertIn('dsb\tosh',asm);self.assertIn('s1e1r',asm);self.assertIn('s1e1w',asm)
            self.assertNotIn('smc\t',asm);self.assertNotIn('hvc\t',asm)
            symbols=subprocess.check_output(['xcrun','nm',obj],text=True)
            self.assertIn('stageCPUOwned',symbols);self.assertNotIn('___cxx_global_var_init',symbols)

if __name__=='__main__':unittest.main()
