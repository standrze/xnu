/* SPDX-License-Identifier: BSD-2-Clause */
/* Pure candidate geometry tests. Synthetic completed sessions are NOT physical
 * receipts; rp1_bars_probe_host separately exercises this with actual core output. */
#include "rp1_bars_plan.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct fixture {
    struct rpi5_pcie_fdt f;
    struct rpi5_rp1_bars_probe s;
    struct rpi5_rp1_bars_size z;
};
static void setup(struct fixture *v)
{
    memset(v,0,sizeof *v);
    v->f.outbound_count=2;
    v->f.outbound[0]=(struct rpi5_pcie_window){0x02000000,0,UINT64_C(0x1f00000000),0xfffffffc};
    v->f.outbound[1]=(struct rpi5_pcie_window){0x43000000,UINT64_C(0x400000000),UINT64_C(0x1c00000000),UINT64_C(0x300000000)};
    v->f.rp1_aperture_size=0x410000;
    v->f.gem_bar_offset=0x100000;v->f.gem_size=0x4000;
    v->f.clock_bar_offset=0x18000;v->f.clock_size=0x10038;
    v->s.state=RPI5_RP1_BARS_COMPLETE;v->s.selected=5;v->s.writes_started=12;v->s.transactions=49;
    v->z.present=7;v->z.command=0x400;v->z.transactions=49;
    const uint32_t sizes[3]={0x4000,0x400000,0x10000},bases[3]={0x410000,0,0x400000};
    for(unsigned i=0;i<3;i++) {
        v->z.bar[i]=(struct rpi5_rp1_bar_size){bases[i],~(sizes[i]-1),sizes[i]};
        v->s.originals[i]=bases[i];
    }
}
static struct rpi5_rp1_bars_plan accepted(const struct fixture *v)
{
    struct rpi5_rp1_bars_plan p;
    assert(!rpi5_rp1_bars_assignment_plan(&v->f,&v->s,&v->z,&p));
    assert(p.present==v->z.present&&p.pci_base[1]==0);
    for(unsigned i=0;i<6;i++) {
        if(!(p.present&(1u<<i))) {assert(!p.pci_base[i]&&!p.cpu[i].start&&!p.cpu[i].end);continue;}
        assert(!(p.pci_base[i]&(v->z.bar[i].size-1)));
        assert(p.cpu[i].start==v->f.outbound[0].cpu_base+p.pci_base[i]);
        assert(p.cpu[i].end-p.cpu[i].start==v->z.bar[i].size);
        assert(p.cpu[i].end<=v->f.outbound[0].cpu_base+v->f.outbound[0].size);
        assert((uint64_t)p.pci_base[i]+v->z.bar[i].size<=UINT64_C(0x100000000));
        for(unsigned j=i+1;j<6;j++)if(p.present&(1u<<j))
            assert(p.cpu[i].end<=p.cpu[j].start||p.cpu[j].end<=p.cpu[i].start);
    }
    assert(!(p.gem_pages.start&0x3fff)&&!(p.gem_pages.end&0x3fff));
    assert(!(p.clock_pages.start&0x3fff)&&!(p.clock_pages.end&0x3fff));
    assert(p.gem_pages.start>=p.cpu[1].start&&p.gem_pages.end<=p.cpu[1].end);
    assert(p.clock_pages.start>=p.cpu[1].start&&p.clock_pages.end<=p.cpu[1].end);
    assert(p.clock_pages.end<=p.gem_pages.start||p.gem_pages.end<=p.clock_pages.start);
    return p;
}
static void rejected(const struct fixture *v)
{
    struct rpi5_rp1_bars_plan out,before;
    memset(&out,0xa5,sizeof out);before=out;
    assert(rpi5_rp1_bars_assignment_plan(&v->f,&v->s,&v->z,&out));
    assert(!memcmp(&out,&before,sizeof out));
}
int main(void)
{
    struct fixture v;setup(&v);
    struct rpi5_rp1_bars_plan p=accepted(&v);
    assert(p.pci_base[0]==0x410000&&p.pci_base[2]==0x400000);
    assert(p.gem_pages.start==UINT64_C(0x1f00100000)&&p.gem_pages.end==UINT64_C(0x1f00104000));
    assert(p.clock_pages.start==UINT64_C(0x1f00018000)&&p.clock_pages.end==UINT64_C(0x1f0002c000));
    unsigned cases=0;
    for(unsigned present=0;present<64;present++)if(present&2) {
        for(unsigned bar=0;bar<6;bar++)for(unsigned power=(bar==1?21:4);power<=28;power++) {
            setup(&v);v.z.present=present;
            for(unsigned i=0;i<6;i++) {
                v.s.originals[i]=0;
                uint32_t size=i==bar?(UINT32_C(1)<<power):(i==1?0x400000:0x4000);
                v.z.bar[i]=(struct rpi5_rp1_bar_size){0,(present&(1u<<i))?~(size-1):0,(present&(1u<<i))?size:0};
            }
            accepted(&v);cases++;
        }
    }
    for(unsigned mutation=0;mutation<34;mutation++) {
        setup(&v);
        switch(mutation) {
        case 0:v.s.state=RPI5_RP1_BARS_FAILED;break;
        case 1:v.s.transactions--;break;
        case 2:v.s.writes_started--;break;
        case 3:v.s.selected--;break;
        case 4:v.z.transactions--;break;
        case 5:v.z.command|=1;break;
        case 6:v.z.command|=2;break;
        case 7:v.z.command|=4;break;
        case 8:v.z.command|=0x10000;break;
        case 9:v.z.present|=64;break;
        case 10:v.z.present&=~2u;break;
        case 11:v.f.outbound_count=0;break;
        case 12:v.f.outbound_count=3;break;
        case 13:v.f.rp1_pci_base=0x100000;break;
        case 14:v.f.rp1_aperture_size=0;break;
        case 15:v.f.outbound[0].space=0x01000000;break;
        case 16:v.f.outbound[0].size=UINT64_MAX;break;
        case 17:v.f.outbound[0].cpu_base=UINT64_C(1)<<40;break;
        case 18:v.f.outbound[0].cpu_base=(UINT64_C(1)<<40)-0x100000;break;
        case 19:v.f.outbound[1].cpu_base=v.f.outbound[0].cpu_base;break;
        case 20:v.f.outbound[1].pci_base=0;break;
        case 21:v.f.outbound[1]=v.f.outbound[0];break;
        case 22:v.f.outbound[0].pci_base=0x100000;v.f.outbound[0].size=0x500000;break;
        case 23:v.f.outbound[0].cpu_base+=0x4000;break;
        case 24:v.f.outbound[0].size=0x413fff;break;
        case 25:v.f.rp1_aperture_size=v.f.outbound[0].size+1;break;
        case 26:v.f.gem_bar_offset=UINT64_MAX;break;
        case 27:v.f.gem_size=UINT64_MAX;break;
        case 28:v.f.clock_size=0;break;
        case 29:v.f.clock_bar_offset=0x3fffff;v.f.clock_size=2;break;
        case 30:v.f.gem_bar_offset=0x410000;break;
        case 31:v.f.clock_bar_offset=v.f.gem_bar_offset;break;
        case 32:v.f.outbound[1].size=0;break;
        case 33:v.f.outbound[1].pci_base=UINT64_MAX;break;
        }
        rejected(&v);
    }
    for(unsigned bar=0;bar<6;bar++)for(unsigned mutation=0;mutation<8;mutation++) {
        setup(&v);v.z.present=63;
        for(unsigned i=3;i<6;i++)v.z.bar[i]=(struct rpi5_rp1_bar_size){0,0xffffc000,0x4000};
        switch(mutation) {
        case 0:v.z.bar[bar].original^=0x10;break;
        case 1:v.z.bar[bar].original|=4;v.s.originals[bar]|=4;break;
        case 2:v.z.bar[bar].mask|=8;break;
        case 3:v.z.bar[bar].size=0;break;
        case 4:v.z.bar[bar].size=0x3000;break;
        case 5:v.z.bar[bar].size=8;break;
        case 6:v.z.bar[bar].mask=0;break;
        case 7:v.z.present&=~(1u<<bar);break;
        }
        rejected(&v);
    }
    /* A pair of 2-GiB BARs cannot coexist with the rest inside the declared
     * four-byte-short 32-bit window. The planner uses 64-bit intermediates. */
    setup(&v);v.z.bar[0]=(struct rpi5_rp1_bar_size){0,0x80000000,0x80000000};
    v.z.bar[1]=v.z.bar[0];v.s.originals[0]=0;rejected(&v);
    setup(&v);assert(rpi5_rp1_bars_assignment_plan(0,&v.s,&v.z,&p));
    assert(rpi5_rp1_bars_assignment_plan(&v.f,0,&v.z,&p));
    assert(rpi5_rp1_bars_assignment_plan(&v.f,&v.s,0,&p));
    assert(rpi5_rp1_bars_assignment_plan(&v.f,&v.s,&v.z,0));
    printf("RP1_BARS_PLAN_PASS LAYOUTS=%u REJECTED=83 PURE_CANDIDATE=1 NO_HARDWARE=1\n",cases);
}
