/* SPDX-License-Identifier: BSD-2-Clause */
/* Real initial cores and real transport allowlist under modeled callbacks.
 * Not execution of IOKit map/lifetime code or a power/clock/recovery receipt. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "pcie_serdes.h"
#include "BCM2712PCIePHYPolicy.h"

struct model {
    unsigned phase, guards, fail_at, writes;
    uint32_t reset_status, start, debug, phy, command, data;
    uint64_t now;
    struct rpi5_pcie_reset reset;
    struct rpi5_pcie_rescal calibration;
    struct rpi5_pcie_serdes serdes;
};
struct result {
    struct rpi5_pcie_reset_observation reset;
    struct rpi5_pcie_rescal_observation calibration;
    struct rpi5_pcie_serdes_observation serdes;
};
static int guard(struct model *m)
{
    if (m->phase == BCM2712_PHY_FAILED) return -1;
    assert(m->phase >= BCM2712_PHY_RESETTING && m->phase <= BCM2712_PHY_CONFIGURING);
    if (++m->guards == m->fail_at) { m->phase = BCM2712_PHY_FAILED; return -1; }
    return 0;
}
static int read_register(struct model *m, unsigned bank, uint32_t off, uint32_t *out)
{
    if (m->phase == BCM2712_PHY_FAILED) return -1;
    assert(bcm2712_phy_access_allowed(m->phase, bank, off, 4, 0));
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
            default: assert(0);
        }
    }
    if (guard(m)) return -1;
    *out = value; return 0;
}
static int write_register(struct model *m, unsigned bank, uint32_t off, uint32_t value)
{
    if (m->phase == BCM2712_PHY_FAILED) return -1;
    assert(bcm2712_phy_access_allowed(m->phase, bank, off, 4, 1));
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
            default: assert(0);
        }
    }
    return guard(m); /* Failure may follow an actual modeled write. */
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
    if (rpi5_pcie_reset_init(&m->reset, &fdt, &reset) || rpi5_pcie_reset_pulse(&m->reset, &result.reset)) goto fail;
    m->phase = BCM2712_PHY_CALIBRATING;
    if (rpi5_pcie_rescal_init(&m->calibration, &fdt, &rescal) ||
        rpi5_pcie_rescal_calibrate(&m->calibration, &result.calibration)) goto fail;
    m->phase = BCM2712_PHY_CONFIGURING;
    if (rpi5_pcie_serdes_init(&m->serdes, &fdt, &bridge, &m->calibration, &m->reset) ||
        rpi5_pcie_serdes_configure54(&m->serdes, &result.serdes) || guard(m)) goto fail;
    m->phase = BCM2712_PHY_COMPLETE;
    *out = result; return 0;
fail:
    m->phase = BCM2712_PHY_FAILED;
    return -1;
}
int main(void)
{
    struct model m = {0};
    struct result result, unchanged;
    assert(!run(&m, &result));
    assert(m.phase == BCM2712_PHY_COMPLETE && m.reset.state == RPI5_PCIE_RESET_COMPLETE);
    assert(m.calibration.state == RPI5_PCIE_RESCAL_COMPLETE && m.serdes.state == RPI5_PCIE_SERDES_COMPLETE);
    assert(result.serdes.mdio_writes_completed == 8 && m.writes == 22);
    unsigned count = m.guards;
    assert(count == 206); /* 18 reset + 23 RESCAL + 164 SerDes + final guard. */
    memset(&unchanged, 0xa5, sizeof unchanged);
    for (unsigned i = 1; i <= count; i++) {
        memset(&m, 0, sizeof m);
        m.fail_at = i;
        result = unchanged;
        assert(run(&m, &result));
        assert(m.phase == BCM2712_PHY_FAILED && m.guards == i);
        assert(!memcmp(&result, &unchanged, sizeof result));
        unsigned before = m.writes;
        uint32_t value = 123;
        assert(read_register(&m, BCM2712_PHY_RESET, 0x20, &value));
        assert(value == 123 && m.guards == i);
        assert(write_register(&m, BCM2712_PHY_RESET, 0x18, 0x1000));
        assert(m.writes == before && m.guards == i);
    }
    printf("PCIE_PHY_CHAIN_PASS GUARD_FAILURES=%u NO_MMIO=1\n", count);
    return 0;
}
