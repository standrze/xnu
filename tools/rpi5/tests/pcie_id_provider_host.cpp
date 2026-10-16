/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual lifecycle, RP1 and released-window implementations, RAM-backed;
 * explicit IOService/CPU/thread/controller/PM/IRQ/firmware doubles. */
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include "iokit/Kernel/BCM2712RP1ConfigPolicy.h"
extern "C" {
#include "loader/rpi5/rp1_config_snapshot.h"
#include "loader/rpi5/pcie_released_windows.h"
}
#define RPI5_PCIE_ID_TRIAL 1
#define RPI5_RP1_CONFIG_DIAGNOSTIC 1
#define RPI5_PCIE_FW_TRANSPORT 1
static unsigned cpus=1;
static unsigned ml_get_cpu_count(){return cpus;}
struct IOService {bool opened=true;bool isOpen(const void *)const{return opened;}};
struct bcm2712_controller_admission {int (*check)(IOService *,unsigned);};
struct bcm2712_controller_observation {uint32_t model;};
struct bcm2712_rp1_observation {
    bcm2712_controller_observation controller;
    struct rpi5_rp1_config_snapshot endpoint;
};
class BCM2712PCIePHYTransport;
static BCM2712PCIePHYTransport *phyOwner;
class BCM2712PCIePHYTransport {
public:
    IOService provider;IOService *ownerProvider=&provider;
    void *maps[3]={this,this,this};bool providerOpened=true,owner=true;
    bool checkingLifecycle=false,claimAttempted=false,irqClaimed=false,fwClaimed=false;
    bool trialMode=false,trialPreclaim=false,rp1Locked=false,rp1Attempted=false;
    rpi5_pcie_released_windows trialWindows={};rpi5_pcie_config rp1Config={};
    rpi5_pcie_fdt binding={};rpi5_pcie_link link={};rpi5_pcie_windows windows={};rpi5_pcie_rc rc={};
    rpi5_pcie_ubus ubus={};rpi5_pcie_serdes serdes={};
    rpi5_pcie_reset reset={};rpi5_pcie_rescal rescal={};
    uintptr_t registers[3]={};uint32_t memory[0x9310/4]={},resetMemory[16]={};
    unsigned phase=BCM2712_PHY_PREPARED,lifecyclePhase=BCM2712_CONTROLLER_PRECLAIM;
    unsigned checks=0,failAt=0,controllerCalls=0;
    unsigned getPhase()const{return phase;}
    void setPhase(unsigned p){phase=p;}
    bool onOwnerThread()const{return owner;}
    int fail(){phase=BCM2712_PHY_FAILED;return -1;}
    bool guard()
    {
        checks++;
        if(!owner || checkingLifecycle || checks==failAt || phase==BCM2712_PHY_FAILED)return fail(),false;
        checkingLifecycle=true;int result=trialAdmission(ownerProvider,lifecyclePhase);checkingLifecycle=false;
        return result?(fail(),false):true;
    }
    int admission(unsigned state)
    {
        lifecyclePhase=state;checkingLifecycle=true;
        int result=trialAdmission(ownerProvider,state);checkingLifecycle=false;return result;
    }
    static int order(void *p){auto*s=static_cast<BCM2712PCIePHYTransport*>(p);return s->guard()&&s->guard()?0:-1;}
    static int read32(void *,uint32_t,uint32_t *){return -1;}
    static int write32(void *,uint32_t,uint32_t){return -1;}
    static int read16(void *,uint32_t,uint16_t *){return -1;}
    static int write16(void *,uint32_t,uint16_t){return -1;}
    bool runController(const bcm2712_controller_admission *a,bcm2712_controller_observation *out)
    {
        controllerCalls++;
        assert(a&&a->check==trialAdmission);
        if(admission(BCM2712_CONTROLLER_PRECLAIM))return fail(),false;
        claimAttempted=irqClaimed=fwClaimed=true;
        phase=BCM2712_PHY_RESETTING;lifecyclePhase=BCM2712_CONTROLLER_INITIALIZING;
        resetMemory[0x20/4]=0x1000;
        if(!guard())return false; /* Real provider permits reset44 assertion. */
        resetMemory[0x20/4]=0;
        lifecyclePhase=BCM2712_CONTROLLER_HELD_RESET;phase=BCM2712_PHY_RC_CONFIGURING;
        if(!guard()||!trialDisableMSI())return false;
        lifecyclePhase=BCM2712_CONTROLLER_RELEASED;phase=BCM2712_PHY_LINK_TRAINING;
        if(!guard())return false; /* PERST still asserted at transition. */
        memory[0x4064/4]=4;memory[0x4068/4]=0xb0;
        if(!guard())return false;
        out->model=123;phase=BCM2712_PHY_COMPLETE;return true;
    }
    static int trialOwner(void *);
    static int trialRead(void *,uint32_t,uint32_t *);
    static int trialOrder(void *);
    static int trialAdmission(IOService *,unsigned);
    bool trialDisableMSI();
    bool runBoundedRP1Trial(bcm2712_rp1_observation *);
    static int rp1Acquire(void *);
    static void rp1Release(void *);
    static int rp1Lifecycle(void *);
    static int rp1DenyWrite(void *,const rpi5_pcie_config_request *);
    static int rp1Read(void *,uint32_t,uint32_t,uint32_t *);
    static int rp1Write(void *,uint32_t,uint32_t,uint32_t);
    bool runControllerAndObserveRP1(const bcm2712_controller_admission *,bcm2712_rp1_observation *);
    void prepare()
    {
        cpus=1;phyOwner=this;
        registers[BCM2712_PHY_BRIDGE]=reinterpret_cast<uintptr_t>(memory);
        registers[BCM2712_PHY_RESET]=reinterpret_cast<uintptr_t>(resetMemory);
        binding.bridge_regs.start=0x1000120000;binding.bridge_regs.end=0x1000129310;
        memory[0x4068/4]=0x80;memory[0x8000/4]=0x00011de4;memory[0x8004/4]=0x10;
        memory[0x4044/4]=0x12345001;
        for(unsigned i=2;i<4;i++)memory[(0x4070+4*i)/4]=0x10; // base > limit
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
    void ready(unsigned state)
    {
        prepare();trialMode=true;trialPreclaim=claimAttempted=irqClaimed=fwClaimed=true;
        lifecyclePhase=state;phase=BCM2712_PHY_RC_CONFIGURING;memory[0x4044/4]&=~1u;
    }
};
#include "iokit/Kernel/BCM2712RP1ConfigTransport.inc"
#include "actual-id-provider.inc"
int main()
{
    unsigned count=0;
    {
        BCM2712PCIePHYTransport s;s.prepare();bcm2712_rp1_observation out={};
        assert(s.runBoundedRP1Trial(&out));count=s.checks;
        assert(out.controller.model==123&&out.endpoint.header[0]==0x00011de4);
        assert(s.phase==BCM2712_PHY_COMPLETE&&!s.rp1Locked&&s.controllerCalls==1);
        assert(s.memory[0x4044/4]==0x12345000&&s.memory[0x9000/4]==0x100000);
        assert(s.trialWindows.checks>700&&s.trialWindows.reads==90);
        assert(!s.runBoundedRP1Trial(&out)&&s.checks==count);
    }
    for(unsigned fault=1;fault<=count;fault++) {
        BCM2712PCIePHYTransport s;s.prepare();s.failAt=fault;
        bcm2712_rp1_observation out;std::memset(&out,0xa5,sizeof out);auto before=out;
        assert(!s.runBoundedRP1Trial(&out)&&s.phase==BCM2712_PHY_FAILED&&s.checks==fault);
        assert(!s.rp1Locked&&!std::memcmp(&before,&out,sizeof out));
        assert(!s.runBoundedRP1Trial(&out)&&s.checks==fault);
    }
    for(unsigned which=0;which<7;which++) {
        BCM2712PCIePHYTransport s;s.prepare();s.trialMode=true;
        if(which==0)s.resetMemory[8]=0x800;
        if(which==1)s.resetMemory[8]=0x1000;
        if(which==2)s.memory[0x4068/4]=0;
        if(which==3)s.memory[0x4068/4]=0xb0;
        if(which==4)s.memory[0x4064/4]=4;
        if(which==5)s.memory[0x4304/4]=0x08000000;
        if(which==6)s.memory[0x4064/4]=1;
        assert(s.admission(BCM2712_CONTROLLER_PRECLAIM));
    }
    {
        BCM2712PCIePHYTransport s;s.prepare();s.trialMode=true;
        assert(!s.admission(BCM2712_CONTROLLER_PRECLAIM));
        assert(s.admission(BCM2712_CONTROLLER_PRECLAIM)); // no cached repeat authority
        s.irqClaimed=s.fwClaimed=true;s.resetMemory[8]=0x1000;
        std::memset(s.memory,0xff,sizeof s.memory);
        assert(!s.admission(BCM2712_CONTROLLER_INITIALIZING)); // No bridge MMIO during reset44.
        s.resetMemory[8]|=0x800;assert(s.admission(BCM2712_CONTROLLER_INITIALIZING));
    }
    for(unsigned state: {BCM2712_CONTROLLER_HELD_RESET,BCM2712_CONTROLLER_RELEASED}) {
        for(unsigned i=0;i<7;i++) {
            BCM2712PCIePHYTransport s;s.ready(state);s.memory[(0x40d4+8*i)/4]=1;
            assert(s.admission(state));
        }
        for(unsigned i=2;i<4;i++) {
            BCM2712PCIePHYTransport s;s.ready(state);s.memory[(0x4070+4*i)/4]=0;
            assert(s.admission(state));
        }
    }
    for(unsigned which=0;which<9;which++) {
        BCM2712PCIePHYTransport s;s.ready(BCM2712_CONTROLLER_RELEASED);
        if(which<3)s.memory[(0x402c+8*which)/4]=1;
        if(which>=3&&which<6)s.windows.plan.inbound[which-3].bar_lo=1;
        if(which==6)s.memory[0x4044/4]|=1;
        if(which==7)s.memory[0x4304/4]=8;
        if(which==8)s.windows.state=RPI5_PCIE_WINDOWS_QUARANTINED;
        assert(s.admission(BCM2712_CONTROLLER_RELEASED));
    }
    for(unsigned which=0;which<8;which++) {
        BCM2712PCIePHYTransport s;s.ready(BCM2712_CONTROLLER_RELEASED);
        if(which==0)s.owner=false;
        if(which==1)cpus=2;
        if(which==2)s.provider.opened=false;
        if(which==3)s.providerOpened=false;
        if(which==4)s.maps[0]=nullptr;
        if(which==5)s.maps[1]=nullptr;
        if(which==6)s.maps[2]=nullptr;
        if(which==7)phyOwner=nullptr;
        assert(s.admission(BCM2712_CONTROLLER_RELEASED));
    }
    {
        BCM2712PCIePHYTransport s;s.prepare();bcm2712_rp1_observation out={};cpus=2;
        assert(!s.runBoundedRP1Trial(&out)&&!s.trialMode&&!s.controllerCalls&&!s.checks);cpus=1;
        s.owner=false;assert(!s.runBoundedRP1Trial(&out)&&!s.controllerCalls);
    }
    {
        BCM2712PCIePHYTransport s;s.ready(BCM2712_CONTROLLER_HELD_RESET);s.memory[0x4044/4]|=1;
        s.failAt=3;assert(!s.trialDisableMSI());
        assert(s.memory[0x4044/4]==0x12345000); // failure does not fabricate a rollback
    }
    {
        BCM2712PCIePHYTransport s;s.ready(BCM2712_CONTROLLER_RELEASED);s.checkingLifecycle=true;
        uint32_t out=42;assert(s.trialRead(&s,0x8000,&out)&&out==42);
        assert(s.trialRead(&s,0x4069,&out)&&out==42);
        s.memory[0x4068/4]=UINT32_MAX;assert(s.trialRead(&s,0x4068,&out)&&out==42);
    }
    printf("PCIE_ID_PROVIDER_PASS ACTUAL_METHODS=13 GUARD_FAILURES=%u NO_HARDWARE=1\n",count);
}
