/* SPDX-License-Identifier: BSD-2-Clause */
/* Observation only: original same-boot FDT, no kernel/root/CPU_ON, mailbox
 * requests, allocation, framebuffer loads/stores, mapping or mirror enable.
 * UART normalization and ONE countdown write to an already active watchdog
 * are the only device writes. Reset destination remains physically unproven. */
#include "framebuffer_observation.h"
#include "uart.h"
#ifndef RPI5_FB_OBSERVE_TAG
#error "A distinct package tag is required"
#endif
#define UART UINT64_C(0x107d001000)
#define PM UINT64_C(0x107d200000)
#define UART_BUDGET 1000000u
#define OUTPUT_LIMIT 32768u
extern uint8_t __probe_start[],__probe_end[];
extern uint64_t rpi5_psci_query(uint64_t,uint64_t);
extern uint32_t rpi5_access_load32(uintptr_t);
static struct rpi5_fb_observation observation,scratch;
static struct rpi5_reservation_plan reservations;
static uintptr_t original_fdt;
static uint32_t original_size,bytes_written;
static uint64_t frequency,deadline;
static volatile uint32_t admitted,armed,stage;
static _Noreturn void park(void){__asm__ volatile("msr daifset,#15; dsb sy" ::: "memory");for(;;)__asm__ volatile("wfe");}
static uint64_t counter(void){uint64_t n;__asm__ volatile("isb; mrs %0,cntvct_el0":"=r"(n));return n;}
static int within(void){return !armed || counter()<deadline;}
static int byte(unsigned char c){
    if(bytes_written>=OUTPUT_LIMIT || !within())return 0;
    if(rpi5_uart_putc(UART,c,UART_BUDGET)!=RPI5_UART_OK)return 0;
    bytes_written++;return within();
}
static int text(const char *s){while(*s)if(!byte((unsigned char)*s++))return 0;return 1;}
static int hex(uint64_t v){static const char digits[]="0123456789ABCDEF";if(!text("0x"))return 0;
    for(int shift=60;shift>=0;shift-=4)if(!byte((unsigned char)digits[(v>>shift)&15]))return 0;return 1;}
static int arm(void){
    uint32_t route=rpi5_access_load32(PM+0x1c),prior=rpi5_access_load32(PM+0x24);
    uint64_t now=counter();
    if(route==UINT32_MAX || (route&0x30)!=0x20 || prior==UINT32_MAX || !(prior&0xfffff) ||
        now>UINT64_MAX-frequency*8)return -1;
    deadline=now+frequency*8;armed=1;
    /* No reset-route/RSTS writes, no start of a stopped watchdog and no later
     * reload. Same supported PM binding as accepted standalone diagnostics. */
    *(volatile uint32_t *)(PM+0x24)=UINT32_C(0x5a0f0000);__asm__ volatile("dsb sy" ::: "memory");
    uint32_t left=rpi5_access_load32(PM+0x24);
    if(left==UINT32_MAX || (left&0xfffff)<(14u<<16) || (left&0xfffff)>(15u<<16))return -1;
    return !(text("RPI5XNU:FBOBS:ARMED WATCHDOG=15 SOFTWARE=8 NO_RELOAD\r\n") && within());
}
/* The early UART is the accepted firmware-preserved console path. These
 * records precede validation, not grant MMIO/FDT or framebuffer authority. */
static void check(uint32_t number){
    stage=number;
    if(!(text("RPI5XNU:FBOBS:CHECK STAGE=") && hex(number) && text("\r\n")))park();
}
static _Noreturn void reject(int rc){
    (void)(text("RPI5XNU:FBOBS:REJECT STAGE=") && hex(stage) && text(" RC=") &&
        hex((uint64_t)(int64_t)rc) && text(" NO_RELOAD OBSERVATION_INCOMPLETE\r\n"));
    (void)rpi5_uart_drain(UART,UART_BUDGET);park();
}
void probe_main(uintptr_t fdt_pa){
    uint64_t el,sctlr,daif,mpidr;
    __asm__ volatile("mrs %0,CurrentEL":"=r"(el));__asm__ volatile("mrs %0,sctlr_el2":"=r"(sctlr));
    __asm__ volatile("mrs %0,daif":"=r"(daif));__asm__ volatile("mrs %0,mpidr_el1":"=r"(mpidr));
    __asm__ volatile("mrs %0,cntfrq_el0":"=r"(frequency));
    if(el!=8 || (sctlr&UINT64_C(0x02001005)) || (daif&0x3c0)!=0x3c0 || frequency<1000000 || frequency>1000000000)park();
    struct rpi5_uart_snapshot uart;
    if(rpi5_uart_snapshot(UART,&uart)!=RPI5_UART_OK)park();
    if(!text("RPI5XNU:FBOBS:ENTRY TAG=" RPI5_FB_OBSERVE_TAG " EL2 PRECHECK NO_XNU NO_CPU_ON ZERO_SERIAL_INPUT\r\n") ||
        !text("RPI5XNU:FBOBS:UART CR=") || !hex(uart.control) || !text(" FR=") || !hex(uart.flags) ||
        !text(" IBRD=") || !hex(uart.integer_divisor) || !text(" FBRD=") || !hex(uart.fractional_divisor) ||
        !text(" LCRH=") || !hex(uart.line_control) || !text(" FIRMWARE_PRESERVED_CLOCK_UNVERIFIED\r\n"))park();
    const uint8_t *fdt=(const uint8_t *)fdt_pa;
    uint32_t size=((uint32_t)fdt[4]<<24)|((uint32_t)fdt[5]<<16)|((uint32_t)fdt[6]<<8)|fdt[7];
    struct rpi5_fdt_cpus cpus;struct rpi5_fdt_memory memory;struct rpi5_range watchdog,ram[8];
    struct rpi5_uart_clocks clocks;struct rpi5_range live[]={{(uintptr_t)__probe_start,(uintptr_t)__probe_end},{fdt_pa,fdt_pa+size}};
    check(1);if(size>1048576 || rpi5_fdt_structure(fdt,size))reject(-1);
    check(2);if(rpi5_fdt_phandles(fdt,size))reject(-1);
    check(3);if(rpi5_fdt_probe_mmio(fdt,size))reject(-1);
    check(4);if(rpi5_fdt_uart_clocks(fdt,size,&clocks))reject(-1);
    check(5);if(rpi5_fdt_watchdog(fdt,size,&watchdog) || watchdog.start!=PM)reject(-1);
    check(6);if(rpi5_fdt_cpus(fdt,size,&cpus) || cpus.count!=4 || cpus.enabled_mask!=15)reject(-1);
    check(7);if(rpi5_fdt_psci_smc(fdt,size))reject(-1);
    check(8);if(rpi5_fdt_memory(fdt,size,&memory))reject(-1);
    check(9);if(rpi5_fdt_reservation_plan(fdt,size,&reservations))reject(-1);
    for(unsigned i=0;i<memory.count;i++)ram[i]=(struct rpi5_range){memory.start[i],memory.end[i]};
    check(10);if(rpi5_ranges_validate_live(ram,memory.count,live,2))reject(-1);
    check(11);
    for(size_t i=0;i<reservations.fixed.count;i++)for(unsigned j=0;j<2;j++)
        if(live[j].start<reservations.fixed.extent[i].end && reservations.fixed.extent[i].start<live[j].end)reject(-1);
    check(12);if((mpidr&UINT64_C(0xff00ffffff))!=cpus.affinity[0])reject(-1);
    check(13);if(rpi5_psci_query(0x8400000a,0xc4000004)!=0)reject(-1);
    for(unsigned i=1;i<4;i++){check(13+i);if(rpi5_psci_query(0xc4000004,cpus.affinity[i])!=1)reject(-1);}
    check(17);if(rpi5_uart_set_exact(UART,clocks.uart_hz,115200,UART_BUDGET)!=RPI5_UART_OK)reject(-1);
    original_fdt=fdt_pa;original_size=size;admitted=1;
}
void probe_el1_main(uintptr_t fdt_pa){
    uint64_t el,sctlr,daif;
    __asm__ volatile("mrs %0,CurrentEL":"=r"(el));__asm__ volatile("mrs %0,sctlr_el1":"=r"(sctlr));
    __asm__ volatile("mrs %0,daif":"=r"(daif));
    check(18);if(!admitted || fdt_pa!=original_fdt || el!=4 || (sctlr&UINT64_C(0x02001005)) || (daif&0x3c0)!=0x3c0)reject(-1);
    check(19);if(arm())reject(-1);
    stage=20;
    if(!text("RPI5XNU:FBOBS:EL1 SCTLR=") || !hex(sctlr) || !text(" DAIF=") || !hex(daif) ||
        !text(" CPU_MMU_CACHE_OFF SCANOUT_CACHE_CONTRACT_UNKNOWN\r\n") ||
        !text("RPI5XNU:FBOBS:LIVE LOADER_START=") || !hex((uintptr_t)__probe_start) ||
        !text(" LOADER_END=") || !hex((uintptr_t)__probe_end) || !text(" FDT_START=") || !hex(fdt_pa) ||
        !text(" FDT_BYTES=") || !hex(original_size) || !text(" TF_A_POLICY_EXCLUSION_END=0x0000000000080000\r\n"))park();
    struct rpi5_range live[]={{0,0x80000},{(uintptr_t)__probe_start,(uintptr_t)__probe_end},{fdt_pa,fdt_pa+original_size}};
    int rc=rpi5_fb_observe_with_scratch((const void *)fdt_pa,original_size,live,3,&observation,&scratch);stage=21;
    if(!within())park();
    if(!rc)rc=rpi5_fb_observation_log(&observation,text,hex);
    stage=22;
    if(!text("RPI5XNU:FBOBS:RESULT TAG=" RPI5_FB_OBSERVE_TAG " RC=") || !hex((uint64_t)(int64_t)rc) ||
        !text(" FRAMEBUFFER_ACCESSES=0 MAILBOX_REQUESTS=0 DRAW=0 MIRROR=0\r\n") ||
        !text("RPI5XNU:FBOBS:STOP TAG=" RPI5_FB_OBSERVE_TAG " NO_RELOAD DESTINATION_UNPROVEN\r\n"))park();
    (void)rpi5_uart_drain(UART,UART_BUDGET);park();
}
void probe_exception(uint64_t vector,uint64_t esr,uint64_t elr,uint64_t far,uint64_t spsr,uint64_t el){
    (void)(text("RPI5XNU:FBOBS:FAULT STAGE=") && hex(stage) && text(" VECTOR=") && hex(vector) &&
        text(" EL=") && hex(el) && text(" ESR=") && hex(esr) && text(" ELR=") && hex(elr) &&
        text(" FAR=") && hex(far) && text(" SPSR=") && hex(spsr) && text(" FATAL_NO_RELOAD\r\n"));park();
}
void probe_secondary_main(uint64_t slot){(void)slot;park();}
