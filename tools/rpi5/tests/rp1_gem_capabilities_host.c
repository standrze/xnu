/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_gem_capabilities.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct model {
    struct rpi5_gem_cap_session session;
    struct rpi5_gem_identify identity;
    struct rpi5_rp1_decode_cycle decode;
    struct rpi5_rp1_assignment assignment;
    struct rpi5_gem_cap_io io;
    struct rpi5_gem_cap_observation output;
    unsigned reads,owners,read_fail,owner_fail,owner_mutate,owner_reenter;
    unsigned changed,mutation,mutation_at;
};
static const uint32_t registers[8]={0x00070109,0x08800000,0x03f00000,0x100,0x0a8000aa,0x01020304,0x5400,0x04000000};
static const uint32_t offsets[8]={0xfc,0x280,0x284,0x290,0x294,0x29c,0x2a4,0x2ac};
static int run(struct model *m)
{return rpi5_gem_cap_run(&m->session,&m->identity,&m->io,&m->output);}
static int current(void *context,const struct rpi5_gem_cap_session *s,const struct rpi5_gem_identify *g,
    const struct rpi5_rp1_decode_cycle *d)
{
    struct model *m=context;m->owners++;
    assert(s==&m->session && g==&m->identity && d==&m->decode);
    if(m->owner_mutate==m->owners)m->session.reads++;
    if(m->owner_reenter==m->owners)assert(run(m));
    return m->owners==m->owner_fail?-1:0;
}
static int read_reg(void *context,uint32_t offset,uint32_t *out)
{
    struct model *m=context;unsigned index=m->reads%8;m->reads++;
    assert(offset==offsets[index] && rpi5_gem_cap_read_allowed(&m->session,offset));
    assert(!rpi5_gem_cap_read_allowed(&m->session,0x24)); /* ISR excluded */
    *out=registers[index];if(m->changed==m->reads)*out^=1;
    if(m->mutation_at==m->reads)switch(m->mutation){
    case 1:m->identity.stage=RPI5_GEM_COMPLETE;break;
    case 2:m->decode.state=RPI5_RP1_DECODE_UNMAPPING;break;
    case 3:m->decode.mapped=0;break;
    case 4:m->identity.mid[0]^=1;break;
    case 5:m->session.identity=(const struct rpi5_gem_identify *)(uintptr_t)1;break;
    case 6:m->identity.decode=(const struct rpi5_rp1_decode_cycle *)(uintptr_t)1;break;
    case 7:m->io.current=0;break;
    case 8:m->session.pass++;break;
    default:assert(run(m));break;
    }
    return m->read_fail==m->reads?-1:0;
}
static void setup(struct model *m)
{
    memset(m,0,sizeof *m);memset(&m->output,0xa5,sizeof m->output);
    m->io=(struct rpi5_gem_cap_io){m,current,read_reg};
    m->decode.state=RPI5_RP1_DECODE_MAPPED;m->decode.mapped=3;
    m->decode.assignment=&m->assignment;m->decode.io.context=m;
    m->identity.stage=RPI5_GEM_MID_SECOND;m->identity.reads=17;
    m->identity.clocks_ready=1;m->identity.mid[0]=m->identity.mid[1]=registers[0];
    m->identity.decode=&m->decode;m->identity.io.context=m;
    const uint32_t clocks[15]={2,1,4,0x80000001,4,20,0,0x51010,0x10000800,1,1,0x10000800,1,1,0x80000800};
    memcpy(m->identity.before,clocks,sizeof clocks);
}
static void failed(struct model *m)
{
    struct rpi5_gem_cap_observation before=m->output;
    assert(run(m)<0 && !memcmp(&before,&m->output,sizeof before));
    assert(m->session.state==RPI5_GEM_CAP_QUARANTINED && !m->session.pending && !m->session.busy);
    unsigned reads=m->reads,owners=m->owners;assert(run(m)<0 && reads==m->reads && owners==m->owners);
}
int main(void)
{
    struct model m;setup(&m);assert(!run(&m));
    assert(m.session.state==RPI5_GEM_CAP_COMPLETE && m.reads==16 && m.output.reads==16);
    assert(!memcmp(m.output.raw,registers,sizeof registers));
    assert(m.output.id==7 && m.output.revision==0x109 && m.output.bus_width_bits==128);
    assert(m.output.queue_mask==0xab && m.output.queue_count==5 && m.output.dma64);
    assert(m.output.isr_clear_on_read && m.output.rx_packet_buffer && m.output.tx_packet_buffer);
    assert(m.output.type1_screeners==1 && m.output.type2_screeners==2 && m.output.type2_ethertypes==3 && m.output.type2_comparators==4);
    assert(m.output.rx_descriptor_prefetch_code==4 && m.output.tx_descriptor_prefetch_code==5);
    unsigned owners=m.owners,cases=0;
    for(unsigned i=1;i<=16;i++){
        setup(&m);m.read_fail=i;failed(&m);assert(m.reads==i);cases++;
        setup(&m);m.changed=i;failed(&m);cases++;
        for(unsigned mutation=1;mutation<=9;mutation++){
            setup(&m);m.mutation=mutation;m.mutation_at=i;failed(&m);assert(m.reads==i);cases++;
        }
    }
    for(unsigned i=1;i<=owners;i++){
        setup(&m);m.owner_fail=i;failed(&m);cases++;
        setup(&m);m.owner_mutate=i;failed(&m);cases++;
        setup(&m);m.owner_reenter=i;failed(&m);cases++;
    }
    setup(&m);m.identity.stage=RPI5_GEM_COMPLETE;failed(&m);assert(!m.reads);
    setup(&m);m.identity.before[0]=0;failed(&m);assert(!m.reads);
    setup(&m);m.decode.unmapped=1;failed(&m);assert(!m.reads);
    const uint32_t invalid_mid[]={0,UINT32_MAX,0x10001,0x0fff0001};
    for(unsigned i=0;i<4;i++){
        setup(&m);m.identity.mid[0]=m.identity.mid[1]=invalid_mid[i];failed(&m);assert(!m.reads);
    }
    for(unsigned code=0;code<8;code++){
        uint32_t raw[8];memcpy(raw,registers,sizeof raw);raw[1]=(raw[1]&~(7u<<25))|(code<<25);
        struct rpi5_gem_cap_observation out;assert(!rpi5_gem_cap_decode(raw,&out));
        assert(out.bus_width_code==code && out.bus_width_bits==(code==1?32u:code==2?64u:code==4?128u:0u));
    }
    setup(&m);assert(rpi5_gem_cap_run(&m.session,&m.identity,&m.io,(void *)&m.session)<0 && !m.reads && !m.owners);
    printf("GEM_CAPABILITIES_PASS READS=16 OWNER_CHECKS=%u FAULT_CASES=%u RAW_ONLY=1 NO_HARDWARE=1\n",owners,cases);
    return 0;
}
