/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_config.h"

#define STATUS UINT32_C(0x4068)
#define DATA UINT32_C(0x8000)
#define INDEX UINT32_C(0x9000)
#define RP1_SELECT UINT32_C(0x00100000)

static int dependencies(const struct rpi5_pcie_link *link, void *context)
{
    if (!(link && link->state == RPI5_PCIE_LINK_COMPLETE &&
        link->windows && link->windows->state == RPI5_PCIE_WINDOWS_COMPLETE &&
        link->windows->io.context == context &&
        link->windows->io.physical_base == UINT64_C(0x1000120000) &&
        link->windows->io.mapped_bytes == UINT64_C(0x9310) &&
        link->io.rc && link->io.rc->state == RPI5_PCIE_RC_COMPLETE &&
        link->io.rc->windows == link->windows &&
        link->ubus && link->ubus->state == RPI5_PCIE_UBUS_COMPLETE)) return 0;
    const struct rpi5_pcie_serdes *s = link->ubus->serdes;
    return s && s->state == RPI5_PCIE_SERDES_COMPLETE &&
        s->mdio.state == RPI5_PCIE_MDIO_READY && s->bridge_reset && s->calibration &&
        s->bridge_reset->state == RPI5_PCIE_RESET_COMPLETE &&
        s->calibration->state == RPI5_PCIE_RESCAL_COMPLETE &&
        link->io.rc->bridge_reset == s->bridge_reset &&
        link->io.rc->calibration == s->calibration &&
        s->mdio.io.context == context &&
        s->mdio.io.physical_base == link->windows->io.physical_base &&
        s->mdio.io.mapped_bytes == link->windows->io.mapped_bytes &&
        s->mdio.io.read32 && s->mdio.io.write32 && s->mdio.io.order &&
        link->windows->io.read32 == s->mdio.io.read32 &&
        link->windows->io.write32 == s->mdio.io.write32 &&
        link->windows->io.order == s->mdio.io.order &&
        link->io.read16 && link->io.write16 &&
        link->io.rc->io.read16 == link->io.read16 &&
        link->io.rc->io.write16 == link->io.write16;
}

int rpi5_pcie_config_init(struct rpi5_pcie_config *s, struct rpi5_pcie_link *link,
    const struct rpi5_pcie_config_io *io)
{
    if (!s || !io || !io->acquire || !io->release || !io->check_lifecycle ||
        !io->authorize_write || !io->read || !io->write || !io->order)
        return RPI5_PCIE_CONFIG_ARGUMENT;
    if (s->state != RPI5_PCIE_CONFIG_EMPTY || s->initialized)
        return RPI5_PCIE_CONFIG_STATE;
    if (!dependencies(link, io->context)) return RPI5_PCIE_CONFIG_DEPENDENCY;
    s->io.context = io->context;
    s->io.acquire = io->acquire;
    s->io.release = io->release;
    s->io.check_lifecycle = io->check_lifecycle;
    s->io.authorize_write = io->authorize_write;
    s->io.read = io->read;
    s->io.write = io->write;
    s->io.order = io->order;
    s->link = link;
    s->state = RPI5_PCIE_CONFIG_READY;
    s->initialized = 1;
    return RPI5_PCIE_CONFIG_OK;
}

static int status(struct rpi5_pcie_config *s, uint32_t endpoint)
{
    uint32_t value, required = endpoint ? UINT32_C(0xb0) : UINT32_C(0x80);
    if (s->io.read(s->io.context, STATUS, 4, &value)) return RPI5_PCIE_CONFIG_IO;
    if (value == UINT32_MAX || (value & required) != required || (value & 0x40))
        return RPI5_PCIE_CONFIG_LINK;
    return RPI5_PCIE_CONFIG_OK;
}

static int selector(struct rpi5_pcie_config *s)
{
    uint32_t value;
    if (s->io.read(s->io.context, INDEX, 4, &value)) return RPI5_PCIE_CONFIG_IO;
    return value == RP1_SELECT ? RPI5_PCIE_CONFIG_OK : RPI5_PCIE_CONFIG_SELECTOR;
}

int rpi5_pcie_config_transfer(struct rpi5_pcie_config *s,
    const struct rpi5_pcie_config_request *r, uint32_t *out)
{
    if (!s || !r || !s->initialized || r->bus > 255 || r->device > 31 ||
        r->function > 7 || (r->width != 1 && r->width != 2 && r->width != 4) ||
        r->offset > 4096 - r->width || (r->offset & (r->width - 1)) ||
        r->write > 1 || (!r->write && !out) ||
        (r->write && r->width < 4 && r->value >> (8 * r->width)))
        return RPI5_PCIE_CONFIG_ARGUMENT;
    if (r->bus > 1 || r->device || r->function) return RPI5_PCIE_CONFIG_ABSENT;
    if (s->io.acquire(s->io.context)) return RPI5_PCIE_CONFIG_LOCK;
    int rc = RPI5_PCIE_CONFIG_STATE;
    uint32_t value = 0;
    if (s->state != RPI5_PCIE_CONFIG_READY) goto unlock;
    s->state = RPI5_PCIE_CONFIG_BUSY;
    if (!dependencies(s->link, s->io.context)) {
        rc = RPI5_PCIE_CONFIG_DEPENDENCY;
        goto failed;
    }
#define IO(call) do { if ((call)) { rc = RPI5_PCIE_CONFIG_IO; goto failed; } } while (0)
#define CHECK(call) do { rc = (call); if (rc) goto failed; } while (0)
    IO(s->io.check_lifecycle(s->io.context));
    if (r->write && s->io.authorize_write(s->io.context, r)) {
        rc = RPI5_PCIE_CONFIG_DENIED;
        goto failed;
    }
    IO(s->io.order(s->io.context));
    CHECK(status(s, r->bus));
    if (r->bus) {
        IO(s->io.write(s->io.context, INDEX, 4, RP1_SELECT));
        IO(s->io.order(s->io.context));
        CHECK(selector(s));
        CHECK(status(s, 1));
    }
    if (r->write) IO(s->io.write(s->io.context, (r->bus ? DATA : 0) + r->offset,
                               r->width, r->value));
    else {
        IO(s->io.read(s->io.context, (r->bus ? DATA : 0) + r->offset, r->width, &value));
        if (r->width < 4 && value >> (8 * r->width)) {
            rc = RPI5_PCIE_CONFIG_VALUE;
            goto failed;
        }
    }
    IO(s->io.order(s->io.context));
    CHECK(status(s, r->bus));
    if (r->bus) CHECK(selector(s));
    IO(s->io.check_lifecycle(s->io.context));
    s->state = RPI5_PCIE_CONFIG_READY;
    rc = RPI5_PCIE_CONFIG_OK;
    goto unlock;
failed:
    s->state = RPI5_PCIE_CONFIG_QUARANTINED;
unlock:
    s->io.release(s->io.context);
    if (!rc && !r->write) *out = value;
    return rc;
#undef IO
#undef CHECK
}

int rpi5_pcie_config_ready(struct rpi5_pcie_config *s)
{
    if (!s || !s->initialized) return 0;
    if (s->io.acquire(s->io.context)) return 0;
    int ready = s->state == RPI5_PCIE_CONFIG_READY && dependencies(s->link, s->io.context);
    s->io.release(s->io.context);
    return ready;
}
