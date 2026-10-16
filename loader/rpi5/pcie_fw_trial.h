/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_FW_TRIAL_H
#define RPI5_PCIE_FW_TRIAL_H
#include "pcie_fw_client.h"
#include "pcie_irq_mask.h"
#include "pcie_watchdog_lease.h"
enum { RPI5_FW_TRIAL_ARMED=1, RPI5_FW_TRIAL_MASKED, RPI5_FW_TRIAL_RPC_BEGIN,
    RPI5_FW_TRIAL_RPC_END, RPI5_FW_TRIAL_CHECKED };
struct rpi5_fw_trial_event {
    uint64_t fid, token, raw[4];
    uint32_t phase, pm_writes, gic_writes, rpc_calls, pm_checks;
};
/* Platform functions are real ordered accesses/SMC in the separate BL33.
 * Host tests explicitly replace these leaves, never the protocol below. */
uint64_t rpi5_fw_trial_daif(void);
uint64_t rpi5_fw_trial_affinity(void);
uint32_t rpi5_fw_trial_gic_load(uint32_t offset);
void rpi5_fw_trial_gic_store(uint32_t offset,uint32_t value);
static int fw_trial_record(const struct rpi5_fw_trial_event *);
#endif
