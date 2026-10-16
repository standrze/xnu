/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_bme.h"

static int
guard(struct rpi5_rp1_usb_bme *lease, int error)
{
    if (lease->io.guard(lease->io.context)) {
        lease->error = error;
        lease->state = RPI5_RP1_USB_BME_QUARANTINED;
        return -1;
    }
    return 0;
}

static int
transfer(struct rpi5_rp1_usb_bme *lease, unsigned write, uint16_t value,
    uint16_t *read_value, int error)
{
    struct rpi5_pcie_config_request request = {
        .bus = 1, .device = 0, .function = 0, .offset = 4, .width = 2,
        .write = write, .value = value,
    };
    uint32_t result = 0;
    if (guard(lease, error) || lease->io.transfer(lease->io.context,
            &request, write ? NULL : &result) || result > UINT16_MAX ||
        guard(lease, error)) {
        lease->error = error;
        lease->state = RPI5_RP1_USB_BME_QUARANTINED;
        return -1;
    }
    if (write) {
        lease->writes++;
    } else {
        lease->reads++;
        *read_value = (uint16_t)result;
    }
    return 0;
}

int
rpi5_rp1_usb_bme_init(struct rpi5_rp1_usb_bme *lease,
    const struct rpi5_rp1_usb_bme_io *io)
{
    if (!lease || !io || !io->guard || !io->transfer ||
        lease->state != RPI5_RP1_USB_BME_EMPTY) {
        return -1;
    }
    lease->io = *io;
    return 0;
}

int
rpi5_rp1_usb_bme_enable(struct rpi5_rp1_usb_bme *lease)
{
    if (!lease || lease->state != RPI5_RP1_USB_BME_EMPTY) {
        return -1;
    }
    lease->state = RPI5_RP1_USB_BME_ENABLING;
    lease->step = 1;
    uint16_t original = 0;
    if (transfer(lease, 0, 0, &original, -2) ||
        (original & RPI5_PCI_COMMAND_BUS_MASTER)) {
        if (!lease->error) lease->error = -3;
        lease->state = RPI5_RP1_USB_BME_QUARANTINED;
        return -1;
    }
    lease->original = original;
    lease->enabled = original | RPI5_PCI_COMMAND_BUS_MASTER;
    lease->step = 2;
    if (transfer(lease, 1, lease->enabled, NULL, -4)) {
        return -1;
    }
    lease->step = 3;
    uint16_t readback = 0;
    if (transfer(lease, 0, 0, &readback, -5) || readback != lease->enabled) {
        if (!lease->error) lease->error = -6;
        lease->state = RPI5_RP1_USB_BME_QUARANTINED;
        return -1;
    }
    lease->current = readback;
    lease->state = RPI5_RP1_USB_BME_ENABLED;
    lease->step = 4;
    return 0;
}

int
rpi5_rp1_usb_bme_disable(struct rpi5_rp1_usb_bme *lease)
{
    if (!lease || lease->state != RPI5_RP1_USB_BME_ENABLED) {
        return -1;
    }
    lease->state = RPI5_RP1_USB_BME_DISABLING;
    lease->step = 5;
    uint16_t current = 0;
    if (transfer(lease, 0, 0, &current, -7) || current != lease->enabled) {
        if (!lease->error) lease->error = -8;
        lease->state = RPI5_RP1_USB_BME_QUARANTINED;
        return -1;
    }
    lease->step = 6;
    if (transfer(lease, 1, lease->original, NULL, -9)) {
        return -1;
    }
    lease->step = 7;
    if (transfer(lease, 0, 0, &current, -10) || current != lease->original) {
        if (!lease->error) lease->error = -11;
        lease->state = RPI5_RP1_USB_BME_QUARANTINED;
        return -1;
    }
    lease->current = current;
    lease->state = RPI5_RP1_USB_BME_DISABLED;
    lease->step = 8;
    return 0;
}

int
rpi5_rp1_usb_bme_ready(struct rpi5_rp1_usb_bme *lease)
{
    if (!lease || lease->state != RPI5_RP1_USB_BME_ENABLED ||
        guard(lease, -12)) {
        return 0;
    }
    uint16_t current = 0;
    if (transfer(lease, 0, 0, &current, -13) || current != lease->enabled) {
        if (!lease->error) lease->error = -14;
        lease->state = RPI5_RP1_USB_BME_QUARANTINED;
        return 0;
    }
    lease->current = current;
    return 1;
}
