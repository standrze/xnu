/* SPDX-License-Identifier: BSD-2-Clause */
/* Independent bounded SDHCI/SD v2 PIO implementation. Hardware facts and
 * protocol references are recorded in docs/rpi5/GATE4-STORAGE.md.
 * No Linux implementation code is incorporated here.
 */
#include "rpi5_sdhci_core.h"

enum {
    BLOCK=0x04, ARGUMENT=0x08, COMMAND=0x0c, RESPONSE=0x10, DATA=0x20,
    PRESENT=0x24, CONTROL=0x28, CLOCK=0x2c, STATUS=0x30,
    STATUS_ENABLE=0x34, SIGNAL_ENABLE=0x38, CONTROL2=0x3c, VERSION=0xfc,
    CMD_DONE=1, TRANSFER_DONE=2, READ_READY=0x20,
    CMD_INHIBIT=1, DATA_INHIBIT=2, BUFFER_READ_READY=0x800,
    RESPONSE_136=1, RESPONSE_48=2, RESPONSE_BUSY=3,
    CHECK_CRC=8, CHECK_INDEX=16, DATA_PRESENT=32
};
#define INTERRUPT_ERRORS UINT32_C(0xffff8000)
#define R1_ERRORS UINT32_C(0xfff98008)
#define COMMAND_US UINT32_C(100000)
#define TRANSFER_US UINT32_C(500000)
#define WAIT_LIMIT UINT32_C(100000)

static int valid_io(const struct rpi5_sd_io *io)
{
    return io && io->read32 && io->write32 && io->microseconds && io->delay_us;
}
static uint32_t read_reg(struct rpi5_sd_card *c, uint32_t reg)
{
    return c->io.read32(c->io.context,reg);
}
static void write_reg(struct rpi5_sd_card *c, uint32_t reg, uint32_t value)
{
    c->io.write32(c->io.context,reg,value);
}
static uint64_t now(struct rpi5_sd_card *c)
{
    return c->io.microseconds(c->io.context);
}
static void delay(struct rpi5_sd_card *c, uint32_t us)
{
    c->io.delay_us(c->io.context,us);
}
static int wait_register(struct rpi5_sd_card *c, uint32_t reg,
    uint32_t mask, uint32_t want, uint32_t budget)
{
    uint64_t start=now(c);
    for (uint32_t i=0;i<WAIT_LIMIT;i++) {
        if ((read_reg(c,reg)&mask)==want) return RPI5_SD_OK;
        if (now(c)-start>=budget) return RPI5_SD_TIMEOUT;
        delay(c,10);
    }
    return RPI5_SD_TIMEOUT; /* Also bounded if the supplied clock stalls. */
}
static int wait_interrupt(struct rpi5_sd_card *c, uint32_t wanted, uint32_t budget)
{
    uint64_t start=now(c);
    for (uint32_t i=0;i<WAIT_LIMIT;i++) {
        uint32_t status=read_reg(c,STATUS);
        c->last_interrupt=status;
        if (status&INTERRUPT_ERRORS) return RPI5_SD_CONTROLLER;
        if (status&wanted) {
            /* W1C only what was consumed; DATA ready/done may arrive together. */
            write_reg(c,STATUS,wanted);
            return RPI5_SD_OK;
        }
        if (now(c)-start>=budget) return RPI5_SD_TIMEOUT;
        delay(c,10);
    }
    return RPI5_SD_TIMEOUT;
}
static int command(struct rpi5_sd_card *c, unsigned index, uint32_t argument,
    unsigned flags, uint32_t *response)
{
    /* Even a future caller cannot accidentally send a card write/erase opcode. */
    switch (index) {
    case 0: case 2: case 3: case 7: case 8: case 9: case 13:
    case 17: case 41: case 55: break;
    default: return RPI5_SD_INVALID;
    }
    c->last_command=index;
    uint32_t inhibit=CMD_INHIBIT;
    if ((flags&DATA_PRESENT) || (flags&3)==RESPONSE_BUSY) inhibit|=DATA_INHIBIT;
    int rc=wait_register(c,PRESENT,inhibit,0,COMMAND_US);
    if (rc) return rc;
    write_reg(c,STATUS,UINT32_MAX);
    if (flags&DATA_PRESENT) write_reg(c,BLOCK,UINT32_C(0x00010200));
    write_reg(c,ARGUMENT,argument);
    /* DMA/multi-block/auto-CMD12 are never enabled. Combined 32-bit write
     * sets transfer mode before issuing the command on the BCM2712 host. */
    uint32_t transfer=(flags&DATA_PRESENT) ? UINT32_C(0x10) : 0;
    write_reg(c,COMMAND,((uint32_t)index<<24)|((uint32_t)flags<<16)|transfer);
    rc=wait_interrupt(c,CMD_DONE,COMMAND_US);
    if (rc) return rc;
    if (response) *response=read_reg(c,RESPONSE);
    if ((flags&3)==RESPONSE_BUSY) return wait_interrupt(c,TRANSFER_DONE,TRANSFER_US);
    return RPI5_SD_OK;
}
void rpi5_sd_csd_bytes(const uint32_t response[4], uint8_t csd[16])
{
    /* SDHCI omits the final CRC/end byte and shifts the 128-bit R2 payload. */
    for (unsigned i=0;i<4;i++) {
        unsigned reg=3-i;
        uint32_t value=response[reg]<<8;
        if (reg) value|=response[reg-1]>>24;
        for (unsigned j=0;j<4;j++) csd[i*4+j]=(uint8_t)(value>>(24-j*8));
    }
}
int rpi5_sd_csd_sectors(const uint8_t csd[16], uint64_t *sectors)
{
    if (!csd || !sectors) return RPI5_SD_INVALID;
    if ((csd[0]>>6)!=1 || (csd[5]&15)!=9) return RPI5_SD_UNSUPPORTED;
    uint32_t size=((uint32_t)(csd[7]&63)<<16)|((uint32_t)csd[8]<<8)|csd[9];
    *sectors=((uint64_t)size+1)*1024;
    return RPI5_SD_OK;
}
static int host_setup(struct rpi5_sd_card *c, uint32_t source_hz)
{
    uint32_t version=(read_reg(c,VERSION)>>16)&255;
    if (version<2 || version>4) return RPI5_SD_UNSUPPORTED;
    write_reg(c,SIGNAL_ENABLE,0);
    write_reg(c,STATUS_ENABLE,0);
    write_reg(c,CLOCK,UINT32_C(0x01000000)); /* Reset all. */
    int rc=wait_register(c,CLOCK,UINT32_C(0x01000000),0,20000);
    if (rc) return rc;
    /* After reset: 1-bit, no high-speed, 3.3 V power, no UHS/1.8-V request.
     * This is not a substitute for the external GPIO regulator prerequisite. */
    write_reg(c,CONTROL,UINT32_C(0x00000f00));
    write_reg(c,CONTROL2,0);
    uint32_t divider=(source_hz+399999)/400000;
    if (divider&1) divider++;
    divider/=2;
    uint32_t clock=((divider&255)<<8)|((divider&768)>>2)|1;
    write_reg(c,CLOCK,clock|UINT32_C(0x000e0000));
    rc=wait_register(c,CLOCK,2,2,20000);
    if (rc) return rc;
    write_reg(c,CLOCK,clock|UINT32_C(0x000e0004));
    write_reg(c,STATUS,UINT32_MAX);
    write_reg(c,STATUS_ENABLE,INTERRUPT_ERRORS|CMD_DONE|TRANSFER_DONE|READ_READY);
    write_reg(c,SIGNAL_ENABLE,0); /* Poll status, never deliver interrupts. */
    delay(c,1000); /* >=74 clocks at <=400 kHz. */
    return RPI5_SD_OK;
}
static int start(struct rpi5_sd_card *c, const struct rpi5_sd_io *io, uint32_t source_hz,
    struct rpi5_sd_identity *identity)
{
    if (!c || !valid_io(io) || source_hz!=200000000) return RPI5_SD_INVALID;
    struct rpi5_sd_io saved=*io;
    *c=(struct rpi5_sd_card){0}; c->io=saved;
    int rc=host_setup(c,source_hz);
    uint32_t response=0;
    struct rpi5_sd_identity observed={{0},{0}};
    if (rc) return rc;
    if ((rc=command(c,0,0,0,0))) return rc;
    if ((rc=command(c,8,0x1aa,RESPONSE_48|CHECK_CRC|CHECK_INDEX,&response))) return rc;
    if (response!=0x1aa) return RPI5_SD_UNSUPPORTED;
    uint64_t start=now(c);
    for (unsigned tries=0;;tries++) {
        if ((rc=command(c,55,0,RESPONSE_48|CHECK_CRC|CHECK_INDEX,&response))) return rc;
        if ((response&R1_ERRORS) || !(response&32)) return RPI5_SD_CARD;
        /* HCS + 3.2--3.4-V window. Never request S18R voltage switching. */
        if ((rc=command(c,41,UINT32_C(0x40300000),RESPONSE_48,&response))) return rc;
        if (response&UINT32_C(0x80000000)) break;
        if (tries>=199 || now(c)-start>=2000000) return RPI5_SD_TIMEOUT;
        delay(c,10000);
    }
    if (!(response&UINT32_C(0x40000000)) || !(response&UINT32_C(0x00300000)))
        return RPI5_SD_UNSUPPORTED;
    if ((rc=command(c,2,0,RESPONSE_136|CHECK_CRC,0))) return rc;
    if (identity) {
        uint32_t cid_words[4];
        for (unsigned i=0;i<4;i++) cid_words[i]=read_reg(c,RESPONSE+i*4);
        rpi5_sd_csd_bytes(cid_words,observed.cid); /* Same canonical R2 layout. */
    }
    if ((rc=command(c,3,0,RESPONSE_48|CHECK_CRC|CHECK_INDEX,&response))) return rc;
    /* R6's error bits differ from R1; upper half is the newly assigned RCA. */
    if ((response&UINT32_C(0xe000)) || !(response>>16)) return RPI5_SD_CARD;
    c->rca=response&UINT32_C(0xffff0000);
    if ((rc=command(c,9,c->rca,RESPONSE_136|CHECK_CRC,0))) return rc;
    uint32_t words[4]; uint8_t csd[16];
    for (unsigned i=0;i<4;i++) words[i]=read_reg(c,RESPONSE+i*4);
    rpi5_sd_csd_bytes(words,csd);
    if (identity) for (unsigned i=0;i<16;i++) observed.csd[i]=csd[i];
    if ((rc=rpi5_sd_csd_sectors(csd,&c->sectors))) return rc;
    if ((rc=command(c,7,c->rca,RESPONSE_BUSY|CHECK_CRC|CHECK_INDEX,&response))) return rc;
    if (response&R1_ERRORS) return RPI5_SD_CARD;
    if ((rc=command(c,13,c->rca,RESPONSE_48|CHECK_CRC|CHECK_INDEX,&response))) return rc;
    if ((response&R1_ERRORS) || (response&UINT32_C(0x1f00))!=UINT32_C(0x900))
        return RPI5_SD_CARD; /* Ready-for-data in transfer state. */
    c->ready=1;
    if (identity) *identity=observed;
    return RPI5_SD_OK;
}
int rpi5_sd_start(struct rpi5_sd_card *c, const struct rpi5_sd_io *io, uint32_t source_hz)
{
    return start(c,io,source_hz,0);
}
int rpi5_sd_start_identified(struct rpi5_sd_card *c, const struct rpi5_sd_io *io,
    uint32_t source_hz, struct rpi5_sd_identity *identity)
{
    if (!identity) return RPI5_SD_INVALID;
    return start(c,io,source_hz,identity);
}
int rpi5_sd_read_sector(struct rpi5_sd_card *c, uint64_t lba, void *out, size_t size)
{
    if (!c || !c->ready || !valid_io(&c->io) || !out || size!=512 ||
        lba>=c->sectors || lba>UINT32_MAX) return RPI5_SD_INVALID;
    uint8_t sector[512]; uint32_t response=0;
    int rc=command(c,17,(uint32_t)lba,RESPONSE_48|CHECK_CRC|CHECK_INDEX|DATA_PRESENT,&response);
    if (rc) goto fail;
    if (response&R1_ERRORS) { rc=RPI5_SD_CARD; goto fail; }
    rc=wait_interrupt(c,READ_READY,TRANSFER_US);
    if (rc) goto fail;
    if (!(read_reg(c,PRESENT)&BUFFER_READ_READY)) { rc=RPI5_SD_CONTROLLER; goto fail; }
    for (unsigned i=0;i<128;i++) {
        uint32_t word=read_reg(c,DATA);
        for (unsigned j=0;j<4;j++) sector[i*4+j]=(uint8_t)(word>>(8*j));
    }
    rc=wait_interrupt(c,TRANSFER_DONE,TRANSFER_US);
    if (rc) goto fail;
    rc=wait_register(c,PRESENT,DATA_INHIBIT,0,TRANSFER_US);
    if (rc) goto fail;
    for (unsigned i=0;i<512;i++) ((uint8_t *)out)[i]=sector[i];
    return RPI5_SD_OK;
fail:
    c->ready=0;
    return rc;
}
