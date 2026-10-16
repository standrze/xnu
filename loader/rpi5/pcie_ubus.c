/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_ubus.h"

#define UBUS_CTRL UINT32_C(0x40a4)
#define UBUS_ERROR_DISABLE UINT32_C(0x00082000)
#define ERROR_DATA UINT32_C(0x4170)
#define UBUS_TIMEOUT UINT32_C(0x40a8)
#define CONFIG_RETRY UINT32_C(0x405c)
#define AXI_CTRL UINT32_C(0x416c)
#define AXI_SET UINT32_C(0x3800)
#define AXI_REQUIRED UINT32_C(0x2800)
#define AXI_TIMING UINT32_C(0x1000)
#define AXI_PROPAGATION UINT32_C(0x80)
#define CTRL1 UINT32_C(0x40a0)
#define VDM_QOS UINT32_C(0x20)

static int dependencies(const struct rpi5_pcie_serdes *s)
{
    return s && s->state == RPI5_PCIE_SERDES_COMPLETE &&
        s->mdio.state == RPI5_PCIE_MDIO_READY && s->calibration && s->bridge_reset &&
        s->calibration->state == RPI5_PCIE_RESCAL_COMPLETE &&
        s->bridge_reset->state == RPI5_PCIE_RESET_COMPLETE;
}

int rpi5_pcie_ubus_init(struct rpi5_pcie_ubus *session, struct rpi5_pcie_serdes *serdes)
{
    if (!session || !serdes) return RPI5_PCIE_UBUS_ARGUMENT;
    if (session->state != RPI5_PCIE_UBUS_EMPTY) return RPI5_PCIE_UBUS_STATE;
    if (!dependencies(serdes)) return RPI5_PCIE_UBUS_DEPENDENCY;
    const struct rpi5_pcie_mdio_io *io = &serdes->mdio.io;
    if (io->physical_base != UINT64_C(0x1000120000) || io->mapped_bytes != 0x9310 ||
        !io->read32 || !io->write32 || !io->order) return RPI5_PCIE_UBUS_ARGUMENT;
    session->serdes = serdes;
    session->completed_callbacks = 0;
    session->state = RPI5_PCIE_UBUS_READY;
    return RPI5_PCIE_UBUS_OK;
}

static int quarantine(struct rpi5_pcie_ubus *session, int result)
{
    session->state = RPI5_PCIE_UBUS_QUARANTINED;
    if (session->serdes) {
        session->serdes->state = RPI5_PCIE_SERDES_QUARANTINED;
        session->serdes->mdio.state = RPI5_PCIE_MDIO_QUARANTINED;
    }
    return result;
}

int rpi5_pcie_ubus_configure(struct rpi5_pcie_ubus *session,
    struct rpi5_pcie_ubus_observation *out)
{
    if (!session || !out) return RPI5_PCIE_UBUS_ARGUMENT;
    if (session->state != RPI5_PCIE_UBUS_READY) return RPI5_PCIE_UBUS_STATE;
    session->state = RPI5_PCIE_UBUS_BUSY;
    if (!dependencies(session->serdes)) return quarantine(session, RPI5_PCIE_UBUS_DEPENDENCY);
    const struct rpi5_pcie_mdio_io *io = &session->serdes->mdio.io;
    struct rpi5_pcie_ubus_observation result;
#define STEP(call) do { \
    if ((call)) return quarantine(session, RPI5_PCIE_UBUS_IO); \
    session->completed_callbacks++; \
} while (0)
#define READ(reg, field) do { \
    STEP(io->read32(io->context, (reg), &(field))); \
    if ((field) == UINT32_MAX) return quarantine(session, RPI5_PCIE_UBUS_READBACK); \
} while (0)
#define WRITE(reg, value) do { \
    STEP(io->write32(io->context, (reg), (value))); \
    STEP(io->order(io->context)); \
} while (0)
    READ(UBUS_CTRL, result.ubus_before);
    WRITE(UBUS_CTRL, result.ubus_before | UBUS_ERROR_DISABLE);
    READ(UBUS_CTRL, result.ubus_after);
    if ((result.ubus_after & UBUS_ERROR_DISABLE) != UBUS_ERROR_DISABLE)
        return quarantine(session, RPI5_PCIE_UBUS_READBACK);
    WRITE(ERROR_DATA, UINT32_MAX);
    WRITE(UBUS_TIMEOUT, UINT32_C(0x0b2d0000));
    READ(UBUS_TIMEOUT, result.ubus_timeout);
    if (result.ubus_timeout != UINT32_C(0x0b2d0000))
        return quarantine(session, RPI5_PCIE_UBUS_READBACK);
    WRITE(CONFIG_RETRY, UINT32_C(0x0aba0000));
    READ(CONFIG_RETRY, result.config_retry_timeout);
    if (result.config_retry_timeout != UINT32_C(0x0aba0000))
        return quarantine(session, RPI5_PCIE_UBUS_READBACK);
    READ(AXI_CTRL, result.axi_before);
    WRITE(AXI_CTRL, (result.axi_before & ~AXI_PROPAGATION) | AXI_SET);
    READ(AXI_CTRL, result.axi_after);
    if ((result.axi_after & (AXI_REQUIRED | AXI_PROPAGATION)) != AXI_REQUIRED)
        return quarantine(session, RPI5_PCIE_UBUS_READBACK);
    result.axi_final = result.axi_after;
    result.outstanding_fallback = !(result.axi_after & AXI_TIMING);
    if (result.outstanding_fallback) {
        WRITE(AXI_CTRL, (result.axi_after & ~UINT32_C(0x3f)) | 15);
        READ(AXI_CTRL, result.axi_final);
        if ((result.axi_final & (AXI_REQUIRED | AXI_PROPAGATION | AXI_TIMING | 0x3f)) != (AXI_REQUIRED | 15))
            return quarantine(session, RPI5_PCIE_UBUS_READBACK);
    }
    READ(CTRL1, result.control_before);
    WRITE(CTRL1, result.control_before & ~VDM_QOS);
    READ(CTRL1, result.control_after);
    if (result.control_after & VDM_QOS) return quarantine(session, RPI5_PCIE_UBUS_READBACK);
#undef WRITE
#undef READ
#undef STEP
    /* Keep the freestanding target free of an implicit memcpy dependency. */
    out->ubus_before = result.ubus_before;
    out->ubus_after = result.ubus_after;
    out->ubus_timeout = result.ubus_timeout;
    out->config_retry_timeout = result.config_retry_timeout;
    out->axi_before = result.axi_before;
    out->axi_after = result.axi_after;
    out->axi_final = result.axi_final;
    out->control_before = result.control_before;
    out->control_after = result.control_after;
    out->outstanding_fallback = result.outstanding_fallback;
    session->state = RPI5_PCIE_UBUS_COMPLETE;
    return RPI5_PCIE_UBUS_OK;
}
