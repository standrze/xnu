# SPDX-License-Identifier: BSD-2-Clause
"""Actual private RC body: fixed root routing, fail-stop, no endpoint changes."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import re
from tools.rpi5 import pcie_root_route_profile as p
ROOT=p.ROOT
TESTS=Path(__file__).resolve().parent


class RootRouteTests(unittest.TestCase):
    def native(self,folder,source,cores=()):
        src=folder/'host.c';src.write_text(source);exe=folder/'host'
        r=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
            '-fsanitize=address,undefined','-I',str(folder),'-I',str(ROOT/'loader/rpi5'),
            '-I',str(ROOT/'iokit/Kernel'),str(src),*map(str,cores),'-o',str(exe)],
            text=True,capture_output=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        r=subprocess.run([exe],text=True,capture_output=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        return r.stdout

    def test_actual_rc_body_full_fault_matrix_and_upper_byte_preservation(self):
        source=(TESTS/'pcie_rc_host.c').read_text().split('static void rc_tests(void)')[0]
        # Reuse actual RC/window fixture, with only the new three root offsets.
        source=source.replace('#include "pcie_link.h"','#include "pcie_link.h"\n#include "pcie_root_route.h"')
        source=p.once(source,'    assert(window_reg(offset) || offset == 0x4068',
            '    assert(offset == 0 || offset == 0x0c || offset == 0x18 || window_reg(offset) || offset == 0x4068')
        source=p.once(source,'    assert(window_reg(offset) || offset == 0x4008',
            '    assert(offset == 0x18 || window_reg(offset) || offset == 0x4008')
        source=p.once(source,'    f->clock = 1000000;',
            '    f->regs[0] = 0x271214e4; f->regs[0x0c/4] = 0x00010000;\n'
            '    f->regs[0x18/4] = 0xa5000000;\n    f->clock = 1000000;')
        source+='''
int main(void) {
    /* Keep old helper callbacks referenced without executing unrelated tests. */
    (void)check_link;(void)now_us;(void)delay_us;(void)rejected;
    struct fixture f; struct rpi5_pcie_rc_observation out,before;
    struct rpi5_pcie_root_route_trace t;
    prepare(&f); assert(!rpi5_pcie_rc_configure_root_route(&f.rc,&out,&t));
    assert(f.calls==156&&out.completed_callbacks==44&&out.window_callbacks==112);
    assert(t.step==7&&t.reads==5&&t.writes==1&&t.id==0x271214e4&&t.header==0x10000);
    assert(t.before==0xa5000000&&t.wanted==0xa5010100&&t.actual==t.wanted);
    assert(f.regs[0x18/4]==t.wanted&&!(f.regs[0x4064/4]&4));
    struct event events[400];memcpy(events,f.events,sizeof events);unsigned count=f.calls;
    unsigned root_write=0,root_before=0,root_immediate=0,root_final=0,root_reads=0;
    for(unsigned i=0;i<count;i++) {
        if(events[i].offset!=0x18)continue;
        if(events[i].kind==WRITE32) { assert(!root_write);root_write=i+1; }
        if(events[i].kind==READ32) {
            root_reads++;if(root_reads==1)root_before=i+1;
            if(root_reads==2)root_immediate=i+1;
            if(root_reads==3)root_final=i+1;
        }
    }
    assert(root_before<root_write&&root_immediate==root_write+2&&root_final>root_immediate);
    assert(rpi5_pcie_rc_configure_root_route(&f.rc,&out,&t)==RPI5_PCIE_RC_STATE&&f.calls==count);
    for(unsigned at=1;at<=count;at++) {
        prepare(&f);f.fail_at=at;memset(&out,0xa5,sizeof out);before=out;
        assert(rpi5_pcie_rc_configure_root_route(&f.rc,&out,&t));
        assert(!memcmp(&out,&before,sizeof out)&&f.calls==at);
        assert(!memcmp(events,f.events,at*sizeof events[0]));
        assert(f.rc.state==RPI5_PCIE_RC_QUARANTINED&&f.windows.state==RPI5_PCIE_WINDOWS_QUARANTINED);
        assert(t.writes==(at>=root_write));
        assert(f.regs[0x18/4]==(at>=root_write?0xa5010100:0xa5000000));
        unsigned stopped=f.calls;
        assert(rpi5_pcie_rc_configure(&f.rc,&out)==RPI5_PCIE_RC_STATE&&f.calls==stopped);
        if(events[at-1].kind==READ32||events[at-1].kind==READ16) {
            prepare(&f);f.bad_at=at;memset(&out,0xa5,sizeof out);before=out;
            assert(rpi5_pcie_rc_configure_root_route(&f.rc,&out,&t));
            assert(f.calls==at&&!memcmp(&out,&before,sizeof out));
        }
        if(events[at-1].kind==WRITE32||events[at-1].kind==WRITE16) {
            prepare(&f);f.drop_at=at;
            assert(rpi5_pcie_rc_configure_root_route(&f.rc,&out,&t));assert(f.calls==at+2);
        }
    }
    for(unsigned high=0;high<256;high++) {
        prepare(&f);f.regs[0x18/4]=(high<<24)|0x123456;
        assert(!rpi5_pcie_rc_configure_root_route(&f.rc,&out,&t));
        assert(t.before==((high<<24)|0x123456)&&t.actual==((high<<24)|0x010100));
    }
    for(unsigned bit=0;bit<32;bit++) {
        prepare(&f);f.regs[0]^=1u<<bit;
        assert(rpi5_pcie_rc_configure_root_route(&f.rc,&out,&t)==RPI5_PCIE_RC_PROFILE&&!t.writes&&f.calls==5);
    }
    for(unsigned h=0;h<256;h++)if(h!=1) {
        prepare(&f);f.regs[0x0c/4]=h<<16;
        assert(rpi5_pcie_rc_configure_root_route(&f.rc,&out,&t)==RPI5_PCIE_RC_PROFILE&&!t.writes);
    }
    for(unsigned at=root_immediate;at<=root_final;at+=root_final-root_immediate) {
        prepare(&f);f.corrupt_at=at;
        assert(rpi5_pcie_rc_configure_root_route(&f.rc,&out,&t)==RPI5_PCIE_RC_READBACK);
        assert(f.calls==at&&t.writes==1&&t.actual!=t.wanted);
    }
    prepare(&f);f.windows.io.read32=0;
    assert(rpi5_pcie_rc_configure_root_route(&f.rc,&out,&t)==RPI5_PCIE_RC_DEPENDENCY&&!f.calls);
    assert(rpi5_pcie_rc_configure_root_route(0,&out,&t)==RPI5_PCIE_RC_ARGUMENT);
    puts("ROOT_ROUTE_PASS FAILURES=156 HIGH_BYTES=256 WRONG_IDS=32 WRONG_HEADERS=255 NO_ENDPOINT_WRITES=1");
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);(folder/'pcie_root_route.h').write_text(p.HEADER)
            core=folder/'pcie_rc.c';core.write_text(p.core((ROOT/'loader/rpi5/pcie_rc.c').read_text()))
            self.assertIn('ROOT_ROUTE_PASS FAILURES=156',self.native(folder,source,[core,ROOT/'loader/rpi5/pcie_windows.c']))

    def test_exact_new_policy_permissions_and_value_guard(self):
        source='''
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#include "BCM2712PCIeControllerPolicy.h"
int main(void) {
    for(unsigned phase=0;phase<32;phase++)for(unsigned bank=0;bank<4;bank++)
    for(unsigned offset=0;offset<0x100;offset+=4)for(unsigned write=0;write<2;write++) {
        int actual=bcm2712_controller_access_allowed(phase,bank,offset,4,write);
        if(offset==0||offset==0x0c||offset==0x18) {
            int want=phase==BCM2712_PHY_RC_CONFIGURING&&bank==BCM2712_PHY_BRIDGE&&(!write||offset==0x18);
            want|=phase==BCM2712_PHY_CLOCK_FINISHING&&bank==BCM2712_PHY_BRIDGE&&offset==0x18&&!write;
            /* Earlier reset/rescal phases retain their original bank-specific permissions. */
            if(phase>=BCM2712_PHY_RC_CONFIGURING)assert(actual==want);
        }
        int allowed=bcm2712_root_route_write_allowed(phase,bank,offset,0xa5010100,4,1,0xa5123456);
        assert(allowed==(phase==BCM2712_PHY_RC_CONFIGURING&&bank==BCM2712_PHY_BRIDGE&&offset==0x18));
    }
    for(unsigned bit=0;bit<32;bit++)assert(!bcm2712_root_route_write_allowed(
        BCM2712_PHY_RC_CONFIGURING,BCM2712_PHY_BRIDGE,0x18,0xa5010100^(1u<<bit),4,1,0xa5123456));
    for(unsigned step=0;step<16;step++)for(unsigned writes=0;writes<4;writes++)
        assert(bcm2712_root_route_write_allowed(BCM2712_PHY_RC_CONFIGURING,BCM2712_PHY_BRIDGE,
            0x18,0xa5010100,step,writes,0xa5123456)==(step==4&&writes==1));
    puts("ROOT_ROUTE_POLICY_PASS");return 0;
}
'''
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);(folder/'BCM2712PCIeControllerPolicy.h').write_text(p.policy((ROOT/'iokit/Kernel/BCM2712PCIeControllerPolicy.h').read_text()))
            self.assertEqual(self.native(folder,source),'ROOT_ROUTE_POLICY_PASS\n')

    def test_emitted_boundary_preserves_link_config_guard_and_deadline_sources(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'overlay';p.emit(folder)
            for name in ('pcie_link.c','rp1_config_snapshot_checked.c','BCM2712RP1ConfigTransport.inc',
                'BCM2712PCIeFWTransport.inc','BCM2712PCIeIDTrialProgress.cpp'):
                if (p.FROZEN/name).exists():self.assertEqual((folder/name).read_bytes(),(p.FROZEN/name).read_bytes())
            self.assertIn('(diagRootRC=rpi5_pcie_rc_configure_root_route(', (folder/'BCM2712PCIeControllerRun.inc').read_text())
            self.assertIn('bcm2712_root_route_write_allowed(', (folder/'BCM2712PCIePHYTransport.cpp').read_text())

    def test_actual_production_write_body_rejects_wrong_values_before_store(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);overlay=folder/'overlay';p.emit(overlay)
            text=(overlay/'BCM2712PCIePHYTransport.cpp').read_text()
            body=re.search(r'int BCM2712PCIePHYTransport::write32\(.*?\n}\n',text,re.S)[0]
            body=body.replace('__asm__ volatile("dmb osh" ::: "memory");','__asm__ volatile("" ::: "memory");')
            body=body.replace('__asm__ volatile("dsb sy" ::: "memory");','__asm__ volatile("" ::: "memory");')
            source='''
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#include "BCM2712PCIeControllerPolicy.h"
#include "pcie_root_route.h"
class BCM2712PCIePHYTransport {
public:
    unsigned phase=BCM2712_PHY_RC_CONFIGURING,checks=0,failAt=0;
    unsigned diagIOBank=0,diagIOOffset=0,diagIODirection=0,diagIOStage=0,diagIOValue=0;
    bool owner=true,controllerMode=true;unsigned lifecyclePhase=BCM2712_CONTROLLER_HELD_RESET;
    uint32_t memory[0x4400/4]={};uintptr_t registers[3]={uintptr_t(memory),0,0};
    rpi5_pcie_root_route_trace diagRoot={4,3,1,0x271214e4,0x10000,0xa5000000,0xa5010100,0,0};
    bool onOwnerThread(){return owner;}unsigned getPhase(){return phase;}
    int fail(){phase=BCM2712_PHY_FAILED;return -1;}
    bool guard(){checks++;if(checks==failAt){fail();return false;}return true;}
    int write32(unsigned,uint32_t,uint32_t);
};
'''+body+'''
int main() {
    for(unsigned position=0;position<=2;position++) {
        BCM2712PCIePHYTransport t;t.memory[6]=0xa5000000;t.failAt=position;
        int rc=t.write32(BCM2712_PHY_BRIDGE,0x18,0xa5010100);
        assert((rc!=0)==(position!=0)&&t.checks==(position==1?1:2));
        assert(t.memory[6]==(position==1?0xa5000000:0xa5010100));
    }
    for(unsigned bit=0;bit<32;bit++) {
        BCM2712PCIePHYTransport t;t.memory[6]=0xa5000000;
        assert(t.write32(BCM2712_PHY_BRIDGE,0x18,0xa5010100^(1u<<bit)));
        assert(!t.checks&&t.memory[6]==0xa5000000);
    }
    for(unsigned step=0;step<8;step++)if(step!=4) {
        BCM2712PCIePHYTransport t;t.memory[6]=0xa5000000;t.diagRoot.step=step;
        assert(t.write32(BCM2712_PHY_BRIDGE,0x18,0xa5010100)&&!t.checks&&t.memory[6]==0xa5000000);
    }
    puts("ROOT_ROUTE_ACTUAL_WRITE_PASS");return 0;
}
'''
            src=folder/'host.cpp';src.write_text(source);exe=folder/'host'
            r=subprocess.run(['xcrun','clang++','-std=c++17','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(overlay),'-I',str(ROOT/'loader/rpi5'),
                '-I',str(ROOT/'iokit/Kernel'),str(src),'-o',str(exe)],text=True,capture_output=True,timeout=60)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run([exe],text=True,capture_output=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(r.stdout,'ROOT_ROUTE_ACTUAL_WRITE_PASS\n')


if __name__=='__main__':unittest.main()
