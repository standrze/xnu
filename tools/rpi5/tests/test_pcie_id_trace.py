# SPDX-License-Identifier: BSD-2-Clause
import subprocess
import tempfile
from pathlib import Path
import unittest
from tools.rpi5 import build_pcie_id_trace_kernel as b


class PCIeIDTraceTests(unittest.TestCase):
    def test_actual_guard_short_circuit_and_access_telemetry(self):
        frozen=b.BASE/'overlay'
        guard=b.trace_guard((frozen/'BCM2712PCIeFWTransport.inc').read_text())
        guard=guard[guard.index('bool BCM2712PCIePHYTransport::guard()'):]
        access=b.trace_access((frozen/'BCM2712PCIePHYTransport.cpp').read_text())
        access=access[access.index('int BCM2712PCIePHYTransport::read32('):access.index('int BCM2712PCIePHYTransport::resetStatus(')]
        host=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include "iokit/Kernel/BCM2712RP1ConfigPolicy.h"
struct IOService{bool isOpen(const void*){return true;}};
struct rpi5_pcie_irq_observation{};struct rpi5_fw_observation{};
static unsigned calls=0,fault=0;
static bool check(){calls++;return calls!=fault;}
static bool pe_rpi5_watchdog_check_pcie(void*){return check();}
static bool pe_rpi5_pcie_irq_check(void*,rpi5_pcie_irq_observation*){return check();}
static bool pe_rpi5_pcie_fw_check(void*,rpi5_fw_observation*){return check();}
static int admission(IOService*,unsigned){return check()?0:-1;}
class BCM2712PCIePHYTransport;
static BCM2712PCIePHYTransport *phyOwner;
class BCM2712PCIePHYTransport{
public:
 unsigned phase=BCM2712_PHY_UBUS_CONFIGURING,lifecyclePhase=BCM2712_CONTROLLER_INITIALIZING;
 bool owner=true,claimAttempted=true,providerOpened=true,controllerMode=true;
 bool checkingLifecycle=false,claimingIRQ=false,claimingFW=false,irqClaimed=true,fwClaimed=true;
 IOService provider,*ownerProvider=&provider;
 struct {int(*check)(IOService*,unsigned);}controllerAdmission={admission};
 unsigned diagGuard=0,diagIOBank=0,diagIOOffset=0,diagIODirection=0,diagIOStage=0,diagIOValue=0;
 uint32_t memory[0x9310/4]={};uintptr_t registers[3]={};
 BCM2712PCIePHYTransport(){phyOwner=this;registers[0]=(uintptr_t)memory;calls=fault=0;}
 bool onOwnerThread(){return owner;}unsigned getPhase(){return phase;}
 int fail(){phase=BCM2712_PHY_FAILED;return -1;}
 bool guard();int read32(unsigned,uint32_t,uint32_t*);int write32(unsigned,uint32_t,uint32_t);
};
'''
        main=r'''
int main(){
 const unsigned codes[]={0,1,3,4,5,7,8,9};
 {BCM2712PCIePHYTransport s;assert(s.guard()&&!s.diagGuard&&calls==7);}
 for(unsigned at=1;at<=7;at++){
  BCM2712PCIePHYTransport s;fault=at;
  assert(!s.guard()&&s.diagGuard==codes[at]&&calls==at&&s.phase==BCM2712_PHY_FAILED);
  assert(!s.guard()&&s.diagGuard==codes[at]&&calls==at);
 }
 {BCM2712PCIePHYTransport s;s.checkingLifecycle=true;
  assert(!s.guard()&&s.diagGuard==2&&calls==1);}
 {BCM2712PCIePHYTransport s;s.owner=false;
  assert(!s.guard()&&!s.diagGuard&&!calls&&s.phase==BCM2712_PHY_UBUS_CONFIGURING);}
 for(unsigned writing=0;writing<2;writing++)for(unsigned at=1;at<=14;at++){
  BCM2712PCIePHYTransport s;fault=at;uint32_t value=0xa5a5a5a5;s.memory[0x40a4/4]=0x12345678;
  int rc=writing?s.write32(0,0x40a4,0x87654321):s.read32(0,0x40a4,&value);
  assert(rc&&calls==at&&s.diagGuard==codes[at<=7?at:at-7]);
  assert(s.diagIOBank==0&&s.diagIOOffset==0x40a4&&s.diagIODirection==writing);
  assert(s.diagIOStage==(at<=7?1:3));
  assert(value==0xa5a5a5a5);
  assert(s.memory[0x40a4/4]==(writing&&at>7?0x87654321:0x12345678));
  assert(s.diagIOValue==(writing?0x87654321:(at<=7?0:0x12345678)));
 }
 for(unsigned writing=0;writing<2;writing++){
  BCM2712PCIePHYTransport s;uint32_t value=0;s.memory[0x40a4/4]=0x12345678;
  assert(!(writing?s.write32(0,0x40a4,0x87654321):s.read32(0,0x40a4,&value)));
  assert(s.diagIOStage==4&&calls==14&&!s.diagGuard);
 }
 {BCM2712PCIePHYTransport s;uint32_t value=0;
  assert(s.read32(0,0x4170,&value)&&s.diagIOStage==1&&!calls&&!s.diagGuard);}
 puts("PCIE_TRACE_PASS GUARD_REASONS=7 IO_FAILURE_POSITIONS=28 NO_EXTRA_MMIO=1");
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);source=path/'trace.cpp';program=path/'trace'
            source.write_text(host+guard+access+main)
            r=subprocess.run(['xcrun','clang++','-std=c++17','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(b.ROOT),str(source),'-o',str(program)],
                capture_output=True,text=True,timeout=60)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run([program],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn('IO_FAILURE_POSITIONS=28 NO_EXTRA_MMIO=1',r.stdout)

    def test_all_transforms_keep_device_operations_and_admission_order(self):
        frozen=b.BASE/'overlay'
        original=(frozen/'BCM2712PCIePHYTransport.cpp').read_text()
        changed=b.trace_access(original)
        for expression in ('*reinterpret_cast<volatile uint32_t *>',
                           'bcm2712_controller_access_allowed(',
                           '__asm__ volatile("dmb osh"', '__asm__ volatile("dsb sy"'):
            self.assertEqual(original.count(expression),changed.count(expression))
        source=(frozen/'BCM2712PCIeFWTransport.inc').read_text()
        traced=b.trace_guard(source)
        for name in ('pe_rpi5_watchdog_check_pcie','pe_rpi5_pcie_irq_check','pe_rpi5_pcie_fw_check','controllerAdmission.check(ownerProvider'):
            self.assertEqual(source.count(name),traced.count(name))
        ubus=b.trace_ubus((b.ROOT/'iokit/Kernel/BCM2712PCIeUBUS.inc').read_text())
        self.assertEqual(ubus.count('rpi5_pcie_ubus_init('),1)
        self.assertEqual(ubus.count('rpi5_pcie_ubus_configure('),1)
        self.assertLess(ubus.index('diagUBUSStep=2'),ubus.index('diagUBUSStep=3'))
        self.assertLess(ubus.index('diagUBUSStep=3'),ubus.index('diagUBUSStep=4'))
        body=b.trace_body((frozen/'BCM2712PCIeIDTrialProgress.inc').read_text())
        self.assertEqual(body.count('kprintf('),3)
        self.assertIn('UBUS_RC=%d',body)
        self.assertIn('IO_STAGE=%u VALUE=%08x',body)


if __name__=='__main__':unittest.main()
