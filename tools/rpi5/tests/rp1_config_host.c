/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual config/snapshot cores, reused explicit RAM/ownership model. */
#define main prior_config_test_main
#include "pcie_config_host.c"
#undef main
#include "rp1_config_snapshot.h"
#include "iokit/Kernel/BCM2712RP1ConfigPolicy.h"
static unsigned mutate_read;
static int snapshot_read(void *context, uint32_t offset, uint32_t width, uint32_t *out)
{
    struct model *m=context;
    int result=read_value(context,offset,width,out);
    if (!result && offset>=0x8000 && offset<=0x803c && m->reads==mutate_read) *out ^= 1;
    return result;
}
static void snapshot_setup(struct fixture *f)
{
    setup(f); mutate_read=0;
    uint32_t words[16]={0x00011de4,0x00100002,0x02000002,0,0,0x00400000};
    for(unsigned i=0;i<16;i++) for(unsigned j=0;j<4;j++) f->m.bytes[1][4*i+j]=(unsigned char)(words[i]>>(8*j));
    f->config.io.read=snapshot_read;
}
int main(void)
{
    struct fixture f; struct rpi5_rp1_config_snapshot out;
    snapshot_setup(&f);
    assert(!rpi5_rp1_config_snapshot(&f.config,&out));
    assert(out.header[0]==0x00011de4 && out.bar1_pci_base==0x00400000 && out.command==2 && out.status==0x10 && out.revision==2);
    assert(f.m.reads==32 && f.m.writes==0 && f.m.calls==448 && !f.m.locked);
    finish(&f);
    unsigned faults=0;
    for(unsigned position=1;position<=448;position++) {
        if(position%14==0)continue; /* release cannot fail */
        snapshot_setup(&f);f.m.fail_at=position;
        memset(&out,0xa5,sizeof out);struct rpi5_rp1_config_snapshot untouched=out;
        assert(rpi5_rp1_config_snapshot(&f.config,&out));
        assert(!memcmp(&out,&untouched,sizeof out));assert(!f.m.writes && !f.m.locked);
        assert(f.m.calls==position+((position-1)%14?1:0));
        finish(&f);faults++;
    }
    for(unsigned index=0;index<16;index++) {
        snapshot_setup(&f);mutate_read=17+index;
        memset(&out,0xa5,sizeof out);struct rpi5_rp1_config_snapshot untouched=out;
        assert(rpi5_rp1_config_snapshot(&f.config,&out)==-3);
        assert(!memcmp(&out,&untouched,sizeof out) && f.m.reads==17+index);
        finish(&f);
    }
    for(unsigned field=0;field<3;field++) {
        snapshot_setup(&f);f.m.bytes[1][field==0?0:field==1?14:20]|=field==0?2:1;
        memset(&out,0xa5,sizeof out);struct rpi5_rp1_config_snapshot untouched=out;
        assert(rpi5_rp1_config_snapshot(&f.config,&out)==-4);
        assert(!memcmp(&out,&untouched,sizeof out));finish(&f);
    }
    snapshot_setup(&f);
    memset(&f.m.bytes[1][20],0,4);f.m.bytes[1][4]=0;
    assert(!rpi5_rp1_config_snapshot(&f.config,&out) && !out.bar1_pci_base && !out.command);
    finish(&f); /* Address zero/decode disabled remain observations, not assignments. */
    unsigned allowed_reads=0,allowed_writes=0;
    for(unsigned offset=0;offset<0x10000;offset++) for(unsigned width=1;width<=8;width++) {
        int read=bcm2712_rp1_config_access(offset,width,0);
        int write=bcm2712_rp1_config_access(offset,width,1);
        assert(read==(width==4 && !(offset&3) && (offset==0x4068||offset==0x9000||(offset>=0x8000&&offset<=0x803c))));
        assert(write==(width==4 && offset==0x9000));
        allowed_reads+=read;allowed_writes+=write;
    }
    assert(allowed_reads==18 && allowed_writes==1);
    printf("RP1_CONFIG_PASS READS=32 SELECTOR_WRITES=32 ENDPOINT_WRITES=0 FAILURES=%u MUTATIONS=16 NO_HARDWARE=1\n",faults);
    return 0;
}
