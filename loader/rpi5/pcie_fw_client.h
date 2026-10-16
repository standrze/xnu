/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_FW_CLIENT_H
#define RPI5_PCIE_FW_CLIENT_H
#include "../../firmware/rpi5/pcie_verifier.h"
#ifdef __cplusplus
extern "C" {
#endif
struct rpi5_pcie_fw_io {
    void *context;
    int (*owner)(void *);
    int (*rpc)(void *, uint32_t fid, uint64_t token, uint64_t result[4]);
};
enum {RPI5_FW_CLIENT_EMPTY,RPI5_FW_CLIENT_READY,RPI5_FW_CLIENT_BUSY,
    RPI5_FW_CLIENT_OWNED,RPI5_FW_CLIENT_QUARANTINED};
struct rpi5_pcie_fw_client {
    struct rpi5_pcie_fw_io io;
    uint64_t token,frequency,deadline,last_counter;
    uint32_t sequence,state;
};
/* Stable/disjoint zeroed storage, same retained real NS owner/thread/PM/IRQ
 * leases. Pure init; begin performs QUERY then CLAIM once. No retry/release.
 * A hung SMC does not return an invented error. Output atomic on failure. */
int rpi5_pcie_fw_client_init(struct rpi5_pcie_fw_client *, const struct rpi5_pcie_fw_io *, uint64_t token, uint64_t frequency);
int rpi5_pcie_fw_client_begin(struct rpi5_pcie_fw_client *, struct rpi5_fw_observation *);
int rpi5_pcie_fw_client_check(struct rpi5_pcie_fw_client *, struct rpi5_fw_observation *);
/* Production SMCCC64 leaf; x2..x7 zero, x19 retains output, four raw results. */
void rpi5_pcie_fw_smccc(uint64_t fid,uint64_t token,uint64_t result[4]);
#ifdef __cplusplus
}
#endif
#endif
