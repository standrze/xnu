#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Derive the discard-only page-granular physmap board verification overlay."""
from pathlib import Path
from tools.rpi5 import gem_mapping_predicate_profile as parent

ROOT = parent.ROOT


def _replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError("Exact physmap verification anchor differs")
    return text.replace(old, new)


def derive():
    files = parent.derive()
    h = files["BCM2712GEMDMABatch.h"].decode()
    h = _replace(h, '#include "rpi5_gem_dma_route.h"', '''#include "rpi5_gem_dma_route.h"
#include "arm64/rpi5_gem_physmap_accounting.h"''')
    h = _replace(h, '    unsigned mappingReason() const { return mappingReason_; }', '''    struct MappingEvidence {
        unsigned page,attribute,vaClass,valid;
        uint64_t physical,readPAR,writePAR;
    };
    MappingEvidence mappingEvidence(unsigned page,unsigned vaClass) const {
        if (page>=2 || vaClass<1 || vaClass>2) return {};
        return mappingEvidence_[page][vaClass-1];
    }
    const struct rpi5_gem_physmap_accounting &physmapAccounting() const { return physmapAccounting_; }
    unsigned physmapReservationClear() const { return physmapReservationClear_; }
    bool verificationDiscarded() const { return mappingReason_==41 && state_==Discarded; }
    unsigned mappingReason() const { return mappingReason_; }''')
    h = _replace(h, '    mutable uint64_t mappingPhysical_=0,mappingReadPAR_=0,mappingWritePAR_=0;', '''    mutable uint64_t mappingPhysical_=0,mappingReadPAR_=0,mappingWritePAR_=0;
    mutable MappingEvidence mappingEvidence_[2][2]={};
    mutable struct rpi5_gem_physmap_accounting physmapAccounting_={};
    mutable unsigned physmapReservationClear_=0;''')
    files["BCM2712GEMDMABatch.h"] = h.encode()

    c = files["BCM2712GEMDMABatch.cpp"].decode()
    start = c.index("bool BCM2712GEMDMABatch::mapping() const")
    end = c.index("\n}\n\n/* SPDX-License-Identifier: BSD-2-Clause */\nbool BCM2712GEMDMABatch::route", start) + 2
    mapping = r'''bool BCM2712GEMDMABatch::mapping() const
{
    mappingReason_=1;mappingPage_=0;mappingAttribute_=0;mappingVAClass_=0;
    mappingPhysical_=0;mappingReadPAR_=0;mappingWritePAR_=0;
    physmapAccounting_={};physmapReservationClear_=0;
    for (unsigned page=0;page<2;page++) for (unsigned vaClass=0;vaClass<2;vaClass++)
        mappingEvidence_[page][vaClass]={};
    auto fail=[&](unsigned reason,unsigned page,unsigned attr,unsigned vaClass,
        uint64_t physical,uint64_t readPAR,uint64_t writePAR) {
        mappingReason_=reason;mappingPage_=page;mappingAttribute_=attr;mappingVAClass_=vaClass;
        mappingPhysical_=physical;mappingReadPAR_=readPAR;mappingWritePAR_=writePAR;return false;
    };
    const auto state=state_;
    auto intact=[&]() {
        return state_==state && (state==Preparing || state==Checking || state==Staging) &&
            thread_==(void *)current_thread() && !ml_at_interrupt_context();
    };
    if (!intact()) return fail(2,0,0,0,0,0,0);
    if (!resolved_) return fail(3,0,0,0,0,0,0);
    const auto currentRecord=rpi5_boot_reservation_record();
    if (resolved_!=currentRecord) return fail(4,0,0,0,0,0,0);
    if (rpi5_gem_physmap_accounting(&physmapAccounting_)) return fail(25,0,0,0,0,0,0);
    const auto &account=physmapAccounting_;
    if (account.enabled!=1 || account.page_bytes!=Alignment || !account.table_pages || account.maximum_pages>259 ||
        account.edge_pages>2 || account.preallocated_upper_pages!=1 ||
        account.table_end<account.table_start ||
        account.table_pages>account.maximum_pages || account.table_bytes!=uint64_t(account.table_pages)*Alignment ||
        account.table_end-account.table_start!=account.table_bytes || !account.mapped_bytes)
        return fail(26,0,0,0,account.table_start,account.table_end,account.table_bytes);
    if (rpi5_reservation_kernel_buffer(currentRecord,account.table_start,account.table_bytes))
        return fail(27,0,0,0,account.table_start,account.table_end,account.table_bytes);
    physmapReservationClear_=1;
    if (!buffer_) return fail(5,0,0,0,0,0,0);
    if (!command_) return fail(6,0,0,0,0,0,0);
    if (!commandPrepared_) return fail(7,0,0,0,0,0,0);
    if (!cpu_) return fail(8,0,0,1,0,0,0);
    if (!physical_) return fail(9,0,0,0,0,0,0);
    if (cpu_&(Alignment-1)) return fail(10,0,0,1,0,0,0);
    if (physical_&(Alignment-1)) return fail(11,0,0,0,physical_,0,0);
    if (cpu_>UINT64_MAX-AllocationBytes) return fail(12,0,0,1,0,0,0);
    if (physical_>UINT64_MAX-AllocationBytes) return fail(13,0,0,0,physical_,0,0);
    auto length=buffer_->getLength();
    if (!intact()) return fail(14,0,0,0,0,0,0);
    if (length!=AllocationBytes) return fail(15,0,0,0,physical_,0,0);
    auto capacity=buffer_->getCapacity();
    if (!intact()) return fail(16,0,0,0,0,0,0);
    if (capacity!=AllocationBytes) return fail(17,0,0,0,physical_,0,0);
    auto bytesVA=buffer_->getBytesNoCopy();
    if (!intact()) return fail(18,0,0,0,0,0,0);
    if ((uint64_t)bytesVA!=cpu_) return fail(19,0,0,1,physical_,0,0);
    auto type=rpi5_physical_memory_type(physical_,physical_+AllocationBytes);
    if (!intact()) return fail(20,0,0,0,0,0,0);
    if (type!=1) return fail(21,0,type,0,physical_,0,0);
    IOByteCount bytes=0;
    auto pa=buffer_->getPhysicalSegment(0,&bytes,kIOMemoryMapperNone);
    if (!intact()) return fail(22,0,0,0,0,0,0);
    if (pa!=physical_) return fail(23,0,0,0,pa,0,0);
    if (bytes!=AllocationBytes) return fail(24,0,0,0,pa,0,0);
    for (uint64_t offset=0;offset<AllocationBytes;offset+=Alignment) {
        unsigned page=(unsigned)(offset/Alignment);pa=physical_+offset;
        auto attr=pmap_cache_attributes((ppnum_t)(pa>>PAGE_SHIFT))&VM_WIMG_MASK;
        if (!intact()) return fail(30,page,attr,0,pa,0,0);
        if (attr!=VM_WIMG_WCOMB) return fail(31,page,attr,0,pa,0,0);
        auto translation=translated_nc(cpu_+offset,pa);
        mappingEvidence_[page][0]={page,attr,1,(unsigned)translation.valid,pa,translation.read_par,translation.write_par};
        if (!intact()) return fail(32,page,attr,1,pa,translation.read_par,translation.write_par);
        if (!translation.valid) return fail(33,page,attr,1,pa,translation.read_par,translation.write_par);
        auto alias=ml_static_ptovirt(pa);
        if (!intact()) return fail(34,page,attr,2,pa,0,0);
        translation=translated_nc(alias,pa);
        mappingEvidence_[page][1]={page,attr,2,(unsigned)translation.valid,pa,translation.read_par,translation.write_par};
        if (!intact()) return fail(35,page,attr,2,pa,translation.read_par,translation.write_par);
        if (!translation.valid) return fail(36,page,attr,2,pa,translation.read_par,translation.write_par);
    }
    if (!intact()) return fail(40,2,0,0,0,0,0);
    mappingReason_=41;return true;
}'''
    c = c[:start] + mapping + c[end:]
    old = '''        prepareStep_=14;
        if (!mapping()) { prepareError_=-13;goto reject; }
        prepareStep_=15;
        struct rpi5_gem_dma_route geometry;
        if (!route(&expected_,&geometry)) { prepareError_=-14;goto reject; }
        prepareStep_=16;
    }
    if (!active()) goto quarantine;
    state_=Prepared;prepareStep_=17;return true;'''
    new = '''        prepareStep_=14;
        if (!mapping()) { prepareError_=-13;goto reject; }
        /* Verification is intentionally terminal: discard the prepared DMA
         * command and buffer before any route or descriptor operation. */
        prepareStep_=15;state_=Rejected;
        if (!discardBeforeAdmission()) { prepareError_=-14;return false; }
        prepareStep_=16;return false;
    }'''
    c = _replace(c, old, new)
    files["BCM2712GEMDMABatch.cpp"] = c.encode()

    ident = files["BCM2712RP1GEMIdentifyTransport.inc"].decode()
    ident = _replace(ident, '''    if(!dmaMemory || !active()) { dmaPreparePhase=3;return false; }''', '''    if(!dmaMemory) {
        dmaMemory=nullptr;dmaPreparePhase=3;
        __asm__ volatile("" ::: "memory");
        return false;
    }
    if(!active()) { dmaPreparePhase=3;return false; }''')
    ident = _replace(ident, '''    bool prepared=dmaMemory->prepare();
    if(!prepared || !active()) { dmaPreparePhase=3;return false; }
    dmaPreparePhase=2;return true;''', '''    bool prepared=dmaMemory->prepare();
    if(!active()) { dmaPreparePhase=3;return false; }
    if(!prepared && dmaMemory->verificationDiscarded()) { dmaPreparePhase=2;return true; }
    dmaPreparePhase=3;return false;''')
    files["BCM2712RP1GEMIdentifyTransport.inc"] = ident.encode()

    th = files["BCM2712PCIePHYTransport.h"].decode()
    th = _replace(th, '    unsigned dmaMappingReason() const { return dmaMemory?dmaMemory->mappingReason():0; }', '''    BCM2712GEMDMABatch::MappingEvidence dmaMappingEvidence(unsigned page,unsigned vaClass) const {
        return dmaMemory?dmaMemory->mappingEvidence(page,vaClass):BCM2712GEMDMABatch::MappingEvidence{};
    }
    const struct rpi5_gem_physmap_accounting *dmaPhysmapAccounting() const {
        return dmaMemory?&dmaMemory->physmapAccounting():nullptr;
    }
    unsigned dmaPhysmapReservationClear() const { return dmaMemory?dmaMemory->physmapReservationClear():0; }
    unsigned dmaVerificationDiscarded() const { return dmaMemory?dmaMemory->verificationDiscarded():0; }
    unsigned dmaMappingReason() const { return dmaMemory?dmaMemory->mappingReason():0; }''')
    files["BCM2712PCIePHYTransport.h"] = th.encode()

    progress = files["BCM2712PCIeIDTrialProgress.inc"].decode()
    progress = _replace(progress, '''    if(prepared)prepared=transport->prepareCPUOwnedRings();
    if(prepared)ok=transport->runBoundedRP1Trial(&observed);''', '''    if(prepared)prepared=transport->prepareCPUOwnedRings();
    ok=prepared && transport->dmaVerificationDiscarded() && transport->dmaMappingReason()==41;''')
    progress = _replace(progress, '''    struct rpi5_pcie_owner_trace owner_trace={};
    (void)pe_rpi5_pcie_owner_trace(transport,&owner_trace);''', '''    /* No post-mapping owner callback: scalar diagnostics below remain zero.
     * Mapping evidence and discard state are the terminal authority. */
    struct rpi5_pcie_owner_trace owner_trace={};''')
    anchor = '''    kprintf("RPI5XNU:PCIEID:DMA_OWNER PREPARE=%u'''
    rows = r'''    for (unsigned page=0;page<2;page++) for (unsigned vaClass=1;vaClass<=2;vaClass++) {
        auto e=transport?transport->dmaMappingEvidence(page,vaClass):BCM2712GEMDMABatch::MappingEvidence{};
        kprintf("RPI5XNU:PCIEID:DMA_ALIAS PAGE=%u VA=%u CACHE=%u PA=%llu PAR_R=%llu PAR_W=%llu ATTR_R=%u ATTR_W=%u VALID=%u\n",
            e.page,e.vaClass,e.attribute,(unsigned long long)e.physical,
            (unsigned long long)e.readPAR,(unsigned long long)e.writePAR,
            (unsigned)(e.readPAR>>56),(unsigned)(e.writePAR>>56),e.valid);
    }
    const auto *account=transport?transport->dmaPhysmapAccounting():nullptr;
    kprintf("RPI5XNU:PCIEID:DMA_PGTABLE START=%llu END=%llu BYTES=%llu PAGES=%u MAX=%u EDGE=%u UPPER=%u PAGE_BYTES=%u MAPPED=%llu RESERVATION_CLEAR=%u\n",
        (unsigned long long)(account?account->table_start:0),(unsigned long long)(account?account->table_end:0),
        (unsigned long long)(account?account->table_bytes:0),account?account->table_pages:0,
        account?account->maximum_pages:0,account?account->edge_pages:0,
        account?account->preallocated_upper_pages:0,account?account->page_bytes:0,
        (unsigned long long)(account?account->mapped_bytes:0),transport?transport->dmaPhysmapReservationClear():0);
'''
    progress = _replace(progress, anchor, rows + anchor)
    files["BCM2712PCIeIDTrialProgress.inc"] = progress.encode()
    return files


def sources():
    return [Path(__file__).resolve(), ROOT / "osfmk/arm64/rpi5_gem_physmap_accounting.h", *parent.sources()]
