/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_observe.h"

#define STATUS UINT32_C(0x4068)
#define INDEX UINT32_C(0x9000)
#define DATA UINT32_C(0x8000)
#define RP1_SELECT UINT32_C(0x00100000)
#define RC_LINK UINT32_C(0xb0) /* RC role, DL_ACTIVE, PHYLINKUP. */

static int link(const struct rpi5_pcie_observe_io *io, uint32_t *status)
{
    uint32_t value;
    if (io->read32(io->context, STATUS, &value)) return RPI5_PCIE_OBSERVE_IO;
    if (value == UINT32_MAX || (value & RC_LINK) != RC_LINK ||
        (value & UINT32_C(0x40))) return RPI5_PCIE_OBSERVE_LINK; /* L23 */
    *status = value;
    return 0;
}

static int profile(const uint32_t *header)
{
    if (header[0] != UINT32_C(0x00011de4) ||
        header[2] >> 8 != UINT32_C(0x020000) ||
        ((header[3] >> 16) & UINT32_C(0x7f)) != 0) return -1;
    /* RP1's first three BARs are independent 32-bit, nonprefetchable memory
     * BARs. Reject a 64-bit BAR0 whose upper word would masquerade as BAR1. */
    for (uint32_t i = 4; i <= 6; i++) {
        if (header[i] & UINT32_C(0xf)) return -1;
    }
    return 0;
}

int rpi5_pcie_observe_rp1(const struct rpi5_pcie_observe_io *io,
    struct rpi5_pcie_observation *out)
{
    if (!io || !out || !io->read32 || !io->select_rp1 || !io->order ||
        io->mapped_bytes < INDEX + 4) return RPI5_PCIE_OBSERVE_ARGUMENT;

    struct rpi5_pcie_observation result;
    uint32_t first[16], selector, ignored;
    int rc = link(io, &result.status_before);
    if (rc) return rc;
    if (io->select_rp1(io->context) || io->order(io->context) ||
        io->read32(io->context, INDEX, &selector)) return RPI5_PCIE_OBSERVE_IO;
    if (selector != RP1_SELECT) return RPI5_PCIE_OBSERVE_SELECTOR;

    for (uint32_t pass = 0; pass < 2; pass++) {
        uint32_t *header = pass ? result.config : first;
        for (uint32_t word = 0; word < 16; word++) {
            rc = link(io, &ignored);
            if (rc) return rc;
            if (io->read32(io->context, DATA + word * 4, &header[word]))
                return RPI5_PCIE_OBSERVE_IO;
        }
        if (profile(header)) return RPI5_PCIE_OBSERVE_PROFILE;
    }
    /* PCI status (upper half of word 1) may legitimately change. Likewise
     * cache-line/latency/BIST bytes in word 3 are not resource authority. */
    if (first[0] != result.config[0] ||
        (first[1] & UINT32_C(0xffff)) != (result.config[1] & UINT32_C(0xffff)) ||
        first[2] != result.config[2] ||
        ((first[3] ^ result.config[3]) & UINT32_C(0x00ff0000)))
        return RPI5_PCIE_OBSERVE_CHANGED;
    for (uint32_t i = 4; i < 10; i++) {
        if (first[i] != result.config[i]) return RPI5_PCIE_OBSERVE_CHANGED;
    }
    rc = link(io, &result.status_after);
    if (rc) return rc;
    result.memory_decode_enabled = (result.config[1] >> 1) & 1;
    result.bus_master_enabled = (result.config[1] >> 2) & 1;
    result.bar1_pci_base = result.config[5] & UINT32_C(0xfffffff0);
    /* Explicit field copies keep this early-boot helper independent of the
     * compiler's aggregate memcpy/memset runtime lowering. All are initialized
     * above; no output is touched until every observation check has passed. */
    out->status_before = result.status_before;
    out->status_after = result.status_after;
    for (uint32_t i = 0; i < 16; i++) out->config[i] = result.config[i];
    out->memory_decode_enabled = result.memory_decode_enabled;
    out->bus_master_enabled = result.bus_master_enabled;
    out->bar1_pci_base = result.bar1_pci_base;
    return RPI5_PCIE_OBSERVE_OK;
}
