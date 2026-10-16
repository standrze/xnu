/* SPDX-License-Identifier: BSD-2-Clause */
#include "bootstrap.h"
int rpi5_bootstrap_mapping(uint64_t phys_base, uint64_t virt_base,
    uint64_t mem_size, uint64_t header_pa, struct rpi5_range usable,
    const struct rpi5_range *required, size_t count, struct rpi5_bootstrap_mapping *out)
{
    const uint64_t limit=1ull<<40, page=1ull<<14, block=1ull<<25;
    if (!out || !required || !count || count>64 || !mem_size || phys_base>=limit ||
        mem_size>limit-phys_base || mem_size>UINT64_MAX-virt_base ||
        ((phys_base|virt_base|header_pa)&(page-1)) || header_pa<phys_base ||
        header_pa-phys_base>=mem_size || usable.start>=usable.end || usable.end>limit) return -1;
    uint64_t delta=header_pa-phys_base, kva=virt_base+delta;
    if (kva!=0xfffffe0007004000ull || (kva&(block-1))!=(header_pa&(block-1))) return -1;
    uint64_t entries=(mem_size-delta)/block;
    if (!entries) return -1;
    struct rpi5_bootstrap_mapping result={0};
    result.entries=entries;
    result.physical_start=header_pa&~(block-1);
    result.virtual_start=kva&~(block-1);
    uint64_t length=entries*block;
    if (length>limit-result.physical_start || length>UINT64_MAX-result.virtual_start) return -1;
    result.physical_end=result.physical_start+length;
    result.virtual_end=result.virtual_start+length;
    uint64_t pages=2+((result.physical_end-1)>>36)-(result.physical_start>>36)+1+
        ((result.virtual_end-1)>>36)-(result.virtual_start>>36)+1;
    if (pages>4 || usable.start>phys_base || phys_base+mem_size>usable.end ||
        usable.start>result.physical_start || result.physical_end>usable.end) return -1;
    result.table_pages=(uint32_t)pages;
    for (size_t i=0;i<count;i++) {
        struct rpi5_range r=required[i];
        if (r.start>=r.end || r.end>limit || r.start<phys_base || r.end>phys_base+mem_size ||
            r.start<result.physical_start || r.end>result.physical_end) return -1;
    }
    *out=result;
    return 0;
}
