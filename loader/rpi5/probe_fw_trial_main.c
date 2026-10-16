/* SPDX-License-Identifier: BSD-2-Clause */
/* Separate primary-only BL33, real firmware ABI trial, no XNU transfer.
 * Firmware supplies readable FDT/loading; unchanged entry validates placement.
 * Only one watchdog and selective GIC-disable writes. No PCIe/reset/DMA writes. */
#include "fdt.h"
#include "uart.h"
#include "pcie_fw_trial.h"
#ifndef RPI5_FW_TRIAL_TAG
#error "Image-bound recorder tag required"
#endif
#define UART UINT64_C(0x107d001000)
#define PM UINT64_C(0x107d200000)
#define UART_BUDGET 1000000u
extern uint8_t __probe_start[],__probe_end[];
extern uint64_t rpi5_psci_query(uint64_t,uint64_t);
static struct rpi5_reservation_plan reservations;
static struct rpi5_pcie_fdt binding;
static uintptr_t original_fdt;
static uint32_t admitted;
static uint64_t frequency,primary;
static _Noreturn void park(void)
{
    __asm__ volatile("msr daifset, #15; dsb sy" ::: "memory");
    for(;;)__asm__ volatile("wfe");
}
static __attribute__((noinline)) int text(const char *p)
{
    while(*p)if(rpi5_uart_putc(UART,(uint8_t)*p++,UART_BUDGET)!=RPI5_UART_OK)return 0;
    return 1;
}
static int hex(uint64_t value)
{
    static const char digits[]="0123456789ABCDEF";
    if(!text("0x"))return 0;
    for(int shift=60;shift>=0;shift-=4)
        if(rpi5_uart_putc(UART,(uint8_t)digits[(value>>shift)&15],UART_BUDGET)!=RPI5_UART_OK)return 0;
    return 1;
}
static int marker(const char *kind)
{
    return text("RPI5XNU:FWABI:") && text(kind) && text(" TAG=" RPI5_FW_TRIAL_TAG);
}
static int drain(void){return rpi5_uart_drain(UART,UART_BUDGET)==RPI5_UART_OK;}
#include "pcie_fw_trial.inc"
static int fw_trial_record(const struct rpi5_fw_trial_event *event)
{
    const char *names[]={"INVALID","ARMED","MASKED","RPC_BEGIN","RPC_END","CHECKED"};
    if(event->phase<1 || event->phase>5)return -1;
    return !(marker(names[event->phase]) && text(" FID=") && hex(event->fid) &&
        text(" TOKEN=") && hex(event->token) && text(" X0=") && hex(event->raw[0]) &&
        text(" X1=") && hex(event->raw[1]) && text(" X2=") && hex(event->raw[2]) &&
        text(" X3=") && hex(event->raw[3]) && text(" PM_WRITES=") && hex(event->pm_writes) &&
        text(" GIC_WRITES=") && hex(event->gic_writes) && text(" RPC_CALLS=") && hex(event->rpc_calls) &&
        text(" PM_CHECKS=") && hex(event->pm_checks) && text("\r\n") && drain());
}
void probe_main(uintptr_t fdt_pa)
{
    uint64_t el,sctlr,daif,mpidr;
    __asm__ volatile("mrs %0, CurrentEL":"=r"(el));
    __asm__ volatile("mrs %0, sctlr_el2":"=r"(sctlr));
    __asm__ volatile("mrs %0, daif":"=r"(daif));
    if(el!=8 || (sctlr&UINT64_C(0x02001005)) || (daif&0x3c0)!=0x3c0)park();
    const uint8_t *fdt=(const uint8_t *)fdt_pa;
    uint32_t size=((uint32_t)fdt[4]<<24)|((uint32_t)fdt[5]<<16)|((uint32_t)fdt[6]<<8)|fdt[7];
    struct rpi5_fdt_cpus cpus;
    struct rpi5_fdt_memory memory;
    struct rpi5_range watchdog;
    struct rpi5_uart_clocks clocks;
    struct rpi5_range ram[8],live[]={{(uintptr_t)__probe_start,(uintptr_t)__probe_end},{fdt_pa,fdt_pa+size}};
    __asm__ volatile("mrs %0, cntfrq_el0":"=r"(frequency));
    __asm__ volatile("mrs %0, mpidr_el1":"=r"(mpidr));
    if(frequency<1000000 || frequency>1000000000 ||
        rpi5_fdt_structure(fdt,size) || rpi5_fdt_phandles(fdt,size) ||
        rpi5_fdt_probe_mmio(fdt,size) || rpi5_fdt_uart_clocks(fdt,size,&clocks) ||
        rpi5_fdt_watchdog(fdt,size,&watchdog) || watchdog.start!=PM ||
        rpi5_fdt_cpus(fdt,size,&cpus) || cpus.count!=4 || cpus.enabled_mask!=15 ||
        rpi5_fdt_psci_smc(fdt,size) || rpi5_fdt_memory(fdt,size,&memory) ||
        rpi5_fdt_reservation_plan(fdt,size,&reservations) || rpi5_fdt_pcie_rp1(fdt,size,&binding))park();
    for(unsigned i=0;i<memory.count;i++)ram[i]=(struct rpi5_range){memory.start[i],memory.end[i]};
    if(rpi5_ranges_validate_live(ram,memory.count,live,2))park();
    for(size_t i=0;i<reservations.fixed.count;i++)for(unsigned j=0;j<2;j++)
        if(live[j].start<reservations.fixed.extent[i].end && reservations.fixed.extent[i].start<live[j].end)park();
    primary=cpus.affinity[0];
    if((mpidr&UINT64_C(0xff00ffffff))!=primary || rpi5_psci_query(0x8400000a,0xc4000004)!=0)park();
    for(unsigned i=1;i<4;i++)if(rpi5_psci_query(0xc4000004,cpus.affinity[i])!=1)park();
    if(rpi5_uart_set_exact(UART,clocks.uart_hz,115200,UART_BUDGET)!=RPI5_UART_OK ||
        !marker("ENTRY") || !text(" EL2 NO_XNU NO_CPU_ON CONTROLLER_WRITES=0 DMA=0\r\n") || !drain())park();
    original_fdt=fdt_pa;fw_trial.frequency=frequency;fw_trial.affinity=primary;admitted=1;
}
void probe_el1_main(uintptr_t fdt_pa)
{
    uint64_t el,sctlr,daif;
    __asm__ volatile("mrs %0, CurrentEL":"=r"(el));
    __asm__ volatile("mrs %0, sctlr_el1":"=r"(sctlr));
    __asm__ volatile("mrs %0, daif":"=r"(daif));
    if(!admitted || original_fdt!=fdt_pa || el!=4 ||
        (sctlr&UINT64_C(0x02001005)) || (daif&0x3c0)!=0x3c0)park();
    if(!marker("EL1") || !text(" MMU_CACHE_OFF DAIF_MASKED PRIMARY_ONLY FREQUENCY=") ||
        !hex(frequency) || !text("\r\n") || !drain())park();
    int rc=fw_trial_run(&binding);
    if(!marker("RESULT") || !text(" RC=") || !hex((uint64_t)(int64_t)rc) ||
        !text(" PHASE=") || !hex(fw_trial.phase) || !text(" PM_WRITES=") || !hex(fw_trial.pm_writes) ||
        !text(" GIC_WRITES=") || !hex(fw_trial.gic_writes) || !text(" RPC_CALLS=") || !hex(fw_trial.rpc_calls) ||
        !text(" SEQUENCE=") || !hex(fw_trial_result.sequence) || !text(" FACTS=") || !hex(fw_trial_result.facts) ||
        !text(" PM_CHECKS=") || !hex(fw_trial_pm.checks) || !text("\r\n") || !drain())park();
    (void)(marker("STOP") && text(" NO_RELOAD WAIT_FOR_RESET CONTROLLER_WRITES=0 DMA=0 RESET_RETURN_PROVEN=0\r\n") && drain());
    park();
}
void probe_exception(uint64_t vector,uint64_t esr,uint64_t elr,uint64_t far,uint64_t spsr,uint64_t el)
{
    (void)(marker("FAULT") && text(" VECTOR=") && hex(vector) && text(" EL=") && hex(el) &&
        text(" ESR=") && hex(esr) && text(" ELR=") && hex(elr) && text(" FAR=") && hex(far) &&
        text(" SPSR=") && hex(spsr) && text(" FATAL_NO_RELOAD\r\n") && drain());
    park();
}
void probe_secondary_main(uint64_t slot){(void)slot;park();}
