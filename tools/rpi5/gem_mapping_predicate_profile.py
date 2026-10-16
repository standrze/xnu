# SPDX-License-Identifier: BSD-2-Clause
"""Predicate-only successor for the observed GEM mapping rejection."""
from pathlib import Path
import hashlib
from tools.rpi5 import gem_cpu_ring_retry_profile as parent

ROOT=parent.ROOT
PARENT=ROOT/'build/rpi5/gem-cpu-ring-retry-trial-20261014-v7'
PARENT_SHA='532968eb3df2fcd6fb8f5dc3addfd11ddd2d1442c66b2ffc7f6de9bf5b744b64'
EVIDENCE=ROOT/'build/rpi5/gem-cpu-ring-retry-successor-capture-20261014/return.json'
EVIDENCE_SHA='0958c0f4b95ebdbae22b32601f1b509f27ecd74814f3c18bb68708c3eba4140f'

def _replace(text,old,new,count=1):
    if text.count(old)!=count:raise ValueError('Exact mapping diagnostic anchor differs')
    return text.replace(old,new)

def derive():
    if hashlib.sha256((PARENT/'manifest.json').read_bytes()).hexdigest()!=PARENT_SHA:
        raise ValueError('Exact ring-retry parent changed')
    if hashlib.sha256(EVIDENCE.read_bytes()).hexdigest()!=EVIDENCE_SHA:
        raise ValueError('Exact step-14 board evidence changed')
    files=parent.derive()
    h=files['BCM2712GEMDMABatch.h'].decode()
    h=_replace(h,'    int preparationError() const { return prepareError_; }','''    int preparationError() const { return prepareError_; }
    unsigned mappingReason() const { return mappingReason_; }
    unsigned mappingPage() const { return mappingPage_; }
    unsigned mappingAttribute() const { return mappingAttribute_; }
    unsigned mappingVAClass() const { return mappingVAClass_; }
    uint64_t mappingPhysical() const { return mappingPhysical_; }
    uint64_t mappingReadPAR() const { return mappingReadPAR_; }
    uint64_t mappingWritePAR() const { return mappingWritePAR_; }''')
    h=_replace(h,'    int prepareError_=0;','''    int prepareError_=0;
    /* Diagnostic-only state; no handle or authority is exposed. */
    mutable unsigned mappingReason_=0,mappingPage_=0,mappingAttribute_=0,mappingVAClass_=0;
    mutable uint64_t mappingPhysical_=0,mappingReadPAR_=0,mappingWritePAR_=0;''')
    files['BCM2712GEMDMABatch.h']=h.encode()

    c=files['BCM2712GEMDMABatch.cpp'].decode()
    old='''static bool translated_nc(uint64_t va, uint64_t physical)
{
    uint64_t saved, read, write;
    boolean_t interrupts=ml_set_interrupts_enabled(FALSE);
    __asm__ volatile("mrs %0, par_el1\\n\\tat s1e1r, %3\\n\\tisb\\n\\tmrs %1, par_el1\\n\\t"
        "at s1e1w, %3\\n\\tisb\\n\\tmrs %2, par_el1\\n\\tmsr par_el1, %0\\n\\tisb"
        : "=&r"(saved), "=&r"(read), "=&r"(write) : "r"(va) : "memory");
    ml_set_interrupts_enabled(interrupts);
    constexpr uint64_t mask=UINT64_C(0x0000fffffffff000);
    return !(read&PAR_F) && !(write&PAR_F) && (read>>56)==0x44 && (write>>56)==0x44 &&
        (read&mask)==(physical&mask) && (write&mask)==(physical&mask);
}'''
    new='''struct rpi5_mapping_translation { bool valid; uint64_t read_par,write_par; };
static struct rpi5_mapping_translation translated_nc(uint64_t va, uint64_t physical)
{
    uint64_t saved, read, write;
    boolean_t interrupts=ml_set_interrupts_enabled(FALSE);
    __asm__ volatile("mrs %0, par_el1\\n\\tat s1e1r, %3\\n\\tisb\\n\\tmrs %1, par_el1\\n\\t"
        "at s1e1w, %3\\n\\tisb\\n\\tmrs %2, par_el1\\n\\tmsr par_el1, %0\\n\\tisb"
        : "=&r"(saved), "=&r"(read), "=&r"(write) : "r"(va) : "memory");
    ml_set_interrupts_enabled(interrupts);
    constexpr uint64_t mask=UINT64_C(0x0000fffffffff000);
    bool valid=!(read&PAR_F) && !(write&PAR_F) && (read>>56)==0x44 && (write>>56)==0x44 &&
        (read&mask)==(physical&mask) && (write&mask)==(physical&mask);
    return {valid,read,write};
}'''
    c=_replace(c,old,new)
    start=c.index('bool BCM2712GEMDMABatch::mapping() const')
    end=c.index('\n}\n\n/* SPDX-License-Identifier: BSD-2-Clause */\nbool BCM2712GEMDMABatch::route',start)+2
    diagnostic='''bool BCM2712GEMDMABatch::mapping() const
{
    mappingReason_=1;mappingPage_=0;mappingAttribute_=0;mappingVAClass_=0;
    mappingPhysical_=0;mappingReadPAR_=0;mappingWritePAR_=0;
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
        auto attr=pmap_cache_attributes((ppnum_t)(pa>>PAGE_SHIFT));
        if (!intact()) return fail(30,page,attr&VM_WIMG_MASK,0,pa,0,0);
        if ((attr&VM_WIMG_MASK)!=VM_WIMG_WCOMB) return fail(31,page,attr&VM_WIMG_MASK,0,pa,0,0);
        auto translation=translated_nc(cpu_+offset,pa);
        if (!intact()) return fail(32,page,attr&VM_WIMG_MASK,1,pa,translation.read_par,translation.write_par);
        if (!translation.valid) return fail(33,page,attr&VM_WIMG_MASK,1,pa,translation.read_par,translation.write_par);
        auto alias=ml_static_ptovirt(pa);
        if (!intact()) return fail(34,page,attr&VM_WIMG_MASK,2,pa,0,0);
        translation=translated_nc(alias,pa);
        if (!intact()) return fail(35,page,attr&VM_WIMG_MASK,2,pa,translation.read_par,translation.write_par);
        if (!translation.valid) return fail(36,page,attr&VM_WIMG_MASK,2,pa,translation.read_par,translation.write_par);
    }
    if (!intact()) return fail(40,2,0,0,0,0,0);
    mappingReason_=41;return true;
}'''
    c=c[:start]+diagnostic+c[end:]
    files['BCM2712GEMDMABatch.cpp']=c.encode()

    th=files['BCM2712PCIePHYTransport.h'].decode()
    th=_replace(th,'    int dmaPreparationError() const { return dmaMemory?dmaMemory->preparationError():0; }','''    int dmaPreparationError() const { return dmaMemory?dmaMemory->preparationError():0; }
    unsigned dmaMappingReason() const { return dmaMemory?dmaMemory->mappingReason():0; }
    unsigned dmaMappingPage() const { return dmaMemory?dmaMemory->mappingPage():0; }
    unsigned dmaMappingAttribute() const { return dmaMemory?dmaMemory->mappingAttribute():0; }
    unsigned dmaMappingVAClass() const { return dmaMemory?dmaMemory->mappingVAClass():0; }
    uint64_t dmaMappingPhysical() const { return dmaMemory?dmaMemory->mappingPhysical():0; }
    uint64_t dmaMappingReadPAR() const { return dmaMemory?dmaMemory->mappingReadPAR():0; }
    uint64_t dmaMappingWritePAR() const { return dmaMemory?dmaMemory->mappingWritePAR():0; }''')
    files['BCM2712PCIePHYTransport.h']=th.encode()
    progress=files['BCM2712PCIeIDTrialProgress.inc'].decode()
    anchor='''    kprintf("RPI5XNU:PCIEID:DMA_OWNER PREPARE=%u'''
    row='''    kprintf("RPI5XNU:PCIEID:DMA_MAP REASON=%u PAGE=%u ATTR=%u VA=%u PA=%llu PAR_R=%llu PAR_W=%llu\\n",
        transport?transport->dmaMappingReason():0,transport?transport->dmaMappingPage():0,
        transport?transport->dmaMappingAttribute():0,transport?transport->dmaMappingVAClass():0,
        (unsigned long long)(transport?transport->dmaMappingPhysical():0),
        (unsigned long long)(transport?transport->dmaMappingReadPAR():0),
        (unsigned long long)(transport?transport->dmaMappingWritePAR():0));
'''
    files['BCM2712PCIeIDTrialProgress.inc']=_replace(progress,anchor,row+anchor).encode()
    return files

def sources():return [Path(__file__).resolve(),*parent.sources(),PARENT/'manifest.json',EVIDENCE]
