/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_gem_identify.h"

/* Hardware definitions independently implemented from Raspberry Pi's Linux
 * clk-rp1.c and rp1.dtsi, and Cadence macb.h/hw_is_gem in macb_main.c:
 * https://github.com/raspberrypi/linux/tree/80d4218cb877ccb07d09a9f21f0678e78d8b36f5
 * Driver enables pclk/hclk/tx/tsu before probing MID. Both bus clocks are clk_sys;
 * its macb configuration has no reset handler or reset property. This reader
 * does not guess at a reset write, or copy Linux's NCR endianness probe. */
static const uint32_t offsets[RPI5_GEM_CLOCK_WORDS]={0x14,0x18,0x20,0x8000,0x8004,0x8008,0x800c,0x8010,
    0x64,0x68,0x70,0x134,0x138,0x140,0x8014};

int rpi5_gem_clock_profile(const uint32_t v[RPI5_GEM_CLOCK_WORDS])
{
    if(!v || !(v[0]&(1u<<11)) || (v[0]&3)!=2 || v[2]!=4 ||
        !v[1] || v[1]>0xffffff || !(v[3]&(1u<<31)) || (v[3]&63)!=1 ||
        (v[4]&0x29) || !(v[4]&4) || (v[5]!=20 && v[5]!=40) || v[6])return 0;
    uint64_t div1=(v[7]>>16)&7,div2=(v[7]>>12)&7;
    if(!div1 || !div2)return 0;
    uint64_t denominator=div1*div2*v[1];
    /* Bounds above make both products fit uint64_t. Exact rational check,
     * not a rounded-rate acceptance of a different inherited frequency. */
    if(UINT64_C(50000000)*v[5]!=UINT64_C(200000000)*denominator)return 0;
    /* Both auxiliary-only clocks select parent index0. SEL is the driver's
     * one-hot live selection, not its disabled-clock CTRL fallback. */
    for(unsigned n=8;n<=11;n+=3){
        if(!(v[n]&(1u<<11)) || (v[n]&0x3e0) || !v[n+1] || v[n+1]>255 ||
            !v[n+2] || (v[n+2]&(v[n+2]-1)))return 0;
    }
    uint64_t sec=(v[14]>>8)&31;
    if((v[14]&(1u<<16)) || sec<8 || sec>18 || v[12]!=1)return 0;
    return UINT64_C(50000000)*v[5]==UINT64_C(125000000)*sec*v[9];
}
static int retained(const struct rpi5_gem_identify *s)
{
    const struct rpi5_rp1_decode_cycle *d=s->decode;
    return d && d->state==RPI5_RP1_DECODE_MAPPED && d->mapped==3 && !d->unmapped &&
        !d->pending_write && !d->pending_map && d->assignment &&
        s->io.current && s->io.read && s->io.context==d->io.context &&
        d->io.current && !d->io.current(d->io.context,d,d->assignment) &&
        !s->io.current(s->io.context,s,d);
}
int rpi5_gem_read_allowed(const struct rpi5_gem_identify *s,unsigned index,uint32_t offset)
{
    if(!s || !s->pending || s->reads>RPI5_GEM_READ_BOUND || s->index!=index || s->offset!=offset || !retained(s))return 0;
    if(s->stage==RPI5_GEM_CLOCK_BEFORE || s->stage==RPI5_GEM_CLOCK_AFTER){
        if(index!=1)return 0;
        for(unsigned i=0;i<RPI5_GEM_CLOCK_WORDS;i++)if(offset==offsets[i])return 1;
    }
    return (s->stage==RPI5_GEM_MID_FIRST || s->stage==RPI5_GEM_MID_SECOND) &&
        s->clocks_ready && rpi5_gem_clock_profile(s->before) && index==0 && offset==0xfc;
}
static int fail(struct rpi5_gem_identify *s,int rc)
{s->pending=0;s->stage=RPI5_GEM_QUARANTINED;return rc;}
static int read_one(struct rpi5_gem_identify *s,unsigned index,uint32_t offset,uint32_t *out)
{
    if(!retained(s) || s->reads>=RPI5_GEM_READ_BOUND)return -3;
    s->index=index;s->offset=offset;s->pending=1;s->reads++;
    if(!rpi5_gem_read_allowed(s,index,offset))return -3;
    uint32_t value=0;int rc=s->io.read(s->io.context,index,offset,&value);s->pending=0;
    if(rc)return -4;
    if(!retained(s))return -3;
    *out=value;return 0;
}
int rpi5_gem_identify_run(struct rpi5_gem_identify *s,const struct rpi5_rp1_decode_cycle *d,
    const struct rpi5_gem_io *io,struct rpi5_gem_observation *out)
{
    if(!s || !d || !io || !out || !io->current || !io->read)return -1;
    if(s->stage!=RPI5_GEM_EMPTY)return -2;
    if(s->decode || s->io.context || s->io.current || s->io.read || s->reads || s->pending ||
        s->index || s->offset || s->clocks_ready || s->mid[0] || s->mid[1])return fail(s,-2);
    for(unsigned i=0;i<RPI5_GEM_CLOCK_WORDS;i++)if(s->before[i] || s->after[i])return fail(s,-2);
    s->decode=d;s->io=*io;s->stage=RPI5_GEM_CLOCK_BEFORE;
    if(!retained(s))return fail(s,-3);
    int rc;
    for(unsigned i=0;i<RPI5_GEM_CLOCK_WORDS;i++)if((rc=read_one(s,1,offsets[i],&s->before[i])))return fail(s,rc);
    if(!rpi5_gem_clock_profile(s->before))return fail(s,-5);
    s->clocks_ready=1;s->stage=RPI5_GEM_MID_FIRST;
    if((rc=read_one(s,0,0xfc,&s->mid[0])))return fail(s,rc);
    s->stage=RPI5_GEM_MID_SECOND;
    if((rc=read_one(s,0,0xfc,&s->mid[1])))return fail(s,rc);
    s->stage=RPI5_GEM_CLOCK_AFTER;
    for(unsigned i=0;i<RPI5_GEM_CLOCK_WORDS;i++)if((rc=read_one(s,1,offsets[i],&s->after[i])))return fail(s,rc);
    for(unsigned i=0;i<RPI5_GEM_CLOCK_WORDS;i++)if(s->before[i]!=s->after[i])return fail(s,-5);
    uint32_t id=(s->mid[0]>>16)&0xfff;
    if(s->mid[0]!=s->mid[1] || !s->mid[0] || s->mid[0]==UINT32_MAX || id<2 || id==0xfff ||
        !rpi5_gem_clock_profile(s->after) || !retained(s))return fail(s,-5);
    struct rpi5_gem_observation result={.mid=s->mid[0],.system_hz=200000000,.reads=s->reads};
    for(unsigned i=0;i<RPI5_GEM_CLOCK_WORDS;i++)result.clocks[i]=s->after[i];
    s->stage=RPI5_GEM_COMPLETE;*out=result;return 0;
}
