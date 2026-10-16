/* SPDX-License-Identifier: BSD-2-Clause */
/* Independent experimental single-sector PIO write engine. Register/protocol
 * facts only from FreeBSD sdhci.h/mmcreg.h; implementation is newly written.
 * See docs/rpi5/GATE4-WRITE-POLICY.md. No read-only opcode list is modified.
 */
#include "rpi5_sdhci_write.h"

enum {
    BLOCK=0x04, ARGUMENT=0x08, COMMAND=0x0c, RESPONSE=0x10, DATA=0x20,
    PRESENT=0x24, STATUS=0x30, STATUS_ENABLE=0x34, SIGNAL_ENABLE=0x38,
    CMD_DONE=1, TRANSFER_DONE=2, WRITE_READY=0x10,
    CMD_INHIBIT=1, DATA_INHIBIT=2, BUFFER_SPACE=0x400, CARD_PRESENT=0x10000
};
#define ERRORS UINT32_C(0xffff8000)
#define R1_ERRORS UINT32_C(0xfff98088)
#define COMMAND_US UINT32_C(100000)
#define TRANSFER_US UINT32_C(1000000)
#define PROGRAM_US UINT32_C(2000000)
#define WAIT_LIMIT UINT32_C(200000)

static uint32_t rd(struct rpi5_sd_card *c, uint32_t offset)
{
    return c->io.read32(c->io.context,offset);
}
static void wr(struct rpi5_sd_card *c, uint32_t offset, uint32_t value)
{
    c->io.write32(c->io.context,offset,value);
}
static uint64_t ticks(struct rpi5_sd_card *c)
{
    return c->io.microseconds(c->io.context);
}
static void delay(struct rpi5_sd_card *c, uint32_t us)
{
    c->io.delay_us(c->io.context,us);
}
static int usable(struct rpi5_sd_card *c)
{
    c->last_interrupt=rd(c,STATUS);
    if (c->last_interrupt&ERRORS) return RPI5_SD_CONTROLLER;
    if (!(rd(c,PRESENT)&CARD_PRESENT)) return RPI5_SD_CARD;
    return RPI5_SD_OK;
}
static int wait_present(struct rpi5_sd_card *c, uint32_t mask, uint32_t want, uint32_t budget)
{
    uint64_t start=ticks(c);
    for (uint32_t i=0;i<WAIT_LIMIT;i++) {
        int rc=usable(c);
        if (rc) return rc;
        if ((rd(c,PRESENT)&mask)==want) return RPI5_SD_OK;
        if (ticks(c)-start>=budget) break;
        delay(c,10);
    }
    return RPI5_SD_TIMEOUT;
}
static int wait_status(struct rpi5_sd_card *c, uint32_t bit, uint32_t budget)
{
    uint64_t start=ticks(c);
    for (uint32_t i=0;i<WAIT_LIMIT;i++) {
        int rc=usable(c);
        if (rc) return rc;
        /* A write cannot finish before the host supplied its payload. Unlike
         * a read, WRITE_READY+TRANSFER_DONE is not a valid coalesced event. */
        if (bit==WRITE_READY && (c->last_interrupt&TRANSFER_DONE)) return RPI5_SD_CONTROLLER;
        if (c->last_interrupt&bit) {
            wr(c,STATUS,bit); /* Consume only this W1C event. */
            return RPI5_SD_OK;
        }
        if (ticks(c)-start>=budget) break;
        delay(c,10);
    }
    return RPI5_SD_TIMEOUT;
}
static int send(struct rpi5_sd_card *c, unsigned index, uint32_t argument, uint32_t *response)
{
    if (index!=13 && index!=24) return RPI5_SD_INVALID;
    c->last_command=index;
    /* Inspect stale errors before clearing them: do not turn a prior failed
     * transfer into an apparently clean new request. */
    int rc=wait_present(c,CMD_INHIBIT|(index==24?DATA_INHIBIT:0),0,COMMAND_US);
    if (rc) return rc;
    wr(c,STATUS,UINT32_MAX);
    if (index==24) wr(c,BLOCK,UINT32_C(0x00010200));
    wr(c,ARGUMENT,argument);
    /* 48-bit response, CRC/index checks; CMD24 adds DATA_PRESENT. Transfer
     * mode zero selects write, single block, no DMA/auto-CMD/block count. */
    wr(c,COMMAND,((uint32_t)index<<24)|((index==24?UINT32_C(0x3a):UINT32_C(0x1a))<<16));
    rc=wait_status(c,CMD_DONE,COMMAND_US);
    if (rc) return rc;
    *response=rd(c,RESPONSE);
    return (*response&R1_ERRORS)?RPI5_SD_CARD:RPI5_SD_OK;
}
static int ready(struct rpi5_sd_card *c)
{
    uint64_t start=ticks(c);
    for (uint32_t i=0;i<2000;i++) {
        uint32_t response;
        int rc=send(c,13,c->rca,&response);
        if (rc) return rc;
        if ((response&UINT32_C(0x1f00))==UINT32_C(0x900)) return RPI5_SD_OK;
        unsigned state=(response>>9)&15;
        if ((response&256) || (state!=4 && state!=6 && state!=7)) return RPI5_SD_CARD;
        if (ticks(c)-start>=PROGRAM_US) break;
        delay(c,1000);
    }
    return RPI5_SD_TIMEOUT;
}
static int inputs(struct rpi5_sd_card *c, struct rpi5_sd_write_policy *p, uint64_t epoch)
{
    if (!c || !p || !c->io.read32 || !c->io.write32 || !c->io.microseconds || !c->io.delay_us ||
        !rpi5_sd_write_request_valid(p,epoch,RPI5_SD_WRITE_START,1,512)) return 0;
    if (c->ready!=1 || c->sectors!=UINT64_C(250347520) || !c->rca || (c->rca&65535)) {
        rpi5_sd_write_revoke(p);
        return 0;
    }
    return 1;
}
static int fail(struct rpi5_sd_card *c, struct rpi5_sd_write_policy *p, int rc)
{
    c->ready=0;
    rpi5_sd_write_quarantine(p);
    return rc;
}
int rpi5_sd_write_wait_ready(struct rpi5_sd_card *c, struct rpi5_sd_write_policy *p, uint64_t epoch)
{
    if (!inputs(c,p,epoch)) return RPI5_SD_INVALID;
    if (rd(c,SIGNAL_ENABLE)) return RPI5_SD_INVALID; /* No IRQ ownership assumption. */
    int rc=wait_present(c,DATA_INHIBIT,0,PROGRAM_US);
    if (!rc) rc=ready(c);
    return rc?fail(c,p,rc):RPI5_SD_OK;
}
int rpi5_sd_write_sector(struct rpi5_sd_card *c, struct rpi5_sd_write_policy *p,
    uint64_t epoch, uint64_t lba, const void *source, size_t bytes)
{
    if (!source || bytes!=512 || !rpi5_sd_write_request_valid(p,epoch,lba,1,bytes) ||
        !inputs(c,p,epoch)) return RPI5_SD_INVALID;
    uint8_t owned[512];
    for (unsigned i=0;i<512;i++) owned[i]=((const uint8_t *)source)[i];
    if (rd(c,SIGNAL_ENABLE)) return RPI5_SD_INVALID;
    int rc=usable(c);
    if (rc) return fail(c,p,rc);
    uint32_t saved=rd(c,STATUS_ENABLE);
    wr(c,STATUS_ENABLE,saved|WRITE_READY);
    if (!(rd(c,STATUS_ENABLE)&WRITE_READY)) { rc=RPI5_SD_CONTROLLER; goto done; }
    rc=wait_present(c,DATA_INHIBIT,0,PROGRAM_US);
    if (!rc) rc=ready(c);
    uint32_t response;
    if (!rc) rc=send(c,24,(uint32_t)lba,&response);
    if (!rc) rc=wait_status(c,WRITE_READY,TRANSFER_US);
    if (!rc && !(rd(c,PRESENT)&BUFFER_SPACE)) rc=RPI5_SD_CONTROLLER;
    if (!rc) for (unsigned i=0;i<128;i++) {
        rc=usable(c);
        if (rc) break;
        if (c->last_interrupt&TRANSFER_DONE) { rc=RPI5_SD_CONTROLLER; break; }
        /* Naturally aligned 32-bit FIFO MMIO; unaligned source is supported. */
        uint32_t word=0;
        for (unsigned j=0;j<4;j++) word|=(uint32_t)owned[i*4+j]<<(8*j);
        wr(c,DATA,word);
    }
    if (!rc) rc=wait_status(c,TRANSFER_DONE,TRANSFER_US);
    if (!rc) rc=wait_present(c,DATA_INHIBIT,0,PROGRAM_US);
    if (!rc) rc=ready(c);
done:
    wr(c,STATUS_ENABLE,saved);
    if (rd(c,STATUS_ENABLE)!=saved) rc=RPI5_SD_CONTROLLER;
    return rc?fail(c,p,rc):RPI5_SD_OK;
}
