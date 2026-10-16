/* SPDX-License-Identifier: BSD-2-Clause */
/* Real NS client/PE owner and real firmware producer/service, with explicit
 * counter/MMIO/thread/IRQ/SMCCC/lock doubles. No actual SMC or IOKit/hardware. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "loader/rpi5/pcie_watchdog_gate.h"
#include "pexpert/arm/rpi5_pcie_irq_api.h"
#define ARM64_BOARD_CONFIG_BCM2712 1
#define DEVELOPMENT 1
#define RPI5_PCI_WDOG_LEASE 1
#define RPI5_PCIE_IRQ_MASK 1
#define RPI5_PCIE_FW_CLIENT 1
#include "firmware/rpi5/pcie_verifier.c"
#include "firmware/rpi5/pcie_verifier_sip.c"
static uint64_t clock_ticks,frequency=1000000,daif=0xc0;
static int thread_id,other_thread_id,identity,other_identity;
static void *thread=&thread_id;
static unsigned thread_refs,irq_checks,smcs,fail_irq_at,bad_call,bad_field;
static uint64_t bad_value;
static int interrupt_context,reentry,firmware_absent;
static uint32_t selected_enable,selected_active;
uint64_t rpi5_fw_counter(void){return clock_ticks+=1000;}
uint64_t rpi5_fw_frequency(void){return frequency;}
int rpi5_fw_trylock(volatile uint32_t *p){if(*p)return 0;*p=1;return 1;}
void rpi5_fw_unlock(volatile uint32_t *p){assert(*p==1);*p=0;}
uint32_t rpi5_fw_load32(uint64_t p)
{
    if(p==GIC+4)return 0xfc69;
    const uint32_t banks[]={5,6,8};
    for(unsigned i=0;i<3;i++){
        if(p==GIC+0x80+4*banks[i])return UINT32_MAX;
        if(p==GIC+0x100+4*banks[i])return selected_enable;
        if(p==GIC+0x300+4*banks[i])return selected_active;
    }
    if(p==RESET || p==RESCAL || p==RESCAL+8)return 0;
    if(p==PM+0x1c)return 0x222;
    if(p==PM+0x24)return (15u<<16)-(uint32_t)(clock_ticks*65536/frequency);
    assert(0);return 0;
}
static bool ml_at_interrupt_context(void){return interrupt_context!=0;}
void *current_thread(void){return thread;}
void thread_reference(void *p){assert(p==&thread_id);thread_refs++;}
static uint64_t reg(const char *name){if(!strcmp(name,"DAIF"))return daif;assert(!strcmp(name,"CNTFRQ_EL0"));return frequency;}
#define __builtin_arm_rsr64(name) reg(name)
bool pe_rpi5_pcie_irq_check(const void *owner,struct rpi5_pcie_irq_observation *out)
{
    irq_checks++;
    if(owner!=&identity || thread!=&thread_id || irq_checks==fail_irq_at || selected_enable || selected_active)return false;
    memset(out,0,sizeof(*out));return true;
}
#include "pexpert/arm/rpi5_pcie_fw_owner.inc"
void rpi5_pcie_fw_smccc(uint64_t fid,uint64_t token,uint64_t raw[4])
{
    smcs++;assert(!interrupt_context);
    if(reentry){struct rpi5_fw_observation out;assert(!pe_rpi5_pcie_fw_check(&identity,&out));}
    struct host_context context;
    rpi5_pcie_sip((uint32_t)fid,token,0,0,0,NULL,&context,1);
    memcpy(raw,context.regs,sizeof(context.regs));
    if(firmware_absent)raw[0]=0xffffffff;
    if(smcs==bad_call)raw[bad_field]=bad_value;
}
static void fresh(void)
{
    memset(&verifier,0,sizeof(verifier));verifier_lock=0;rpi5_pcie_fw_gate=(struct rpi5_pcie_watchdog_gate){0};
    memset(&rpi5_pcie_fw_session,0,sizeof(rpi5_pcie_fw_session));rpi5_pcie_fw_identity=NULL;rpi5_pcie_fw_thread=NULL;
    clock_ticks=0;frequency=1000000;daif=0xc0;thread=&thread_id;thread_refs=irq_checks=smcs=fail_irq_at=bad_call=0;
    bad_field=0;bad_value=0;interrupt_context=reentry=firmware_absent=0;selected_enable=selected_active=0;
}
static void refused_claim(void)
{
    struct rpi5_fw_observation out,saved;memset(&out,0xa5,sizeof(out));saved=out;
    assert(!pe_rpi5_pcie_fw_claim(&identity,&out) && !memcmp(&out,&saved,sizeof(out)));
    unsigned calls=smcs;assert(!pe_rpi5_pcie_fw_claim(&identity,&out) && !pe_rpi5_pcie_fw_check(&identity,&out));
    assert(smcs==calls && !memcmp(&out,&saved,sizeof(out)));
}
int main(void)
{
    struct rpi5_fw_observation out,saved;memset(&saved,0xa5,sizeof(saved));
    fresh();reentry=1;assert(pe_rpi5_pcie_fw_claim(&identity,&out));
    assert(smcs==2 && irq_checks==5 && thread_refs==1 && out.sequence==1 && out.facts==31);
    assert(pe_rpi5_pcie_fw_check(&identity,&out) && smcs==3 && irq_checks==7 && out.sequence==2);
    unsigned before=smcs;thread=&other_thread_id;assert(!pe_rpi5_pcie_fw_check(&identity,&out) && smcs==before);
    thread=&thread_id;assert(!pe_rpi5_pcie_fw_check(&other_identity,&out) && smcs==before);
    assert(pe_rpi5_pcie_fw_check(&identity,&out));
    for(unsigned call=1;call<=3;call++)for(unsigned field=0;field<4;field++){
        fresh();if(call==3)assert(pe_rpi5_pcie_fw_claim(&identity,&out));
        bad_call=call;bad_field=field;bad_value=(uint64_t[]){0xffffffff,0,0,0}[field];out=saved;
        if(call<=2)refused_claim();else{
            assert(!pe_rpi5_pcie_fw_check(&identity,&out) && !memcmp(&out,&saved,sizeof(out)));
            before=smcs;assert(!pe_rpi5_pcie_fw_check(&identity,&out) && smcs==before);
        }
    }
    for(unsigned failure=2;failure<=5;failure++){fresh();fail_irq_at=failure;refused_claim();}
    for(unsigned failure=1;failure<=2;failure++){
        fresh();assert(pe_rpi5_pcie_fw_claim(&identity,&out));fail_irq_at=irq_checks+failure;out=saved;
        assert(!pe_rpi5_pcie_fw_check(&identity,&out) && !memcmp(&out,&saved,sizeof(out)));
    }
    fresh();firmware_absent=1;refused_claim();
    fresh();bad_call=2;bad_field=2;bad_value=UINT64_MAX;refused_claim();
    fresh();daif=0;out=saved;assert(!pe_rpi5_pcie_fw_claim(&identity,&out) && !smcs && !irq_checks && !thread_refs);
    fresh();interrupt_context=1;assert(!pe_rpi5_pcie_fw_claim(&identity,&out) && !smcs && !thread_refs);
    fresh();thread=NULL;assert(!pe_rpi5_pcie_fw_claim(&identity,&out) && !smcs && !thread_refs);
    fresh();assert(pe_rpi5_pcie_fw_claim(&identity,&out));bad_call=3;bad_field=2;bad_value=rpi5_pcie_fw_session.deadline;
    assert(!pe_rpi5_pcie_fw_check(&identity,&out));
    fresh();assert(pe_rpi5_pcie_fw_claim(&identity,&out));rpi5_pcie_fw_session.sequence=65536;before=smcs;
    assert(!pe_rpi5_pcie_fw_check(&identity,&out) && smcs==before);
    fresh();struct rpi5_pcie_fw_client s={0};struct rpi5_pcie_fw_io io={&rpi5_pcie_fw_gate,rpi5_pcie_fw_owner,rpi5_pcie_fw_rpc};
    assert(!rpi5_pcie_fw_client_init(&s,&io,7,1000000));
    assert(rpi5_pcie_fw_client_begin(&s,(struct rpi5_fw_observation *)(void *)&s)<0 && s.state==RPI5_FW_CLIENT_READY);
    assert(rpi5_pcie_fw_client_init(&s,&io,7,1000000)<0);
    puts("FW_CLIENT_HOST_PASS REAL_PRODUCER_SERVICE_CLIENT_PE=1 ABI_MUTATIONS=12 IRQ_FAILURES=6 NO_MMIO=1");return 0;
}
