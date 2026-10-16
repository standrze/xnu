/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_sdhci_core.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

struct model {
    uint32_t regs[64], commands[512], arguments[512], ncommands, ndata;
    uint64_t time;
    unsigned fault, acmd_waits;
};
enum { RESET_STUCK=1, CLOCK_STUCK, COMMAND_STUCK, COMMAND_CRC, DATA_CRC,
    READ_STUCK, TRANSFER_STUCK, BAD_R7, BAD_R6, BAD_R1, OCR_STUCK, SDSC,
    CLOCK_STALL, BUSY_STUCK, PRESENT_MISMATCH };

static uint32_t read32(void *context, uint32_t offset)
{
    struct model *m=context;
    assert(!(offset&3) && offset<256);
    if (offset==0x20) {
        assert(m->ncommands && m->commands[m->ncommands-1]==17);
        assert(m->ndata<128);
        uint32_t word=0, lba=m->arguments[m->ncommands-1];
        for (unsigned i=0;i<4;i++) word|=((m->ndata*4+i+lba)&255)<<(i*8);
        if (++m->ndata==128) {
            m->regs[0x24/4]=0;
            if (m->fault!=TRANSFER_STUCK) m->regs[0x30/4]|=2;
            if (m->fault==DATA_CRC) m->regs[0x30/4]|=UINT32_C(0x00208000);
        }
        return word;
    }
    return m->regs[offset/4];
}
static void write32(void *context, uint32_t offset, uint32_t value)
{
    struct model *m=context;
    assert(!(offset&3) && offset<256);
    if (offset==0x30) { m->regs[offset/4]&=~value; return; }
    if (offset==0x38) assert(value==0); /* IRQ signals disabled throughout. */
    if (offset==0x28) assert(value==0xf00); /* 1-bit, 3.3-V host selection. */
    if (offset==0x3c) assert(value==0); /* No UHS switch/1.8-V enable. */
    if (offset==0x2c) {
        if (value&UINT32_C(0x01000000)) {
            m->regs[offset/4]=(m->fault==RESET_STUCK)?value:0;
            return;
        }
        assert(((value>>8)&255)==250 && !(value&0xc0));
        m->regs[offset/4]=value|((m->fault==CLOCK_STUCK)?0:2);
        return;
    }
    m->regs[offset/4]=value;
    if (offset!=0x0c) return;
    unsigned index=value>>24, flags=(value>>16)&255;
    assert(m->ncommands<512);
    m->commands[m->ncommands]=index;
    m->arguments[m->ncommands++]=m->regs[0x08/4];
    assert(!(value&15)); /* No DMA/block-count/auto-command bits. */
    assert((value&0xffff)==(index==17?0x10u:0));
    assert((flags&32)==(index==17?32u:0));
    if (m->fault==COMMAND_STUCK || m->fault==CLOCK_STALL) return;
    if (m->fault==COMMAND_CRC) { m->regs[0x30/4]=UINT32_C(0x00028000); return; }
    m->regs[0x30/4]=1;
    m->regs[0x10/4]=0;
    uint32_t arg=m->regs[0x08/4];
    switch (index) {
    case 0:
        assert(arg==0 && flags==0); break;
    case 8:
        assert(arg==0x1aa && flags==26);
        m->regs[0x10/4]=(m->fault==BAD_R7)?0x1ab:0x1aa; break;
    case 55:
        assert(arg==0 && flags==26);
        m->regs[0x10/4]=32; break;
    case 41:
        assert(m->ncommands>=2 && m->commands[m->ncommands-2]==55);
        assert(arg==UINT32_C(0x40300000) && flags==2);
        m->regs[0x10/4]=UINT32_C(0x40300000);
        if (m->fault==SDSC) m->regs[0x10/4]&=~UINT32_C(0x40000000);
        if (m->fault!=OCR_STUCK && !m->acmd_waits) m->regs[0x10/4]|=UINT32_C(0x80000000);
        if (m->acmd_waits) m->acmd_waits--;
        break;
    case 2:
        assert(arg==0 && flags==9);
        m->regs[0x10/4]=UINT32_C(0x44556677);
        m->regs[0x14/4]=UINT32_C(0x00112233);
        m->regs[0x18/4]=UINT32_C(0x89abcdef);
        m->regs[0x1c/4]=UINT32_C(0x001b534d);
        break;
    case 3:
        assert(arg==0 && flags==26);
        m->regs[0x10/4]=(m->fault==BAD_R6)?UINT32_C(0x1234e000):UINT32_C(0x12340000);
        break;
    case 9:
        assert(arg==UINT32_C(0x12340000) && flags==9);
        /* Wire CSD: 40 00 00 00 00 09 00 00 01 ff 00 00 00 00 00 CRC.
         * 512 * 1024 sectors = 256 MiB. RESP0 contains the low end. */
        m->regs[0x10/4]=0;
        m->regs[0x14/4]=UINT32_C(0x0001ff00);
        m->regs[0x18/4]=UINT32_C(0x00000900);
        m->regs[0x1c/4]=UINT32_C(0x00400000);
        break;
    case 7:
        assert(arg==UINT32_C(0x12340000) && flags==27);
        if (m->fault!=BUSY_STUCK) m->regs[0x30/4]|=2;
        break;
    case 13:
        assert(arg==UINT32_C(0x12340000) && flags==26);
        m->regs[0x10/4]=(m->fault==BAD_R1)?UINT32_C(0x00400900):0x900;
        break;
    case 17:
        assert(flags==58 && m->regs[0x04/4]==UINT32_C(0x00010200));
        assert(m->ncommands>9); m->ndata=0;
        if (m->fault==BAD_R1) m->regs[0x10/4]=UINT32_C(0x00400000);
        if (m->fault!=READ_STUCK) m->regs[0x30/4]|=0x20;
        m->regs[0x24/4]=(m->fault==PRESENT_MISMATCH)?0:0x800;
        break;
    default: assert(!"write/erase/unexpected command issued");
    }
}
static uint64_t microseconds(void *context) { return ((struct model *)context)->time; }
static void delay_us(void *context, uint32_t us)
{
    struct model *m=context;
    if (m->fault!=CLOCK_STALL) m->time+=us;
}
static struct rpi5_sd_io io_for(struct model *m)
{
    struct rpi5_sd_io io={m,read32,write32,microseconds,delay_us};
    return io;
}
static void new_model(struct model *m)
{
    memset(m,0,sizeof *m); m->regs[0xfc/4]=UINT32_C(0x00020000);
}
static void capacity_tests(void)
{
    uint8_t csd[16]={0x40,0,0,0,0,9,0,0,1,0xff,0,0,0,0,0,0};
    uint64_t sectors=123;
    assert(!rpi5_sd_csd_sectors(csd,&sectors) && sectors==524288);
    csd[7]=0x3f; csd[8]=0xff; csd[9]=0xff;
    assert(!rpi5_sd_csd_sectors(csd,&sectors) && sectors==(UINT64_C(1)<<32));
    csd[0]=0x80; sectors=123;
    assert(rpi5_sd_csd_sectors(csd,&sectors)==RPI5_SD_UNSUPPORTED && sectors==123);
    csd[0]=0x40; csd[5]=8;
    assert(rpi5_sd_csd_sectors(csd,&sectors)==RPI5_SD_UNSUPPORTED && sectors==123);
    assert(rpi5_sd_csd_sectors(0,&sectors)==RPI5_SD_INVALID);
    assert(rpi5_sd_csd_sectors(csd,0)==RPI5_SD_INVALID);
    const uint32_t regs[4]={0,UINT32_C(0x0001ff00),UINT32_C(0x00000900),UINT32_C(0x00400000)};
    const uint8_t expected[16]={0x40,0,0,0,0,9,0,0,1,0xff,0,0,0,0,0,0};
    rpi5_sd_csd_bytes(regs,csd); assert(!memcmp(csd,expected,16));
}
static void happy_path(void)
{
    struct model m; new_model(&m); m.acmd_waits=2;
    struct rpi5_sd_card c; struct rpi5_sd_io io=io_for(&m);
    assert(!rpi5_sd_start(&c,&io,200000000));
    assert(c.ready && c.rca==UINT32_C(0x12340000) && c.sectors==524288);
    const uint32_t sequence[]={0,8,55,41,55,41,55,41,2,3,9,7,13};
    assert(m.ncommands==13 && !memcmp(m.commands,sequence,sizeof sequence));
    uint8_t out[514]; memset(out,0xa5,sizeof out);
    for (unsigned k=0;k<4;k++) {
        uint64_t lba=k==3?c.sectors-1:k*17;
        assert(!rpi5_sd_read_sector(&c,lba,out+1,512));
        for (unsigned i=0;i<512;i++) assert(out[i+1]==(uint8_t)(i+lba));
        assert(out[0]==0xa5 && out[513]==0xa5 && c.ready);
    }
    unsigned prior=m.ncommands;
    assert(rpi5_sd_read_sector(&c,c.sectors,out,512)==RPI5_SD_INVALID);
    assert(rpi5_sd_read_sector(&c,UINT64_MAX,out,512)==RPI5_SD_INVALID);
    assert(rpi5_sd_read_sector(&c,0,0,512)==RPI5_SD_INVALID);
    assert(rpi5_sd_read_sector(&c,0,out,511)==RPI5_SD_INVALID);
    assert(m.ncommands==prior && c.ready);
}
static void initialization_faults(void)
{
    const unsigned faults[]={RESET_STUCK,CLOCK_STUCK,COMMAND_STUCK,COMMAND_CRC,
        BAD_R7,BAD_R6,BAD_R1,OCR_STUCK,SDSC,CLOCK_STALL,BUSY_STUCK};
    for (unsigned i=0;i<sizeof faults/sizeof faults[0];i++) {
        struct model m; new_model(&m); m.fault=faults[i];
        struct rpi5_sd_card c={0}; struct rpi5_sd_io io=io_for(&m);
        c.ready=1; c.sectors=UINT64_MAX;
        assert(rpi5_sd_start(&c,&io,200000000)<0 && !c.ready);
        assert(m.time<UINT64_C(4000000));
        uint8_t out[512]; assert(rpi5_sd_read_sector(&c,0,out,512)==RPI5_SD_INVALID);
    }
    struct model m; new_model(&m); struct rpi5_sd_card c={0};
    struct rpi5_sd_io io=io_for(&m);
    assert(rpi5_sd_start(&c,&io,0)==RPI5_SD_INVALID && !m.ncommands);
    assert(rpi5_sd_start(0,&io,200000000)==RPI5_SD_INVALID);
    io.read32=0;
    assert(rpi5_sd_start(&c,&io,200000000)==RPI5_SD_INVALID);
}
static void read_faults(void)
{
    const unsigned faults[]={COMMAND_STUCK,COMMAND_CRC,DATA_CRC,READ_STUCK,
        TRANSFER_STUCK,BAD_R1,CLOCK_STALL,PRESENT_MISMATCH};
    for (unsigned i=0;i<sizeof faults/sizeof faults[0];i++) {
        struct model m; new_model(&m); struct rpi5_sd_card c={0};
        struct rpi5_sd_io io=io_for(&m); assert(!rpi5_sd_start(&c,&io,200000000));
        m.fault=faults[i]; uint8_t out[512], prior[512];
        memset(out,0xa5,sizeof out); memcpy(prior,out,sizeof prior);
        assert(rpi5_sd_read_sector(&c,31,out,512)<0 && !c.ready);
        assert(!memcmp(out,prior,sizeof out));
        unsigned commands=m.ncommands;
        assert(rpi5_sd_read_sector(&c,31,out,512)==RPI5_SD_INVALID && m.ncommands==commands);
        m.fault=0;
        assert(!rpi5_sd_start(&c,&io,200000000));
        assert(!rpi5_sd_read_sector(&c,31,out,512) && c.ready);
    }
}
static void identity_observations(void)
{
    struct model m; new_model(&m);
    struct rpi5_sd_io io=io_for(&m);
    struct rpi5_sd_card c;
    struct rpi5_sd_identity identity, before;
    memset(&identity,0xa5,sizeof identity); before=identity;
    assert(rpi5_sd_start_identified(&c,&io,200000000,0)==RPI5_SD_INVALID && !m.ncommands);
    assert(rpi5_sd_start_identified(&c,&io,1,&identity)==RPI5_SD_INVALID);
    assert(!memcmp(&identity,&before,sizeof identity) && !m.ncommands);
    assert(!rpi5_sd_start_identified(&c,&io,200000000,&identity));
    const uint8_t cid[16]={0x1b,0x53,0x4d,0x89,0xab,0xcd,0xef,0,0x11,0x22,0x33,0x44,0x55,0x66,0x77,0};
    const uint8_t csd[16]={0x40,0,0,0,0,9,0,0,1,0xff,0,0,0,0,0,0};
    assert(!memcmp(identity.cid,cid,16) && !memcmp(identity.csd,csd,16));
    const uint32_t sequence[]={0,8,55,41,2,3,9,7,13};
    assert(m.ncommands==9 && !memcmp(m.commands,sequence,sizeof sequence));
    new_model(&m); m.fault=BAD_R1; identity=before;
    assert(rpi5_sd_start_identified(&c,&io,200000000,&identity)==RPI5_SD_CARD);
    assert(!memcmp(&identity,&before,sizeof identity) && !c.ready);
}
int main(void)
{
    capacity_tests(); happy_path(); initialization_faults(); read_faults(); identity_observations();
    puts("SDHCI_CORE_PASS"); return 0;
}
