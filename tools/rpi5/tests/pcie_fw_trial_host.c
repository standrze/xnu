/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual standalone orchestrator, PM/IRQ/client cores and actual firmware
 * verifier/service. Explicit MMIO/counter/DAIF/affinity/SMC/UART/lock doubles.
 * Fabricated binding below is model setup, not a real FDT or admission. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define RPI5_PCIE_FW_TRIAL 1
#include "loader/rpi5/pcie_fw_trial.inc"
#include "firmware/rpi5/pcie_verifier.c"
#include "firmware/rpi5/pcie_verifier_sip.c"
static struct {
    uint64_t ticks,armed,daif,affinity,step;
    uint32_t enable[3],pending[3],active[3],group[3],reset,rescal,route;
    unsigned pm_reads,pm_bad_at,records,record_bad_at,smcs,bad_call,bad_field;
    unsigned ns_reads,fw_reads,context_at;
    int absent,reenter,stalled,hold_lock,trace;
} fake;
static struct rpi5_pcie_fdt model_binding;
static uint64_t tick(void){fake.ticks+=fake.step;return fake.ticks;}
uint64_t rpi5_fw_trial_daif(void){return fake.daif;}
uint64_t rpi5_fw_trial_affinity(void){return fake.affinity;}
uint64_t rpi5_recovery_counter(void){return tick();}
uint32_t rpi5_recovery_route(void)
{
    fake.pm_reads++;return fake.pm_reads==fake.pm_bad_at?UINT32_MAX:fake.route;
}
uint32_t rpi5_recovery_countdown(void)
{
    fake.pm_reads++;
    if(fake.pm_reads==fake.pm_bad_at)return UINT32_MAX;
    if(!fw_trial.pm_writes)return 60u<<16;
    return (15u<<16)-(fake.stalled?0:(uint32_t)((fake.ticks-fake.armed)*65536/1000000));
}
void rpi5_recovery_write_countdown(uint32_t value)
{
    assert(value==UINT32_C(0x5a0f0000) && fw_trial.pm_writes==1);
    fake.armed=fake.ticks;
}
void rpi5_recovery_order(void){}
static uint32_t gic_read(uint32_t off,int secure)
{
    static const unsigned banks[]={5,6,8};
    if(off==4)return 0xfc69;
    for(unsigned i=0;i<3;i++){
        if(off==0x80+4*banks[i]){assert(secure);return fake.group[i];}
        if(off==0x100+4*banks[i])return fake.enable[i];
        if(off==0x200+4*banks[i]){assert(!secure);return fake.pending[i];}
        if(off==0x300+4*banks[i])return fake.active[i];
    }
    assert(0);return 0;
}
uint32_t rpi5_fw_trial_gic_load(uint32_t off){fake.ns_reads++;return gic_read(off,0);}
void rpi5_fw_trial_gic_store(uint32_t off,uint32_t value)
{
    static const unsigned banks[]={5,6,8};static const uint32_t masks[]={UINT32_MAX,UINT32_MAX,0x7e0};
    unsigned i=fw_trial.gic_writes-1;assert(i<3 && off==0x180+4*banks[i] && value==masks[i]);
    fake.enable[i]&=~value;
}
uint64_t rpi5_fw_counter(void){return tick();}
uint64_t rpi5_fw_frequency(void){return 1000000;}
uint32_t rpi5_fw_load32(uint64_t p)
{
    fake.fw_reads++;
    if(p>=GIC && p<GIC+0x1000)return gic_read((uint32_t)(p-GIC),1);
    if(p==RESET)return fake.reset;
    if(p==RESCAL)return fake.rescal;
    if(p==RESCAL+8)return 1;
    if(p==PM+0x1c)return rpi5_recovery_route();
    if(p==PM+0x24)return rpi5_recovery_countdown();
    assert(0);return 0;
}
int rpi5_fw_trylock(volatile uint32_t *p){if(*p || fake.hold_lock)return 0;*p=1;return 1;}
void rpi5_fw_unlock(volatile uint32_t *p){assert(*p==1);*p=0;}
void rpi5_pcie_fw_smccc(uint64_t fid,uint64_t token,uint64_t raw[4])
{
    fake.smcs++;assert(fw_trial.pm_writes==1 && fw_trial.gic_writes==3 && (fake.daif&0x3c0)==0x3c0);
    const uint32_t fids[]={RPI5_FW_PCIE_QUERY,RPI5_FW_PCIE_CLAIM,RPI5_FW_PCIE_CHECK,RPI5_FW_PCIE_CHECK,RPI5_FW_PCIE_CHECK};
    assert(fake.smcs<=5 && fid==fids[fake.smcs-1]);
    assert(token==(fake.smcs==1?0:(uintptr_t)&fw_trial));
    if(fake.absent){raw[0]=0xffffffff;raw[1]=raw[2]=raw[3]=0;return;}
    struct host_context context;
    rpi5_pcie_sip((uint32_t)fid,token,0,0,0,NULL,&context,1);
    memcpy(raw,context.regs,sizeof(context.regs));
    if(fake.smcs==fake.bad_call)raw[fake.bad_field]=fake.bad_field==0?0xffffffff:0;
}
static int fw_trial_record(const struct rpi5_fw_trial_event *event)
{
    fake.records++;
    assert(event->pm_writes==1);
    if(event->phase==RPI5_FW_TRIAL_ARMED)assert(!event->gic_writes && !fake.smcs);
    else assert(event->gic_writes==3);
    if(fake.reenter)assert(fw_trial_run(&model_binding)<0);
    if(fake.records==fake.context_at)fake.daif=0;
    if(fake.trace){
        const char *names[]={"INVALID","ARMED","MASKED","RPC_BEGIN","RPC_END","CHECKED"};
        printf("RPI5XNU:FWABI:%s TAG=0123456789abcdef0123456789abcdef FID=0x%016llX TOKEN=0x%016llX X0=0x%016llX X1=0x%016llX X2=0x%016llX X3=0x%016llX PM_WRITES=0x%016X GIC_WRITES=0x%016X RPC_CALLS=0x%016X PM_CHECKS=0x%016X\r\n",
            names[event->phase],(unsigned long long)event->fid,(unsigned long long)event->token,
            (unsigned long long)event->raw[0],(unsigned long long)event->raw[1],
            (unsigned long long)event->raw[2],(unsigned long long)event->raw[3],
            event->pm_writes,event->gic_writes,event->rpc_calls,event->pm_checks);
    }
    return fake.records==fake.record_bad_at?-1:0;
}
static void fresh(void)
{
    memset(&fake,0,sizeof(fake));memset(&fw_trial,0,sizeof(fw_trial));
    memset(&fw_trial_pm,0,sizeof(fw_trial_pm));memset(&fw_trial_irq,0,sizeof(fw_trial_irq));
    memset(&fw_trial_client,0,sizeof(fw_trial_client));memset(&fw_trial_result,0,sizeof(fw_trial_result));
    memset(&verifier,0,sizeof(verifier));verifier_lock=0;
    fake.daif=0x3c0;fake.route=0x222;fake.step=1;fake.ticks=1000000;
    fake.enable[0]=fake.enable[1]=UINT32_MAX;fake.enable[2]=0x7e1;
    fake.pending[0]=1;fake.pending[1]=2;fake.pending[2]=0x21;
    for(unsigned i=0;i<3;i++)fake.group[i]=UINT32_MAX;
    fw_trial.frequency=1000000;fw_trial.affinity=0;
    model_binding=(struct rpi5_pcie_fdt){.bridge_regs={UINT64_C(0x1000120000),UINT64_C(0x1000129310)},
        .bridge_reset_id=44,.gic_phandle=7,.bridge_intid={265,266},.intx_intid={261,262,263,264},
        .mip_intid_base=160,.mip_intid_count=64};
}
static void refused(void)
{
    assert(fw_trial_run(&model_binding)<0 && fw_trial.phase==3);
    assert(fw_trial_pm.state==RPI5_PCIE_WDOG_QUARANTINED &&
        fw_trial_irq.state==RPI5_PCIE_IRQ_QUARANTINED && fw_trial_client.state==RPI5_FW_CLIENT_QUARANTINED);
    unsigned pm=fake.pm_reads,ns=fake.ns_reads,fw=fake.fw_reads,smc=fake.smcs,records=fake.records;
    assert(fw_trial_run(&model_binding)<0 && pm==fake.pm_reads && ns==fake.ns_reads &&
        fw==fake.fw_reads && smc==fake.smcs && records==fake.records);
}
int main(int argc,char **argv)
{
    fresh();fake.reenter=1;
    if(argc==2 && !strcmp(argv[1],"--trace")){
        fake.trace=1;
        puts("RPI5XNU:FWABI:ENTRY TAG=0123456789abcdef0123456789abcdef EL2 NO_XNU NO_CPU_ON CONTROLLER_WRITES=0 DMA=0\r");
        puts("RPI5XNU:FWABI:EL1 TAG=0123456789abcdef0123456789abcdef MMU_CACHE_OFF DAIF_MASKED PRIMARY_ONLY FREQUENCY=0x00000000000F4240\r");
    }
    assert(!fw_trial_run(&model_binding));
    assert(fw_trial.phase==2 && fw_trial.pm_writes==1 && fw_trial.gic_writes==3 && fake.smcs==5);
    assert(fw_trial_result.sequence==4 && fw_trial_result.facts==31 && fake.records==15);
    assert(!fake.enable[0] && !fake.enable[1] && fake.enable[2]==1 && fake.pending[2]==0x21);
    unsigned pm_reads=fake.pm_reads,ns_reads=fake.ns_reads,checks=fw_trial_pm.checks;
    if(fake.trace){
        printf("RPI5XNU:FWABI:RESULT TAG=0123456789abcdef0123456789abcdef RC=0x0000000000000000 PHASE=0x0000000000000002 PM_WRITES=0x0000000000000001 GIC_WRITES=0x0000000000000003 RPC_CALLS=0x0000000000000005 SEQUENCE=0x0000000000000004 FACTS=0x000000000000001F PM_CHECKS=0x%016X\r\n",checks);
        puts("RPI5XNU:FWABI:STOP TAG=0123456789abcdef0123456789abcdef NO_RELOAD WAIT_FOR_RESET CONTROLLER_WRITES=0 DMA=0 RESET_RETURN_PROVEN=0\r");
        return 0;
    }
    assert(fw_trial_run(&model_binding)<0 && fake.pm_reads==pm_reads);
    for(unsigned i=1;i<=pm_reads;i++){fresh();fake.pm_bad_at=i;refused();}
    for(unsigned i=1;i<=15;i++){fresh();fake.record_bad_at=i;refused();}
    for(unsigned i=1;i<=5;i++)for(unsigned j=0;j<4;j++){
        fresh();fake.bad_call=i;fake.bad_field=j;refused();
    }
    fresh();fake.absent=1;refused();assert(fake.smcs==1);
    fresh();fake.hold_lock=1;refused();assert(fake.smcs==1);
    fresh();fake.active[0]=1;refused();assert(!fw_trial.gic_writes && !fake.smcs);
    fresh();fake.group[0]=0;refused();assert(fake.smcs==1);
    fresh();fake.reset=1u<<11;refused();assert(fake.smcs==2);
    fresh();fake.rescal=1;refused();assert(fake.smcs==2);
    fresh();fake.daif=0;refused();assert(!fw_trial.pm_writes && !fake.ns_reads && !fake.smcs);
    fresh();fake.affinity=1;refused();assert(!fw_trial.pm_writes);
    fresh();fake.context_at=3;refused();assert(!fake.smcs); /* RPC_BEGIN context mutation. */
    fresh();fake.stalled=1;refused();assert(fake.smcs==2); /* 2ms wait detects stopped PM. */
    fresh();fake.step=0;refused();assert(fake.smcs==2); /* Query/claim counters cannot advance. */
    fresh();model_binding.bridge_reset_id=43;refused();assert(!fw_trial.pm_writes);
    printf("FW_TRIAL_HOST_PASS ACTUAL_PROTOCOL_CORES_PRODUCER_SERVICE=1 PM_FAILURES=%u RECORD_FAILURES=15 ABI_MUTATIONS=20 NS_READS=%u PM_CHECKS=%u NO_MMIO=1\n",pm_reads,ns_reads,checks);
    return 0;
}
