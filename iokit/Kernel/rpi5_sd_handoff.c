/* SPDX-License-Identifier: BSD-2-Clause */
/* Register/protocol facts: docs/rpi5/GATE4-STORAGE.md. No Linux source copied. */
#include "rpi5_sd_handoff.h"

#define IO_SELECT UINT32_C(8)
#define CARD_POWER UINT32_C(16)
#define CARD_DETECT UINT32_C(32)
enum { HOST_PRESENT=0x24, HOST_CONTROL=0x28, HOST_CLOCK=0x2c,
    HOST_STATUS_ENABLE=0x34, HOST_SIGNAL_ENABLE=0x38, HOST_CONTROL2=0x3c,
    HOST_CAPS=0x40, HOST_VERSION=0xfc, CQ_VERSION=0x200, CQ_CONFIG=0x208,
    CQ_CONTROL=0x20c, CQ_STATUS=0x210, CQ_STATUS_ENABLE=0x214,
    CQ_SIGNAL_ENABLE=0x218, CQ_DOORBELL=0x228, CQ_PENDING=0x234,
    GPIO_ODEN=0, GPIO_DATA=4, GPIO_DIRECTION=8, AON_MUX=0x0c, CFG_PINS=0x44 };

static uint32_t rd(const struct rpi5_sd_platform_io *io, enum rpi5_sd_bank bank, uint32_t reg)
{
    return io->read32(io->context,bank,reg);
}
static void wr(const struct rpi5_sd_platform_io *io, enum rpi5_sd_bank bank, uint32_t reg, uint32_t value)
{
    io->write32(io->context,bank,reg,value);
}
static int update(const struct rpi5_sd_platform_io *io, struct rpi5_sd_handoff_result *out, enum rpi5_sd_bank bank,
    uint32_t reg, uint32_t mask, uint32_t value)
{
    uint32_t previous=rd(io,bank,reg);
    wr(io,bank,reg,(previous&~mask)|(value&mask));
    uint32_t observed=rd(io,bank,reg);
    if ((observed&mask)==(value&mask)) return 0;
    if (!out->readback_mask) {
        out->failed_bank=(uint32_t)bank; out->failed_offset=reg;
        out->readback_mask=mask; out->expected=value&mask; out->observed=observed&mask;
    }
    return RPI5_SD_HANDOFF_READBACK;
}
static int settle(const struct rpi5_sd_platform_io *io, uint32_t us)
{
    /* Do not trust a no-op delay callback. Both iterations and elapsed time
     * are bounded. Clock rollback/wrap is rejected rather than read as success. */
    uint64_t start=io->microseconds(io->context), previous=start;
    for (unsigned i=0;i<20000;i++) {
        uint64_t current=io->microseconds(io->context);
        if (current<previous) return RPI5_SD_HANDOFF_TIMEOUT;
        if (current-start>=us) return 0;
        previous=current;
        io->delay_us(io->context,10);
    }
    return RPI5_SD_HANDOFF_TIMEOUT;
}
static int halt_queue(const struct rpi5_sd_platform_io *io, struct rpi5_sd_handoff_result *out)
{
    if (!(rd(io,RPI5_SD_HOST,CQ_CONFIG)&1)) return 0;
    /* Reject outstanding work rather than abort an unknown firmware write. */
    if (rd(io,RPI5_SD_HOST,CQ_DOORBELL) || rd(io,RPI5_SD_HOST,CQ_PENDING))
        return RPI5_SD_HANDOFF_BUSY;
    uint32_t control=rd(io,RPI5_SD_HOST,CQ_CONTROL);
    if (control&1) {
        /* A pre-existing request without acknowledgement is not a halt. */
        if (!(rd(io,RPI5_SD_HOST,CQ_STATUS)&1)) return RPI5_SD_HANDOFF_BUSY;
    } else {
        wr(io,RPI5_SD_HOST,CQ_STATUS,1); /* W1C old halt acknowledgement only. */
        wr(io,RPI5_SD_HOST,CQ_CONTROL,control|1);
        uint64_t start=io->microseconds(io->context);
        unsigned i;
        for (i=0;i<10000;i++) {
            if (rd(io,RPI5_SD_HOST,CQ_STATUS)&1) break;
            uint64_t now=io->microseconds(io->context);
            if (now<start || now-start>=100000) return RPI5_SD_HANDOFF_TIMEOUT;
            io->delay_us(io->context,10);
        }
        if (i==10000) return RPI5_SD_HANDOFF_TIMEOUT;
    }
    if (!(rd(io,RPI5_SD_HOST,CQ_CONTROL)&1)) return RPI5_SD_HANDOFF_READBACK;
    if (rd(io,RPI5_SD_HOST,CQ_DOORBELL) || rd(io,RPI5_SD_HOST,CQ_PENDING))
        return RPI5_SD_HANDOFF_BUSY;
    wr(io,RPI5_SD_HOST,CQ_STATUS,1);
    return update(io,out,RPI5_SD_HOST,CQ_CONFIG,1,0);
}
int rpi5_sd_handoff(const struct rpi5_sd_platform_io *io, uint32_t variant,
    uint32_t source_hz, struct rpi5_sd_handoff_result *out)
{
    if (!io || !io->read32 || !io->write32 || !io->microseconds || !io->delay_us ||
        !out || variant>1 || source_hz!=200000000) return RPI5_SD_HANDOFF_INVALID;
    *out=(struct rpi5_sd_handoff_result){.stage=RPI5_SD_PREFLIGHT};
    uint32_t version=(rd(io,RPI5_SD_HOST,HOST_VERSION)>>16)&255;
    out->capabilities=rd(io,RPI5_SD_HOST,HOST_CAPS);
    out->gpio_data=rd(io,RPI5_SD_GPIO,GPIO_DATA);
    out->gpio_direction=rd(io,RPI5_SD_GPIO,GPIO_DIRECTION);
    if (version<2 || version>4 || ((out->capabilities>>8)&255)!=200 ||
        !(out->capabilities&UINT32_C(0x01000000)) ||
        /* The BCM2712 removable host reports CQHCI 5.1.0 (0x510), not
         * the synthetic 1.0.0 assumed by the initial model. This exact
         * board profile is captured before any handoff writes. */
        rd(io,RPI5_SD_HOST,CQ_VERSION)!=UINT32_C(0x510))
        return RPI5_SD_HANDOFF_UNSUPPORTED;
    /* Power controls must already be plain push-pull GPIO outputs. Re-routing
     * an unknown pin owner is not a recovery strategy. Only SD3/4 are inspected. */
    if ((rd(io,RPI5_SD_AON_PINS,AON_MUX)&UINT32_C(0x000ff000)) ||
        (out->gpio_direction&(IO_SELECT|CARD_POWER)) ||
        (rd(io,RPI5_SD_GPIO,GPIO_ODEN)&(IO_SELECT|CARD_POWER)))
        return RPI5_SD_HANDOFF_UNSUPPORTED;
    if ((rd(io,RPI5_SD_HOST,HOST_PRESENT)&UINT32_C(0x303)) ||
        (rd(io,RPI5_SD_HOST,HOST_CLOCK)&UINT32_C(0xff000000)) ||
        rd(io,RPI5_SD_HOST,CQ_DOORBELL) || rd(io,RPI5_SD_HOST,CQ_PENDING))
        return RPI5_SD_HANDOFF_BUSY;
    int rc=halt_queue(io,out);
    if (rc) return rc;
    out->stage=RPI5_SD_QUEUE_HALTED;
    if ((rc=update(io,out,RPI5_SD_HOST,CQ_SIGNAL_ENABLE,UINT32_MAX,0)) ||
        (rc=update(io,out,RPI5_SD_HOST,CQ_STATUS_ENABLE,UINT32_MAX,0)) ||
        (rc=update(io,out,RPI5_SD_HOST,HOST_SIGNAL_ENABLE,UINT32_MAX,0)) ||
        (rc=update(io,out,RPI5_SD_HOST,HOST_STATUS_ENABLE,UINT32_MAX,0)) ||
        (rc=update(io,out,RPI5_SD_HOST,HOST_CLOCK,UINT32_C(0xfffd),0))) return rc;
    out->stage=RPI5_SD_CLOCK_OFF;
    /* Power control byte at 0x29: bit 0 enables bus power; bits 3:1
     * select voltage, not power state. The board retains 0xe (3.3-V select)
     * after a zero-byte write. Preserve selection and require POWER_ON clear,
     * rather than incorrectly requiring voltage selection to become zero.
     * This does not prove rail-off: external GPIO power and dwell follow. */
    if ((rc=update(io,out,RPI5_SD_HOST,HOST_CONTROL,UINT32_C(0x0100),0))) return rc;
    if ((rc=update(io,out,RPI5_SD_GPIO,GPIO_DATA,CARD_POWER,0))) goto fail;
    out->stage=RPI5_SD_POWER_OFF;
    if ((rc=settle(io,100000))) goto fail;
    if ((rc=update(io,out,RPI5_SD_GPIO,GPIO_DATA,IO_SELECT,0)) ||
        (rc=settle(io,5000))) goto fail;
    out->stage=RPI5_SD_IO_3300;
    /* Remove host UHS/1.8-V signaling while the card is powered down. */
    if ((rc=update(io,out,RPI5_SD_HOST,HOST_CONTROL2,UINT32_C(0x000f0000),0)) ||
        (rc=update(io,out,RPI5_SD_CFG,CFG_PINS,3,2))) goto fail;
    uint32_t pull_offset=variant ? 0x18 : 0x2c;
    uint32_t pull_mask=variant ? UINT32_C(0x000ff0c0) : UINT32_C(0x0000ff0c);
    uint32_t pull_value=variant ? UINT32_C(0x000aa080) : UINT32_C(0x0000aa08);
    uint32_t cd_pull_offset=variant ? 0x14 : 0x1c;
    uint32_t cd_pull_shift=variant ? 28 : 0;
    if ((rc=update(io,out,RPI5_SD_PINS,pull_offset,pull_mask,pull_value)) ||
        (rc=update(io,out,RPI5_SD_AON_PINS,cd_pull_offset,3u<<cd_pull_shift,2u<<cd_pull_shift)) ||
        (rc=update(io,out,RPI5_SD_GPIO,GPIO_DIRECTION,CARD_DETECT,CARD_DETECT)) ||
        (rc=update(io,out,RPI5_SD_AON_PINS,AON_MUX,UINT32_C(0x00f00000),
            (variant ? 4u : 6u)<<20))) goto fail;
    out->stage=RPI5_SD_PINS_SET;
    /* Card detect is active low. Leave the rail off if the card is absent. */
    if (rd(io,RPI5_SD_GPIO,GPIO_DATA)&CARD_DETECT) { rc=RPI5_SD_HANDOFF_NO_CARD; goto fail; }
    if ((rc=update(io,out,RPI5_SD_GPIO,GPIO_DATA,CARD_POWER,CARD_POWER))) goto fail;
    out->stage=RPI5_SD_POWER_ON;
    if ((rc=settle(io,10000))) goto fail;
    out->gpio_data=rd(io,RPI5_SD_GPIO,GPIO_DATA);
    out->gpio_direction=rd(io,RPI5_SD_GPIO,GPIO_DIRECTION);
    out->cfg_pins=rd(io,RPI5_SD_CFG,CFG_PINS);
    if ((out->gpio_data&(IO_SELECT|CARD_POWER|CARD_DETECT))!=CARD_POWER ||
        (out->gpio_direction&(IO_SELECT|CARD_POWER)) ||
        !(rd(io,RPI5_SD_HOST,HOST_PRESENT)&UINT32_C(0x10000))) {
        rc=RPI5_SD_HANDOFF_READBACK; goto fail;
    }
    out->stage=RPI5_SD_DIGITAL_READY;
    return 0;
fail:
    /* Never restore an inherited UHS state after an incomplete power cycle. */
    (void)update(io,out,RPI5_SD_GPIO,GPIO_DATA,CARD_POWER,0);
    return rc;
}
