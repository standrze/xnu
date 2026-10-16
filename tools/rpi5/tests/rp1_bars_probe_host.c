/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual config engine and all-BAR core with explicit register/mask doubles. */
#define main prior_config_test_main
#include "pcie_config_host.c"
#undef main
#include "rp1_bars_probe.h"
#include "rp1_bars_plan.h"
static struct rpi5_rp1_bars_probe *active;
static uint32_t masks[6];
static unsigned char releases[1024];
static unsigned corrupt_read;
static int bars_authorize(void *context,const struct rpi5_pcie_config_request *r)
{
    return authorize(context,r) || !rpi5_rp1_bars_write_allowed(active,r) ? -1 : 0;
}
static int bars_read(void *context,uint32_t offset,uint32_t width,uint32_t *out)
{
    int rc=read_value(context,offset,width,out);
    if(!rc && offset==0x8010+4*active->selected && active->state==RPI5_RP1_BARS_PROBING)
        *out=masks[active->selected];
    struct model *m=context;
    if(!rc && offset>=0x8000 && offset<0x9000 && m->reads==corrupt_read)
        *out^=offset==0x800c?0x10000:1;
    return rc;
}
static int bars_write(void *context,uint32_t offset,uint32_t width,uint32_t value)
{
    if(offset!=0x9000) {
        assert(offset>=0x8010&&offset<=0x8024&&width==4);
        const struct rpi5_pcie_config_request r={1,0,0,offset-0x8000,4,1,value};
        assert(rpi5_rp1_bars_write_allowed(active,&r));
    }
    return write_value(context,offset,width,value);
}
static void bars_release(void *context)
{
    struct model *m=context;assert(m->calls+1<sizeof releases);releases[m->calls+1]=1;release(context);
}
static void bars_setup(struct fixture *f,struct rpi5_rp1_bars_probe *s,struct rpi5_rp1_config_snapshot *expected)
{
    setup(f);memset(s,0,sizeof *s);memset(expected,0,sizeof *expected);memset(releases,0,sizeof releases);
    active=s;corrupt_read=0;masks[0]=0xffffc000;masks[1]=0xffc00000;masks[2]=0xffff0000;
    masks[3]=masks[4]=masks[5]=0;
    expected->header[0]=0x00011de4;expected->header[1]=0x00100400;expected->command=0x0400;
    expected->header[4]=0x410000;expected->header[6]=0x400000;
    for(unsigned i=0;i<16;i++)for(unsigned j=0;j<4;j++)f->m.bytes[1][i*4+j]=(unsigned char)(expected->header[i]>>(8*j));
    f->config.io.authorize_write=bars_authorize;f->config.io.read=bars_read;
    f->config.io.write=bars_write;f->config.io.release=bars_release;
}
/* Under the explicit posted-store model only the currently probed slot may
 * retain its all-ones request. No recovery accesses are authorized on failure.
 * Real BAR readback masks hardwired bits; this is a bounded write-set check,
 * not a claim of restoration after the lease or transport failed. */
static void bounded_partial(const struct fixture *f,const struct rpi5_rp1_bars_probe *s,
    const unsigned char before[2][4096])
{
    assert(!memcmp(f->m.bytes[0],before[0],4096));
    for(unsigned off=0;off<4096;off++) {
        if(off>=0x10+4*s->selected && off<0x14+4*s->selected)continue;
        assert(f->m.bytes[1][off]==before[1][off]);
    }
    uint32_t value;memcpy(&value,&f->m.bytes[1][0x10+4*s->selected],4);
    uint32_t original;memcpy(&original,&before[1][0x10+4*s->selected],4);
    assert(value==original || value==UINT32_MAX);
}
int main(void)
{
    struct fixture f;struct rpi5_rp1_bars_probe s;struct rpi5_rp1_config_snapshot expected;
    struct rpi5_rp1_bars_size out;unsigned count;unsigned char nonfailing[1024];
    bars_setup(&f,&s,&expected);
    assert(!rpi5_rp1_bars_probe(&s,&f.config,&expected,&out));
    assert(out.present==7&&out.command==0x400&&out.transactions==49);
    assert(out.bar[0].size==0x4000&&out.bar[1].size==0x400000&&out.bar[2].size==0x10000);
    assert(s.state==RPI5_RP1_BARS_COMPLETE&&s.writes_started==12);
    assert(f.m.writes==12&&f.m.reads==37&&!f.m.locked);
    for(unsigned i=0;i<6;i++)assert(!memcmp(&f.m.bytes[1][16+4*i],&expected.header[4+i],4));
    assert(f.m.bytes[1][4]==0&&f.m.bytes[1][5]==4&&f.m.bytes[1][6]==0x10&&f.m.bytes[1][7]==0);
    struct rpi5_pcie_fdt binding={0};binding.outbound_count=1;
    binding.outbound[0]=(struct rpi5_pcie_window){0x02000000,0,UINT64_C(0x1f00000000),0xfffffffc};
    binding.rp1_aperture_size=0x410000;binding.gem_bar_offset=0x100000;binding.gem_size=0x4000;
    binding.clock_bar_offset=0x18000;binding.clock_size=0x10038;
    struct rpi5_rp1_bars_plan plan;
    assert(!rpi5_rp1_bars_assignment_plan(&binding,&s,&out,&plan));
    assert(plan.pci_base[0]==0x410000&&plan.pci_base[1]==0&&plan.pci_base[2]==0x400000);
    count=f.m.calls;memcpy(nonfailing,releases,sizeof releases);finish(&f);
    unsigned faults=0;
    for(unsigned fault=1;fault<=count;fault++)if(!nonfailing[fault]) {
        bars_setup(&f,&s,&expected);f.m.fail_at=fault;
        unsigned char initial[2][4096];memcpy(initial,f.m.bytes,sizeof initial);
        memset(&out,0xa5,sizeof out);struct rpi5_rp1_bars_size before=out;
        assert(rpi5_rp1_bars_probe(&s,&f.config,&expected,&out));
        assert(s.state==RPI5_RP1_BARS_FAILED&&!memcmp(&before,&out,sizeof out)&&!f.m.locked);
        assert(f.m.calls==fault || f.m.calls==fault+1);bounded_partial(&f,&s,initial);
        unsigned stopped=f.m.calls;assert(rpi5_rp1_bars_probe(&s,&f.config,&expected,&out)==-2&&f.m.calls==stopped);
        assert(f.m.writes<=12);finish(&f);faults++;
    }
    for(unsigned read=1;read<=37;read++) {
        bars_setup(&f,&s,&expected);corrupt_read=read;
        unsigned char initial[2][4096];memcpy(initial,f.m.bytes,sizeof initial);
        memset(&out,0xa5,sizeof out);struct rpi5_rp1_bars_size before=out;
        assert(rpi5_rp1_bars_probe(&s,&f.config,&expected,&out));
        assert(s.state==RPI5_RP1_BARS_FAILED&&!memcmp(&before,&out,sizeof out));
        assert(f.m.reads==read);bounded_partial(&f,&s,initial);finish(&f);
    }
    const uint32_t invalid[]={0xffffffff,0xffc00008,0xffb00000,0x7fffffff,0xffc00004};
    for(unsigned bar=0;bar<6;bar++)for(unsigned i=0;i<sizeof invalid/sizeof invalid[0];i++) {
        bars_setup(&f,&s,&expected);masks[bar]=invalid[i];
        assert(rpi5_rp1_bars_probe(&s,&f.config,&expected,&out)==-6&&s.state==RPI5_RP1_BARS_FAILED);
        assert(f.m.writes==bar*2+1);finish(&f);
    }
    for(unsigned bad=0;bad<12;bad++) {
        bars_setup(&f,&s,&expected);
        if(bad<3){expected.command|=1u<<bad;expected.header[1]|=1u<<bad;}
        else if(bad==3)expected.header[12]=1;
        else if(bad==4)expected.header[3]=0x010000;
        else if(bad==5)expected.header[0]^=1;
        else expected.header[bad-2]|=4;
        assert(rpi5_rp1_bars_probe(&s,&f.config,&expected,&out)==-3&&!f.m.calls);finish(&f);
    }
    /* All low-nibble shapes, including IO, obsolete/reserved memory types,
     * prefetch and 64-bit pairs (including an impossible pair at slot 5), are
     * rejected before the first config access. No high half can be sized as
     * an independent MEM32 BAR. The RP1 inventory admits MEM32 only. */
    for(unsigned bar=0;bar<6;bar++)for(unsigned attributes=1;attributes<16;attributes++) {
        bars_setup(&f,&s,&expected);expected.header[4+bar]|=attributes;
        if(bar<5 && (attributes&6)==4)expected.header[5+bar]=0x12340000;
        expected.bar1_pci_base=expected.header[5];
        assert(rpi5_rp1_bars_probe(&s,&f.config,&expected,&out)==-3&&!f.m.calls);finish(&f);
    }
    for(unsigned bar=0;bar<6;bar++)for(unsigned power=4;power<=31;power++) {
        bars_setup(&f,&s,&expected);expected.header[4+bar]=0;memset(&f.m.bytes[1][16+4*bar],0,4);
        masks[bar]=~((UINT32_C(1)<<power)-1);
        assert(!rpi5_rp1_bars_probe(&s,&f.config,&expected,&out)&&out.bar[bar].size==(UINT32_C(1)<<power));finish(&f);
    }
    for(unsigned bar=0;bar<3;bar++) {
        bars_setup(&f,&s,&expected);masks[bar]=0;
        assert(rpi5_rp1_bars_probe(&s,&f.config,&expected,&out)==-6);finish(&f);
    }
    for(unsigned selected=0;selected<6;selected++) {
        memset(&s,0,sizeof s);s.selected=selected;s.state=RPI5_RP1_BARS_PROBING;s.writes_started=2*selected+1;
        struct rpi5_pcie_config_request r={1,0,0,0x10+4*selected,4,1,UINT32_MAX};
        assert(rpi5_rp1_bars_write_allowed(&s,&r));
        for(unsigned field=0;field<7;field++) {
            struct rpi5_pcie_config_request bad=r;((uint32_t *)&bad)[field]^=1;
            assert(!rpi5_rp1_bars_write_allowed(&s,&bad));
        }
        s.state=RPI5_RP1_BARS_RESTORING;s.writes_started++;r.value=s.originals[selected]=0x400000;
        assert(rpi5_rp1_bars_write_allowed(&s,&r));
        s.state=RPI5_RP1_BARS_COMPLETE;assert(!rpi5_rp1_bars_write_allowed(&s,&r));
    }
    printf("RP1_BARS_PASS CONFIG_TRANSACTIONS=49 ENDPOINT_WRITES=12 CALLBACK_FAILURES=%u ALL_SLOTS=6 NO_HARDWARE=1\n",faults);
}
