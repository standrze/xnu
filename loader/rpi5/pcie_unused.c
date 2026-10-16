/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_unused.h"

static int dependencies(const struct rpi5_pcie_unused *s)
{
    if (!s->ubus || s->ubus->state != RPI5_PCIE_UBUS_COMPLETE || !s->ubus->serdes)
        return 0;
    const struct rpi5_pcie_serdes *phy = s->ubus->serdes;
    return phy->state == RPI5_PCIE_SERDES_COMPLETE && phy->calibration && phy->bridge_reset &&
        phy->calibration->state == RPI5_PCIE_RESCAL_COMPLETE &&
        phy->bridge_reset->state == RPI5_PCIE_RESET_COMPLETE &&
        phy->mdio.state == RPI5_PCIE_MDIO_READY &&
        s->io.physical_base == UINT64_C(0x1000120000) && s->io.mapped_bytes == 0x9310 &&
        phy->mdio.io.physical_base == s->io.physical_base &&
        phy->mdio.io.mapped_bytes == s->io.mapped_bytes &&
        s->io.context == phy->mdio.io.context && s->io.read32 == phy->mdio.io.read32 &&
        s->io.check_owner && s->io.read32;
}
int rpi5_pcie_unused_init(struct rpi5_pcie_unused *s, struct rpi5_pcie_ubus *ubus,
    const struct rpi5_pcie_unused_io *io)
{
    if (!s || !io) return RPI5_PCIE_UNUSED_ARGUMENT;
    if (s->state != RPI5_PCIE_UNUSED_EMPTY) return RPI5_PCIE_UNUSED_STATE;
    struct rpi5_pcie_unused view = {0};
    view.ubus = ubus; view.io = *io;
    if (!dependencies(&view)) return RPI5_PCIE_UNUSED_DEPENDENCY;
    s->ubus = ubus; s->io = *io; s->completed_callbacks = 0;
    s->state = RPI5_PCIE_UNUSED_READY;
    return RPI5_PCIE_UNUSED_OK;
}
static int quarantine(struct rpi5_pcie_unused *s, int result)
{
    s->state = RPI5_PCIE_UNUSED_QUARANTINED;
    if (s->ubus) {
        s->ubus->state = RPI5_PCIE_UBUS_QUARANTINED;
        if (s->ubus->serdes) {
            s->ubus->serdes->state = RPI5_PCIE_SERDES_QUARANTINED;
            s->ubus->serdes->mdio.state = RPI5_PCIE_MDIO_QUARANTINED;
        }
    }
    return result;
}
static int owner(struct rpi5_pcie_unused *s)
{
    if (!dependencies(s)) return RPI5_PCIE_UNUSED_DEPENDENCY;
    if (s->io.check_owner(s->io.context)) return RPI5_PCIE_UNUSED_IO;
    s->completed_callbacks++;
    return dependencies(s) ? RPI5_PCIE_UNUSED_OK : RPI5_PCIE_UNUSED_DEPENDENCY;
}
static int read32(struct rpi5_pcie_unused *s, uint32_t offset, uint32_t *out)
{
    int rc = owner(s);
    if (rc) return rc;
    uint32_t value;
    if (s->io.read32(s->io.context, offset, &value)) return RPI5_PCIE_UNUSED_IO;
    s->completed_callbacks++;
    rc = owner(s);
    if (rc) return rc;
    if (value == UINT32_MAX) return RPI5_PCIE_UNUSED_IO;
    *out = value;
    return RPI5_PCIE_UNUSED_OK;
}
static int snapshot(struct rpi5_pcie_unused *s, uint32_t words[23])
{
    int rc;
#define READ(index, offset) do { rc = read32(s, offset, &words[index]); if (rc) return rc; } while (0)
    READ(0, 0x4068); READ(1, 0x4064); READ(2, 0x4304);
    if ((words[0] & 0xf0) != 0x80 || (words[1] & 5) || (words[2] & 0x08000000))
        return RPI5_PCIE_UNUSED_ACTIVE;
    for (unsigned i = 0; i < 7; i++) {
        READ(3 + 2 * i, 0x40d4 + 8 * i);
        READ(4 + 2 * i, 0x410c + 8 * i);
        if (words[3 + 2 * i] & 0x1f) return RPI5_PCIE_UNUSED_ACTIVE;
    }
    for (unsigned i = 0; i < 2; i++) {
        unsigned slot = i + 2, index = 17 + 3 * i;
        READ(index, 0x4070 + 4 * slot);
        READ(index + 1, 0x4080 + 8 * slot);
        READ(index + 2, 0x4084 + 8 * slot);
        uint64_t base = ((uint64_t)(words[index + 1] & 0xff) << 32) |
            ((uint64_t)(words[index] & 0xfff0) << 16);
        uint64_t limit = ((uint64_t)(words[index + 2] & 0xff) << 32) |
            (words[index] & UINT32_C(0xfff00000)) | UINT64_C(0xfffff);
        if (base <= limit) return RPI5_PCIE_UNUSED_ACTIVE;
    }
#undef READ
    return RPI5_PCIE_UNUSED_OK;
}
int rpi5_pcie_unused_inspect(struct rpi5_pcie_unused *s, struct rpi5_pcie_unused_observation *out)
{
    if (!s || !out) return RPI5_PCIE_UNUSED_ARGUMENT;
    if (s->state != RPI5_PCIE_UNUSED_READY) return RPI5_PCIE_UNUSED_STATE;
    s->state = RPI5_PCIE_UNUSED_BUSY;
    uint32_t first[23], second[23];
    int rc = snapshot(s, first);
    if (rc) return quarantine(s, rc);
    rc = snapshot(s, second);
    if (rc) return quarantine(s, rc);
    /* Status/control/debug predicates were independently checked both times.
     * Only window tuples must be identical; unrelated live status may vary. */
    for (unsigned i = 3; i < 23; i++)
        if (first[i] != second[i]) return quarantine(s, RPI5_PCIE_UNUSED_DRIFT);
    rc = owner(s);
    if (rc) return quarantine(s, rc);
    struct rpi5_pcie_unused_observation result = {0};
    for (unsigned i = 0; i < 7; i++) {
        result.inbound_bar_lo[i] = second[3 + 2 * i];
        result.inbound_remap_lo[i] = second[4 + 2 * i];
        result.remap_enabled_mask |= (second[4 + 2 * i] & 1) << i;
    }
    for (unsigned i = 0; i < 2; i++) {
        result.outbound_base_limit[i] = second[17 + 3 * i];
        result.outbound_base_hi[i] = second[18 + 3 * i];
        result.outbound_limit_hi[i] = second[19 + 3 * i];
    }
    result.final_status = second[0]; result.final_control = second[1];
    result.final_debug = second[2]; result.completed_callbacks = s->completed_callbacks;
    *out = result;
    s->state = RPI5_PCIE_UNUSED_COMPLETE;
    return RPI5_PCIE_UNUSED_OK;
}
