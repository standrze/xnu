/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual serialized config + BAR size core; explicit register/mask model. */
#define main prior_config_test_main
#include "pcie_config_host.c"
#undef main
#include "rp1_bar1_probe.h"
static struct rpi5_rp1_bar1_probe *active;
static uint32_t observed_mask;
static unsigned drift_read;
static unsigned char releases[256];
static int bar_authorize(void *context,const struct rpi5_pcie_config_request *r)
{
    return authorize(context,r) || !rpi5_rp1_bar1_write_allowed(active,r) ? -1 : 0;
}
static int bar_read(void *context,uint32_t offset,uint32_t width,uint32_t *out)
{
    struct model *m=context;int rc=read_value(context,offset,width,out);
    if(!rc && offset==0x8014 && active->state==RPI5_RP1_BAR1_PROBING)*out=observed_mask;
    if(!rc && offset>=0x8000 && offset<=0x8014 && m->reads==drift_read)*out^=4;
    return rc;
}
static int bar_write(void *context,uint32_t offset,uint32_t width,uint32_t value)
{
    if(offset!=0x9000) {
        assert(offset==0x8014 && width==4);
        struct rpi5_pcie_config_request r={1,0,0,0x14,4,1,value};
        assert(rpi5_rp1_bar1_write_allowed(active,&r));
    }
    return write_value(context,offset,width,value);
}
static void bar_release(void *context)
{
    struct model *m=context;assert(m->calls+1<sizeof releases);releases[m->calls+1]=1;release(context);
}
static void bar_setup(struct fixture *f,struct rpi5_rp1_bar1_probe *s,struct rpi5_rp1_config_snapshot *expected)
{
    setup(f);memset(s,0,sizeof *s);memset(expected,0,sizeof *expected);memset(releases,0,sizeof releases);
    active=s;observed_mask=0xffc00000;drift_read=0;
    expected->header[0]=0x00011de4;expected->header[1]=0x00100400;expected->command=0x0400;
    expected->header[5]=expected->bar1_pci_base=0x00400000;
    for(unsigned i=0;i<16;i++)for(unsigned j=0;j<4;j++)f->m.bytes[1][i*4+j]=(unsigned char)(expected->header[i]>>(8*j));
    f->config.io.authorize_write=bar_authorize;f->config.io.read=bar_read;
    f->config.io.write=bar_write;f->config.io.release=bar_release;
}
int main(void)
{
    struct fixture f;struct rpi5_rp1_bar1_probe s;struct rpi5_rp1_config_snapshot expected;
    struct rpi5_rp1_bar1_size out;unsigned count;unsigned char nonfailing[256];
    bar_setup(&f,&s,&expected);
    assert(!rpi5_rp1_bar1_probe(&s,&f.config,&expected,&out));
    assert(out.size==0x400000&&out.mask==0xffc00000&&out.original_bar1==0x400000&&out.final_command==0x400);
    assert(s.state==RPI5_RP1_BAR1_COMPLETE&&s.writes_started==2&&out.transactions==13);
    assert(f.m.writes==2&&f.m.reads==11&&f.m.calls==184&&!f.m.locked);
    assert(!memcmp(&f.m.bytes[1][20],&expected.header[5],4));
    assert(f.m.bytes[1][4]==0&&f.m.bytes[1][5]==4&&f.m.bytes[1][6]==0x10&&f.m.bytes[1][7]==0);
    count=f.m.calls;memcpy(nonfailing,releases,sizeof releases);finish(&f);
    unsigned faults=0;
    for(unsigned fault=1;fault<=count;fault++)if(!nonfailing[fault]) {
        bar_setup(&f,&s,&expected);f.m.fail_at=fault;
        memset(&out,0xa5,sizeof out);struct rpi5_rp1_bar1_size before=out;
        assert(rpi5_rp1_bar1_probe(&s,&f.config,&expected,&out));
        assert(s.state==RPI5_RP1_BAR1_FAILED&&!memcmp(&before,&out,sizeof out)&&!f.m.locked);
        unsigned stopped=f.m.calls;assert(rpi5_rp1_bar1_probe(&s,&f.config,&expected,&out)==-2&&f.m.calls==stopped);
        assert(f.m.writes<=2);finish(&f);faults++;
    }
    for(unsigned read=1;read<=11;read++) {
        bar_setup(&f,&s,&expected);drift_read=read;
        memset(&out,0xa5,sizeof out);struct rpi5_rp1_bar1_size before=out;
        int rc=rpi5_rp1_bar1_probe(&s,&f.config,&expected,&out);
        /* A changed cache-line-size byte (read4? no: header type read3) is not
         * part of the type predicate; only that intentionally ignored bit passes. */
        if(read==3)assert(!rc);else assert(rc&&s.state==RPI5_RP1_BAR1_FAILED&&!memcmp(&before,&out,sizeof out));
        finish(&f);
    }
    const uint32_t invalid[]={0,0xffffffff,0xffc00008,0xffb00000,0x7fffffff,0xffc00004};
    for(unsigned i=0;i<sizeof invalid/sizeof invalid[0];i++) {
        bar_setup(&f,&s,&expected);observed_mask=invalid[i];
        assert(rpi5_rp1_bar1_probe(&s,&f.config,&expected,&out)==-6&&s.state==RPI5_RP1_BAR1_FAILED);
        assert(f.m.writes==1);finish(&f); // No speculative restore after failure.
    }
    for(unsigned bit=1;bit<=4;bit*=2) {
        bar_setup(&f,&s,&expected);expected.command|=bit;expected.header[1]|=bit;
        assert(rpi5_rp1_bar1_probe(&s,&f.config,&expected,&out)==-3&&!f.m.calls);finish(&f);
    }
    for(unsigned power=4;power<=31;power++) {
        bar_setup(&f,&s,&expected);expected.bar1_pci_base=expected.header[5]=0;
        memset(&f.m.bytes[1][20],0,4);observed_mask=~((UINT32_C(1)<<power)-1);
        assert(!rpi5_rp1_bar1_probe(&s,&f.config,&expected,&out)&&out.size==(UINT32_C(1)<<power));
        finish(&f);
    }
    struct rpi5_pcie_config_request r={1,0,0,0x14,4,1,UINT32_MAX};
    memset(&s,0,sizeof s);s.state=RPI5_RP1_BAR1_PROBING;s.writes_started=1;
    assert(rpi5_rp1_bar1_write_allowed(&s,&r));
    for(unsigned field=0;field<7;field++) {
        struct rpi5_pcie_config_request bad=r;((uint32_t *)&bad)[field]^=1;
        assert(!rpi5_rp1_bar1_write_allowed(&s,&bad));
    }
    s.state=RPI5_RP1_BAR1_RESTORING;s.writes_started=2;r.value=s.original_bar1=0x400000;
    assert(rpi5_rp1_bar1_write_allowed(&s,&r));
    s.state=RPI5_RP1_BAR1_COMPLETE;assert(!rpi5_rp1_bar1_write_allowed(&s,&r));
    printf("RP1_BAR1_PASS CONFIG_TRANSACTIONS=13 ENDPOINT_WRITES=2 CALLBACK_FAILURES=%u NO_HARDWARE=1\n",faults);
}
