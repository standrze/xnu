/* SPDX-License-Identifier: BSD-2-Clause */
/* Real four-core chain and access policy under modeled callbacks only.
 * Does not execute IOKit map/lifetime code or admit physical power/recovery. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "pcie_ubus.h"
#include "BCM2712PCIeUBUSPolicy.h"

struct model {
    unsigned phase, guards, fail_at, writes, reserved, ubus_bad_read;
    uint32_t reset_status, start, debug, phy, command, data;
    uint32_t ubus_ctrl, error_data, timeout, retry, axi, ctrl;
    uint64_t now;
    struct rpi5_pcie_reset reset;
    struct rpi5_pcie_rescal calibration;
    struct rpi5_pcie_serdes serdes;
    struct rpi5_pcie_ubus ubus;
};
struct result {
    struct rpi5_pcie_reset_observation reset;
    struct rpi5_pcie_rescal_observation calibration;
    struct rpi5_pcie_serdes_observation serdes;
    struct rpi5_pcie_ubus_observation ubus;
};
static int fail(struct model *m)
{
    m->phase = BCM2712_PHY_FAILED;
    m->reset.state = RPI5_PCIE_RESET_QUARANTINED;
    m->calibration.state = RPI5_PCIE_RESCAL_QUARANTINED;
    m->serdes.state = RPI5_PCIE_SERDES_QUARANTINED;
    m->serdes.mdio.state = RPI5_PCIE_MDIO_QUARANTINED;
    m->ubus.state = RPI5_PCIE_UBUS_QUARANTINED;
    return -1;
}
static int guard(struct model *m)
{
    if (m->phase == BCM2712_PHY_FAILED) return -1;
    assert((m->phase >= BCM2712_PHY_RESETTING && m->phase <= BCM2712_PHY_CONFIGURING) ||
           m->phase == BCM2712_PHY_UBUS_CONFIGURING);
    if (++m->guards == m->fail_at) return fail(m);
    return 0;
}
static int read_register(struct model *m, unsigned bank, uint32_t off, uint32_t *out)
{
    if (m->phase == BCM2712_PHY_FAILED) return -1;
    assert(bcm2712_ubus_access_allowed(m->phase, bank, off, 4, 0));
    if (guard(m)) return -1;
    uint32_t value = 0;
    if (bank == BCM2712_PHY_RESET) value = m->reset_status;
    else if (bank == BCM2712_PHY_RESCAL) value = off ? 1 : m->start;
    else {
        switch (off) {
            case 0x4304: value = m->debug; break;
            case 0x184c: value = m->phy; break;
            case 0x1100: value = m->command; break;
            case 0x1104: value = m->data & 0xffff; break;
            case 0x40a4: value = m->ubus_ctrl; break;
            case 0x40a8: value = m->timeout; break;
            case 0x405c: value = m->retry; break;
            case 0x416c: value = m->axi; break;
            case 0x40a0: value = m->ctrl; break;
            default: assert(0);
        }
    }
    if (m->phase == BCM2712_PHY_UBUS_CONFIGURING && m->ubus_bad_read == off) value = UINT32_MAX;
    if (guard(m)) return -1;
    *out = value; return 0;
}
static int write_register(struct model *m, unsigned bank, uint32_t off, uint32_t value)
{
    if (m->phase == BCM2712_PHY_FAILED) return -1;
    assert(bcm2712_ubus_access_allowed(m->phase, bank, off, 4, 1));
    if (guard(m)) return -1;
    m->writes++;
    if (bank == BCM2712_PHY_RESET) {
        assert(value == 0x1000);
        if (off == 0x18) m->reset_status |= value; else m->reset_status &= ~value;
    } else if (bank == BCM2712_PHY_RESCAL) {
        assert((m->start ^ value) == 1); m->start = value;
    } else {
        switch (off) {
            case 0x4304: m->debug = value; break;
            case 0x184c: m->phy = value; break;
            case 0x1100: m->command = value; break;
            case 0x1104: m->data = value; break;
            case 0x40a4: assert(value == (m->ubus_ctrl | 0x82000)); m->ubus_ctrl = value; break;
            case 0x4170: assert(value == UINT32_MAX); m->error_data = value; break;
            case 0x40a8: assert(value == 0x0b2d0000); m->timeout = value; break;
            case 0x405c: assert(value == 0x0aba0000); m->retry = value; break;
            case 0x416c: m->axi = value & ~(m->reserved ? 0x1000u : 0u); break;
            case 0x40a0: assert(value == (m->ctrl & ~0x20u)); m->ctrl = value; break;
            default: assert(0);
        }
    }
    return guard(m); /* A failure here must not imply the write was undone. */
}
static int status(void *p, uint32_t *out) { return read_register(p, BCM2712_PHY_RESET, 0x20, out); }
static int assert_reset(void *p) { return write_register(p, BCM2712_PHY_RESET, 0x18, 0x1000); }
static int release_reset(void *p) { return write_register(p, BCM2712_PHY_RESET, 0x1c, 0x1000); }
static int read_start(void *p, uint32_t *out) { return read_register(p, BCM2712_PHY_RESCAL, 0, out); }
static int write_start(void *p, uint32_t value) { return write_register(p, BCM2712_PHY_RESCAL, 0, value); }
static int read_status(void *p, uint32_t *out) { return read_register(p, BCM2712_PHY_RESCAL, 8, out); }
static int bridge_read(void *p, uint32_t off, uint32_t *out) { return read_register(p, BCM2712_PHY_BRIDGE, off, out); }
static int bridge_write(void *p, uint32_t off, uint32_t value) { return write_register(p, BCM2712_PHY_BRIDGE, off, value); }
static int order(void *p) { struct model *m = p; return guard(m) || guard(m) ? -1 : 0; }
static int now_us(void *p, uint64_t *out)
{ struct model *m = p; if (guard(m) || guard(m)) return -1; *out = m->now; return 0; }
static int delay_us(void *p, uint32_t us)
{ struct model *m = p; assert(us && us <= 100); if (guard(m)) return -1; m->now += us; return guard(m); }
static int claim(void *p)
{
    struct model *m = p;
    assert(m->phase == BCM2712_PHY_CALIBRATING && m->reset.state == RPI5_PCIE_RESET_COMPLETE);
    return guard(m);
}
static int run(struct model *m, struct result *out)
{
    if (!out || m->phase != BCM2712_PHY_PREPARED) return -1;
    struct rpi5_pcie_fdt fdt = {0};
    fdt.bridge_regs = (struct rpi5_range){0x1000120000, 0x1000129310};
    fdt.rescal_regs = (struct rpi5_range){0x1000119500, 0x1000119510};
    fdt.bridge_reset_regs = (struct rpi5_range){0x1001504318, 0x1001504348};
    fdt.bridge_reset_id = 44;
    struct rpi5_pcie_reset_io reset = {m, fdt.bridge_reset_regs.start, 0x30,
        status, assert_reset, release_reset, order, delay_us};
    struct rpi5_pcie_rescal_io rescal = {m, fdt.rescal_regs.start, 0x10,
        claim, read_start, write_start, read_status, order, now_us, delay_us};
    struct rpi5_pcie_mdio_io bridge = {m, fdt.bridge_regs.start, 0x9310,
        bridge_read, bridge_write, order, now_us, delay_us};
    struct result result = {0};
    m->phase = BCM2712_PHY_RESETTING;
    if (rpi5_pcie_reset_init(&m->reset, &fdt, &reset) || rpi5_pcie_reset_pulse(&m->reset, &result.reset)) goto failed;
    m->phase = BCM2712_PHY_CALIBRATING;
    if (rpi5_pcie_rescal_init(&m->calibration, &fdt, &rescal) ||
        rpi5_pcie_rescal_calibrate(&m->calibration, &result.calibration)) goto failed;
    m->phase = BCM2712_PHY_CONFIGURING;
    if (rpi5_pcie_serdes_init(&m->serdes, &fdt, &bridge, &m->calibration, &m->reset) ||
        rpi5_pcie_serdes_configure54(&m->serdes, &result.serdes) || guard(m)) goto failed;
    /* Real C++ runInitialPHY commits only its LOCAL result, then the wrapper
     * enters the UBUS phase with the same sessions and no new watchdog claim. */
    m->phase = BCM2712_PHY_UBUS_CONFIGURING;
    if (guard(m) || rpi5_pcie_ubus_init(&m->ubus, &m->serdes) ||
        rpi5_pcie_ubus_configure(&m->ubus, &result.ubus) || guard(m)) goto failed;
    m->phase = BCM2712_PHY_COMPLETE;
    *out = result;
    return 0;
failed:
    return fail(m);
}
static void prepare(struct model *m, unsigned reserved)
{
    memset(m, 0, sizeof *m);
    m->phase = BCM2712_PHY_PREPARED;
    m->reserved = reserved;
    m->ubus_ctrl = 0x12340001;
    m->axi = 0x900080ff;
    m->ctrl = 0x12345678;
}
int main(void)
{
    struct model m;
    struct result result, unchanged;
    memset(&unchanged, 0xa5, sizeof unchanged);
    unsigned failures = 0;
    for (unsigned reserved = 0; reserved < 2; reserved++) {
        prepare(&m, reserved);
        assert(run(&m, NULL) && !m.guards && !m.writes);
        assert(!run(&m, &result));
        assert(m.phase == BCM2712_PHY_COMPLETE && m.ubus.state == RPI5_PCIE_UBUS_COMPLETE);
        assert(m.ubus.serdes == &m.serdes && m.serdes.calibration == &m.calibration &&
               m.serdes.bridge_reset == &m.reset);
        assert(m.serdes.mdio.io.context == &m && result.serdes.mdio_writes_completed == 8);
        assert(result.ubus.outstanding_fallback == reserved && m.writes == 28 + reserved);
        assert(m.error_data == UINT32_MAX && !(m.ctrl & 0x20) && !(m.axi & 0x80));
        assert(m.ubus.completed_callbacks == 20 + 3 * reserved);
        unsigned count = m.guards;
        assert(count == 248 + 6 * reserved);
        assert(run(&m, &result) && m.guards == count); /* No second sequence. */
        for (unsigned i = 1; i <= count; i++) {
            prepare(&m, reserved); m.fail_at = i; result = unchanged;
            assert(run(&m, &result) && m.guards == i);
            assert(m.phase == BCM2712_PHY_FAILED && m.ubus.state == RPI5_PCIE_UBUS_QUARANTINED);
            assert(m.reset.state == RPI5_PCIE_RESET_QUARANTINED &&
                   m.calibration.state == RPI5_PCIE_RESCAL_QUARANTINED &&
                   m.serdes.state == RPI5_PCIE_SERDES_QUARANTINED &&
                   m.serdes.mdio.state == RPI5_PCIE_MDIO_QUARANTINED);
            assert(!memcmp(&result, &unchanged, sizeof result));
            unsigned before = m.writes;
            uint32_t value = 123;
            assert(read_register(&m, BCM2712_PHY_BRIDGE, 0x40a4, &value));
            assert(value == 123 && m.guards == i);
            assert(write_register(&m, BCM2712_PHY_BRIDGE, 0x40a4, 0));
            assert(run(&m, &result) && m.writes == before && m.guards == i);
            failures++;
        }
        const unsigned reads[] = {0x40a4, 0x40a8, 0x405c, 0x416c, 0x40a0};
        for (unsigned i = 0; i < sizeof reads / sizeof reads[0]; i++) {
            prepare(&m, reserved); m.ubus_bad_read = reads[i]; result = unchanged;
            assert(run(&m, &result) && m.phase == BCM2712_PHY_FAILED);
            assert(!memcmp(&result, &unchanged, sizeof result));
        }
    }
    printf("PCIE_UBUS_CHAIN_PASS GUARD_FAILURES=%u NO_MMIO=1\n", failures);
    return 0;
}
