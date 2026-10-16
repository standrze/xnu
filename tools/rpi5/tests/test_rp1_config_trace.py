# SPDX-License-Identifier: BSD-2-Clause
"""Actual old/new snapshot and production RP1 callback methods, explicit RAM doubles."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import rp1_config_trace_profile as p
ROOT=p.ROOT
TESTS=Path(__file__).resolve().parent


class ConfigTraceTests(unittest.TestCase):
    def run_native(self,folder,source,sources,language='c'):
        path=folder/('harness.'+language);path.write_text(source);program=folder/'harness'
        cmd=['xcrun','clang++' if language=='cpp' else 'clang','-std=c++17' if language=='cpp' else '-std=c11',
            '-D_DARWIN_C_SOURCE','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
            '-I',str(folder),'-I',str(ROOT),'-I',str(ROOT/'loader/rpi5'),'-I',str(TESTS),str(path),
            *map(str,sources),'-o',str(program)]
        r=subprocess.run(cmd,text=True,capture_output=True,timeout=60);self.assertEqual(r.returncode,0,r.stderr)
        r=subprocess.run([program],text=True,capture_output=True,timeout=30);self.assertEqual(r.returncode,0,r.stderr)
        return r.stdout

    def test_actual_snapshot_fault_matrix_and_all_partial_fields(self):
        source=(TESTS/'rp1_config_host.c').read_text().replace('int main(void)','int original_tests(void)')
        source+='''
#include "rp1_config_trace.h"
int main(void) {
    assert(!original_tests());
    struct fixture f;struct rpi5_rp1_config_snapshot out,saved;
    struct rpi5_rp1_config_trace t;
    snapshot_setup(&f);assert(!rpi5_rp1_config_snapshot_trace(&f.config,&out,&t));
    assert(t.step==5&&t.pass==1&&t.index==15&&t.reads==32&&!t.transfer_rc);
    assert(t.id==0x11de4&&!t.header&&!t.bar0&&t.bar1==0x400000);
    assert(f.m.calls==448&&!f.m.writes);finish(&f);
    for(unsigned position=1;position<=448;position++) {
        if(position%14==0)continue;
        snapshot_setup(&f);f.m.fail_at=position;memset(&out,0xa5,sizeof out);saved=out;
        assert(rpi5_rp1_config_snapshot_trace(&f.config,&out,&t)==-2);
        assert(t.step==2&&t.transfer_rc<0&&t.transfer_rc>=-10);
        assert(t.reads==(position-1)/14&&t.pass==t.reads/16&&t.index==t.reads%16);
        assert(!memcmp(&saved,&out,sizeof out)&&!f.m.locked&&!f.m.writes);finish(&f);
    }
    for(unsigned index=0;index<16;index++) {
        snapshot_setup(&f);mutate_read=17+index;memset(&out,0xa5,sizeof out);saved=out;
        assert(rpi5_rp1_config_snapshot_trace(&f.config,&out,&t)==-3);
        assert(t.step==3&&t.pass==1&&t.index==index&&t.reads==17+index);
        assert(!t.transfer_rc&&(t.previous^t.value)==1&&!memcmp(&saved,&out,sizeof out));finish(&f);
    }
    for(unsigned slot=4;slot<=5;slot++)for(unsigned shape=1;shape<16;shape++) {
        snapshot_setup(&f);f.m.bytes[1][4*slot]|=shape;
        assert(rpi5_rp1_config_snapshot_trace(&f.config,&out,&t)==-4&&t.step==4&&t.reads==32);
        assert(((slot==4?t.bar0:t.bar1)&15)==shape);finish(&f);
    }
    assert(rpi5_rp1_config_snapshot_trace(0,&out,&t)==-1&&t.step==1&&!t.reads);
    puts("RP1_TRACE_PASS CALLBACK_FAILURES=416 MISMATCHES=16 BAR_SHAPES=30 NO_EXTRA_MMIO=1");return 0;
}
'''
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);(folder/'rp1_config_trace.h').write_text(p.HEADER)
            core=folder/'snapshot.c';core.write_text(p.core((ROOT/'loader/rpi5/rp1_config_snapshot_checked.c').read_text()))
            output=self.run_native(folder,source,[ROOT/'loader/rpi5/pcie_config.c',core])
            self.assertIn('RP1_TRACE_PASS CALLBACK_FAILURES=416',output)

    def test_actual_transport_pass_failure_and_passive_reads(self):
        source=(TESTS/'rp1_transport_host.cpp').read_text()
        source=p.once(source,'#include "loader/rpi5/rp1_config_snapshot.h"','#include "rp1_config_trace.h"')
        source=p.once(source,'    unsigned phase=BCM2712_PHY_PREPARED,checks=0,failAt=0,controllerCalls=0;',
            '    unsigned phase=BCM2712_PHY_PREPARED,checks=0,failAt=0,controllerCalls=0;\n'
            '    unsigned diagIOBank=0,diagIOOffset=0,diagIODirection=0,diagIOStage=0,diagIOValue=0;\n'
            '    unsigned diagRP1Call=0,diagRP1Selector=0,diagRP1Status=0;int diagRP1RC=0;\n'
            '    rpi5_rp1_config_trace diagRP1={};')
        methods=p.transport((ROOT/'iokit/Kernel/BCM2712RP1ConfigTransport.inc').read_text())
        methods=methods.replace('__asm__ volatile("dmb osh" ::: "memory");','__asm__ volatile("" ::: "memory");')
        methods=methods.replace('__asm__ volatile("dsb sy" ::: "memory");','__asm__ volatile("" ::: "memory");')
        source=p.once(source,'#include "iokit/Kernel/BCM2712RP1ConfigTransport.inc"',methods)
        source=p.once(source,'        assert(owner.phase==BCM2712_PHY_COMPLETE&&!owner.rp1Locked);count=owner.checks;',
            '        assert(owner.phase==BCM2712_PHY_COMPLETE&&!owner.rp1Locked);count=owner.checks;\n'
            '        assert(owner.diagRP1Call==5&&!owner.diagRP1RC&&owner.diagRP1.step==5&&owner.diagRP1.reads==32);\n'
            '        assert(owner.diagRP1Selector==0x100000&&owner.diagRP1Status==0xb0);\n'
            '        assert(owner.diagIOOffset==0x9000&&owner.diagIOValue==0x100000&&owner.diagIOStage==4);')
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);(folder/'rp1_config_trace.h').write_text(p.HEADER)
            core=folder/'snapshot.c';core.write_text(p.core((ROOT/'loader/rpi5/rp1_config_snapshot_checked.c').read_text()))
            objects=[]
            for c in (ROOT/'loader/rpi5/pcie_config.c',core):
                o=folder/(c.name+'.o');objects.append(o)
                r=subprocess.run(['xcrun','clang','-std=c11','-fsanitize=address,undefined','-I',str(folder),
                    '-I',str(ROOT/'loader/rpi5'),'-c',str(c),'-o',str(o)],text=True,capture_output=True,timeout=60)
                self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn('RP1_TRANSPORT_PASS ACTUAL_METHODS=7',self.run_native(folder,source,objects,'cpp'))

    def test_same_original_guards_accesses_and_layout_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'overlay';p.emit(folder)
            for name in ('BCM2712PCIePHYTransport.cpp','BCM2712PCIeControllerRun.inc','BCM2712PCIeFWTransport.inc','pcie_link.c'):
                self.assertEqual((folder/name).read_bytes(),(p.FROZEN/name).read_bytes())
            original=(ROOT/'iokit/Kernel/BCM2712RP1ConfigTransport.inc').read_text()
            new=(folder/'BCM2712RP1ConfigTransport.inc').read_text()
            for token in ('__asm__ volatile("dmb osh"','__asm__ volatile("dsb sy"',
                'reinterpret_cast<volatile uint32_t *>','bcm2712_rp1_config_access(',
                'self->guard()','rpi5_pcie_config_init('):
                self.assertEqual(original.count(token),new.count(token),token)


if __name__=='__main__':unittest.main()
