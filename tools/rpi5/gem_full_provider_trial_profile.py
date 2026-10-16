# SPDX-License-Identifier: BSD-2-Clause
"""Observation-only full GEM provider caller for the bounded RP1 trial."""
from pathlib import Path

from tools.rpi5 import gem_cpu_ring_retry_profile as parent

ROOT = parent.ROOT
BOOTARGS = parent.trial.BOOTARGS
FROZEN = ROOT / "build/rpi5/gem-cpu-ring-physmap-trial-20261014-v2/overlay"


def _replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError("exact full-provider trial anchor differs")
    return text.replace(old, new)


def marker(tag):
    return "RPI5XNU:FULL_PROVIDER:ENTRY TAG=" + tag + " CPUS=1 NO_CPU_ON NO_QUEUE NO_BME NO_DMA"


def derive():
    files = {path.name: path.read_bytes() for path in FROZEN.iterdir() if path.is_file()}
    files["BCM2712GEMDMAMemory.h"] = (ROOT / "iokit/Kernel/BCM2712GEMDMAMemory.h").read_bytes()
    files["BCM2712GEMDMABatch.cpp"] = (ROOT / "iokit/Kernel/BCM2712GEMDMAMemory.cpp").read_bytes()

    header = files["BCM2712PCIePHYTransport.h"].decode()
    header = _replace(header, '#include "BCM2712GEMDMABatch.h"',
        '#include "BCM2712GEMDMAMemory.h"\n#include "arm64/rpi5_reservation_api.h"')
    old = '''    BCM2712GEMDMABatch *dmaMemory=nullptr;
    unsigned dmaPreparePhase=0; /*0empty,1preparing,2ready,3quarantined*/
    bool dmaRingAttempted=false,dmaRingActive=false,dmaRingRevoked=false;
    struct rpi5_gem_dma_route dmaCandidate={};
    struct BCM2712GEMDMALive dmaLive={};
    struct rpi5_gem_stage_observation dmaRingsObserved={};
    int dmaRingSource() const;
    static int dmaRingCurrent(void *,const BCM2712GEMDMABatch *,const struct rpi5_gem_cap_session *,uint64_t *);
    bool stagePreparedCPUOwnedRings();'''
    new = '''    struct bcm2712_gem_quiescence {
        uint32_t ncr,imr,rbqp,tbqp,tbqph,rbqph;
    };
    BCM2712GEMDMAMemory *dmaMemory=nullptr;
    unsigned dmaPreparePhase=0; /*0empty,1preparing,2ready,3quarantined*/
    bool dmaRingAttempted=false,dmaRingActive=false,dmaRingRevoked=false;
    unsigned dmaObserveStep=0;
    int dmaObserveError=0;
    struct rpi5_gem_dma_route dmaCandidate={};
    struct rpi5_gem_full_provider_observation dmaFullObserved={};
    struct bcm2712_gem_quiescence dmaBefore={},dmaAfter={};
    int dmaRingSource() const;
    bool readFullProviderQuiescence(struct bcm2712_gem_quiescence *);
    bool observePreparedFullProvider();'''
    header = _replace(header, old, new)
    old = '''    unsigned dmaPreparationStep() const { return dmaMemory?dmaMemory->preparationStep():0; }
    int dmaPreparationError() const { return dmaMemory?dmaMemory->preparationError():0; }
    unsigned dmaAttempted() const { return dmaRingAttempted; }
    unsigned dmaActive() const { return dmaRingActive; }
    unsigned dmaRevoked() const { return dmaRingRevoked; }'''
    new = '''    unsigned dmaPreparationStep() const { return dmaMemory?dmaMemory->preparationStep():0; }
    int dmaPreparationError() const { return dmaMemory?dmaMemory->preparationError():0; }
    unsigned dmaQualificationStep() const { return dmaMemory?dmaMemory->qualificationStep():0; }
    int dmaQualificationError() const { return dmaMemory?dmaMemory->qualificationError():0; }
    unsigned dmaMappingReason() const { return dmaMemory?dmaMemory->mappingReason():0; }
    unsigned dmaMappingPage() const { return dmaMemory?dmaMemory->mappingPage():0; }
    unsigned dmaMappingAttribute() const { return dmaMemory?dmaMemory->mappingAttribute():0; }
    uint64_t dmaMappingPhysical() const { return dmaMemory?dmaMemory->mappingPhysical():0; }
    uint64_t dmaMappingRetainedReadPAR() const { return dmaMemory?dmaMemory->mappingRetainedReadPAR():0; }
    uint64_t dmaMappingRetainedWritePAR() const { return dmaMemory?dmaMemory->mappingRetainedWritePAR():0; }
    uint64_t dmaMappingStaticReadPAR() const { return dmaMemory?dmaMemory->mappingStaticReadPAR():0; }
    uint64_t dmaMappingStaticWritePAR() const { return dmaMemory?dmaMemory->mappingStaticWritePAR():0; }
    unsigned dmaObservationStep() const { return dmaObserveStep; }
    int dmaObservationError() const { return dmaObserveError; }
    unsigned dmaAttempted() const { return dmaRingAttempted; }
    unsigned dmaActive() const { return dmaRingActive; }
    unsigned dmaRevoked() const { return dmaRingRevoked; }'''
    header = _replace(header, old, new)
    old = '''    const struct rpi5_gem_dma_route &dmaRoute() const { return dmaCandidate; }
    const struct rpi5_gem_stage_observation &dmaObserved() const { return dmaRingsObserved; }
    const struct rpi5_gem_stage_session *dmaTrace() const { return dmaMemory?&dmaMemory->stageTrace():nullptr; }
    bool prepareCPUOwnedRings();'''
    new = '''    const struct rpi5_gem_dma_route &dmaRoute() const { return dmaCandidate; }
    const struct rpi5_gem_full_provider_observation &dmaObserved() const { return dmaFullObserved; }
    const struct bcm2712_gem_quiescence &dmaQuiescenceBefore() const { return dmaBefore; }
    const struct bcm2712_gem_quiescence &dmaQuiescenceAfter() const { return dmaAfter; }
    bool prepareCPUOwnedRings();'''
    header = _replace(header, old, new)
    files["BCM2712PCIePHYTransport.h"] = header.encode()

    progress = files["BCM2712PCIeIDTrialProgress.inc"].decode()
    progress = _replace(progress, "BCM2712GEMDMABatch::Prepared", "BCM2712GEMDMAMemory::Prepared")
    progress = _replace(progress, '''    auto state=self->dmaMemory->state();
    if(state!=BCM2712GEMDMABatch::Held && state!=BCM2712GEMDMABatch::Staging &&
        state!=BCM2712GEMDMABatch::RingsHeld)return -1;''', '''    auto state=self->dmaMemory->state();
    if(state!=BCM2712GEMDMAMemory::Held)return -1;''')
    start = progress.index('    const struct rpi5_reservation_record *record=rpi5_boot_reservation_record();')
    end = progress.index('    kprintf("RPI5XNU:PCIEID:END OK=%u', start)
    rows = '''    const struct rpi5_reservation_record *record=rpi5_boot_reservation_record();
    const auto *full=transport?&transport->dmaObserved():nullptr;
    const auto *before=transport?&transport->dmaQuiescenceBefore():nullptr;
    const auto *after=transport?&transport->dmaQuiescenceAfter():nullptr;
    kprintf("RPI5XNU:PCIEID:FULL_OWNER PREPARE=%u STATE=%u STEP=%u ERROR=%d QSTEP=%u QERROR=%d OSTEP=%u OERROR=%d ATTEMPTED=%u ACTIVE=%u REVOKED=%u DISABLED=%u RECORD=%u\\n",
        transport?transport->dmaPreparation():0,transport?transport->dmaState():0,
        transport?transport->dmaPreparationStep():0,transport?transport->dmaPreparationError():0,
        transport?transport->dmaQualificationStep():0,transport?transport->dmaQualificationError():0,
        transport?transport->dmaObservationStep():0,transport?transport->dmaObservationError():0,
        transport?transport->dmaAttempted():0,transport?transport->dmaActive():0,
        transport?transport->dmaRevoked():0,transport?transport->dmaDisabled():0,record?1:0);
    kprintf("RPI5XNU:PCIEID:FULL_MAP REASON=%u PAGE=%u ATTR=%u PA=%llu RETAINED_R=%llu RETAINED_W=%llu STATIC_R=%llu STATIC_W=%llu\\n",
        transport?transport->dmaMappingReason():0,transport?transport->dmaMappingPage():0,
        transport?transport->dmaMappingAttribute():0,(unsigned long long)(transport?transport->dmaMappingPhysical():0),
        (unsigned long long)(transport?transport->dmaMappingRetainedReadPAR():0),
        (unsigned long long)(transport?transport->dmaMappingRetainedWritePAR():0),
        (unsigned long long)(transport?transport->dmaMappingStaticReadPAR():0),
        (unsigned long long)(transport?transport->dmaMappingStaticWritePAR():0));
    kprintf("RPI5XNU:PCIEID:FULL_ROUTE CPU=%llu PHYSICAL=%llu PCI=%llu RP1=%llu BYTES=%llu BITMAP=%llx\\n",
        (unsigned long long)(full?full->base_cpu_address:0),(unsigned long long)(full?full->base_physical_address:0),
        (unsigned long long)(transport?transport->dmaRoute().pci:0),
        (unsigned long long)(full?full->base_rp1_dma_address:0),
        (unsigned long long)(transport?transport->dmaRoute().bytes:0),
        (unsigned long long)(full?full->normal_nc_page_bitmap:0));
    kprintf("RPI5XNU:PCIEID:FULL_LAYOUT VERSION=%u PAGES=%u RINGS=%u PACKETS=%u PACKET_BYTES=%u MAPPED=%u CPU_OWNED=%u\\n",
        full?full->version:0,full?full->mapping_pages:0,full?full->ring_pages:0,full?full->packet_spans:0,
        full?full->packet_bytes:0,full?full->packet_mapped_bytes:0,full?full->packet_spans_cpu_owned:0);
    kprintf("RPI5XNU:PCIEID:FULL_QUIESCE_BEFORE NCR=%08x IMR=%08x RBQP=%08x TBQP=%08x TBQPH=%08x RBQPH=%08x\\n",
        before?before->ncr:0,before?before->imr:0,before?before->rbqp:0,before?before->tbqp:0,
        before?before->tbqph:0,before?before->rbqph:0);
    kprintf("RPI5XNU:PCIEID:FULL_QUIESCE_AFTER NCR=%08x IMR=%08x RBQP=%08x TBQP=%08x TBQPH=%08x RBQPH=%08x\\n",
        after?after->ncr:0,after?after->imr:0,after?after->rbqp:0,after?after->tbqp:0,
        after?after->tbqph:0,after?after->rbqph:0);
    for(unsigned i=0;i<RPI5_GEM_FULL_PROVIDER_MAPPING_PAGES;i++) {
        const auto &page=full->page[i];
        kprintf("RPI5XNU:PCIEID:FULL_PAGE INDEX=%u ATTR=%u RETAINED_OK=%u STATIC_OK=%u RETAINED=%llu STATIC=%llu PA=%llu RETAINED_R=%llu RETAINED_W=%llu STATIC_R=%llu STATIC_W=%llu\\n",
            page.index,page.cache_attribute,page.retained_valid,page.static_valid,
            (unsigned long long)page.retained_cpu_address,(unsigned long long)page.static_cpu_address,
            (unsigned long long)page.physical_address,(unsigned long long)page.retained_read_par,
            (unsigned long long)page.retained_write_par,(unsigned long long)page.static_read_par,
            (unsigned long long)page.static_write_par);
    }
    for(unsigned i=0;i<RPI5_GEM_FULL_PROVIDER_PACKET_SPANS;i++) {
        const auto &span=full->packet[i];
        kprintf("RPI5XNU:PCIEID:FULL_SPAN INDEX=%u CPU=%llu RP1=%llu BYTES=%u PAGE=%u OWNER=%u\\n",
            i,(unsigned long long)span.cpu_address,(unsigned long long)span.dma_address,
            span.bytes,span.mapping_page,(unsigned)span.owner);
    }
'''
    progress = progress[:start] + rows + progress[end:]
    progress = _replace(progress,
        'kprintf("RPI5XNU:PCIEID:BEGIN PREFERRED_RAM_ONLY NO_BME\\n");',
        'kprintf("RPI5XNU:PCIEID:BEGIN FULL_PROVIDER PREFERRED_RAM_ONLY NO_QUEUE NO_BME NO_DMA\\n");')
    files["BCM2712PCIeIDTrialProgress.inc"] = progress.encode()

    identify = files["BCM2712RP1GEMIdentifyTransport.inc"].decode()
    identify = _replace(identify, "if(!self->stagePreparedCPUOwnedRings())return -7;",
        "if(!self->observePreparedFullProvider())return -7;")
    boundary = identify.index('/* SPDX-License-Identifier: BSD-2-Clause */\n/* This is a real caller')
    identify = identify[:boundary] + '''/* SPDX-License-Identifier: BSD-2-Clause */
/* Observation-only retained full provider. No descriptor/packet write, queue
 * publication, BME, DMA, IRQ or engine activation occurs in this path. */
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
    dmaMemory=new BCM2712GEMDMAMemory;
    if(!dmaMemory || !active()) { dmaMemory=nullptr;dmaPreparePhase=3;return false; }
    bool prepared=dmaMemory->prepare();
    if(!prepared || !active()) { dmaPreparePhase=3;return false; }
    dmaPreparePhase=2;return true;
}
int BCM2712PCIePHYTransport::dmaRingSource() const
{
    if(!dmaMemory)return -1;
    if(!dmaRingActive || dmaRingRevoked || !onOwnerThread() || checkingLifecycle)return -2;
    if(getPhase()!=BCM2712_PHY_RP1_INSPECTING || lifecyclePhase!=BCM2712_CONTROLLER_RELEASED)return -3;
    if(capabilitySession.self!=&capabilitySession || capabilitySession.identity!=&gemSession)return -4;
    if(capabilitySession.state!=RPI5_GEM_CAP_COMPLETE || capabilitySession.reads!=16 ||
        capabilitySession.busy || capabilitySession.pending)return -5;
    if(gemSession.stage!=RPI5_GEM_COMPLETE || gemSession.reads!=32 || gemSession.pending ||
        !gemSession.clocks_ready)return -6;
    if(trialWindows.state!=RPI5_PCIE_RELEASED_READY || trialWindows.windows!=&windows ||
        windows.state!=RPI5_PCIE_WINDOWS_COMPLETE)return -7;
    if(rpi5_gem_ram_window_match(&binding,&windows.plan))return -8;
    return gemSource(const_cast<BCM2712PCIePHYTransport *>(this),&gemSession,&decodeCycle)?-9:0;
}
bool BCM2712PCIePHYTransport::readFullProviderQuiescence(struct bcm2712_gem_quiescence *out)
{
    if(!out) { dmaObserveError=-10;return false; }
    int source=dmaRingSource();if(source) { dmaObserveError=source;return false; }
    if(!guard()) { dmaObserveError=-11;return false; }
    source=dmaRingSource();if(source) { dmaObserveError=source;return false; }
    IOMemoryMap *map=deviceMaps[0];
    if(!map || map->getLength()<0x4d8) { dmaObserveError=-12;return false; }
    const uint32_t offsets[6]={0x0000,0x0030,0x0018,0x001c,0x04c8,0x04d4};
    uint32_t values[6]={};
    for(unsigned i=0;i<6;i++) {
        __asm__ volatile("dmb osh" ::: "memory");
        values[i]=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offsets[i]);
        __asm__ volatile("dsb sy" ::: "memory");
        if(values[i]==UINT32_MAX) { dmaObserveError=-20-(int)i;return false; }
        source=dmaRingSource();if(source) { dmaObserveError=source;return false; }
        if(!guard()) { dmaObserveError=-30-(int)i;return false; }
        source=dmaRingSource();if(source) { dmaObserveError=source;return false; }
    }
    *out={values[0],values[1],values[2],values[3],values[4],values[5]};return true;
}
bool BCM2712PCIePHYTransport::observePreparedFullProvider()
{
    dmaObserveStep=1;dmaObserveError=0;
    if(dmaRingActive) { dmaRingRevoked=true;dmaObserveError=-40;return false; }
    if(dmaRingAttempted || !dmaMemory ||
        dmaMemory->state()!=BCM2712GEMDMAMemory::Held || !onOwnerThread()) {
        dmaObserveError=-41;return false;
    }
    dmaRingAttempted=true;dmaRingActive=true;
    struct bcm2712_gem_quiescence before={},after={};
    dmaObserveStep=2;dmaObserveError=dmaRingSource();if(dmaObserveError)return false;
    dmaObserveStep=3;if(!readFullProviderQuiescence(&before))return false;
    dmaObserveStep=4;if(!dmaMemory->observeCPUOwnedLayout(&dmaFullObserved)) {
        dmaObserveError=-42;return false;
    }
    dmaObserveStep=5;dmaObserveError=dmaRingSource();if(dmaObserveError)return false;
    dmaObserveStep=6;if(!readFullProviderQuiescence(&after))return false;
    dmaObserveStep=7;dmaObserveError=dmaRingSource();if(dmaObserveError)return false;
    dmaObserveStep=8;
    /* Publish both read-only snapshots even when the equality gate rejects;
     * they are diagnostics, not queue ownership or activation authority. */
    dmaBefore=before;dmaAfter=after;
    /* Cadence GEM IMR is active-low: one means the interrupt is disabled.
     * RP1 GEM_GXL implements bits 0..29, observed as the stable all-masked
     * value below.  Reject a partial mask as well as any change. */
    if(before.ncr || after.ncr ||
        before.imr!=UINT32_C(0x3fffffff) ||
        after.imr!=UINT32_C(0x3fffffff) ||
        before.rbqp!=after.rbqp || before.tbqp!=after.tbqp ||
        before.tbqph!=after.tbqph || before.rbqph!=after.rbqph) {
        dmaObserveError=-43;return false;
    }
    dmaRingActive=false;dmaObserveStep=9;dmaObserveError=0;return true;
}
'''
    files["BCM2712RP1GEMIdentifyTransport.inc"] = identify.encode()
    return files


def loader(original):
    return parent.trial.loader(original).replace(
        "RPI5XNU:CPU_RINGS:ENTRY TAG=", "RPI5XNU:FULL_PROVIDER:ENTRY TAG=").replace(
        "CPUS=1 NO_CPU_ON NO_QUEUE NO_DMA", "CPUS=1 NO_CPU_ON NO_QUEUE NO_BME NO_DMA")


def psci(original):
    return parent.trial.psci(original)


def sources():
    return [Path(__file__).resolve(), *sorted(FROZEN.iterdir()),
        ROOT / "iokit/Kernel/BCM2712GEMDMAMemory.h",
        ROOT / "iokit/Kernel/BCM2712GEMDMAMemory.cpp"]
