/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_CONFIG_SNAPSHOT_H
#define RPI5_RP1_CONFIG_SNAPSHOT_H
#include "pcie_config.h"
#ifdef __cplusplus
extern "C" {
#endif
struct rpi5_rp1_config_snapshot {
    uint32_t header[16];
    uint32_t bar1_pci_base;
    uint16_t command, status;
    uint8_t revision;
};
/* One fixed 01:00.0 RP1 endpoint, two complete 64-byte header snapshots.
 * Reuses actual serialized config transfer (including selector/status checks).
 * Caller exclusively owns the controller for this entire call and retains
 * independent power, source, endpoint/DMA and recovery admission. No endpoint
 * config writes: the config transport may write only the fixed selector.
 * Output is unchanged on any failure. Identity/header/BAR1 MEM32 shape and
 * equality of both observations are required. BAR address zero is allowed;
 * no assignment, aperture SIZE, memory decode, DMA or mapping is inferred.
 * A failure is terminal to this diagnostic caller; never automatically retry.
 */
int rpi5_rp1_config_snapshot(struct rpi5_pcie_config *,
    struct rpi5_rp1_config_snapshot *);
#ifdef __cplusplus
}
#endif
#endif
