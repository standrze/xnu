/* SPDX-License-Identifier: BSD-2-Clause */
#if !defined(ARM64_BOARD_CONFIG_BCM2712) || !DEVELOPMENT || !RPI5_PCI_WDOG_LEASE || !RPI5_PCIE_IRQ_MASK || !RPI5_PCIE_FW_CLIENT
#error "PCIe firmware owner requires the separate DEVELOPMENT PM/IRQ/client build"
#endif
#include <kern/thread.h>
#include <pexpert/arm/rpi5_pcie_fw_api.h>
static struct rpi5_pcie_watchdog_gate rpi5_pcie_fw_gate;
static struct rpi5_pcie_fw_client rpi5_pcie_fw_session;
static thread_t rpi5_pcie_fw_thread;
static const void *rpi5_pcie_fw_identity;
static int rpi5_pcie_fw_owner(void *context)
{
    return context!=&rpi5_pcie_fw_gate || !rpi5_pcie_fw_identity || ml_at_interrupt_context() ||
        current_thread()!=rpi5_pcie_fw_thread ||
        __atomic_load_n(&rpi5_pcie_fw_gate.owner,__ATOMIC_ACQUIRE)!=rpi5_pcie_fw_identity ? -1:0;
}
static int rpi5_pcie_fw_rpc(void *context,uint32_t fid,uint64_t token,uint64_t raw[4])
{
    struct rpi5_pcie_irq_observation irq;
    if(!raw || rpi5_pcie_fw_owner(context) ||
        !((fid==RPI5_FW_PCIE_QUERY && !token) ||
          ((fid==RPI5_FW_PCIE_CLAIM || fid==RPI5_FW_PCIE_CHECK) && token==(uintptr_t)rpi5_pcie_fw_identity)) ||
        !pe_rpi5_pcie_irq_check(rpi5_pcie_fw_identity,&irq))return -1;
    rpi5_pcie_fw_smccc(fid,token,raw);
    /* Real SMC may hang/abort, not return a synthetic I/O error. A returned
     * SMC_UNK/error is interpreted by the actual client, never as success. */
    return rpi5_pcie_fw_owner(context) || !pe_rpi5_pcie_irq_check(rpi5_pcie_fw_identity,&irq) ? -1:0;
}
bool pe_rpi5_pcie_fw_claim(const void *owner,struct rpi5_fw_observation *out)
{
    struct rpi5_pcie_irq_observation irq;
    if(!owner || !out || ml_at_interrupt_context() || !current_thread() ||
        (__builtin_arm_rsr64("DAIF")&0xc0)!=0xc0 || !pe_rpi5_pcie_irq_check(owner,&irq) ||
        !rpi5_pcie_watchdog_gate_claim(&rpi5_pcie_fw_gate,owner))return false;
    rpi5_pcie_fw_identity=owner;rpi5_pcie_fw_thread=current_thread();thread_reference(rpi5_pcie_fw_thread);
    const struct rpi5_pcie_fw_io io={&rpi5_pcie_fw_gate,rpi5_pcie_fw_owner,rpi5_pcie_fw_rpc};
    struct rpi5_fw_observation result;
    bool ok=!rpi5_pcie_fw_client_init(&rpi5_pcie_fw_session,&io,(uintptr_t)owner,__builtin_arm_rsr64("CNTFRQ_EL0")) &&
        !rpi5_pcie_fw_client_begin(&rpi5_pcie_fw_session,&result) && !rpi5_pcie_fw_owner(&rpi5_pcie_fw_gate);
    if(ok)*out=result;else rpi5_pcie_fw_session.state=RPI5_FW_CLIENT_QUARANTINED;
    rpi5_pcie_watchdog_gate_leave(&rpi5_pcie_fw_gate);return ok;
}
bool pe_rpi5_pcie_fw_check(const void *owner,struct rpi5_fw_observation *out)
{
    if(!owner || !out || ml_at_interrupt_context() || !rpi5_pcie_watchdog_gate_owner(&rpi5_pcie_fw_gate,owner))return false;
    bool ok=false;
    if(current_thread()==rpi5_pcie_fw_thread){
        struct rpi5_fw_observation result;
        ok=!rpi5_pcie_fw_client_check(&rpi5_pcie_fw_session,&result) && !rpi5_pcie_fw_owner(&rpi5_pcie_fw_gate);
        if(ok)*out=result;else rpi5_pcie_fw_session.state=RPI5_FW_CLIENT_QUARANTINED;
    }
    rpi5_pcie_watchdog_gate_leave(&rpi5_pcie_fw_gate);return ok;
}
