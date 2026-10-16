/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual standalone protocol, also executed with explicit host leaf doubles.
 * Not the XNU PE owner/IOKit caller, nor full controller ownership admission. */
#if !RPI5_PCIE_FW_TRIAL
#error "Firmware ABI trial requires its separate opt-in BL33"
#endif
#include "pcie_fw_trial.h"
#include "recovery_pm.h"
static struct {
    uint64_t frequency, affinity;
    uint32_t phase, pm_writes, gic_writes, rpc_calls;
} fw_trial;
static struct rpi5_pcie_watchdog_lease fw_trial_pm;
static struct rpi5_pcie_irq_mask fw_trial_irq;
static struct rpi5_pcie_fw_client fw_trial_client;
static struct rpi5_pcie_irq_observation fw_trial_irq_result;
static struct rpi5_fw_observation fw_trial_result;
static int fw_trial_context(void *context)
{
    return context!=&fw_trial || fw_trial.phase!=1 ||
        (rpi5_fw_trial_daif()&0x3c0)!=0x3c0 ||
        rpi5_fw_trial_affinity()!=fw_trial.affinity ? -1:0;
}
static int fw_trial_route(void *context,uint32_t *out)
{
    if(!out || fw_trial_context(context))return -1;
    *out=rpi5_recovery_route();return 0;
}
static int fw_trial_count(void *context,uint32_t *out)
{
    if(!out || fw_trial_context(context))return -1;
    *out=rpi5_recovery_countdown();return 0;
}
static int fw_trial_write_pm(void *context,uint32_t value)
{
    if(fw_trial_context(context) || fw_trial.pm_writes || value!=UINT32_C(0x5a0f0000))return -1;
    fw_trial.pm_writes=1; /* Irreversible even if the real store aborts/hangs. */
    rpi5_recovery_write_countdown(value);return 0;
}
static int fw_trial_order(void *context)
{
    if(fw_trial_context(context))return -1;
    rpi5_recovery_order();return 0;
}
static int fw_trial_counter(void *context,uint64_t *out)
{
    if(!out || fw_trial_context(context))return -1;
    *out=rpi5_recovery_counter();return 0;
}
static int fw_trial_pm_owner(void *context)
{
    return fw_trial_context(context) || rpi5_pcie_watchdog_check(&fw_trial_pm) ? -1:0;
}
static int fw_trial_gic_read(void *context,uint32_t offset,uint32_t *out)
{
    if(!out || fw_trial_context(context))return -1;
    int allowed=offset==4;
    static const uint32_t banks[]={5,6,8};
    for(unsigned i=0;i<3;i++)for(unsigned base=0x100;base<=0x300;base+=0x100)
        if(offset==base+4*banks[i])allowed=1;
    if(!allowed)return -1;
    *out=rpi5_fw_trial_gic_load(offset);return 0;
}
static int fw_trial_gic_write(void *context,uint32_t offset,uint32_t value)
{
    static const uint32_t banks[]={5,6,8},masks[]={UINT32_MAX,UINT32_MAX,0x7e0};
    unsigned i=fw_trial.gic_writes;
    if(fw_trial_context(context) || i>=3 || offset!=0x180+4*banks[i] || value!=masks[i])return -1;
    fw_trial.gic_writes++;rpi5_fw_trial_gic_store(offset,value);return 0;
}
static int fw_trial_irq_owner(void *context)
{
    return fw_trial_context(context) ||
        rpi5_pcie_irq_check(&fw_trial_irq,&fw_trial_irq_result) ? -1:0;
}
static int fw_trial_event(unsigned phase,uint32_t fid,uint64_t token,const uint64_t raw[4])
{
    struct rpi5_fw_trial_event event={.phase=phase,.fid=fid,.token=token,
        .pm_writes=fw_trial.pm_writes,.gic_writes=fw_trial.gic_writes,
        .rpc_calls=fw_trial.rpc_calls,.pm_checks=fw_trial_pm.checks};
    if(raw)for(unsigned i=0;i<4;i++)event.raw[i]=raw[i];
    if(phase==RPI5_FW_TRIAL_CHECKED){
        event.raw[1]=fw_trial_result.sequence;event.raw[2]=fw_trial_result.counter;event.raw[3]=fw_trial_result.facts;
    }
    return fw_trial_record(&event);
}
static int fw_trial_rpc(void *context,uint32_t fid,uint64_t token,uint64_t raw[4])
{
    if(fw_trial_context(context) || !raw || fw_trial.rpc_calls>=5 ||
        (fid==RPI5_FW_PCIE_QUERY ? token!=0 :
         ((fid!=RPI5_FW_PCIE_CLAIM && fid!=RPI5_FW_PCIE_CHECK) || token!=(uintptr_t)&fw_trial)))return -1;
    if(fw_trial_event(RPI5_FW_TRIAL_RPC_BEGIN,fid,token,0) || fw_trial_context(context))return -1;
    fw_trial.rpc_calls++;rpi5_pcie_fw_smccc(fid,token,raw);
    /* No synthesized error for an SMC that hangs or takes a fatal exception. */
    return fw_trial_event(RPI5_FW_TRIAL_RPC_END,fid,token,raw);
}
static int fw_trial_wait(void)
{
    uint64_t start=rpi5_recovery_counter(),last=start,minimum=(fw_trial.frequency+499)/500;
    for(unsigned i=0;i<1000000;i++){
        uint64_t now=rpi5_recovery_counter();
        if(now<last)return -1;
        if(now-start>=minimum)return fw_trial_pm_owner(&fw_trial);
        last=now;
    }
    return -1;
}
static int fw_trial_run(const struct rpi5_pcie_fdt *binding)
{
    if(!binding || fw_trial.phase || fw_trial.frequency<1000000 || fw_trial.frequency>1000000000)return -1;
    fw_trial.phase=1;
    const struct rpi5_pcie_watchdog_io pm={&fw_trial,fw_trial_route,fw_trial_count,
        fw_trial_write_pm,fw_trial_order,fw_trial_counter};
    const struct rpi5_pcie_irq_io irq={&fw_trial,UINT64_C(0x107fff9000),0x1000,
        fw_trial_pm_owner,fw_trial_gic_read,fw_trial_gic_write,fw_trial_order};
    const struct rpi5_pcie_fw_io client={&fw_trial,fw_trial_irq_owner,fw_trial_rpc};
    struct rpi5_pcie_watchdog_observation armed;
    if(rpi5_pcie_watchdog_init(&fw_trial_pm,&pm,fw_trial.frequency) ||
        rpi5_pcie_irq_init(&fw_trial_irq,binding,&irq) ||
        rpi5_pcie_fw_client_init(&fw_trial_client,&client,(uintptr_t)&fw_trial,fw_trial.frequency) ||
        rpi5_pcie_watchdog_begin(&fw_trial_pm,&armed) ||
        fw_trial_event(RPI5_FW_TRIAL_ARMED,0,0,0) ||
        rpi5_pcie_irq_begin(&fw_trial_irq,&fw_trial_irq_result) ||
        fw_trial_event(RPI5_FW_TRIAL_MASKED,0,0,0) ||
        rpi5_pcie_fw_client_begin(&fw_trial_client,&fw_trial_result))goto failed;
    for(unsigned i=0;i<3;i++){
        if(fw_trial_wait() || rpi5_pcie_fw_client_check(&fw_trial_client,&fw_trial_result) ||
            fw_trial_event(RPI5_FW_TRIAL_CHECKED,0,0,0))goto failed;
    }
    if(fw_trial_pm_owner(&fw_trial))goto failed;
    fw_trial.phase=2;return 0; /* Park, do not service/release/retry. */
failed:
    fw_trial.phase=3;
    fw_trial_pm.state=RPI5_PCIE_WDOG_QUARANTINED;
    fw_trial_irq.state=RPI5_PCIE_IRQ_QUARANTINED;
    fw_trial_client.state=RPI5_FW_CLIENT_QUARANTINED;
    return -1;
}
