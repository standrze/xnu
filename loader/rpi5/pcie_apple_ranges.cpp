/* SPDX-License-Identifier: BSD-2-Clause */
/* Board policy around unmodified Apple IOPCIRange; not a second allocator. */
#include "pcie_apple_ranges.h"
#include <IOKit/pci/IOPCIPrivate.h>

extern "C" void rpi5_apple_range_zero(void *p, size_t n)
{
    volatile unsigned char *bytes=static_cast<volatile unsigned char *>(p);
    for (size_t i=0;i<n;i++) bytes[i]=0;
}
extern "C" [[noreturn]] void *rpi5_apple_range_unsupported(void)
{
    __builtin_trap();
}
extern "C" void rpi5_apple_range_log(const char *, ...)
{
    /* No hidden logger/heap dependency: diagnostic-only upstream paths are not
     * in this adapter's call graph. An accidental call fails visibly. */
    __builtin_trap();
}

static bool span(uint64_t base,uint64_t size,uint64_t limit)
{
    return size && base<limit && size<=limit-base;
}
static bool overlaps(uint64_t a,uint64_t ae,uint64_t b,uint64_t be)
{
    return a<be && b<ae;
}

int rpi5_apple_rp1_bar_candidates(const struct rpi5_pcie_window *windows,
    uint32_t count,const uint64_t sizes[RPI5_RP1_BAR_COUNT],
    const struct rpi5_range *reserved,uint32_t nreserved,
    struct rpi5_rp1_bar_candidates *out)
{
    if (!windows || !sizes || !out || count<1 || count>2 ||
        nreserved>RPI5_PCI_RESERVED_MAX || (nreserved && !reserved))
        return RPI5_APPLE_RANGE_ARGUMENT;
    const struct rpi5_pcie_window *memory=nullptr;
    for (uint32_t i=0;i<count;i++) {
        const auto &w=windows[i];
        if ((w.space!=UINT32_C(0x02000000) && w.space!=UINT32_C(0x43000000)) ||
            !span(w.pci_base,w.size,UINT64_C(1)<<40) ||
            !span(w.cpu_base,w.size,UINT64_C(1)<<40)) return RPI5_APPLE_RANGE_PROFILE;
        if (w.space==UINT32_C(0x02000000)) {
            if (memory || !span(w.pci_base,w.size,UINT64_C(1)<<32))
                return RPI5_APPLE_RANGE_PROFILE;
            memory=&w;
        }
        for (uint32_t j=0;j<i;j++) {
            const auto &v=windows[j];
            if (overlaps(w.cpu_base,w.cpu_base+w.size,v.cpu_base,v.cpu_base+v.size) ||
                overlaps(w.pci_base,w.pci_base+w.size,v.pci_base,v.pci_base+v.size))
                return RPI5_APPLE_RANGE_PROFILE;
        }
    }
    if (!memory) return RPI5_APPLE_RANGE_PROFILE;
    uint64_t end=memory->pci_base+memory->size;
    for (uint32_t i=0;i<RPI5_RP1_BAR_COUNT;i++)
        if (sizes[i]<16 || (sizes[i]&(sizes[i]-1)) || sizes[i]>memory->size)
            return RPI5_APPLE_RANGE_PROFILE;
    for (uint32_t i=0;i<nreserved;i++) {
        const auto &r=reserved[i];
        if (r.start<memory->pci_base || r.start>=r.end || r.end>end)
            return RPI5_APPLE_RANGE_PROFILE;
        for (uint32_t j=0;j<i;j++)
            if (overlaps(r.start,r.end,reserved[j].start,reserved[j].end))
                return RPI5_APPLE_RANGE_PROFILE;
    }

    IOPCIRange head, occupied[RPI5_PCI_RESERVED_MAX], bars[RPI5_RP1_BAR_COUNT];
    IOPCIRangeInitAlloc(&head,0,memory->pci_base,memory->size,1);
    for (uint32_t i=0;i<nreserved;i++) {
        const auto &r=reserved[i];
        IOPCIRangeInit(&occupied[i],0,r.start,r.end-r.start,1);
        occupied[i].maxAddress=end;
        if (!IOPCIRangeListAllocateSubRange(&head,&occupied[i],r.start) ||
            occupied[i].start!=r.start || occupied[i].end!=r.end)
            return RPI5_APPLE_RANGE_INVARIANT;
    }
    unsigned order[3]={0,1,2};
    for (unsigned i=0;i<3;i++) for (unsigned j=i+1;j<3;j++)
        if (sizes[order[j]]>sizes[order[i]]) {
            unsigned n=order[i]; order[i]=order[j]; order[j]=n;
        }
    for (unsigned n=0;n<3;n++) {
        unsigned i=order[n];
        IOPCIRangeInit(&bars[i],0,0,sizes[i],sizes[i]);
        bars[i].maxAddress=end;
        if (!IOPCIRangeListAllocateSubRange(&head,&bars[i])) return RPI5_APPLE_RANGE_NO_SPACE;
        if (bars[i].size!=sizes[i] || bars[i].start<memory->pci_base ||
            bars[i].end>end || bars[i].end-bars[i].start!=sizes[i] ||
            (bars[i].start&(sizes[i]-1))) return RPI5_APPLE_RANGE_INVARIANT;
    }
    for (unsigned i=0;i<3;i++) {
        for (unsigned j=0;j<i;j++)
            if (overlaps(bars[i].start,bars[i].end,bars[j].start,bars[j].end))
                return RPI5_APPLE_RANGE_INVARIANT;
        for (uint32_t j=0;j<nreserved;j++)
            if (overlaps(bars[i].start,bars[i].end,reserved[j].start,reserved[j].end))
                return RPI5_APPLE_RANGE_INVARIANT;
    }
    for (unsigned i=0;i<3;i++) {
        out->bar[i].pci_base=bars[i].start;
        out->bar[i].size=bars[i].size;
    }
    return RPI5_APPLE_RANGE_OK;
}
