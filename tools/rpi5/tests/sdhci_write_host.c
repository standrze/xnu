/* SPDX-License-Identifier: BSD-2-Clause */
/* Synthetic register model only. Never opens a device. */
#include "rpi5_sdhci_write.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum fault { NONE, STALE_ERROR, NO_CARD, ENABLE_FAIL, RESTORE_FAIL, COMMAND_TIMEOUT,
    PRE_R1_ERROR, WRITE_R1_ERROR, NO_READY, EARLY_DONE, NO_SPACE, FIFO_ERROR,
    FIFO_EARLY_DONE, DATA_TIMEOUT, BUSY_TIMEOUT, PROGRAM_TIMEOUT, REMOVE_MID_FIFO,
    COMMAND_INHIBIT_TIMEOUT, INITIAL_BUSY_TIMEOUT };
struct model {
    enum fault fault;
    uint32_t status, enable, signal, argument;
    unsigned accesses, writes, words, commands, status_commands, write_commands;
    unsigned post, frozen;
    uint64_t us;
    uint8_t *source;
    uint32_t payload[128];
};
static uint32_t read32(void *context, uint32_t offset)
{
    struct model *m=context; m->accesses++;
    if (m->source) { memset(m->source,0xff,512); m->source=0; }
    switch (offset) {
    case 0x24:
        if (m->fault==NO_CARD || (m->fault==REMOVE_MID_FIFO && m->words==64)) return 0;
        return 0x10000 | (m->fault==NO_SPACE?0:0x400) |
            (m->fault==BUSY_TIMEOUT && m->post?2:0) |
            (m->fault==COMMAND_INHIBIT_TIMEOUT?1:0) |
            (m->fault==INITIAL_BUSY_TIMEOUT?2:0);
    case 0x30:
        if (m->fault==STALE_ERROR || (m->fault==FIFO_ERROR && m->words==64)) return 0x8000;
        if (m->fault==FIFO_EARLY_DONE && m->words==64) return m->status|2;
        return m->status;
    case 0x34: return m->enable;
    case 0x38: return m->signal;
    case 0x10:
        if (m->fault==PRE_R1_ERROR && !m->write_commands) return 0x80000000;
        if (m->fault==WRITE_R1_ERROR && m->write_commands && !m->post) return 0x80000000;
        if (m->fault==PROGRAM_TIMEOUT && m->post) return 7<<9;
        return 0x900;
    default: assert(0); return 0;
    }
}
static void write32(void *context, uint32_t offset, uint32_t value)
{
    struct model *m=context; m->accesses++; m->writes++;
    switch (offset) {
    case 0x30: m->status&=~value; break;
    case 0x34:
        if (m->fault==ENABLE_FAIL && (value&0x10)) return;
        if (m->fault==RESTORE_FAIL && value==0x8003) return;
        m->enable=value; break;
    case 0x04: assert(value==0x10200); break;
    case 0x08: m->argument=value; break;
    case 0x0c: {
        unsigned cmd=value>>24; m->commands++;
        assert(cmd==13 || cmd==24);
        if (cmd==13) {
            assert(value==0x0d1a0000 && m->argument==0x12340000);
            m->status_commands++; m->status=1;
        } else {
            assert(value==0x183a0000 && m->argument>=1050624 && m->argument<1312768);
            m->write_commands++; assert(m->write_commands==1);
            m->status=m->fault==COMMAND_TIMEOUT?0:1;
            if (m->fault!=NO_READY) m->status|=0x10;
            if (m->fault==EARLY_DONE) m->status|=2;
        }
        break;
    }
    case 0x20:
        assert(m->words<128); m->payload[m->words++]=value;
        if (m->words==128) { m->post=1; if (m->fault!=DATA_TIMEOUT) m->status|=2; }
        break;
    default: assert(0);
    }
}
static uint64_t micros(void *context) { return ((struct model *)context)->us; }
static void delay(void *context, uint32_t us)
{
    struct model *m=context; if (!m->frozen) m->us+=us;
}
static struct rpi5_sd_card card(struct model *m)
{
    return (struct rpi5_sd_card){ .io={m,read32,write32,micros,delay},
        .sectors=250347520,.rca=0x12340000,.ready=1 };
}
/* Admission has independent identity/header mutation tests. Here the only
 * synthetic lease isolates transport behavior; no hardware is authorized. */
static struct rpi5_sd_write_policy lease(void)
{
    return (struct rpi5_sd_write_policy){.epoch=9,.start=RPI5_SD_WRITE_START,
        .blocks=RPI5_SD_WRITE_BLOCKS,.max_request_blocks=RPI5_SD_WRITE_MAX_REQUEST_BLOCKS,
        .state=RPI5_SD_WRITE_ENABLED};
}
int main(void)
{
    uint8_t raw[514]; uint8_t *source=raw+1;
    for (unsigned boundary=0;boundary<2;boundary++) {
        for (unsigned i=0;i<512;i++) source[i]=(uint8_t)i;
        struct model m={.enable=0x8003,.source=source};
        struct rpi5_sd_card c=card(&m); struct rpi5_sd_write_policy p=lease();
        assert(!rpi5_sd_write_sector(&c,&p,9,boundary?1312767:1050624,source,512));
        assert(m.words==128 && m.write_commands==1 && m.status_commands==2);
        assert(m.enable==0x8003 && c.ready==1 && p.state==RPI5_SD_WRITE_ENABLED);
        for (unsigned i=0;i<128;i++) {
            uint32_t expected=0; for (unsigned j=0;j<4;j++) expected|=(uint32_t)(uint8_t)(i*4+j)<<(8*j);
            assert(m.payload[i]==expected);
        }
    }
    for (unsigned fault=STALE_ERROR;fault<=INITIAL_BUSY_TIMEOUT;fault++) {
        struct model m={.enable=0x8003,.fault=(enum fault)fault};
        struct rpi5_sd_card c=card(&m); struct rpi5_sd_write_policy p=lease();
        int rc=rpi5_sd_write_sector(&c,&p,9,1050624,source,512);
        assert(rc<0 && !c.ready && p.state==RPI5_SD_WRITE_QUARANTINED);
        assert(m.write_commands<=1 && m.words<=128 && m.commands<2100);
        if (fault!=RESTORE_FAIL) assert(m.enable==0x8003);
        if (fault==EARLY_DONE || fault==NO_READY || fault==NO_SPACE || fault==WRITE_R1_ERROR)
            assert(m.words==0);
        if (fault==FIFO_ERROR || fault==FIFO_EARLY_DONE || fault==REMOVE_MID_FIFO) assert(m.words==64);
        unsigned accesses=m.accesses;
        assert(rpi5_sd_write_sector(&c,&p,9,1050624,source,512)==RPI5_SD_INVALID);
        assert(m.accesses==accesses); /* Quarantine: no retries or reset. */
    }
    struct model m={.enable=0x8003}; struct rpi5_sd_card c=card(&m);
    struct rpi5_sd_write_policy p=lease();
    const uint64_t invalid[]={0,2048,1050623,1312768,UINT64_MAX};
    for (unsigned i=0;i<sizeof invalid/sizeof invalid[0];i++)
        assert(rpi5_sd_write_sector(&c,&p,9,invalid[i],source,512)==RPI5_SD_INVALID);
    assert(rpi5_sd_write_sector(&c,&p,8,1050624,source,512)==RPI5_SD_INVALID);
    assert(rpi5_sd_write_sector(&c,&p,9,1050624,0,512)==RPI5_SD_INVALID);
    assert(rpi5_sd_write_sector(&c,&p,9,1050624,source,511)==RPI5_SD_INVALID);
    assert(rpi5_sd_write_sector(0,&p,9,1050624,source,512)==RPI5_SD_INVALID);
    assert(rpi5_sd_write_sector(&c,0,9,1050624,source,512)==RPI5_SD_INVALID);
    assert(m.accesses==0);
    c.sectors--; assert(rpi5_sd_write_sector(&c,&p,9,1050624,source,512)==RPI5_SD_INVALID);
    assert(m.accesses==0 && p.state==RPI5_SD_WRITE_DISABLED);
    c=card(&m); p=lease(); c.rca|=1;
    assert(rpi5_sd_write_sector(&c,&p,9,1050624,source,512)==RPI5_SD_INVALID && !m.accesses);
    c=card(&m); p=lease(); c.io.delay_us=0;
    assert(rpi5_sd_write_sector(&c,&p,9,1050624,source,512)==RPI5_SD_INVALID && !m.accesses);
    c=card(&m); p=lease(); m.signal=1;
    assert(rpi5_sd_write_sector(&c,&p,9,1050624,source,512)==RPI5_SD_INVALID && !m.writes);
    m.signal=0; assert(!rpi5_sd_write_wait_ready(&c,&p,9)); assert(!m.words && !m.write_commands);
    m=(struct model){.enable=0x8003,.fault=PROGRAM_TIMEOUT,.post=1}; c=card(&m); p=lease();
    assert(rpi5_sd_write_wait_ready(&c,&p,9)==RPI5_SD_TIMEOUT);
    assert(!c.ready && p.state==RPI5_SD_WRITE_QUARANTINED && !m.words && !m.write_commands);
    m=(struct model){.enable=0x8003,.fault=NO_READY,.frozen=1}; c=card(&m); p=lease();
    assert(rpi5_sd_write_sector(&c,&p,9,1050624,source,512)==RPI5_SD_TIMEOUT);
    assert(!c.ready && p.state==RPI5_SD_WRITE_QUARANTINED && m.accesses<2000000);
    puts("SDHCI_WRITE_PASS");
    return 0;
}
