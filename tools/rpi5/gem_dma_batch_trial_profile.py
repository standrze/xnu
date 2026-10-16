# SPDX-License-Identifier: BSD-2-Clause
"""Distinct real CPU-ring caller, passive evidence and single-CPU loader recipe."""
from tools.rpi5 import gem_dma_batch_transport_profile as transport
from tools.rpi5 import reservation_record_loader_profile as record
from tools.rpi5 import loader_copy_phase_profile as copy
ROOT=transport.ROOT
change=transport.change
BOOTARGS='serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress cpus=1'
def marker(tag):return 'RPI5XNU:CPU_RINGS:ENTRY TAG='+tag+' CPUS=1 NO_CPU_ON NO_QUEUE NO_DMA'
def derive():
    files=transport.derive()
    h=files['BCM2712GEMDMABatch.h'].decode()
    h=change(h,'    State state() const',
        '    const struct rpi5_gem_stage_session &stageTrace() const { return ringSession_; }\n    State state() const')
    files['BCM2712GEMDMABatch.h']=h.encode()
    h=files['BCM2712PCIePHYTransport.h'].decode()
    h=change(h,'    bool prepareCPUOwnedRings();',
        '''    unsigned dmaPreparation() const { return dmaPreparePhase; }
    unsigned dmaState() const { return dmaMemory?(unsigned)dmaMemory->state():0; }
    unsigned dmaAttempted() const { return dmaRingAttempted; }
    unsigned dmaActive() const { return dmaRingActive; }
    unsigned dmaRevoked() const { return dmaRingRevoked; }
    unsigned dmaDisabled() const {
        if(windows.state!=RPI5_PCIE_WINDOWS_COMPLETE)return 0;
        for(unsigned i=0;i<3;i++)if(windows.plan.inbound[i].bar_lo&31)return 0;
        return 1;
    }
    const struct rpi5_gem_dma_route &dmaRoute() const { return dmaCandidate; }
    const struct rpi5_gem_stage_observation &dmaObserved() const { return dmaRingsObserved; }
    const struct rpi5_gem_stage_session *dmaTrace() const { return dmaMemory?&dmaMemory->stageTrace():nullptr; }
    bool prepareCPUOwnedRings();''')
    files['BCM2712PCIePHYTransport.h']=h.encode()
    p=files['BCM2712PCIeIDTrialProgress.inc'].decode()
    anchor='    kprintf("RPI5XNU:PCIEID:END OK=%u'
    at=p.index(anchor)
    rows='''    const struct rpi5_reservation_record *record=rpi5_boot_reservation_record();
    const struct rpi5_gem_stage_session *ring=transport?transport->dmaTrace():nullptr;
    kprintf("RPI5XNU:PCIEID:DMA_OWNER PREPARE=%u STATE=%u ATTEMPTED=%u ACTIVE=%u REVOKED=%u DISABLED=%u RECORD=%u\\n",
        transport?transport->dmaPreparation():0,transport?transport->dmaState():0,
        transport?transport->dmaAttempted():0,transport?transport->dmaActive():0,
        transport?transport->dmaRevoked():0,transport?transport->dmaDisabled():0,record?1:0);
    kprintf("RPI5XNU:PCIEID:DMA_RECORD FIXED=%u DYNAMIC=%u MANAGED_START=%llu MANAGED_END=%llu\\n",
        (unsigned)(record?record->fixed_count:0),(unsigned)(record?record->dynamic_count:0),
        (unsigned long long)(record?record->managed_start:0),(unsigned long long)(record?record->managed_end:0));
    kprintf("RPI5XNU:PCIEID:DMA_ROUTE PHYSICAL=%llu PCI=%llu RP1=%llu BYTES=%llu\\n",
        (unsigned long long)(transport?transport->dmaRoute().physical:0),
        (unsigned long long)(transport?transport->dmaRoute().pci:0),
        (unsigned long long)(transport?transport->dmaRoute().rp1:0),
        (unsigned long long)(transport?transport->dmaRoute().bytes:0));
    kprintf("RPI5XNU:PCIEID:DMA_STAGE STATE=%u ERROR=%d ATTEMPTED=%u WRITTEN=%u READ=%u CALLS=%u CHECKS=%u\\n",
        ring?ring->state:0,ring?ring->error:0,ring?ring->writes_attempted:0,
        ring?ring->writes_completed:0,ring?ring->reads_completed:0,
        ring?ring->callbacks:0,ring?ring->current_checks:0);
    kprintf("RPI5XNU:PCIEID:DMA_RINGS RX=%llu TX=%llu GENERATION=%llu BYTES=%u DESC=%u SLOTS=%u TAIL=%u OWNED=%u\\n",
        (unsigned long long)(transport?transport->dmaObserved().ring_dma[0]:0),
        (unsigned long long)(transport?transport->dmaObserved().ring_dma[1]:0),
        (unsigned long long)(transport?transport->dmaObserved().generation:0),
        transport?transport->dmaObserved().ring_bytes:0,transport?transport->dmaObserved().descriptor_bytes:0,
        transport?transport->dmaObserved().real_slots:0,transport?transport->dmaObserved().prefetch_bytes:0,
        transport?transport->dmaObserved().cpu_owned_descriptors:0);
'''
    files['BCM2712PCIeIDTrialProgress.inc']=(p[:at]+rows+p[at:]).encode()
    return files
def loader(original):
    text=copy.transform(record.loader(original))
    text=change(text,'#include "pcie_device_handoff.h"',
        '#include "pcie_device_handoff.h"\n#include "rp1_device_handoff.h"')
    text=change(text,'    types=pcie_types;',
        '''    static struct rpi5_memory_types rp1_types;
    if (rpi5_rp1_device_handoff((const void *)fdt_pa,fdt_length,&pcie_types,&rp1_types)) return 0;
    types=rp1_types;''')
    text=change(text,'    if (!text("RPI5XNU:BL33:FIRMWARE_FDT RETAINED_DESCRIPTOR_ONLY',
        '    if (!text("RPI5XNU:BL33:RP1_DEVICE_HANDOFF RANGES=2 PAGES=6 GEM_CLOCK_ONLY DECLARATIONS_ONLY RP1_MMIO=0\\r\\n")) return 0;\n'
        '    if (!text("RPI5XNU:BL33:FIRMWARE_FDT RETAINED_DESCRIPTOR_ONLY')
    start=text.index('static int start_secondaries(')
    end=text.index('static int psci_affinity_inventory(',start)
    text=text[:start]+text[end:]
    text=change(text,'extern uint64_t rpi5_psci_cpu_on(uint64_t affinity, uintptr_t entry, uint64_t context);\n','')
    text=change(text,'    if (!psci_affinity_inventory(cpus)) return 0;\n    return start_secondaries(cpus);',
        '    return psci_affinity_inventory(cpus);')
    text=change(text,'    size_t command_length=0;',
        '    command_line = "'+BOOTARGS+'";\n    size_t command_length=0;')
    text=change(text,'RPI5XNU:DISPLAYXNU:ENTRY TAG=" RPI5_DISPLAY_XNU_TAG " SAME_BOOT OWNED_FRAMEBUFFER_CONSOLE_V1',
        'RPI5XNU:CPU_RINGS:ENTRY TAG=" RPI5_DISPLAY_XNU_TAG " CPUS=1 NO_CPU_ON NO_QUEUE NO_DMA')
    if 'rpi5_psci_cpu_on(' in text or 'start_secondaries' in text:raise ValueError('CPU_ON remains')
    return text
def psci(original):
    start=original.index('/* CPU_ON64:');end=original.index('/* CPU_OFF32',start)
    text=original[:start]+original[end:]
    if 'rpi5_psci_cpu_on' in text:raise ValueError('CPU_ON helper remains')
    return text
def sources():
    from pathlib import Path
    return [Path(__file__).resolve(),Path(transport.__file__),*record.sources(),*copy.sources(),
        ROOT/'loader/rpi5/rp1_device_handoff.c',ROOT/'loader/rpi5/rp1_device_handoff.h',
        ROOT/'tools/rpi5/tests/test_rp1_device_handoff.py',ROOT/'tools/rpi5/tests/rp1_device_handoff_host.c']
