/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_sd_handoff.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

struct model {
    uint32_t r[5][0x260/4];
    uint32_t variant, writes, reads, delays;
    uint64_t time, off_time, select_time, on_time;
    int frozen, backwards, no_halt, remove_on_power, ignore_bank, ignore_reg, retain_voltage;
};
static uint32_t read32(void *context, enum rpi5_sd_bank bank, uint32_t reg)
{
    struct model *m=context;
    assert(bank<=RPI5_SD_AON_PINS && !(reg&3) && reg<0x260);
    m->reads++;
    return m->r[bank][reg/4];
}
static void write32(void *context, enum rpi5_sd_bank bank, uint32_t reg, uint32_t value)
{
    struct model *m=context;
    uint32_t mask=0, previous=read32(m,bank,reg);
    m->writes++;
    switch (bank) {
    case RPI5_SD_HOST:
        switch (reg) {
        case 0x208: case 0x20c: case 0x210: mask=1; break;
        case 0x214: case 0x218: case 0x34: case 0x38: mask=UINT32_MAX; break;
        case 0x2c: mask=0xfffd; break;
        case 0x28: mask=0x100; break;
        case 0x3c: mask=0xf0000; break;
        default: assert(!"No SD command, DMA descriptor or data-port writes permitted");
        }
        break;
    case RPI5_SD_CFG: assert(reg==0x44); mask=3; break;
    case RPI5_SD_GPIO: assert(reg==4 || reg==8); mask=reg==4 ? 0x18 : 0x20; break;
    case RPI5_SD_PINS:
        assert(reg==(m->variant ? 0x18u : 0x2cu));
        mask=m->variant ? 0xff0c0 : 0xff0c; break;
    case RPI5_SD_AON_PINS:
        if (reg==0x0c) mask=0xf00000;
        else { assert(reg==(m->variant ? 0x14u : 0x1cu)); mask=m->variant ? 0x30000000 : 3; }
        break;
    }
    /* No non-SD bit may be changed, including UART, PMIC and RP1 pins. */
    if (!(bank==RPI5_SD_HOST && reg==0x210)) assert((value&~mask)==(previous&~mask));
    if ((int)bank==m->ignore_bank && (int)reg==m->ignore_reg) return;
    if (bank==RPI5_SD_HOST && reg==0x210) m->r[bank][reg/4]&=~value;
    else m->r[bank][reg/4]=value;
    /* Physical diagnostic: power-enable clears, 3.3-V selection remains.
     * Treat those voltage bits as retained even if a caller tries to clear
     * them; the mask assertion above also forbids changing non-power bits. */
    if (bank==RPI5_SD_HOST && reg==0x28 && m->retain_voltage)
        m->r[bank][reg/4]=(m->r[bank][reg/4]&~0xe00u)|(previous&0xe00u);
    if (bank==RPI5_SD_HOST && reg==0x20c && (value&1) && !m->no_halt)
        m->r[RPI5_SD_HOST][0x210/4]|=1;
    if (bank==RPI5_SD_GPIO && reg==4) {
        if ((previous&16) && !(value&16)) m->off_time=m->time;
        if ((previous&8) && !(value&8)) {
            assert(!(value&16)); assert(m->time-m->off_time>=100000);
            m->select_time=m->time;
        }
        if (!(previous&16) && (value&16)) {
            assert(!(value&8)); assert(m->time-m->select_time>=5000);
            assert(!(m->r[RPI5_SD_HOST][0x2c/4]&5));
            assert(!(m->r[RPI5_SD_HOST][0x208/4]&1));
            m->on_time=m->time;
            if (m->remove_on_power) m->r[bank][reg/4]|=32;
        }
    }
}
static uint64_t now(void *context)
{
    struct model *m=context;
    return m->backwards && m->delays ? 0 : m->time;
}
static void delay(void *context, uint32_t us)
{
    struct model *m=context;
    assert(us==10); m->delays++;
    if (!m->frozen) m->time+=us;
}
static void init(struct model *m, unsigned variant)
{
    memset(m,0,sizeof *m);
    m->variant=variant; m->time=1000; m->ignore_bank=m->ignore_reg=-1;
    for (unsigned b=0;b<5;b++) for (unsigned i=0;i<0x260/4;i++) m->r[b][i]=0xa5a5a5a5;
    m->r[RPI5_SD_HOST][0xfc/4]=2<<16;
    m->r[RPI5_SD_HOST][0x40/4]=0x0100c800;
    m->r[RPI5_SD_HOST][0x200/4]=0x510;
    m->r[RPI5_SD_HOST][0x208/4]=0x1001;
    m->r[RPI5_SD_HOST][0x20c/4]=0;
    m->r[RPI5_SD_HOST][0x210/4]=0xa5a50000;
    m->r[RPI5_SD_HOST][0x228/4]=m->r[RPI5_SD_HOST][0x234/4]=0;
    m->r[RPI5_SD_HOST][0x24/4]=0x10000;
    m->r[RPI5_SD_HOST][0x2c/4]=0x000e0907;
    m->r[RPI5_SD_AON_PINS][0x0c/4]&=~0xff000u;
    m->r[RPI5_SD_GPIO][0/4]&=~0x18u;
    m->r[RPI5_SD_GPIO][8/4]&=~0x18u;
    m->r[RPI5_SD_GPIO][4/4]=(m->r[RPI5_SD_GPIO][4/4]&~0x38u)|0x18;
}
static int run(struct model *m, struct rpi5_sd_handoff_result *result)
{
    struct rpi5_sd_platform_io io={m,read32,write32,now,delay};
    int rc=rpi5_sd_handoff(&io,m->variant,200000000,result);
    assert(m->reads<100000 && m->delays<=20000);
    return rc;
}
int main(void)
{
    struct model m;
    struct rpi5_sd_handoff_result result, old;
    for (unsigned variant=0;variant<2;variant++) {
        init(&m,variant); assert(!run(&m,&result));
        assert(result.stage==RPI5_SD_DIGITAL_READY);
        assert(m.time-m.on_time>=10000);
        assert((result.gpio_data&0x38)==16 && (result.cfg_pins&3)==2);
        assert(!(result.gpio_direction&24));
        assert(((m.r[RPI5_SD_AON_PINS][3]>>20)&15)==(variant ? 4u : 6u));
    }
    /* Initial digital values from the first physical Gate 4 boot capture.
     * This remains a host model, not proof of the resulting board voltages. */
    init(&m,0);
    m.r[RPI5_SD_HOST][0xfc/4]=0x10020000;
    m.r[RPI5_SD_HOST][0x40/4]=0x55eec832;
    m.r[RPI5_SD_HOST][0x24/4]=0x1fff0000;
    m.r[RPI5_SD_HOST][0x28/4]=0x00800f06;
    m.r[RPI5_SD_HOST][0x2c/4]=0x000e0207;
    m.r[RPI5_SD_HOST][0x3c/4]=0;
    m.r[RPI5_SD_HOST][0x208/4]=0;
    m.r[RPI5_SD_GPIO][4/4]=0x16257;
    m.r[RPI5_SD_GPIO][8/4]=0x1fde3;
    m.r[RPI5_SD_GPIO][0/4]=0;
    m.r[RPI5_SD_AON_PINS][0x0c/4]=0x76;
    m.r[RPI5_SD_CFG][0x44/4]=0;
    m.retain_voltage=1;
    assert(!run(&m,&result) && result.stage==RPI5_SD_DIGITAL_READY);
    assert(m.r[RPI5_SD_HOST][0x28/4]==0x00800e06);
    init(&m,0); m.r[RPI5_SD_HOST][0x208/4]&=~1u;
    assert(!run(&m,&result)); /* Already disabled CQE needs no halt request. */
    init(&m,0); m.r[RPI5_SD_HOST][0x20c/4]=1; m.r[RPI5_SD_HOST][0x210/4]|=1;
    assert(!run(&m,&result)); /* An acknowledged prior halt is safe. */
    init(&m,0); m.r[RPI5_SD_HOST][0x20c/4]=1;
    assert(run(&m,&result)==RPI5_SD_HANDOFF_BUSY && !m.writes);
    struct {unsigned bank,reg; uint32_t mask,value; int error;} bad[]={
        {RPI5_SD_HOST,0x40,0xff00,0x9600,RPI5_SD_HANDOFF_UNSUPPORTED},
        {RPI5_SD_HOST,0x40,0x1000000,0,RPI5_SD_HANDOFF_UNSUPPORTED},
        {RPI5_SD_HOST,0x200,0xfff,0x200,RPI5_SD_HANDOFF_UNSUPPORTED},
        {RPI5_SD_AON_PINS,0x0c,0xf000,0x1000,RPI5_SD_HANDOFF_UNSUPPORTED},
        {RPI5_SD_GPIO,8,16,16,RPI5_SD_HANDOFF_UNSUPPORTED},
        {RPI5_SD_GPIO,0,8,8,RPI5_SD_HANDOFF_UNSUPPORTED},
        {RPI5_SD_HOST,0x24,1,1,RPI5_SD_HANDOFF_BUSY},
        {RPI5_SD_HOST,0x24,0x200,0x200,RPI5_SD_HANDOFF_BUSY},
        {RPI5_SD_HOST,0x2c,0x1000000,0x1000000,RPI5_SD_HANDOFF_BUSY},
        {RPI5_SD_HOST,0x228,1,1,RPI5_SD_HANDOFF_BUSY},
        {RPI5_SD_HOST,0x234,1,1,RPI5_SD_HANDOFF_BUSY},
    };
    for (unsigned i=0;i<sizeof bad/sizeof bad[0];i++) {
        init(&m,0);
        m.r[bad[i].bank][bad[i].reg/4]=(m.r[bad[i].bank][bad[i].reg/4]&~bad[i].mask)|bad[i].value;
        assert(run(&m,&result)==bad[i].error && !m.writes);
        assert(result.stage==RPI5_SD_PREFLIGHT);
    }
    init(&m,0); m.no_halt=1;
    assert(run(&m,&result)==RPI5_SD_HANDOFF_TIMEOUT && m.r[RPI5_SD_GPIO][1]&16);
    init(&m,0); m.no_halt=1; m.frozen=1;
    assert(run(&m,&result)==RPI5_SD_HANDOFF_TIMEOUT && m.r[RPI5_SD_GPIO][1]&16);
    init(&m,0); m.frozen=1;
    assert(run(&m,&result)==RPI5_SD_HANDOFF_TIMEOUT && !(m.r[RPI5_SD_GPIO][1]&16));
    init(&m,0); m.backwards=1;
    assert(run(&m,&result)==RPI5_SD_HANDOFF_TIMEOUT && !(m.r[RPI5_SD_GPIO][1]&16));
    init(&m,0); m.r[RPI5_SD_GPIO][1]|=32;
    assert(run(&m,&result)==RPI5_SD_HANDOFF_NO_CARD && !m.on_time && !(m.r[RPI5_SD_GPIO][1]&16));
    init(&m,0); m.remove_on_power=1;
    assert(run(&m,&result)==RPI5_SD_HANDOFF_READBACK && !(m.r[RPI5_SD_GPIO][1]&16));
    struct {int bank,reg;} ignored[]={
        {RPI5_SD_HOST,0x208},{RPI5_SD_HOST,0x218},{RPI5_SD_HOST,0x214},
        {RPI5_SD_HOST,0x34},{RPI5_SD_HOST,0x38},{RPI5_SD_HOST,0x2c},
        {RPI5_SD_HOST,0x28},{RPI5_SD_HOST,0x3c},{RPI5_SD_CFG,0x44},
        {RPI5_SD_PINS,0x2c},{RPI5_SD_AON_PINS,0x1c},{RPI5_SD_AON_PINS,0x0c},
        {RPI5_SD_GPIO,4},{RPI5_SD_GPIO,8},
    };
    for (unsigned i=0;i<sizeof ignored/sizeof ignored[0];i++) {
        init(&m,0); m.ignore_bank=ignored[i].bank; m.ignore_reg=ignored[i].reg;
        /* Force each tested masked field to differ from its target. */
        if (ignored[i].bank==RPI5_SD_GPIO && ignored[i].reg==8) m.r[RPI5_SD_GPIO][2]&=~32u;
        if (ignored[i].bank==RPI5_SD_CFG) m.r[RPI5_SD_CFG][0x44/4]&=~3u;
        if (ignored[i].bank==RPI5_SD_HOST && ignored[i].reg==0x3c) m.r[RPI5_SD_HOST][0x3c/4]|=0xf0000;
        assert(run(&m,&result)==RPI5_SD_HANDOFF_READBACK);
        assert(result.readback_mask && result.failed_bank==(unsigned)ignored[i].bank &&
            result.failed_offset==(unsigned)ignored[i].reg && result.expected!=result.observed);
        if (ignored[i].bank==RPI5_SD_HOST && ignored[i].reg==0x28) {
            assert(result.stage==RPI5_SD_CLOCK_OFF && result.readback_mask==0x100);
            assert(result.expected==0 && result.observed==0x100);
            assert(!m.off_time); /* Failed bus-power off must not change rails. */
        }
    }
    init(&m,0); memset(&old,0xaa,sizeof old); result=old;
    struct rpi5_sd_platform_io io={&m,read32,write32,now,delay};
    assert(rpi5_sd_handoff(&io,2,200000000,&result)==RPI5_SD_HANDOFF_INVALID);
    assert(!memcmp(&old,&result,sizeof old) && !m.reads && !m.writes);
    assert(rpi5_sd_handoff(&io,0,199000000,&result)==RPI5_SD_HANDOFF_INVALID);
    io.delay_us=0;
    assert(rpi5_sd_handoff(&io,0,200000000,&result)==RPI5_SD_HANDOFF_INVALID);
    assert(!memcmp(&old,&result,sizeof old) && !m.reads && !m.writes);
    puts("SD_HANDOFF_PASS");
    return 0;
}
