/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_gem_capabilities.h"
/* Independently implemented from preserved Raspberry Pi Linux80d4218 macb.h
 * design configuration offsets/fields and macb_configure_caps/probe_queues.
 * No Linux code is imported. ISR/status/counters are deliberately excluded. */
static const uint32_t offsets[RPI5_GEM_CAP_WORDS]={0xfc,0x280,0x284,0x290,0x294,0x29c,0x2a4,0x2ac};
static int same(const void *a,const void *b,size_t n)
{const unsigned char *x=a,*y=b;for(size_t i=0;i<n;i++)if(x[i]!=y[i])return 0;return 1;}
static void copy(void *a,const void *b,size_t n)
{unsigned char *x=a;const unsigned char *y=b;for(size_t i=0;i<n;i++)x[i]=y[i];}
static int apart(const void *a,size_t na,const void *b,size_t nb)
{uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return a && b && na<=UINTPTR_MAX-x && nb<=UINTPTR_MAX-y && (x+na<=y || y+nb<=x);}
int rpi5_gem_cap_decode(const uint32_t raw[RPI5_GEM_CAP_WORDS],struct rpi5_gem_cap_observation *out)
{
    if(!raw || !out || !apart(raw,RPI5_GEM_CAP_WORDS*sizeof *raw,out,sizeof *out))return -1;
    uint32_t id=(raw[0]>>16)&0xfff;
    if(!raw[0] || raw[0]==UINT32_MAX || id<2 || id==0xfff)return -1;
    struct rpi5_gem_cap_observation r={0};
    for(unsigned i=0;i<RPI5_GEM_CAP_WORDS;i++)r.raw[i]=raw[i];
    r.id=id;r.revision=raw[0]&0xffff;r.bus_width_code=(raw[1]>>25)&7;
    r.bus_width_bits=r.bus_width_code==1?32:r.bus_width_code==2?64:r.bus_width_code==4?128:0;
    r.queue_mask=(raw[4]&255)|1;for(unsigned i=0;i<8;i++)r.queue_count+=(r.queue_mask>>i)&1;
    r.dma64=(raw[4]>>23)&1;r.isr_clear_on_read=(raw[1]>>23)&1;r.pcs=!(raw[1]&1);
    r.rx_packet_buffer=(raw[2]>>20)&1;r.tx_packet_buffer=(raw[2]>>21)&1;
    r.rx_packet_address_bits=(raw[2]>>22)&15;r.tsu=(raw[3]>>8)&1;
    r.lso=(raw[4]>>27)&1;r.cutthrough=(raw[4]>>25)&1;r.high_speed=(raw[7]>>26)&1;
    r.type1_screeners=raw[5]>>24;r.type2_screeners=(raw[5]>>16)&255;
    r.type2_ethertypes=(raw[5]>>8)&255;r.type2_comparators=raw[5]&255;
    r.rx_descriptor_prefetch_code=(raw[6]>>8)&15;r.tx_descriptor_prefetch_code=(raw[6]>>12)&15;
    *out=r;return 0;
}
static int retained(const struct rpi5_gem_cap_session *s)
{
    const struct rpi5_gem_identify *g=s->identity;
    const struct rpi5_rp1_decode_cycle *d=g?g->decode:0;
    return s->self==s && s->state==RPI5_GEM_CAP_READING && s->busy==1 &&
        g && g->stage==RPI5_GEM_MID_SECOND && !g->pending && g->reads==RPI5_GEM_CLOCK_WORDS+2 &&
        g->clocks_ready==1 && g->mid[0]==g->mid[1] &&
        g->mid[0] && g->mid[0]!=UINT32_MAX && ((g->mid[0]>>16)&0xfff)>=2 &&
        ((g->mid[0]>>16)&0xfff)!=0xfff &&
        rpi5_gem_clock_profile(g->before) &&
        d && d->state==RPI5_RP1_DECODE_MAPPED && d->mapped==3 && !d->unmapped &&
        !d->pending_write && !d->pending_map && d->assignment &&
        s->io.current && s->io.read && s->io.context==g->io.context && s->io.context==d->io.context;
}
int rpi5_gem_cap_read_allowed(const struct rpi5_gem_cap_session *s,uint32_t offset)
{
    return s && retained(s) && s->pending==1 && s->pass<2 && s->index<RPI5_GEM_CAP_WORDS &&
        s->reads==s->pass*RPI5_GEM_CAP_WORDS+s->index+1 && s->reads<=RPI5_GEM_CAP_READ_LIMIT &&
        s->offset==offset && offset==offsets[s->index];
}
struct run {
    struct rpi5_gem_cap_session *s;
    const struct rpi5_gem_identify *source_identity;
    const struct rpi5_rp1_decode_cycle *source_decode;
    const struct rpi5_gem_cap_io *original;
    struct rpi5_gem_cap_io io;
    struct rpi5_gem_identify identity;
    struct rpi5_rp1_decode_cycle decode;
};
static int fail(struct run *r,int rc)
{r->s->state=RPI5_GEM_CAP_QUARANTINED;r->s->busy=0;r->s->pending=0;r->s->error=rc;return rc;}
static int intact(struct run *r)
{
    return r->s->identity==r->source_identity && r->source_identity->decode==r->source_decode &&
        same(r->original,&r->io,sizeof r->io) &&
        same(&r->s->io,&r->io,sizeof r->io) &&
        same(r->s->identity,&r->identity,sizeof r->identity) &&
        same(r->s->identity->decode,&r->decode,sizeof r->decode) && retained(r->s);
}
static int guard(struct run *r)
{
    if(!intact(r))return fail(r,-3);
    struct rpi5_gem_cap_session held;copy(&held,r->s,sizeof held);
    int rc=r->io.current(r->io.context,r->s,r->s->identity,r->s->identity->decode);
    if(rc || !intact(r) || !same(r->s,&held,sizeof held))return fail(r,-3);
    return 0;
}
int rpi5_gem_cap_run(struct rpi5_gem_cap_session *s,const struct rpi5_gem_identify *g,
    const struct rpi5_gem_cap_io *io,struct rpi5_gem_cap_observation *out)
{
    if(!s)return -1;
    if(s->state!=RPI5_GEM_CAP_UNUSED){
        if(s->state==RPI5_GEM_CAP_READING){s->state=RPI5_GEM_CAP_QUARANTINED;s->busy=0;s->pending=0;s->error=-2;}
        return -2;
    }
    if(!g || !g->decode || !io || !out || !io->current || !io->read || s->self || s->identity ||
        s->io.context || s->io.current || s->io.read || s->busy || s->pending || s->reads ||
        s->pass || s->index || s->offset || s->error)return -1;
    for(unsigned p=0;p<2;p++)for(unsigned i=0;i<RPI5_GEM_CAP_WORDS;i++)if(s->words[p][i])return -1;
    const void *objects[]={s,g,g->decode,io,out};
    const size_t sizes[]={sizeof *s,sizeof *g,sizeof *g->decode,sizeof *io,sizeof *out};
    for(unsigned i=0;i<5;i++)for(unsigned j=0;j<i;j++)if(!apart(objects[i],sizes[i],objects[j],sizes[j]))return -1;
    struct run r={.s=s,.source_identity=g,.source_decode=g->decode,.original=io};copy(&r.io,io,sizeof *io);
    copy(&r.identity,g,sizeof *g);copy(&r.decode,g->decode,sizeof *g->decode);
    s->self=s;s->identity=g;copy(&s->io,io,sizeof *io);s->state=RPI5_GEM_CAP_READING;s->busy=1;
    if(guard(&r))return s->error;
    for(unsigned p=0;p<2;p++)for(unsigned i=0;i<RPI5_GEM_CAP_WORDS;i++){
        s->pass=p;s->index=i;s->offset=offsets[i];s->pending=1;s->reads++;
        if(guard(&r) || !rpi5_gem_cap_read_allowed(s,s->offset))return fail(&r,-3);
        struct rpi5_gem_cap_session held;copy(&held,s,sizeof held);
        uint32_t value=0;int rc=r.io.read(r.io.context,s->offset,&value);
        if(!same(s,&held,sizeof held) || guard(&r))return fail(&r,-3);
        if(rc)return fail(&r,-4);
        s->pending=0;s->words[p][i]=value;
    }
    if(!same(s->words[0],s->words[1],sizeof s->words[0]) || s->words[0][0]!=g->mid[0])return fail(&r,-5);
    struct rpi5_gem_cap_observation result;
    if(rpi5_gem_cap_decode(s->words[0],&result) || guard(&r))return fail(&r,-5);
    result.reads=s->reads;s->state=RPI5_GEM_CAP_COMPLETE;s->busy=0;*out=result;return 0;
}
