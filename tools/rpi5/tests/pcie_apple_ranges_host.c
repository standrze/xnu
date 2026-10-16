/* SPDX-License-Identifier: BSD-2-Clause */
/* Original Apple allocator + board policy, synthetic resources, no MMIO. */
#include "pcie_apple_ranges.h"
#include "pcie_resource_plan.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static const struct rpi5_pcie_window native_windows[2]={
    {0x02000000,0,0x1f00000000ull,0xfffffffc},
    {0x43000000,0x400000000ull,0x1c00000000ull,0x300000000ull}
};
/* Sizes match the saved Linux reference, but this run is a synthetic model. */
static const uint64_t native_sizes[3]={0x4000,0x400000,0x10000};

static int rejected(const struct rpi5_pcie_window *w,unsigned count,
    const uint64_t *sizes,const struct rpi5_range *r,unsigned nr)
{
    struct rpi5_rp1_bar_candidates before,out;
    memset(&before,0xa5,sizeof before); out=before;
    int rc=rpi5_apple_rp1_bar_candidates(w,count,sizes,r,nr,&out);
    assert(rc && !memcmp(&before,&out,sizeof out));
    return rc;
}
static void valid(const struct rpi5_pcie_window *w,const uint64_t *sizes,
    const struct rpi5_range *r,unsigned nr,const struct rpi5_rp1_bar_candidates *out)
{
    for (unsigned i=0;i<3;i++) {
        uint64_t base=out->bar[i].pci_base,end=base+sizes[i];
        assert(out->bar[i].size==sizes[i] && !(base&(sizes[i]-1)));
        assert(base>=w->pci_base && end<=w->pci_base+w->size);
        for (unsigned j=0;j<i;j++)
            assert(end<=out->bar[j].pci_base || base>=out->bar[j].pci_base+sizes[j]);
        for (unsigned j=0;j<nr;j++) assert(end<=r[j].start || base>=r[j].end);
    }
}

int main(void)
{
    struct rpi5_rp1_bar_candidates out;
    assert(!rpi5_apple_rp1_bar_candidates(native_windows,2,native_sizes,NULL,0,&out));
    assert(out.bar[0].pci_base==0x410000 && out.bar[1].pci_base==0 && out.bar[2].pci_base==0x400000);
    valid(native_windows,native_sizes,NULL,0,&out);
    /* A separate MODEL of later assignment/readback, not a candidate promoted
     * into hardware evidence. Reuse the existing CPU translation planner. */
    struct rpi5_pcie_fdt binding={0};
    binding.outbound[0]=native_windows[0]; binding.outbound[1]=native_windows[1];
    binding.outbound_count=2; binding.rp1_aperture_size=0x410000;
    binding.gem_bar_offset=0x100000; binding.gem_size=0x4000;
    binding.clock_bar_offset=0x18000; binding.clock_size=0x10038;
    struct rpi5_rp1_bar_observation live={0x1de4,1,1,1,1,0x02000000,0,0x400000};
    struct rpi5_pcie_resource_plan mapped;
    assert(!rpi5_pcie_resource_plan(&binding,&live,&mapped));
    assert(mapped.gem_cpu.start==0x1f00100000ull && mapped.clock_pages.end==0x1f0002c000ull);

    struct rpi5_range occupied[8]={{0,0x1000},{0x800000,0x801000}};
    assert(!rpi5_apple_rp1_bar_candidates(native_windows,2,native_sizes,occupied,2,&out));
    assert(out.bar[1].pci_base==0x400000);
    valid(native_windows,native_sizes,occupied,2,&out);
    /* Input reservation order is not an ordering authority. */
    struct rpi5_range reverse[2]={occupied[1],occupied[0]};
    struct rpi5_rp1_bar_candidates reordered;
    assert(!rpi5_apple_rp1_bar_candidates(native_windows,2,native_sizes,reverse,2,&reordered));
    assert(!memcmp(&out,&reordered,sizeof out));

    assert(rejected(NULL,2,native_sizes,NULL,0)==RPI5_APPLE_RANGE_ARGUMENT);
    assert(rejected(native_windows,0,native_sizes,NULL,0)==RPI5_APPLE_RANGE_ARGUMENT);
    assert(rejected(native_windows,3,native_sizes,NULL,0)==RPI5_APPLE_RANGE_ARGUMENT);
    assert(rejected(native_windows,2,NULL,NULL,0)==RPI5_APPLE_RANGE_ARGUMENT);
    assert(rejected(native_windows,2,native_sizes,NULL,1)==RPI5_APPLE_RANGE_ARGUMENT);
    assert(rejected(native_windows,2,native_sizes,occupied,9)==RPI5_APPLE_RANGE_ARGUMENT);
    assert(rpi5_apple_rp1_bar_candidates(native_windows,2,native_sizes,NULL,0,NULL)==RPI5_APPLE_RANGE_ARGUMENT);
    const uint64_t bad_sizes[]={0,1,8,17,0x1001,UINT64_MAX,0x100000000ull};
    for (unsigned index=0;index<3;index++) for (unsigned j=0;j<sizeof bad_sizes/sizeof bad_sizes[0];j++) {
        uint64_t sizes[3]; memcpy(sizes,native_sizes,sizeof sizes); sizes[index]=bad_sizes[j];
        assert(rejected(native_windows,2,sizes,NULL,0)==RPI5_APPLE_RANGE_PROFILE);
    }
    for (unsigned field=0;field<8;field++) {
        struct rpi5_pcie_window w[2]; memcpy(w,native_windows,sizeof w);
        if (field==0) w[0].space=0x01000000;
        if (field==1) w[0].space=0x43000000;
        if (field==2) w[1].space=0x02000000;
        if (field==3) w[0].size=0;
        if (field==4) w[0].size=0x100000001ull;
        if (field==5) w[1].cpu_base=w[0].cpu_base;
        if (field==6) w[1].pci_base=0x80000000;
        if (field==7) w[1].cpu_base=UINT64_MAX;
        assert(rejected(w,2,native_sizes,NULL,0)==RPI5_APPLE_RANGE_PROFILE);
    }
    const struct rpi5_range bad_reserved[][2]={
        {{1,1},{0,0}}, {{2,1},{0,0}}, {{0,0x100000000ull},{0,0}},
        {{0,0x1000},{0x800,0x2000}}, {{0,0x1000},{0,0x1000}}
    };
    for (unsigned i=0;i<sizeof bad_reserved/sizeof bad_reserved[0];i++)
        assert(rejected(native_windows,2,native_sizes,bad_reserved[i],i<3?1:2)==RPI5_APPLE_RANGE_PROFILE);

    /* Only declared MEM32 bytes: no allocation into the 4-byte decode excess.
     * Full 2^32 endpoint is nevertheless representable for other declarations. */
    struct rpi5_pcie_window end_window={0x02000000,0xfffffff0,0x1f00000000ull,12};
    const uint64_t tiny[3]={16,16,16};
    assert(rejected(&end_window,1,tiny,NULL,0)==RPI5_APPLE_RANGE_PROFILE);
    end_window.pci_base=0xffffffc0; end_window.size=64;
    assert(!rpi5_apple_rp1_bar_candidates(&end_window,1,tiny,NULL,0,&out));
    valid(&end_window,tiny,NULL,0,&out);

    /* 4,096 deterministic bounded fragmented-window cases. Success must fit
     * all reservations; an exhausted case must leave the output untouched. */
    unsigned successes=0,exhausted=0;
    struct rpi5_pcie_window small={0x02000000,0,0x1f00000000ull,1024};
    for (unsigned mask=0;mask<256;mask++) for (unsigned shape=0;shape<16;shape++) {
        unsigned nr=0;
        for (unsigned bit=0;bit<8;bit++) if (mask&(1u<<bit))
            occupied[nr++]=(struct rpi5_range){bit*128,bit*128+64};
        uint64_t sizes[3]={16ull<<(shape&3),16ull<<((shape>>2)&3),64};
        struct rpi5_rp1_bar_candidates before;
        memset(&before,0xa5,sizeof before); out=before;
        int rc=rpi5_apple_rp1_bar_candidates(&small,1,sizes,occupied,nr,&out);
        if (!rc) { successes++; valid(&small,sizes,occupied,nr,&out); }
        else { exhausted++; assert(rc==RPI5_APPLE_RANGE_NO_SPACE && !memcmp(&out,&before,sizeof out)); }
    }
    assert(successes && exhausted);
    printf("APPLE_RANGE_HOST_PASS CASES=4096 SUCCESS=%u EXHAUSTED=%u NO_MMIO=1\n",successes,exhausted);
    return 0;
}
