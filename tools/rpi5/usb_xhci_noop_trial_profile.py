# SPDX-License-Identifier: BSD-2-Clause
"""One-command RP1 USB0 xHCI composition layered on passed lifecycle evidence."""
from pathlib import Path

from tools.rpi5 import usb_xhci_lifecycle_trial_profile as parent


ROOT = parent.ROOT
BOOTARGS = parent.BOOTARGS
FROZEN = ROOT / "build/rpi5/usb-xhci-lifecycle-candidate-20261014-v2/overlay"


def _replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError("exact USB No-Op trial anchor differs")
    return text.replace(old, new)


def marker(tag):
    return ("RPI5XNU:USB_XHCI_NOOP:ENTRY TAG=" + tag +
        " CPUS=1 POLLING ONE_NOOP NO_PORT NO_IRQ BME_LEASE DMA")


def derive():
    files = {path.name: path.read_bytes() for path in FROZEN.iterdir()
        if path.is_file()}
    for name, relative in {
        "BCM2712USBXHCIMemory.h": "iokit/Kernel/BCM2712USBXHCIMemory.h",
        "BCM2712GEMDMABatch.cpp": "iokit/Kernel/BCM2712USBXHCIMemory.cpp",
        "rpi5_rp1_dma_route.h": "iokit/Kernel/rpi5_rp1_dma_route.h",
        "rp1_usb_xhci_dma_layout.h": "loader/rpi5/rp1_usb_xhci_dma_layout.h",
        "rp1_usb_xhci_noop.h": "loader/rpi5/rp1_usb_xhci_noop.h",
        "rp1_usb_xhci_noop_run.h": "loader/rpi5/rp1_usb_xhci_noop_run.h",
        "rp1_usb_bme.h": "loader/rpi5/rp1_usb_bme.h",
    }.items():
        files[name] = (ROOT / relative).read_bytes()

    header = files["BCM2712PCIePHYTransport.h"].decode()
    header = _replace(header, '#include "BCM2712GEMDMAMemory.h"',
        '#include "BCM2712USBXHCIMemory.h"')
    header = _replace(header, '#include "rp1_usb_xhci_lifecycle.h"',
        '#include "rp1_usb_xhci_lifecycle.h"')
    header = _replace(header, 'extern "C" {\n#include "rp1_bars_plan.h"',
        'extern "C" {\n#include "rp1_usb_xhci_noop_run.h"\n'
        '#include "rp1_usb_bme.h"\n#include "rp1_bars_plan.h"')
    old = '''    struct bcm2712_gem_quiescence {
        uint32_t ncr,imr,rbqp,tbqp,tbqph,rbqph;
    };
    BCM2712GEMDMAMemory *dmaMemory=nullptr;
    unsigned dmaPreparePhase=0; /*0empty,1preparing,2ready,3quarantined*/
    bool dmaRingAttempted=false,dmaRingActive=false,dmaRingRevoked=false;
    unsigned dmaObserveStep=0;
    int dmaObserveError=0;'''
    new = '''    BCM2712USBXHCIMemory *dmaMemory=nullptr;
    unsigned dmaPreparePhase=0; /*0empty,1preparing,2ready,3quarantined*/
    bool dmaRingAttempted=false,dmaRingActive=false,dmaRingRevoked=false;
    struct rpi5_usb_xhci_memory_observation dmaObserved={};
    struct rpi5_xhci_noop_image usbNoopImage={};
    struct rpi5_xhci_noop_run_observation usbNoopObserved={};
    struct rpi5_rp1_usb_bme usbBME={};
    bool usbDMAActive=false,usbQualificationActive=false;
    unsigned usbNoopStep=0;
    int usbNoopError=0;'''
    header = _replace(header, old, new)
    old = '''    struct rpi5_gem_dma_route dmaCandidate={};
    struct rpi5_gem_full_provider_observation dmaFullObserved={};
    struct bcm2712_gem_quiescence dmaBefore={},dmaAfter={};
    int dmaRingSource() const;
    bool readFullProviderQuiescence(struct bcm2712_gem_quiescence *);
    bool observePreparedFullProvider();'''
    new = '''    static int usbNoopRead(void *,uint32_t,uint32_t *);
    static int usbNoopWrite(void *,uint32_t,uint32_t);
    static int usbNoopDelay(void *,uint32_t);
    static int usbNoopGuard(void *);
    static int usbDMAGuard(void *);
    static int usbBMEGuard(void *);
    static int usbBMETransfer(void *,const struct rpi5_pcie_config_request *,uint32_t *);
    bool runUSBNoOp();'''
    header = _replace(header, old, new)
    old = '''    unsigned dmaMappingReason() const { return dmaMemory?dmaMemory->mappingReason():0; }
    unsigned dmaMappingPage() const { return dmaMemory?dmaMemory->mappingPage():0; }
    unsigned dmaMappingAttribute() const { return dmaMemory?dmaMemory->mappingAttribute():0; }
    uint64_t dmaMappingPhysical() const { return dmaMemory?dmaMemory->mappingPhysical():0; }
    uint64_t dmaMappingRetainedReadPAR() const { return dmaMemory?dmaMemory->mappingRetainedReadPAR():0; }
    uint64_t dmaMappingRetainedWritePAR() const { return dmaMemory?dmaMemory->mappingRetainedWritePAR():0; }
    uint64_t dmaMappingStaticReadPAR() const { return dmaMemory?dmaMemory->mappingStaticReadPAR():0; }
    uint64_t dmaMappingStaticWritePAR() const { return dmaMemory?dmaMemory->mappingStaticWritePAR():0; }
    unsigned dmaObservationStep() const { return dmaObserveStep; }
    int dmaObservationError() const { return dmaObserveError; }'''
    new = '''    unsigned usbNoopTrialStep() const { return usbNoopStep; }
    int usbNoopTrialError() const { return usbNoopError; }
    const struct rpi5_usb_xhci_memory_observation &usbMemoryObservation() const { return dmaObserved; }
    const struct rpi5_xhci_noop_image &usbNoopImageObservation() const { return usbNoopImage; }
    const struct rpi5_xhci_noop_run_observation &usbNoopRunObservation() const { return usbNoopObserved; }
    const struct rpi5_rp1_usb_bme &usbBMEObservation() const { return usbBME; }'''
    header = _replace(header, old, new)
    old = '''    const struct rpi5_gem_dma_route &dmaRoute() const { return dmaCandidate; }
    const struct rpi5_gem_full_provider_observation &dmaObserved() const { return dmaFullObserved; }
    const struct bcm2712_gem_quiescence &dmaQuiescenceBefore() const { return dmaBefore; }
    const struct bcm2712_gem_quiescence &dmaQuiescenceAfter() const { return dmaAfter; }'''
    header = _replace(header, old, '')
    files["BCM2712PCIePHYTransport.h"] = header.encode()

    policy = files["BCM2712RP1ConfigPolicy.h"].decode()
    policy = _replace(policy,
        '''    if (width != 4 || (offset & 3) || write > 1) return 0;
    if (write) return offset == 0x9000;
    return offset == 0x4068 || offset == 0x9000 ||
        (offset >= 0x8000 && offset <= 0x803c);''',
        '''    if (write > 1) return 0;
    if (width == 2) return offset == 0x8004;
    if (width != 4 || (offset & 3)) return 0;
    if (write) return offset == 0x9000;
    return offset == 0x4068 || offset == 0x9000 ||
        (offset >= 0x8000 && offset <= 0x803c);''')
    files["BCM2712RP1ConfigPolicy.h"] = policy.encode()

    config = files["BCM2712RP1ConfigTransport.inc"].decode()
    config = _replace(config,
        '''    uint32_t value = *reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset);''',
        '''    uint32_t value = width==2 ?
        *reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset) :
        *reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset);''')
    files["BCM2712RP1ConfigTransport.inc"] = config.encode()

    decode = files["BCM2712RP1DecodeTransport.inc"].decode()
    decode = _replace(decode,
        '''    if(!self)return -1;
    if(!self->decodeActive)return assignmentAuthorize(context,r);
    if(!self->rp1Locked || self->rp1Config.state!=RPI5_PCIE_CONFIG_BUSY ||
        !rpi5_rp1_decode_write_allowed(&self->decodeCycle,r))return -1;
    return self->guard()?0:-1;''',
        '''    if(!self)return -1;
    if(!self->decodeActive)return assignmentAuthorize(context,r);
    if(!self->rp1Locked || self->rp1Config.state!=RPI5_PCIE_CONFIG_BUSY)return -1;
    if(self->usbDMAActive) {
        if(!r || r->bus!=1 || r->device || r->function || r->offset!=4 ||
            r->width!=2 || r->write!=1)return -1;
        const bool enabling=self->usbBME.state==RPI5_RP1_USB_BME_ENABLING &&
            self->usbBME.enabled==(uint16_t)(self->usbBME.original|RPI5_PCI_COMMAND_BUS_MASTER) &&
            r->value==self->usbBME.enabled;
        const bool disabling=self->usbBME.state==RPI5_RP1_USB_BME_DISABLING &&
            r->value==self->usbBME.original;
        return (enabling||disabling) && self->usbBMEGuard(self)==0 ? 0 : -1;
    }
    if(!rpi5_rp1_decode_write_allowed(&self->decodeCycle,r))return -1;
    return self->guard()?0:-1;''')
    decode = _replace(decode,
        '''    if(!self->decodeActive || offset==0x9000)return assignmentWrite(context,offset,width,value);''',
        '''    if(!self->decodeActive || offset==0x9000)return assignmentWrite(context,offset,width,value);
    if(self->usbDMAActive) {
        if(offset!=0x8004 || width!=2)return -1;
        const struct rpi5_pcie_config_request request={1,0,0,4,2,1,value};
        if(decodeAuthorize(context,&request))return -1;
        self->diagIOBank=BCM2712_PHY_BRIDGE;self->diagIOOffset=offset;
        self->diagIODirection=1;self->diagIOStage=2;self->diagIOValue=value;
        __asm__ volatile("dmb osh" ::: "memory");
        *reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=(uint16_t)value;
        __asm__ volatile("dsb sy" ::: "memory");
        self->diagIOStage=3;
        return self->usbBMEGuard(self)==0 ? 0 : -1;
    }''')
    files["BCM2712RP1DecodeTransport.inc"] = decode.encode()

    progress = files["BCM2712PCIeIDTrialProgress.inc"].decode()
    progress = _replace(progress,
        "BEGIN USB_XHCI_LIFECYCLE HALT_RESET_ONLY NO_PORT NO_IRQ NO_BME NO_DMA",
        "BEGIN USB_XHCI_NOOP POLLING ONE_NOOP NO_PORT NO_IRQ BME_LEASE DMA")
    progress = _replace(progress,
        '''    return self && self->trialMode && self->checkingLifecycle && self->onOwnerThread() &&
        ml_get_cpu_count()==1''',
        '''    const bool windowQualification=self && self->usbQualificationActive &&
        self->getPhase()==BCM2712_PHY_RP1_INSPECTING && self->decodeActive &&
        self->decodeCycle.state==RPI5_RP1_DECODE_MAPPED;
    return self && self->trialMode && (self->checkingLifecycle||windowQualification) && self->onOwnerThread() &&
        ml_get_cpu_count()==1''')
    progress = _replace(progress, "BCM2712GEMDMAMemory::Prepared",
        "BCM2712USBXHCIMemory::Prepared")
    progress = _replace(progress,
        '''    if(self->dmaMemory->state()==BCM2712USBXHCIMemory::Prepared)
        return self->dmaMemory->qualify(&self->trialWindows,&self->dmaCandidate)?0:-1;
    auto state=self->dmaMemory->state();
    if(state!=BCM2712GEMDMAMemory::Held)return -1;
    struct rpi5_pcie_released_observation observed;
    return rpi5_pcie_released_windows_check(&self->trialWindows,&observed);''',
        '''    auto state=self->dmaMemory->state();
    if(state!=BCM2712USBXHCIMemory::Prepared &&
        state!=BCM2712USBXHCIMemory::Staged)return -1;
    struct rpi5_pcie_released_observation observed;
    return rpi5_pcie_released_windows_check(&self->trialWindows,&observed);''')
    start = progress.index(
        '    const struct rpi5_reservation_record *record=rpi5_boot_reservation_record();')
    end = progress.index(
        '    const auto *usb=transport?&transport->usbObservation():nullptr;', start)
    rows = '''    const struct rpi5_reservation_record *record=rpi5_boot_reservation_record();
    const auto *memory=transport?&transport->usbMemoryObservation():nullptr;
    const auto *image=transport?&transport->usbNoopImageObservation():nullptr;
    const auto *run=transport?&transport->usbNoopRunObservation():nullptr;
    const auto *bme=transport?&transport->usbBMEObservation():nullptr;
    kprintf("RPI5XNU:USB_XHCI_NOOP:MEMORY PREPARE=%u STATE=%u PSTEP=%u PERROR=%d QSTEP=%u QERROR=%d TRIAL_STEP=%u TRIAL_ERROR=%d PAGES=%u BITMAP=%llx CPU=%llu PHYSICAL=%llu RP1=%llu RECORD=%u\\n",
        transport?transport->dmaPreparation():0,transport?transport->dmaState():0,
        transport?transport->dmaPreparationStep():0,transport?transport->dmaPreparationError():0,
        transport?transport->dmaQualificationStep():0,transport?transport->dmaQualificationError():0,
        transport?transport->usbNoopTrialStep():0,transport?transport->usbNoopTrialError():0,
        memory?memory->mapping_pages:0,(unsigned long long)(memory?memory->normal_nc_page_bitmap:0),
        (unsigned long long)(memory?memory->base_cpu_address:0),
        (unsigned long long)(memory?memory->base_physical_address:0),
        (unsigned long long)(memory?memory->base_rp1_dma_address:0),record?1:0);
    kprintf("RPI5XNU:USB_XHCI_NOOP:IMAGE VERSION=%u ZEROED=%u SCRATCH=%u EVENTS=%u DCBAA=%llu CR=%llu NOOP=%llu LINK=%llu ER=%llu ERST=%llu\\n",
        image?image->version:0,image?image->bytes_zeroed:0,image?image->scratchpad_count:0,
        image?image->event_trbs:0,(unsigned long long)(image?image->dcbaa_dma:0),
        (unsigned long long)(image?image->command_ring_dma:0),(unsigned long long)(image?image->noop_trb_dma:0),
        (unsigned long long)(image?image->link_trb_dma:0),(unsigned long long)(image?image->event_ring_dma:0),
        (unsigned long long)(image?image->erst_dma:0));
    kprintf("RPI5XNU:USB_XHCI_NOOP:BME STATE=%u STEP=%u ERROR=%d ORIGINAL=%04x ENABLED=%04x CURRENT=%04x READS=%u WRITES=%u\\n",
        bme?bme->state:0,bme?bme->step:0,bme?bme->error:0,bme?bme->original:0,
        bme?bme->enabled:0,bme?bme->current:0,bme?bme->reads:0,bme?bme->writes:0);
    kprintf("RPI5XNU:USB_XHCI_NOOP:RUN STEP=%u ERROR=%d READS=%u WRITES=%u POLLS=%u DELAY_US=%u DMA_CHECKS=%u OP=%08x RT=%08x DB=%08x EVENT=%llu CC=%u TYPE=%u PSC=%u HALT_CMD=%08x HALT_STS=%08x\\n",
        run?run->step:0,run?run->error:0,run?run->reads:0,run?run->writes:0,
        run?run->polls:0,run?run->delayed_us:0,run?run->dma_checks:0,
        run?run->operational_base:0,
        run?run->runtime_base:0,run?run->doorbell_base:0,
        (unsigned long long)(run?run->event_parameter:0),run?run->completion_code:0,
        run?run->event_type:0,run?run->port_status_events:0,
        run?run->command_halted:0,run?run->status_halted:0);
'''
    progress = progress[:start] + rows + progress[end:]
    files["BCM2712PCIeIDTrialProgress.inc"] = progress.encode()

    identify = files["BCM2712RP1GEMIdentifyTransport.inc"].decode()
    identify = _replace(identify,
        "    if(!self->observePreparedFullProvider())return -7;\n", "")
    start = identify.index('/* SPDX-License-Identifier: BSD-2-Clause */\n/* Observation-only retained full provider.')
    end = identify.index('bool BCM2712PCIePHYTransport::observeUSB0Capabilities()', start)
    provider = r'''/* SPDX-License-Identifier: BSD-2-Clause */
/* Retained Apple USB allocation. Qualification and command construction stay
 * CPU-only until the exact, separately logged BME lease is acquired. */
bool BCM2712PCIePHYTransport::prepareCPUOwnedRings()
{
    if(dmaPreparePhase==1) { dmaPreparePhase=3;return false; }
    if(dmaPreparePhase || dmaMemory || !onOwnerThread() || ml_get_cpu_count()!=1 ||
        claimAttempted || irqClaimed || fwClaimed || trialMode ||
        getPhase()!=BCM2712_PHY_PREPARED || !providerOpened || !ownerProvider)return false;
    dmaPreparePhase=1;
    IOService *provider=ownerProvider;
    auto active=[&]() {return dmaPreparePhase==1 && onOwnerThread() &&
        getPhase()==BCM2712_PHY_PREPARED && providerOpened && ownerProvider==provider &&
        !claimAttempted && !irqClaimed && !fwClaimed && !trialMode;};
    if(!provider->isOpen(this) || !active()) { dmaPreparePhase=3;return false; }
    dmaMemory=new BCM2712USBXHCIMemory;
    if(!dmaMemory || !active()) { dmaMemory=nullptr;dmaPreparePhase=3;return false; }
    if(!dmaMemory->prepare() || !active()) { dmaPreparePhase=3;return false; }
    dmaPreparePhase=2;return true;
}

'''
    identify = identify[:start] + provider + identify[end:]
    identify = _replace(identify,
        '''    usbCapabilityObserved=decoded;usbCapabilityStep=5;
    struct rpi5_xhci_lifecycle_io lifecycleIO={this,usbLifecycleRead,
        usbLifecycleWrite,usbLifecycleDelay,usbLifecycleGuard};''',
        '''    usbCapabilityObserved=decoded;usbCapabilityStep=5;
    if(!dmaMemory || dmaMemory->state()!=BCM2712USBXHCIMemory::Prepared) {
        usbCapabilityError=-13;return false;
    }
    usbQualificationActive=true;
    bool qualified=dmaMemory->qualify(&trialWindows,&usbCapabilityObserved);
    usbQualificationActive=false;
    if(!qualified || !dmaMemory->observeCPUOwnedLayout(&dmaObserved) ||
        !dmaMemory->stageNoOpCommand(&usbCapabilityObserved,&usbNoopImage)) {
        usbCapabilityError=-13;return false;
    }
    struct rpi5_xhci_lifecycle_io lifecycleIO={this,usbLifecycleRead,
        usbLifecycleWrite,usbLifecycleDelay,usbLifecycleGuard};''')
    identify = _replace(identify,
        '''    usbCapabilityStep=7;
    if(usbCapabilityMap->unmap()!=kIOReturnSuccess || usbCapabilityMap->getVirtualAddress()) {''',
        '''    usbCapabilityStep=7;
    if(!runUSBNoOp()) { usbCapabilityError=-14;return false; }
    if(usbCapabilityMap->unmap()!=kIOReturnSuccess || usbCapabilityMap->getVirtualAddress()) {''')
    implementation = r'''

int BCM2712PCIePHYTransport::usbNoopGuard(void *context)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    return !self || !self->usbDMAActive || !self->dmaMemory ||
        self->dmaMemory->state()!=BCM2712USBXHCIMemory::Staged ||
        usbLifecycleGuard(context) ? -1 : 0;
}

int BCM2712PCIePHYTransport::usbBMEGuard(void *context)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    return !self || !self->usbDMAActive || !self->decodeActive ||
        self->decodeCycle.state!=RPI5_RP1_DECODE_MAPPED ||
        usbLifecycleGuard(context) ? -1 : 0;
}

int BCM2712PCIePHYTransport::usbBMETransfer(void *context,
    const struct rpi5_pcie_config_request *request,uint32_t *value)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(usbBMEGuard(context) || !request || request->bus!=1 || request->device ||
        request->function || request->offset!=4 || request->width!=2)return -1;
    return rpi5_pcie_config_transfer(&self->rp1Config,request,value);
}

int BCM2712PCIePHYTransport::usbDMAGuard(void *context)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    return usbNoopGuard(context) || !rpi5_rp1_usb_bme_ready(&self->usbBME) ? -1 : 0;
}

int BCM2712PCIePHYTransport::usbNoopRead(void *context,uint32_t offset,uint32_t *value)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    const uint32_t op=self?self->usbCapabilityObserved.capability_length:0;
    const uint32_t rt=self?self->usbCapabilityObserved.runtime_offset:0;
    bool allowed=offset==op || offset==op+4 || offset==op+8 || offset==rt+0x20;
    if(!value || !allowed || (offset&3) || usbNoopGuard(context))return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    *value=*reinterpret_cast<volatile uint32_t *>(self->usbCapabilityMap->getVirtualAddress()+offset);
    __asm__ volatile("dsb sy" ::: "memory");
    return usbNoopGuard(context);
}

int BCM2712PCIePHYTransport::usbNoopWrite(void *context,uint32_t offset,uint32_t value)
{
    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);
    if(!self || usbNoopGuard(context) || (offset&3))return -1;
    const uint32_t op=self->usbCapabilityObserved.capability_length;
    const uint32_t rt=self->usbCapabilityObserved.runtime_offset;
    const uint32_t db=self->usbCapabilityObserved.doorbell_offset;
    bool allowed=offset==op || offset==op+0x18 || offset==op+0x1c ||
        offset==op+0x30 || offset==op+0x34 || offset==op+0x38 ||
        offset==rt+0x24 || offset==rt+0x28 || offset==rt+0x30 ||
        offset==rt+0x34 || offset==rt+0x38 || offset==rt+0x3c || offset==db;
    if(!allowed || offset>self->usbCapabilityMap->getLength()-4)return -1;
    __asm__ volatile("dmb osh" ::: "memory");
    *reinterpret_cast<volatile uint32_t *>(self->usbCapabilityMap->getVirtualAddress()+offset)=value;
    __asm__ volatile("dsb sy" ::: "memory");
    return usbNoopGuard(context);
}

int BCM2712PCIePHYTransport::usbNoopDelay(void *context,uint32_t us)
{
    if(usbNoopGuard(context) || !us || us>1000)return -1;
    IODelay(us);
    return usbNoopGuard(context);
}

bool BCM2712PCIePHYTransport::runUSBNoOp()
{
    usbNoopStep=1;usbNoopError=0;
    if(usbDMAActive || !dmaMemory ||
        dmaMemory->state()!=BCM2712USBXHCIMemory::Staged ||
        usbLifecycleGuard(this)) { usbNoopError=-1;return false; }
    usbDMAActive=true;dmaRingAttempted=true;dmaRingActive=true;
    const struct rpi5_rp1_usb_bme_io bmeIO={this,usbBMEGuard,usbBMETransfer};
    usbNoopStep=2;
    if(rpi5_rp1_usb_bme_init(&usbBME,&bmeIO)) { usbNoopError=-2;return false; }
    usbNoopStep=3;
    if(rpi5_rp1_usb_bme_enable(&usbBME)) { usbNoopError=-3;return false; }
    const auto &layout=dmaObserved.layout;
    const struct rpi5_xhci_noop_run_io runIO={this,usbNoopRead,usbNoopWrite,
        usbNoopDelay,usbNoopGuard,usbDMAGuard};
    usbNoopStep=4;
    if(rpi5_rp1_xhci_run_noop(&usbCapabilityObserved,&layout,&usbNoopImage,
        &runIO,&usbNoopObserved)) { usbNoopError=-4;return false; }
    usbNoopStep=5;
    if(rpi5_rp1_usb_bme_disable(&usbBME)) { usbNoopError=-5;return false; }
    dmaRingActive=false;usbDMAActive=false;usbNoopStep=6;return true;
}
'''
    identify += implementation
    files["BCM2712RP1GEMIdentifyTransport.inc"] = identify.encode()
    return files


def loader(original):
    return parent.loader(original).replace(
        "RPI5XNU:USB_XHCI_LIFECYCLE:ENTRY TAG=",
        "RPI5XNU:USB_XHCI_NOOP:ENTRY TAG=").replace(
        "CPUS=1 HALT_RESET_ONLY NO_PORT NO_IRQ NO_BME NO_DMA",
        "CPUS=1 POLLING ONE_NOOP NO_PORT NO_IRQ BME_LEASE DMA")


def psci(original):
    return parent.psci(original)


def sources():
    own = [
        ROOT / "iokit/Kernel/BCM2712USBXHCIMemory.h",
        ROOT / "iokit/Kernel/BCM2712USBXHCIMemory.cpp",
        ROOT / "iokit/Kernel/rpi5_rp1_dma_route.h",
        ROOT / "iokit/Kernel/rpi5_rp1_dma_route.c",
        ROOT / "loader/rpi5/rp1_usb_xhci_dma_layout.h",
        ROOT / "loader/rpi5/rp1_usb_xhci_dma_layout.c",
        ROOT / "loader/rpi5/rp1_usb_xhci_noop.h",
        ROOT / "loader/rpi5/rp1_usb_xhci_noop.c",
        ROOT / "loader/rpi5/rp1_usb_xhci_noop_run.h",
        ROOT / "loader/rpi5/rp1_usb_xhci_noop_run.c",
        ROOT / "loader/rpi5/rp1_usb_bme.h",
        ROOT / "loader/rpi5/rp1_usb_bme.c",
        ROOT / "loader/rpi5/pcie_watchdog_lease.c",
        ROOT / "loader/rpi5/pcie_watchdog_lease_usb_noop.c",
    ]
    return [Path(__file__).resolve(), *sorted(FROZEN.iterdir()), *own]
