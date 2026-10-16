/* SPDX-License-Identifier: BSD-2-Clause */
/* New implementation from SDA v6 protocol facts, not Linux implementation.
 * Sources and exact offsets: docs/rpi5/GATE4-WRITE-POLICY.md. Unlinked for now. */
#include "rpi5_sd_cache.h"

static uint16_t le16(const uint8_t *p) { return (uint16_t)(p[0]|((uint16_t)p[1]<<8)); }
static uint32_t le32(const uint8_t *p)
{
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void publish(struct rpi5_sd_cache_observation *out, const struct rpi5_sd_cache_observation *value)
{
    volatile uint8_t *destination=(volatile uint8_t *)out;
    const uint8_t *source=(const uint8_t *)value;
    for (unsigned i=0;i<sizeof *out;i++) destination[i]=source[i];
}
int rpi5_sd_cache_scr(const void *bytes, size_t size, unsigned *version, int *extensions)
{
    if (!bytes || size!=8 || !version || !extensions) return RPI5_SD_INVALID;
    const uint8_t *p=bytes;
    unsigned spec=p[0]&15, spec3=p[2]>>7, spec4=(p[2]>>2)&1;
    unsigned x=((p[2]&3)<<2)|(p[3]>>6);
    if ((p[0]>>4) || spec!=2 || (p[1]&15)!=5 || (p[3]&0x30) ||
        (!spec3 && (spec4 || x)) || x>2) return RPI5_SD_UNSUPPORTED;
    unsigned value=!spec3 ? 2 : x ? 4+x : spec4 ? 4 : 3;
    int ext=(p[3]&4)!=0;
    if ((value<4 && (p[3]&12)) || ((p[3]&8) && !ext)) return RPI5_SD_UNSUPPORTED;
    /* SD6 cache requires extension commands; contradictory/missing capability
     * on a newer card is not converted into an absent-cache claim. */
    if (value>=6 && !ext) return RPI5_SD_UNSUPPORTED;
    *version=value; *extensions=ext;
    return RPI5_SD_OK;
}
int rpi5_sd_cache_location(const void *bytes, size_t size, unsigned *function, uint32_t *address)
{
    if (!bytes || !function || !address || size<16 || size>1024) return RPI5_SD_INVALID;
    const uint8_t *p=bytes;
    unsigned length=le16(p+2), count=p[4];
    if (le16(p)!=0 || length<16 || length>size || count<1 || count>15)
        return RPI5_SD_UNSUPPORTED;
    for (unsigned i=5;i<16;i++) if (p[i]) return RPI5_SD_UNSUPPORTED;
    unsigned starts[15], ends[15], functions[15], offset=16, found=0, fno=0;
    uint32_t location=0;
    for (unsigned entry=0;entry<count;entry++) {
        if (offset<16 || offset>length || length-offset<44) return RPI5_SD_UNSUPPORTED;
        unsigned sets=p[offset+42], next=le16(p+offset+40);
        if (!sets || p[offset+43] || sets>(length-offset-44)/4) return RPI5_SD_UNSUPPORTED;
        unsigned end=offset+44+sets*4;
        for (unsigned i=0;i<entry;i++)
            if (offset<ends[i] && starts[i]<end) return RPI5_SD_UNSUPPORTED;
        starts[entry]=offset; ends[entry]=end;
        unsigned first=0;
        for (unsigned i=0;i<sets;i++) {
            uint32_t raw=le32(p+offset+44+i*4);
            unsigned fn=(raw>>18)&15;
            if ((raw&UINT32_C(0xffc20000)) || !fn || (i && fn!=first)) return RPI5_SD_UNSUPPORTED;
            first=fn;
        }
        for (unsigned i=0;i<entry;i++) if (functions[i]==first) return RPI5_SD_UNSUPPORTED;
        functions[entry]=first;
        if (le16(p+offset)==2) { /* Standard performance-enhancement function. */
            if (found++ || sets!=1 || le16(p+offset+2) || le16(p+offset+4) ||
                le16(p+offset+22)) return RPI5_SD_UNSUPPORTED;
            for (unsigned i=6;i<22;i++) if (p[offset+i]) return RPI5_SD_UNSUPPORTED;
            static const uint8_t name[16]={'P','E','F',0};
            for (unsigned i=0;i<16;i++) if (p[offset+24+i]!=name[i]) return RPI5_SD_UNSUPPORTED;
            uint32_t raw=le32(p+offset+44);
            fno=first; location=raw&UINT32_C(0x1ffff);
            if (location>UINT32_C(0x20000)-512) return RPI5_SD_UNSUPPORTED;
        }
        if (entry+1==count) { if (next) return RPI5_SD_UNSUPPORTED; }
        else if (!next || next>=length) return RPI5_SD_UNSUPPORTED;
        offset=next;
    }
    *function=found ? fno : 0; *address=found ? location : 0;
    return RPI5_SD_OK;
}
int rpi5_sd_cache_performance(const void *bytes, size_t size, struct rpi5_sd_cache_observation *out)
{
    if (!bytes || size!=512 || !out) return RPI5_SD_INVALID;
    const uint8_t *p=bytes;
    if (p[0] || (p[4]&~1u) || (p[260]&~1u) || (p[261]&~1u) ||
        p[258] || p[259] || p[262] || p[261] || (p[260] && !p[4]))
        return RPI5_SD_UNSUPPORTED;
    struct rpi5_sd_cache_observation value;
    publish(&value,out);
    value.revision=p[0]; value.supported=p[4]; value.enabled=p[260];
    value.flushing=p[261]; value.cq=p[262]; value.maintenance=p[258];
    value.state=p[260] ? RPI5_SD_CACHE_ENABLED : p[4] ? RPI5_SD_CACHE_DISABLED : RPI5_SD_CACHE_ABSENT;
    publish(out,&value);
    return RPI5_SD_OK;
}

enum { BLOCK=4, ARGUMENT=8, COMMAND=12, RESPONSE=16, DATA=32, PRESENT=36,
    STATUS=48, SIGNAL_ENABLE=56, DONE=1, TRANSFER=2, READ_READY=32 };
#define ERRORS UINT32_C(0xffff8000)
#define R1_ERRORS UINT32_C(0xfff98088)
#define WAIT_LIMIT UINT32_C(100000)
static uint32_t rd(struct rpi5_sd_card *c, uint32_t r) { return c->io.read32(c->io.context,r); }
static void wr(struct rpi5_sd_card *c, uint32_t r, uint32_t v) { c->io.write32(c->io.context,r,v); }
static int usable(struct rpi5_sd_card *c)
{
    c->last_interrupt=rd(c,STATUS);
    if (c->last_interrupt&ERRORS) return RPI5_SD_CONTROLLER;
    return (rd(c,PRESENT)&UINT32_C(0x10000)) ? RPI5_SD_OK : RPI5_SD_CARD;
}
static int wait(struct rpi5_sd_card *c, uint32_t reg, uint32_t mask, uint32_t want, uint32_t budget)
{
    uint64_t start=c->io.microseconds(c->io.context);
    for (uint32_t i=0;i<WAIT_LIMIT;i++) {
        int rc=usable(c);
        if (rc) return rc;
        if ((rd(c,reg)&mask)==want) return RPI5_SD_OK;
        if (c->io.microseconds(c->io.context)-start>=budget) break;
        c->io.delay_us(c->io.context,10);
    }
    return RPI5_SD_TIMEOUT;
}
static int event(struct rpi5_sd_card *c, uint32_t bit, uint32_t budget)
{
    int rc=wait(c,STATUS,bit,bit,budget);
    if (!rc) wr(c,STATUS,bit);
    return rc;
}
static int send(struct rpi5_sd_card *c, unsigned cmd, uint32_t arg, unsigned bytes, uint32_t *response)
{
    /* No general-purpose opcode/raw-extension write escape hatch. */
    if (!((cmd==13 || cmd==55) && !bytes) && !(cmd==51 && bytes==8 && !arg) &&
        !(cmd==48 && bytes==512 && !(arg&UINT32_C(0x84000000)))) return RPI5_SD_INVALID;
    int rc=wait(c,PRESENT,3,0,100000);
    if (rc) return rc;
    c->last_command=cmd;
    wr(c,STATUS,UINT32_MAX);
    if (bytes) wr(c,BLOCK,UINT32_C(0x10000)|bytes);
    wr(c,ARGUMENT,arg);
    wr(c,COMMAND,((uint32_t)cmd<<24)|((bytes?UINT32_C(0x3a):UINT32_C(0x1a))<<16)|(bytes?16u:0u));
    rc=event(c,DONE,100000);
    if (rc) return rc;
    *response=rd(c,RESPONSE);
    return (*response&R1_ERRORS) ? RPI5_SD_CARD : RPI5_SD_OK;
}
static int ready(struct rpi5_sd_card *c)
{
    uint32_t response;
    int rc=send(c,13,c->rca,0,&response);
    if (rc) return rc;
    return (response&UINT32_C(0x1f00))==UINT32_C(0x900) ? RPI5_SD_OK : RPI5_SD_CARD;
}
static int read_data(struct rpi5_sd_card *c, unsigned cmd, uint32_t arg, uint8_t *out, unsigned bytes)
{
    uint32_t response;
    int rc=send(c,cmd,arg,bytes,&response);
    if (rc) return rc;
    if ((rc=event(c,READ_READY,1000000))) return rc;
    if (!(rd(c,PRESENT)&0x800)) return RPI5_SD_CONTROLLER;
    for (unsigned i=0;i<bytes;i+=4) {
        uint32_t word=rd(c,DATA);
        for (unsigned j=0;j<4;j++) out[i+j]=(uint8_t)(word>>(j*8));
    }
    if ((rc=event(c,TRANSFER,1000000))) return rc;
    if ((rc=wait(c,PRESENT,2,0,1000000))) return rc;
    return ready(c); /* Extension errors can be deferred to the next R1. */
}
static int extension(struct rpi5_sd_card *c, unsigned function, uint32_t address, unsigned count, uint8_t *out)
{
    if (function>15 || address>UINT32_C(0x1ffff) || !count || count>512-(address&511))
        return RPI5_SD_INVALID;
    /* The wire data block is always 512 bytes, but LEN describes the exact
     * register range; the remainder is dummy data. Do not read an adjacent
     * unassigned register or data port just to align the host buffer. */
    return read_data(c,48,((uint32_t)function<<27)|(address<<9)|(count-1),out,512);
}
static void diagnostic_stage(struct rpi5_sd_cache_diagnostic *trace, unsigned stage)
{
    if (trace) { trace->stage=stage; trace->payload_bytes=0; }
}
static void diagnostic_payload(struct rpi5_sd_cache_diagnostic *trace, const uint8_t *data, unsigned bytes)
{
    if (!trace) return;
    for (unsigned i=0;i<bytes;i++) trace->payload[i]=data[i];
    trace->payload_bytes=bytes;
}
int rpi5_sd_cache_probe_traced(struct rpi5_sd_card *c, struct rpi5_sd_cache_observation *out,
    void *scratch, size_t scratch_bytes, struct rpi5_sd_cache_diagnostic *trace)
{
    if (trace) {
        volatile uint8_t *p=(volatile uint8_t *)trace;
        for (unsigned i=0;i<sizeof *trace;i++) p[i]=0;
    }
    if (!c || c->ready!=1 || !out || !scratch || scratch_bytes!=1024 || !c->rca ||
        (c->rca&65535) || !c->io.read32 || !c->io.write32 ||
        !c->io.microseconds || !c->io.delay_us) return RPI5_SD_INVALID;
    if (rd(c,SIGNAL_ENABLE)) return RPI5_SD_INVALID;
    struct rpi5_sd_cache_observation value={0};
    unsigned version; int ext;
    uint8_t *data=scratch;
    uint32_t response;
    diagnostic_stage(trace,RPI5_SD_CACHE_STAGE_READY);
    int rc=ready(c);
    if (rc) goto failed;
    diagnostic_stage(trace,RPI5_SD_CACHE_STAGE_APP);
    rc=send(c,55,c->rca,0,&response);
    if (!rc && !(response&32)) rc=RPI5_SD_CARD;
    if (rc) goto failed;
    diagnostic_stage(trace,RPI5_SD_CACHE_STAGE_SCR_READ);
    rc=read_data(c,51,0,value.scr,8);
    if (rc) goto failed;
    diagnostic_stage(trace,RPI5_SD_CACHE_STAGE_SCR_DECODE);
    diagnostic_payload(trace,value.scr,8);
    if (trace) for (unsigned i=0;i<8;i++) trace->scr[i]=value.scr[i];
    rc=rpi5_sd_cache_scr(value.scr,8,&version,&ext);
    if (rc) goto failed;
    value.specification=version;
    if (trace) trace->specification=version;
    if (version<6) {
        value.state=RPI5_SD_CACHE_ABSENT; publish(out,&value);
        diagnostic_stage(trace,RPI5_SD_CACHE_STAGE_COMPLETE); return RPI5_SD_OK;
    }
    if (!ext) { rc=RPI5_SD_UNSUPPORTED; goto failed; }
    diagnostic_stage(trace,RPI5_SD_CACHE_STAGE_GENERAL_FIRST);
    if ((rc=extension(c,0,0,512,data))) goto failed;
    unsigned length=le16(data+2);
    if (length>512 && length<=1024) {
        diagnostic_stage(trace,RPI5_SD_CACHE_STAGE_GENERAL_SECOND);
        if ((rc=extension(c,0,512,512,data+512))) goto failed;
    }
    diagnostic_stage(trace,RPI5_SD_CACHE_STAGE_GENERAL_DECODE);
    diagnostic_payload(trace,data,length>512 && length<=1024?1024:512);
    unsigned function; uint32_t address;
    if ((rc=rpi5_sd_cache_location(data,length>512?1024:512,&function,&address))) goto failed;
    value.function=function; value.address=address;
    if (trace) { trace->function=function; trace->address=address; }
    if (!function) {
        value.state=RPI5_SD_CACHE_ABSENT; publish(out,&value);
        diagnostic_stage(trace,RPI5_SD_CACHE_STAGE_COMPLETE); return RPI5_SD_OK;
    }
    /* One register set may straddle two pages. Request only its exact bytes,
     * discard each wire block's dummy suffix, and assemble the register view. */
    unsigned first=512-(address&511), remainder=512-first;
    diagnostic_stage(trace,RPI5_SD_CACHE_STAGE_PERFORMANCE_FIRST);
    if ((rc=extension(c,function,address,first,data))) goto failed;
    if (remainder) {
        diagnostic_stage(trace,RPI5_SD_CACHE_STAGE_PERFORMANCE_SECOND);
        if ((rc=extension(c,function,address+first,remainder,data+512))) goto failed;
        for (unsigned i=0;i<remainder;i++) data[first+i]=data[512+i];
    }
    diagnostic_stage(trace,RPI5_SD_CACHE_STAGE_PERFORMANCE_DECODE);
    diagnostic_payload(trace,data,512);
    if ((rc=rpi5_sd_cache_performance(data,512,&value))) goto failed;
    publish(out,&value);
    diagnostic_stage(trace,RPI5_SD_CACHE_STAGE_COMPLETE);
    return RPI5_SD_OK;
failed:
    c->ready=0;
    return rc;
}
int rpi5_sd_cache_probe(struct rpi5_sd_card *c, struct rpi5_sd_cache_observation *out,
    void *scratch, size_t scratch_bytes)
{
    return rpi5_sd_cache_probe_traced(c,out,scratch,scratch_bytes,0);
}
