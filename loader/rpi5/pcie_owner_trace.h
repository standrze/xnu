/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_OWNER_TRACE_H
#define RPI5_PCIE_OWNER_TRACE_H
#include <stdint.h>
/* In-memory diagnostic state only. No callback, MMIO, clock or SMC accessor.
 * All values describe the existing operation, never new access authority. */
struct rpi5_pcie_owner_trace {
    uint32_t available, fw_stage; int32_t fw_rc; uint32_t fw_state, fw_sequence;
    uint64_t fw_frequency, fw_last, fw_deadline;
    uint32_t rpc_stage, rpc_calls, rpc_fid;
    uint64_t rpc_raw[4];
    uint32_t pm_stage; int32_t pm_rc; uint32_t pm_state, pm_checks, pm_callbacks;
    uint32_t pm_first, pm_count; uint64_t pm_start, pm_last, pm_deadline;
    uint32_t irq_stage; int32_t irq_rc; uint32_t irq_state, irq_callbacks;
};
#ifdef __cplusplus
extern "C" {
#endif
int pe_rpi5_pcie_owner_trace(const void *,struct rpi5_pcie_owner_trace *);
#ifdef __cplusplus
}
#endif
#endif
