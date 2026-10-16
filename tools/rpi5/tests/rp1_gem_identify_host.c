/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_gem_identify.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static struct rpi5_gem_identify session;
static struct rpi5_rp1_decode_cycle decode;
static struct rpi5_rp1_assignment assignment;
static unsigned reads,currents,fail_read,fail_current,clock_change,mid_change;
static uint32_t clock_values[RPI5_GEM_CLOCK_WORDS],mid_value;
static const uint32_t offsets[RPI5_GEM_CLOCK_WORDS]={0x14,0x18,0x20,0x8000,0x8004,0x8008,0x800c,0x8010,
    0x64,0x68,0x70,0x134,0x138,0x140,0x8014};
static int context;
static int current_decode(void *c,const struct rpi5_rp1_decode_cycle *d,
    const struct rpi5_rp1_assignment *a)
{return c!=&context || d!=&decode || a!=&assignment;}
static int current(void *c,const struct rpi5_gem_identify *s,const struct rpi5_rp1_decode_cycle *d)
{currents++;return currents==fail_current || c!=&context || s!=&session || d!=&decode;}
static int read_register(void *c,unsigned index,uint32_t offset,uint32_t *out)
{
    assert(c==&context);
    if(!rpi5_gem_read_allowed(&session,index,offset))return -1;
    reads++;
    if(reads==fail_read)return -1;
    assert(!rpi5_gem_read_allowed(&session,index^1,offset));
    assert(!rpi5_gem_read_allowed(&session,index,offset+4));
    if(index){
        unsigned n=0;while(n<RPI5_GEM_CLOCK_WORDS&&offsets[n]!=offset)n++;assert(n<RPI5_GEM_CLOCK_WORDS);
        *out=clock_values[n];
        if(session.stage==RPI5_GEM_CLOCK_AFTER && n+1==clock_change)*out^=1u<<27;
    }else{assert(offset==0xfc && reads>=16 && reads<=17);*out=mid_value;
        if(mid_change&&reads==17)*out^=1;}
    return 0;
}
static const struct rpi5_gem_io io={&context,current,read_register};
static void reset(void)
{
    memset(&session,0,sizeof session);memset(&decode,0,sizeof decode);memset(&assignment,0,sizeof assignment);
    reads=currents=fail_read=fail_current=clock_change=mid_change=0;
    decode.state=RPI5_RP1_DECODE_MAPPED;decode.mapped=3;decode.assignment=&assignment;
    decode.io.context=&context;decode.io.current=current_decode;
    const uint32_t values[RPI5_GEM_CLOCK_WORDS]={0x802,1,4,0x80000001,4,20,0,0x51000,
        0x800,1,2,0x800,1,2,0x80000800};
    memcpy(clock_values,values,sizeof values);mid_value=0x00070106;
}
static void rejected(void)
{
    struct rpi5_gem_observation out,before;memset(&out,0xa5,sizeof out);before=out;
    assert(rpi5_gem_identify_run(&session,&decode,&io,&out));
    assert(!memcmp(&out,&before,sizeof out)&&session.stage==RPI5_GEM_QUARANTINED&&!session.pending);
    unsigned before_reads=reads,before_currents=currents;
    assert(rpi5_gem_identify_run(&session,&decode,&io,&out)==-2);
    assert(reads==before_reads && currents==before_currents);
    assert(!rpi5_gem_read_allowed(&session,1,0x14));
}
int main(void)
{
    unsigned faults=0;
    reset();struct rpi5_gem_observation out;
    assert(!rpi5_gem_identify_run(&session,&decode,&io,&out));
    assert(session.stage==RPI5_GEM_COMPLETE && reads==32 && out.reads==32 && out.mid==mid_value);
    assert(out.system_hz==200000000 && !memcmp(out.clocks,clock_values,sizeof clock_values));
    unsigned all_currents=currents;
    for(unsigned n=1;n<=32;n++){reset();fail_read=n;rejected();assert(reads==n);faults++;}
    for(unsigned n=1;n<=all_currents;n++){reset();fail_current=n;rejected();faults++;}
    for(unsigned n=1;n<=RPI5_GEM_CLOCK_WORDS;n++){reset();clock_change=n;rejected();assert(reads==32);faults++;}
    reset();mid_change=1;rejected();assert(reads==32);faults++;
    const uint32_t invalid_mid[]={0,UINT32_MAX,0x00000106,0x00010106,0x0fff0106};
    for(unsigned i=0;i<sizeof invalid_mid/sizeof invalid_mid[0];i++){
        reset();mid_value=invalid_mid[i];rejected();assert(reads==32);faults++;
    }
    const unsigned fields[]={0,0,1,1,2,2,3,3,4,4,4,4,5,5,6,7,7};
    const uint32_t bad[]={2,0x803,0,0x1000000,0,5,1,0x80000002,0,5,12,36,19,41,1,0x1000,0x50000};
    for(unsigned i=0;i<sizeof bad/sizeof bad[0];i++){
        reset();clock_values[fields[i]]=bad[i];assert(!rpi5_gem_clock_profile(clock_values));
        rejected();assert(reads==15);faults++;
    }
    reset();clock_values[5]=40;clock_values[7]=0x52000;clock_values[14]=0x80001000;
    assert(rpi5_gem_clock_profile(clock_values));
    assert(!rpi5_gem_identify_run(&session,&decode,&io,&out));
    for(unsigned n=8;n<15;n++)for(unsigned bit=0;bit<32;bit++){
        reset();clock_values[n]^=1u<<bit;
        int good=rpi5_gem_clock_profile(clock_values);
        if(good){assert(!rpi5_gem_identify_run(&session,&decode,&io,&out));assert(reads==32);}
        else{rejected();assert(reads==15);faults++;}
    }
    for(unsigned div=1;div<16;div++)for(unsigned a=0;a<8;a++)for(unsigned b=0;b<8;b++){
        reset();clock_values[1]=div;clock_values[7]=(a<<16)|(b<<12);
        assert(rpi5_gem_clock_profile(clock_values)==(a&&b&&a*b*div==5));
    }
    for(unsigned i=0;i<11;i++){
        reset();switch(i){
        case 0:decode.state=RPI5_RP1_DECODE_UNMAPPING;break;
        case 1:decode.mapped=1;break;case 2:decode.unmapped=2;break;
        case 3:decode.pending_write=1;break;case 4:decode.pending_map=1;break;
        case 5:decode.assignment=NULL;break;case 6:decode.io.context=NULL;break;
        case 7:decode.io.current=NULL;break;case 8:session.before[7]=1;break;
        case 9:session.pending=1;break;case 10:session.mid[1]=1;break;
        }rejected();assert(!reads);faults++;
    }
    printf("RP1_GEM_IDENTIFY_PASS READS=32 FAULTS=%u DIVIDER_CASES=960 NO_WRITES=1 NO_HARDWARE=1\n",faults);
    return 0;
}
