/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual TF-A runtime service. Host tests use explicit ABI/lock doubles. */
#include <common/runtime_svc.h>
#include <smccc_helpers.h>
#include "pcie_verifier.h"
static uint32_t verifier_lock;
extern int rpi5_fw_trylock(volatile uint32_t *);
extern void rpi5_fw_unlock(volatile uint32_t *);
static uintptr_t rpi5_pcie_sip(uint32_t fid, u_register_t x1, u_register_t x2,
    u_register_t x3, u_register_t x4, void *cookie, void *handle, u_register_t flags)
{
    (void)cookie;
    if (!is_caller_non_secure(flags) || x2 || x3 || x4 ||
        (fid!=RPI5_FW_PCIE_QUERY && fid!=RPI5_FW_PCIE_CLAIM && fid!=RPI5_FW_PCIE_CHECK))
        SMC_RET1(handle,SMC_UNK);
    /* Never wait behind another CPU/interrupt or a stuck secure MMIO access. */
    if (!rpi5_fw_trylock(&verifier_lock)) SMC_RET1(handle,(u_register_t)(int64_t)RPI5_FW_STATE);
    struct rpi5_fw_observation observed={0};
    int rc=rpi5_fw_verifier_call(fid,x1,&observed);
    rpi5_fw_unlock(&verifier_lock);
    SMC_RET4(handle,(u_register_t)(int64_t)rc,observed.sequence,observed.counter,observed.facts);
}
DECLARE_RT_SVC(rpi5_pcie_verifier,OEN_SIP_START,OEN_SIP_END,SMC_TYPE_FAST,NULL,rpi5_pcie_sip);
