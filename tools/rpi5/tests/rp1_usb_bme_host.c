/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_bme.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

struct model {
    uint16_t command;
    unsigned calls, reads, writes, guards, fail, bad_readback;
};

static int
guard(void *context)
{
    struct model *model = context;
    model->guards++;
    return model->fail == model->calls + 1 ? -1 : 0;
}

static int
transfer(void *context, const struct rpi5_pcie_config_request *request,
    uint32_t *out)
{
    struct model *model = context;
    model->calls++;
    assert(request->bus == 1 && request->device == 0 &&
        request->function == 0 && request->offset == 4 &&
        request->width == 2);
    if (model->fail == model->calls) return -1;
    if (request->write) {
        assert(!out && request->value <= UINT16_MAX);
        model->writes++;
        model->command = (uint16_t)request->value;
    } else {
        assert(out);
        model->reads++;
        *out = model->bad_readback && model->writes ?
            model->command ^ 4 : model->command;
    }
    return 0;
}

int
main(void)
{
    struct model model = {.command = 0x402};
    struct rpi5_rp1_usb_bme lease = {0};
    struct rpi5_rp1_usb_bme_io io = {&model, guard, transfer};
    assert(!rpi5_rp1_usb_bme_init(&lease, &io));
    assert(!rpi5_rp1_usb_bme_enable(&lease));
    assert(lease.state == RPI5_RP1_USB_BME_ENABLED &&
        lease.original == 0x402 && lease.enabled == 0x406 &&
        lease.current == 0x406 && lease.reads == 2 && lease.writes == 1);
    assert(rpi5_rp1_usb_bme_ready(&lease));
    assert(!rpi5_rp1_usb_bme_disable(&lease));
    assert(lease.state == RPI5_RP1_USB_BME_DISABLED &&
        lease.current == 0x402 && lease.reads == 5 && lease.writes == 2 &&
        model.command == 0x402);

    unsigned faults = 0;
    for (unsigned fail = 1; fail <= 3; fail++) {
        memset(&model, 0, sizeof(model)); model.command = 2; model.fail = fail;
        memset(&lease, 0, sizeof(lease));
        assert(!rpi5_rp1_usb_bme_init(&lease, &io));
        assert(rpi5_rp1_usb_bme_enable(&lease));
        assert(lease.state == RPI5_RP1_USB_BME_QUARANTINED);
        faults++;
    }
    memset(&model, 0, sizeof(model)); model.command = 4;
    memset(&lease, 0, sizeof(lease));
    assert(!rpi5_rp1_usb_bme_init(&lease, &io));
    assert(rpi5_rp1_usb_bme_enable(&lease));
    assert(lease.state == RPI5_RP1_USB_BME_QUARANTINED && !model.writes);
    faults++;
    memset(&model, 0, sizeof(model)); model.command = 2; model.bad_readback = 1;
    memset(&lease, 0, sizeof(lease));
    assert(!rpi5_rp1_usb_bme_init(&lease, &io));
    assert(rpi5_rp1_usb_bme_enable(&lease));
    assert(lease.state == RPI5_RP1_USB_BME_QUARANTINED && model.writes == 1);
    faults++;
    printf("RP1_USB_BME_PASS faults=%u EXACT_COMMAND_BIT2_ONLY\n", faults);
    return 0;
}
