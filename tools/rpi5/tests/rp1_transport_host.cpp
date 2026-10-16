/* SPDX-License-Identifier: BSD-2-Clause */
/* Production transport methods and C cores with explicit controller/owner/
 * lifecycle doubles and RAM backing, not physical IOKit or MMIO evidence. */
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "iokit/Kernel/BCM2712RP1ConfigPolicy.h"
extern "C" {
#include "loader/rpi5/rp1_config_snapshot.h"
}
#define RPI5_RP1_CONFIG_DIAGNOSTIC 1
#define RPI5_PCIE_FW_TRANSPORT 1
struct bcm2712_controller_admission { int admitted; };
struct bcm2712_controller_observation { uint32_t model; };
struct bcm2712_rp1_observation {
    bcm2712_controller_observation controller;
    struct rpi5_rp1_config_snapshot endpoint;
};
class BCM2712PCIePHYTransport {
public:
    rpi5_pcie_config rp1Config={}; bool rp1Locked=false,rp1Attempted=false;
    rpi5_pcie_link link={};rpi5_pcie_windows windows={};rpi5_pcie_rc rc={};
    rpi5_pcie_ubus ubus={};rpi5_pcie_serdes serdes={};
    rpi5_pcie_reset reset={};rpi5_pcie_rescal rescal={};
    uintptr_t registers[3]={};uint32_t memory[0x9310/4]={};
    unsigned phase=BCM2712_PHY_PREPARED,checks=0,failAt=0,controllerCalls=0;
    bool owner=true,denyController=false;
    unsigned getPhase() const {return phase;}
    void setPhase(unsigned p){phase=p;}
    bool onOwnerThread()const{return owner;}
    int fail(){phase=BCM2712_PHY_FAILED;return -1;}
    bool guard(){assert(owner);checks++;return checks==failAt?(fail(),false):phase==BCM2712_PHY_RP1_INSPECTING;}
    static int order(void *p){auto*s=static_cast<BCM2712PCIePHYTransport*>(p);return s->guard()&&s->guard()?0:-1;}
    static int read32(void *,uint32_t,uint32_t *){return -1;}
    static int write32(void *,uint32_t,uint32_t){return -1;}
    static int read16(void *,uint32_t,uint16_t *){return -1;}
    static int write16(void *,uint32_t,uint16_t){return -1;}
    bool runController(const bcm2712_controller_admission *a,bcm2712_controller_observation *out)
    {
        controllerCalls++;
        if(!a||!a->admitted||denyController)return false;
        out->model=123;phase=BCM2712_PHY_COMPLETE;return true;
    }
    static int rp1Acquire(void *);
    static void rp1Release(void *);
    static int rp1Lifecycle(void *);
    static int rp1DenyWrite(void *,const rpi5_pcie_config_request *);
    static int rp1Read(void *,uint32_t,uint32_t,uint32_t *);
    static int rp1Write(void *,uint32_t,uint32_t,uint32_t);
    bool runControllerAndObserveRP1(const bcm2712_controller_admission *,bcm2712_rp1_observation *);
    void prepare()
    {
        registers[BCM2712_PHY_BRIDGE]=reinterpret_cast<uintptr_t>(memory);
        memory[0x4068/4]=0xb0;memory[0x8000/4]=0x00011de4;memory[0x8004/4]=0x10;
        windows.state=RPI5_PCIE_WINDOWS_COMPLETE;windows.io.context=this;
        windows.io.physical_base=0x1000120000;windows.io.mapped_bytes=0x9310;
        windows.io.read32=read32;windows.io.write32=write32;windows.io.order=order;
        rc.state=RPI5_PCIE_RC_COMPLETE;rc.windows=&windows;rc.bridge_reset=&reset;rc.calibration=&rescal;
        rc.io.read16=read16;rc.io.write16=write16;
        ubus.state=RPI5_PCIE_UBUS_COMPLETE;ubus.serdes=&serdes;
        serdes.state=RPI5_PCIE_SERDES_COMPLETE;serdes.mdio.state=RPI5_PCIE_MDIO_READY;
        serdes.bridge_reset=&reset;serdes.calibration=&rescal;serdes.mdio.io.context=this;
        serdes.mdio.io.physical_base=windows.io.physical_base;serdes.mdio.io.mapped_bytes=0x9310;
        serdes.mdio.io.read32=read32;serdes.mdio.io.write32=write32;serdes.mdio.io.order=order;
        reset.state=RPI5_PCIE_RESET_COMPLETE;rescal.state=RPI5_PCIE_RESCAL_COMPLETE;
        link.state=RPI5_PCIE_LINK_COMPLETE;link.windows=&windows;link.io.rc=&rc;
        link.io.read16=read16;link.io.write16=write16;link.ubus=&ubus;
    }
};
#include "iokit/Kernel/BCM2712RP1ConfigTransport.inc"
int main()
{
    bcm2712_controller_admission admission={1};unsigned count;
    {
        BCM2712PCIePHYTransport owner;owner.prepare();bcm2712_rp1_observation out={};
        assert(owner.runControllerAndObserveRP1(&admission,&out));
        assert(owner.controllerCalls==1&&out.controller.model==123&&out.endpoint.header[0]==0x00011de4);
        assert(owner.phase==BCM2712_PHY_COMPLETE&&!owner.rp1Locked);count=owner.checks;
        assert(!owner.runControllerAndObserveRP1(&admission,&out)&&owner.checks==count);
        assert(owner.memory[0x9000/4]==0x100000 && owner.memory[0x8004/4]==0x10);
    }
    for(unsigned failure=1;failure<=count;failure++) {
        BCM2712PCIePHYTransport owner;owner.prepare();owner.failAt=failure;
        bcm2712_rp1_observation out;std::memset(&out,0xa5,sizeof out);auto saved=out;
        assert(!owner.runControllerAndObserveRP1(&admission,&out));
        assert(owner.checks==failure&&owner.phase==BCM2712_PHY_FAILED&&!owner.rp1Locked);
        assert(!std::memcmp(&saved,&out,sizeof out)&&owner.rp1Config.state==RPI5_PCIE_CONFIG_QUARANTINED);
        assert(!owner.runControllerAndObserveRP1(&admission,&out)&&owner.checks==failure);
    }
    {
        BCM2712PCIePHYTransport owner;owner.prepare();bcm2712_rp1_observation out={};
        owner.owner=false;assert(!owner.runControllerAndObserveRP1(&admission,&out));
        assert(!owner.rp1Attempted&&!owner.controllerCalls&&!owner.checks);
        owner.owner=true;owner.denyController=true;
        assert(!owner.runControllerAndObserveRP1(&admission,&out)&&!owner.checks);
    }
    {
        BCM2712PCIePHYTransport owner;owner.prepare();owner.phase=BCM2712_PHY_RP1_INSPECTING;
        assert(!owner.rp1Acquire(&owner));assert(owner.rp1Acquire(&owner));
        assert(owner.rp1DenyWrite(&owner,nullptr));
        uint32_t before=owner.memory[0x8004/4];
        assert(owner.rp1Write(&owner,0x8004,4,7));
        assert(owner.memory[0x8004/4]==before&&!owner.checks);owner.rp1Release(&owner);
    }
    printf("RP1_TRANSPORT_PASS ACTUAL_METHODS=7 GUARD_FAILURES=%u NO_HARDWARE=1\n",count);
}
