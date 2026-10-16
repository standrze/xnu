/* SPDX-License-Identifier: BSD-2-Clause */
/* Explicit host counter, PM/GIC MMIO, XNU thread and SMC doubles. All PE
 * owners, lease/IRQ/client cores and secure verifier/service are production
 * bodies. This is not an IOKit, firmware timing or board proof. */
#include <cstdint>
#include <cassert>
#include <cstring>
extern "C" {
#include "loader/rpi5/pcie_watchdog_gate.h"
#include "pexpert/arm/rpi5_pcie_watchdog_api.h"
#include "pexpert/arm/rpi5_pcie_irq_api.h"
#include "pexpert/arm/rpi5_pcie_fw_api.h"
void model_secure_reset(void);
void model_secure_call(uint64_t,uint64_t,uint64_t[4]);
}
#define GIC UINT64_C(0x107fff9000)
#define PM UINT64_C(0x107d200000)
#define RESET UINT64_C(0x1001504338)
#define RESCAL UINT64_C(0x1000119500)
#define ARM64_BOARD_CONFIG_BCM2712 1
#define DEVELOPMENT 1
#define RPI5_PCI_WDOG_LEASE 1
#define RPI5_PCIE_IRQ_MASK 1
#define RPI5_PCIE_FW_CLIENT 1
#define RPI5_PCIE_IRQ_TRANSPORT 1
#define RPI5_PCIE_FW_TRANSPORT 1
#define RPI5_PCIE_CONTROLLER_DIAGNOSTIC 1
#define RPI5_GICD_PHYS UINT64_C(0x107fff9000)
#define RPI5_GICD_SIZE UINT64_C(0x1000)
#define RPI5_PM_RSTC 0x1c
#define RPI5_PM_WDOG 0x24
#define DSB_SY 0
typedef uintptr_t vm_offset_t;
typedef void *thread_t;
static int thread_identity;
static uint64_t model_ticks, model_frequency=1000000, arm_ticks;
static uint64_t rpi5_wdog_deadline=1;
static unsigned rpi5_wdog_soak_seconds, pm_writes, ns_reads, secure_reads, smc_calls;
static uint32_t gic_model[1024];
static vm_offset_t rpi5_gicd_base=reinterpret_cast<uintptr_t>(gic_model);
static vm_offset_t rpi5_pm_base=0x80000000;
static uint64_t daif=0x3c0;
static unsigned corrupt_smc, corrupt_field, corrupt_pm_at;
static bool corrupt_irq_after_smc;
static uint64_t corrupt_raw;
static bool ml_at_interrupt_context(){return false;}
static thread_t current_thread(){return &thread_identity;}
static void thread_reference(thread_t t){assert(t==&thread_identity);}
static void rpi5_watchdog_service_unlocked(bool){assert(false);}
static uint64_t model_register(const char *name)
{
    if(!strcmp(name,"CNTFRQ_EL0"))return model_frequency;
    if(!strcmp(name,"CNTVCT_EL0"))return ++model_ticks;
    assert(!strcmp(name,"DAIF"));return daif;
}
#define __builtin_arm_rsr64(name) model_register(name)
#define __builtin_arm_dsb(scope) ((void)(scope))
static uint32_t countdown()
{
    uint64_t elapsed=(model_ticks-arm_ticks)*65536/model_frequency;
    return elapsed>=(15u<<16)?0:(15u<<16)-static_cast<uint32_t>(elapsed);
}
static uint32_t rpi5_mmio_read32(vm_offset_t base,uint32_t offset)
{
    ns_reads++;
    if(base==rpi5_pm_base){
        if(corrupt_pm_at==ns_reads)return UINT32_MAX;
        if(offset==RPI5_PM_RSTC)return 0x20;
        assert(offset==RPI5_PM_WDOG);return countdown();
    }
    assert(base==rpi5_gicd_base&&offset<sizeof(gic_model));
    return gic_model[offset/4];
}
static void rpi5_mmio_write32(vm_offset_t base,uint32_t offset,uint32_t value)
{
    if(base==rpi5_pm_base){assert(offset==RPI5_PM_WDOG&&value==0x5a0f0000);arm_ticks=model_ticks;pm_writes++;return;}
    assert(base==rpi5_gicd_base);
    assert(offset==0x194||offset==0x198||offset==0x1a0);
    gic_model[(offset-0x80)/4]&=~value;
}
extern "C" uint64_t rpi5_fw_counter(){return ++model_ticks;}
extern "C" uint64_t rpi5_fw_frequency(){return model_frequency;}
extern "C" int rpi5_fw_trylock(volatile uint32_t *p){if(*p)return 0;*p=1;return 1;}
extern "C" void rpi5_fw_unlock(volatile uint32_t *p){assert(*p==1);*p=0;}
extern "C" uint32_t rpi5_fw_load32(uint64_t address)
{
    secure_reads++;
    if(address>=GIC&&address<GIC+0x1000){
        if(address>=GIC+0x80&&address<GIC+0x100)return UINT32_MAX;
        return gic_model[(address-GIC)/4];
    }
    if(address==PM+0x1c)return 0x20;
    if(address==PM+0x24)return countdown();
    assert(address==RESET||address==RESCAL||address==RESCAL+8);return 0;
}
#include "pexpert/arm/rpi5_pcie_watchdog_owner.inc"
#include "pexpert/arm/rpi5_pcie_irq_owner.inc"
#include "pexpert/arm/rpi5_pcie_fw_owner.inc"
extern "C" void rpi5_pcie_fw_smccc(uint64_t fid,uint64_t token,uint64_t out[4])
{
    smc_calls++;model_secure_call(fid,token,out);
    if(smc_calls==corrupt_smc)out[corrupt_field]=corrupt_raw;
    if(corrupt_irq_after_smc)gic_model[0x114/4]|=1;
}
static void fresh_owner_composition()
{
    model_ticks=100;arm_ticks=0;model_frequency=1000000;
    pm_writes=ns_reads=secure_reads=smc_calls=0;
    corrupt_smc=corrupt_field=corrupt_pm_at=0;corrupt_raw=0;
    corrupt_irq_after_smc=false;
    rpi5_pcie_wdog_gate={};rpi5_pcie_wdog_lease={};
    rpi5_pcie_irq_gate={};rpi5_pcie_irq_session={};rpi5_pcie_irq_thread=nullptr;
    rpi5_pcie_irq_identity=nullptr;rpi5_pcie_irq_mapping=0;rpi5_pcie_irq_claiming=false;
    rpi5_pcie_fw_gate={};rpi5_pcie_fw_session={};rpi5_pcie_fw_thread=nullptr;rpi5_pcie_fw_identity=nullptr;
    model_secure_reset();
    memset(gic_model,0,sizeof(gic_model));gic_model[1]=0x469;
    for(unsigned i=0;i<3;i++)gic_model[(0x100+4*(i<2?i+5:8))/4]=UINT32_MAX;
}
