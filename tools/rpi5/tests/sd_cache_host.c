/* SPDX-License-Identifier: BSD-2-Clause */
/* Sanitized explicit byte/register models only, never real hardware access. */
#include "rpi5_sd_cache.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void put16(uint8_t *p, unsigned v) { p[0]=(uint8_t)v; p[1]=(uint8_t)(v>>8); }
static void put32(uint8_t *p, uint32_t v)
{
    for (unsigned i=0;i<4;i++) p[i]=(uint8_t)(v>>(8*i));
}
static void general(uint8_t *p, unsigned offset, unsigned function, unsigned address)
{
    memset(p,0,1024); put16(p+2,offset+48); p[4]=1;
    /* Leave a standard unknown function at offset16 when PEF is elsewhere. */
    if (offset!=16) {
        p[4]=2; put16(p+16,1); put16(p+56,offset); p[58]=1;
        put32(p+60,UINT32_C(1)<<18);
    }
    put16(p+offset,2); memcpy(p+offset+24,"PEF",3); p[offset+42]=1;
    put32(p+offset+44,((uint32_t)function<<18)|address);
}
static void parsers(void)
{
    uint8_t scr[8]={2,5,0,0,0,0,0,0}; unsigned v=99; int ext=99;
    assert(!rpi5_sd_cache_scr(scr,8,&v,&ext) && v==2 && !ext);
    scr[2]=0x80;
    assert(!rpi5_sd_cache_scr(scr,8,&v,&ext) && v==3);
    scr[2]=0x84; scr[3]=4;
    assert(!rpi5_sd_cache_scr(scr,8,&v,&ext) && v==4 && ext);
    scr[3]=0x44;
    assert(!rpi5_sd_cache_scr(scr,8,&v,&ext) && v==5);
    scr[3]=0x84;
    assert(!rpi5_sd_cache_scr(scr,8,&v,&ext) && v==6);
    const unsigned indices[]={0,0,1,2,3,3,3};
    const uint8_t bad[]={0x12,1,4,0,0x80,0xc4,0x94};
    for (unsigned i=0;i<sizeof bad;i++) {
        uint8_t mutated[8]; memcpy(mutated,scr,8); mutated[indices[i]]=bad[i]; v=99; ext=99;
        assert(rpi5_sd_cache_scr(mutated,8,&v,&ext) && v==99 && ext==99);
    }
    assert(rpi5_sd_cache_scr(scr,7,&v,&ext)==RPI5_SD_INVALID);
    uint8_t data[1024], copy[1024]; unsigned fn=99; uint32_t address=99;
    general(data,16,2,0);
    assert(!rpi5_sd_cache_location(data,512,&fn,&address) && fn==2 && !address);
    general(data,530,15,0x1fe00);
    assert(!rpi5_sd_cache_location(data,1024,&fn,&address) && fn==15 && address==0x1fe00);
    assert(rpi5_sd_cache_location(data,512,&fn,&address));
    general(data,16,2,1);
    assert(!rpi5_sd_cache_location(data,512,&fn,&address) && address==1);
    const unsigned mutation_offsets[]={0,2,3,4,5,16+2,16+4,16+6,16+22,16+24,16+27,16+40,16+42,16+43,16+46,16+47};
    const uint8_t mutation_values[]={1,31,255,0,1,1,1,1,1,'X',1,16,0,1,0x0a,0x80};
    general(data,16,2,0);
    for (unsigned i=0;i<sizeof mutation_values;i++) {
        memcpy(copy,data,1024); copy[mutation_offsets[i]]=mutation_values[i]; fn=99; address=99;
        assert(rpi5_sd_cache_location(copy,512,&fn,&address) && fn==99 && address==99);
    }
    general(data,64,2,0); put16(data+56,16); /* Cycle. */
    assert(rpi5_sd_cache_location(data,512,&fn,&address));
    general(data,64,2,0); put16(data+16,2); memcpy(data+40,"PEF",3); /* Duplicate PEF. */
    assert(rpi5_sd_cache_location(data,512,&fn,&address));
    general(data,64,2,0); put16(data+56,40); /* Overlapping descriptor. */
    assert(rpi5_sd_cache_location(data,512,&fn,&address));
    general(data,64,1,0); /* Two functions cannot claim the same FNO. */
    assert(rpi5_sd_cache_location(data,512,&fn,&address));
    general(data,16,2,0); put32(data+60,((uint32_t)2<<18)|0x1fe01);
    assert(rpi5_sd_cache_location(data,512,&fn,&address));
    general(data,16,2,0); put16(data+16,1); /* Valid descriptor with no PEF. */
    assert(!rpi5_sd_cache_location(data,512,&fn,&address) && !fn && !address);
    struct rpi5_sd_cache_observation out={0}, before;
    memset(data,0,sizeof data);
    assert(!rpi5_sd_cache_performance(data,512,&out) && out.state==RPI5_SD_CACHE_ABSENT);
    data[4]=1;
    assert(!rpi5_sd_cache_performance(data,512,&out) && out.state==RPI5_SD_CACHE_DISABLED);
    data[260]=1;
    assert(!rpi5_sd_cache_performance(data,512,&out) && out.state==RPI5_SD_CACHE_ENABLED);
    const unsigned offsets[]={0,4,258,259,260,261,262};
    for (unsigned i=0;i<sizeof offsets/sizeof *offsets;i++) {
        memset(data,0,512); data[offsets[i]]=2; before=out;
        assert(rpi5_sd_cache_performance(data,512,&out) && !memcmp(&out,&before,sizeof out));
    }
    memset(data,0,512); data[260]=1;
    assert(rpi5_sd_cache_performance(data,512,&out));
    memset(data,0,512); data[4]=1; data[261]=1;
    assert(rpi5_sd_cache_performance(data,512,&out));
}

struct model {
    uint32_t regs[64], command, argument, words, commands[64], arguments[64], count;
    uint64_t time;
    uint8_t scr[8], info[1024], perf[1024];
    unsigned base, old, fault, fault_at, reads, writes;
};
enum { COMMAND_TIMEOUT=1, COMMAND_ERROR, READ_TIMEOUT, TRANSFER_TIMEOUT, FIFO_MISSING,
    REMOVED, BAD_RESPONSE, NO_APP, BAD_STATE, CLOCK_STALL, DEFERRED_ERROR, DATA_INHIBIT,
    DATA_ERROR, IRQ_OWNED };
static unsigned active_fault(const struct model *m)
{
    return !m->fault_at || m->fault_at==m->count ? m->fault : 0;
}
static uint32_t read32(void *ctx, uint32_t offset)
{
    struct model *m=ctx;
    unsigned fault=active_fault(m);
    assert(!(offset&3) && offset<256); m->reads++;
    if (offset==32) {
        assert(m->command==51 || m->command==48);
        unsigned bytes=m->command==51?8:512;
        assert(m->words<bytes/4);
        const uint8_t *data=m->command==51 ? m->scr :
            (m->argument>>27)==0 ? m->info+((m->argument>>9)&0x1ffff) :
            m->perf+(((m->argument>>9)&0x1ffff)-(m->base&~511u));
        uint32_t word=0;
        unsigned effective=m->command==51 ? 8 : (m->argument&511)+1;
        for (unsigned i=0;i<4;i++) {
            unsigned index=m->words*4+i;
            word|=(uint32_t)(index<effective ? data[index] : 0xdd)<<(8*i);
        }
        if (++m->words==bytes/4) {
            m->regs[36/4]=0x10000 | (fault==DATA_INHIBIT?2:0);
            if (fault!=TRANSFER_TIMEOUT) m->regs[48/4]|=2;
            if (fault==DATA_ERROR) m->regs[48/4]|=0x208000;
        }
        return word;
    }
    return m->regs[offset/4];
}
static void write32(void *ctx, uint32_t offset, uint32_t value)
{
    struct model *m=ctx;
    assert(!(offset&3) && offset<256); m->writes++;
    assert(offset==4 || offset==8 || offset==12 || offset==48);
    if (offset==48) { m->regs[offset/4]&=~value; return; }
    m->regs[offset/4]=value;
    if (offset!=12) return;
    m->command=value>>24; m->argument=m->regs[8/4]; m->words=0;
    assert(m->count<64); m->commands[m->count]=m->command; m->arguments[m->count++]=m->argument;
    unsigned fault=active_fault(m);
    int data=m->command==51 || m->command==48;
    assert(m->command==13 || m->command==55 || data);
    assert(value==((m->command<<24)|((data?0x3au:0x1au)<<16)|(data?16u:0u)));
    assert(!(value&15)); /* No DMA, multi-block or auto-command. */
    if (fault==COMMAND_TIMEOUT || fault==CLOCK_STALL) return;
    if (fault==COMMAND_ERROR) { m->regs[48/4]=0x28000; return; }
    m->regs[48/4]=1;
    m->regs[16/4]=fault==BAD_RESPONSE?0x400900:0x900;
    if (m->command==13) {
        assert(m->argument==0x12340000);
        if (fault==BAD_STATE) m->regs[16/4]=0x700;
        if (fault==DEFERRED_ERROR && m->count>1) m->regs[16/4]=0x400900;
    } else if (m->command==55) {
        assert(m->argument==0x12340000);
        if (fault!=NO_APP) m->regs[16/4]|=32;
    } else {
        assert(m->regs[4/4]==(0x10000u|(m->command==51?8u:512u)));
        if (m->command==51) assert(!m->argument && m->count>=2 && m->commands[m->count-2]==55);
        else {
            assert(!(m->argument&0x84000000));
            unsigned fn=m->argument>>27, addr=(m->argument>>9)&0x1ffff, count=(m->argument&511)+1;
            assert(count<=512-(addr&511));
            if (!fn) assert((addr==0 || addr==512) && count==512);
            else assert(fn==2 && addr>=m->base && addr+count<=m->base+512);
        }
        if (fault!=READ_TIMEOUT) m->regs[48/4]|=32;
        m->regs[36/4]=0x10000 | (fault==FIFO_MISSING?0:0x800);
    }
}
static uint64_t microseconds(void *ctx) { return ((struct model *)ctx)->time; }
static void delay_us(void *ctx, uint32_t us)
{
    struct model *m=ctx;
    if (active_fault(m)!=CLOCK_STALL) m->time+=us;
}
static void setup(struct model *m, struct rpi5_sd_card *c, unsigned fault, unsigned base)
{
    memset(m,0,sizeof *m); m->base=base;
    m->fault=fault; m->regs[36/4]=fault==REMOVED?0:0x10000;
    m->regs[56/4]=fault==IRQ_OWNED?1:0;
    m->scr[0]=2; m->scr[1]=5; m->scr[2]=0x84; m->scr[3]=0x84;
    general(m->info,16,2,base); m->perf[base&511]=0; m->perf[(base&511)+4]=1;
    memset(c,0,sizeof *c);
    c->io=(struct rpi5_sd_io){m,read32,write32,microseconds,delay_us};
    c->ready=1; c->rca=0x12340000; c->sectors=250347520;
}
static void transport(void)
{
    struct model m; struct rpi5_sd_card c;
    uint8_t scratch[1024]; struct rpi5_sd_cache_observation out, before;
    for (unsigned offset=0;offset<512;offset++) {
        unsigned base=1024+offset; setup(&m,&c,0,base); memset(&out,0xa5,sizeof out);
        assert(!rpi5_sd_cache_probe(&c,&out,scratch,sizeof scratch));
        assert(c.ready && out.state==RPI5_SD_CACHE_DISABLED && out.function==2 && out.address==base);
        assert(out.specification==6 && !memcmp(out.scr,m.scr,8));
        assert(m.count==(offset?10u:8u));
        m.perf[(base&511)+260]=1;
        assert(!rpi5_sd_cache_probe(&c,&out,scratch,sizeof scratch) && out.state==RPI5_SD_CACHE_ENABLED);
    }
    setup(&m,&c,0,0); m.scr[3]=0x44; /* Version5, cache feature not defined. */
    assert(!rpi5_sd_cache_probe(&c,&out,scratch,1024) && out.state==RPI5_SD_CACHE_ABSENT && m.count==4);
    setup(&m,&c,0,0); general(m.info,530,2,0); /* Header spans page1. */
    assert(!rpi5_sd_cache_probe(&c,&out,scratch,1024) && out.state==RPI5_SD_CACHE_DISABLED && m.count==10);
    setup(&m,&c,0,0); put16(m.info+16,1);
    assert(!rpi5_sd_cache_probe(&c,&out,scratch,1024) && out.state==RPI5_SD_CACHE_ABSENT);
    setup(&m,&c,0,0); m.perf[4]=0;
    assert(!rpi5_sd_cache_probe(&c,&out,scratch,1024) && out.state==RPI5_SD_CACHE_ABSENT);
    for (unsigned fault=1;fault<=IRQ_OWNED;fault++) {
        setup(&m,&c,fault,0); memset(&out,0xa5,sizeof out); before=out;
        assert(rpi5_sd_cache_probe(&c,&out,scratch,1024));
        assert(!memcmp(&out,&before,sizeof out));
        if (fault==IRQ_OWNED) assert(c.ready && !m.writes);
        else assert(!c.ready);
    }
    setup(&m,&c,0,0); memset(&out,0xa5,sizeof out); before=out;
    m.scr[3]=0xc4; /* Unknown future version: never absent-cache fallback. */
    assert(rpi5_sd_cache_probe(&c,&out,scratch,1024) && !c.ready && !memcmp(&out,&before,sizeof out));
    setup(&m,&c,0,0); m.perf[261]=1;
    assert(rpi5_sd_cache_probe(&c,&out,scratch,1024) && !c.ready);
    setup(&m,&c,0,0); c.ready=0;
    assert(rpi5_sd_cache_probe(&c,&out,scratch,1024)==RPI5_SD_INVALID && !m.reads && !m.writes);
    setup(&m,&c,0,0);
    assert(rpi5_sd_cache_probe(&c,&out,scratch,1023)==RPI5_SD_INVALID && !m.reads && !m.writes);
    assert(rpi5_sd_cache_probe(&c,0,scratch,1024)==RPI5_SD_INVALID && !m.reads && !m.writes);
}
static void diagnostics(void)
{
    struct model plain, traced;
    struct rpi5_sd_card a,b;
    struct rpi5_sd_cache_observation out, other, before;
    struct rpi5_sd_cache_diagnostic trace;
    uint8_t scratch[1024], other_scratch[1024];
    /* Every alignment, plus all existing transport faults: tracing changes
     * neither command arguments/counts nor any register access count. */
    for (unsigned scenario=0;scenario<512+IRQ_OWNED;scenario++) {
        unsigned base=scenario<512?1024+scenario:1024;
        unsigned fault=scenario<512?0:scenario-511;
        setup(&plain,&a,fault,base); setup(&traced,&b,fault,base);
        memset(&out,0xa5,sizeof out); other=out; before=out;
        int rc=rpi5_sd_cache_probe(&a,&out,scratch,sizeof scratch);
        memset(&trace,0xa5,sizeof trace);
        assert(rpi5_sd_cache_probe_traced(&b,&other,other_scratch,sizeof other_scratch,&trace)==rc);
        assert(!memcmp(&out,&other,sizeof out) && a.ready==b.ready);
        assert(plain.count==traced.count && plain.reads==traced.reads && plain.writes==traced.writes);
        assert(!memcmp(plain.commands,traced.commands,sizeof plain.commands));
        assert(!memcmp(plain.arguments,traced.arguments,sizeof plain.arguments));
        if (rc) assert(!memcmp(&other,&before,sizeof other) && trace.payload_bytes==0);
        else assert(trace.stage==RPI5_SD_CACHE_STAGE_COMPLETE && !trace.payload_bytes &&
            trace.specification==6 && trace.function==2 && trace.address==base &&
            !memcmp(trace.scr,traced.scr,8));
    }
    const unsigned stages[]={0,RPI5_SD_CACHE_STAGE_READY,RPI5_SD_CACHE_STAGE_APP,
        RPI5_SD_CACHE_STAGE_SCR_READ,RPI5_SD_CACHE_STAGE_SCR_READ,
        RPI5_SD_CACHE_STAGE_GENERAL_FIRST,RPI5_SD_CACHE_STAGE_GENERAL_FIRST,
        RPI5_SD_CACHE_STAGE_PERFORMANCE_FIRST,RPI5_SD_CACHE_STAGE_PERFORMANCE_FIRST};
    for (unsigned command=1;command<=8;command++) {
        setup(&traced,&b,COMMAND_TIMEOUT,0); traced.fault_at=command;
        memset(&other,0xa5,sizeof other); before=other;
        assert(rpi5_sd_cache_probe_traced(&b,&other,scratch,1024,&trace)==RPI5_SD_TIMEOUT);
        assert(trace.stage==stages[command] && !trace.payload_bytes && !b.ready &&
            !memcmp(&other,&before,sizeof other));
    }
    for (unsigned decoder=0;decoder<3;decoder++) {
        setup(&traced,&b,0,0); memset(&other,0xa5,sizeof other); before=other;
        if (!decoder) traced.scr[3]=0xc4;
        else if (decoder==1) traced.info[0]=1;
        else traced.perf[261]=1;
        assert(rpi5_sd_cache_probe_traced(&b,&other,scratch,1024,&trace)==RPI5_SD_UNSUPPORTED);
        assert(!b.ready && !memcmp(&other,&before,sizeof other));
        assert(!memcmp(trace.scr,traced.scr,8));
        assert(trace.payload_bytes==(!decoder?8u:512u));
        assert(trace.stage==(!decoder?RPI5_SD_CACHE_STAGE_SCR_DECODE:decoder==1?
            RPI5_SD_CACHE_STAGE_GENERAL_DECODE:RPI5_SD_CACHE_STAGE_PERFORMANCE_DECODE));
        assert(!memcmp(trace.payload,!decoder?traced.scr:decoder==1?traced.info:traced.perf,trace.payload_bytes));
        assert(trace.specification==(!decoder?0u:6u));
    }
    setup(&traced,&b,0,0); general(traced.info,530,2,0); traced.info[530+24]='X';
    assert(rpi5_sd_cache_probe_traced(&b,&other,scratch,1024,&trace)==RPI5_SD_UNSUPPORTED);
    assert(trace.stage==RPI5_SD_CACHE_STAGE_GENERAL_DECODE && trace.payload_bytes==1024 &&
        !memcmp(trace.payload,traced.info,1024));
    setup(&traced,&b,COMMAND_TIMEOUT,0); general(traced.info,530,2,0); traced.fault_at=7;
    assert(rpi5_sd_cache_probe_traced(&b,&other,scratch,1024,&trace)==RPI5_SD_TIMEOUT);
    assert(trace.stage==RPI5_SD_CACHE_STAGE_GENERAL_SECOND && !trace.payload_bytes);
    setup(&traced,&b,COMMAND_TIMEOUT,1025); traced.fault_at=9;
    assert(rpi5_sd_cache_probe_traced(&b,&other,scratch,1024,&trace)==RPI5_SD_TIMEOUT);
    assert(trace.stage==RPI5_SD_CACHE_STAGE_PERFORMANCE_SECOND && !trace.payload_bytes);
    setup(&traced,&b,0,0); traced.scr[3]=0x44;
    assert(!rpi5_sd_cache_probe_traced(&b,&other,scratch,1024,&trace));
    assert(trace.stage==RPI5_SD_CACHE_STAGE_COMPLETE && trace.specification==5 && !trace.payload_bytes && traced.count==4);
    setup(&traced,&b,0,0); memset(&trace,0xa5,sizeof trace);
    assert(rpi5_sd_cache_probe_traced(&b,&other,scratch,1023,&trace)==RPI5_SD_INVALID);
    assert(trace.stage==RPI5_SD_CACHE_STAGE_VALIDATE && !trace.payload_bytes && !traced.reads && !traced.writes);
    /* Actual W3 capture 2026-10-12: SCR 0205848700000000, then a completed
     * all-zero General Information block. Inject those bytes, not invented
     * cache state. Linux comparison is pending; malformed data cannot become
     * an absent-cache claim merely because its descriptor count is zero. */
    setup(&traced,&b,0,0); traced.scr[3]=0x87; memset(traced.info,0,sizeof traced.info);
    memset(&other,0xa5,sizeof other); before=other;
    assert(rpi5_sd_cache_probe_traced(&b,&other,scratch,1024,&trace)==RPI5_SD_UNSUPPORTED);
    assert(!b.ready && traced.count==6 && !memcmp(&other,&before,sizeof other));
    assert(trace.stage==RPI5_SD_CACHE_STAGE_GENERAL_DECODE && trace.specification==6 && trace.payload_bytes==512);
    assert(!memcmp(trace.scr,traced.scr,8) && !memcmp(trace.payload,traced.info,512));
}
int main(void)
{
    parsers(); transport(); diagnostics(); puts("SD_CACHE_OBSERVATION_PASS"); return 0;
}
