/* SPDX-License-Identifier: BSD-2-Clause */
/* Distinct standalone diagnostic, not a replacement XNU boot main. No kernel,
 * root disk, endpoint config access, reset/calibration writes or DMA. Firmware
 * owns readable FDT/loading/primary entry; unchanged probe_entry.S enforces
 * linked placement and EL2 -> EL1 HCR.RW-only, M/C/I-off masked-DAIF entry.
 * Whole-image fatal/watchdog recovery and the next boot destination are NOT
 * physically proven by this source or a successful host build. */
#include "fdt.h"
#include "pcie_access.h"
#include "uart.h"

#define UART UINT64_C(0x107d001000)
#define PM UINT64_C(0x107d200000)
#define UART_BUDGET 1000000u
extern uint8_t __probe_start[], __probe_end[];
extern uint64_t rpi5_psci_query(uint64_t, uint64_t);
extern uint32_t rpi5_access_load32(uintptr_t);
extern uint16_t rpi5_access_load16(uintptr_t);
static struct rpi5_pcie_fdt binding;
static struct rpi5_pcie_access session;
static struct rpi5_pcie_access_observation observed;
static struct rpi5_reservation_plan reservations;
static uint64_t frequency;
static uintptr_t original_fdt;
static volatile uint32_t admitted, stage;
static uint32_t guard_first_ticks, guard_last_ticks, guard_samples;

static _Noreturn void park(void)
{
    __asm__ volatile("msr daifset, #15; dsb sy" ::: "memory");
    for (;;) __asm__ volatile("wfe");
}
static int text(const char *p)
{
    while (*p) if (rpi5_uart_putc(UART,(uint8_t)*p++,UART_BUDGET) != RPI5_UART_OK) return 0;
    return 1;
}
static int hex(uint64_t value)
{
    static const char digits[] = "0123456789ABCDEF";
    if (!text("0x")) return 0;
    for (int shift = 60; shift >= 0; shift -= 4)
        if (rpi5_uart_putc(UART,(uint8_t)digits[(value >> shift)&15],UART_BUDGET) != RPI5_UART_OK) return 0;
    return 1;
}
static uint64_t counter(void)
{
    uint64_t ticks;
    __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(ticks));
    return ticks;
}
static int now_us(void *context, uint64_t *value)
{
    (void)context;
    uint64_t ticks = counter(), seconds = ticks/frequency;
    if (seconds > (UINT64_MAX-UINT64_C(999999))/1000000) return -1;
    *value = seconds*1000000 + (ticks%frequency)*1000000/frequency;
    return 0;
}
static int guard(void *context)
{
    (void)context;
    stage = 0; /* A PM/UART fault is not a failed PCIe-table load. */
    uint32_t route = rpi5_access_load32(PM+0x1c);
    if (route == UINT32_MAX || (route&0x30) != 0x20) return -1;
    uint32_t left = rpi5_access_load32(PM+0x24);
    uint32_t ticks = left&0xfffff;
    if (left == UINT32_MAX || ticks <= (8u<<16) || ticks > guard_last_ticks ||
        (guard_samples && ticks >= guard_first_ticks)) return -1;
    guard_last_ticks = ticks;
    guard_samples++;
    return 0;
}
static int arm(void *context)
{
    (void)context;
    uint32_t route = rpi5_access_load32(PM+0x1c);
    if (route == UINT32_MAX || (route&0x30) != 0x20) return -1;
    uint32_t prior = rpi5_access_load32(PM+0x24);
    if (prior == UINT32_MAX || !(prior&0xfffff)) return -1;
    /* Only watchdog countdown is written, exactly once. Never change reset
     * routing/RSTS, enable a stopped watchdog, or reload after this callback. */
    *(volatile uint32_t *)(PM+0x24) = UINT32_C(0x5a0f0000);
    __asm__ volatile("dsb sy" ::: "memory");
    uint32_t left = rpi5_access_load32(PM+0x24);
    if (left == UINT32_MAX || (left&0xfffff) < (14u<<16) || (left&0xfffff) > (15u<<16)) return -1;
    guard_first_ticks = guard_last_ticks = left&0xfffff;
    if (guard(0) || !text("RPI5XNU:ACCESS:ARMED WATCHDOG_15S NO_RELOAD FATAL_ONLY\r\n") ||
        rpi5_uart_drain(UART,UART_BUDGET) != RPI5_UART_OK) return -1;
    return 0;
}
static int before(void *context, unsigned pass, unsigned index, uint64_t address, unsigned width)
{
    (void)context;
    stage = 1+pass*RPI5_PCIE_ACCESS_REGISTERS+index;
    return !text("RPI5XNU:ACCESS:READ_BEGIN PASS=") || !hex(pass) || !text(" INDEX=") ||
        !hex(index) || !text(" PA=") || !hex(address) || !text(" WIDTH=") || !hex(width) ||
        !text("\r\n") || rpi5_uart_drain(UART,UART_BUDGET) != RPI5_UART_OK ? -1 : 0;
}
static int load(void *context, uint64_t address, unsigned width, uint32_t *value)
{
    (void)context;
    /* Reject anything outside the private initialized allowlist even if a
     * future caller attempts to use this as a general physical read primitive. */
    unsigned i;
    for (i = 0; i < RPI5_PCIE_ACCESS_REGISTERS; i++)
        if (session.registers[i].address == address && session.registers[i].width == width) break;
    if (i == RPI5_PCIE_ACCESS_REGISTERS) return -1;
    *value = width == 2 ? rpi5_access_load16(address) : rpi5_access_load32(address);
    return 0; /* A CPU abort/hang never returns an invented error/success here. */
}
static int after(void *context, unsigned pass, unsigned index, uint32_t value)
{
    (void)context;
    stage = 0;
    return !text("RPI5XNU:ACCESS:READ_END PASS=") || !hex(pass) || !text(" INDEX=") ||
        !hex(index) || !text(" VALUE=") || !hex(value) || !text("\r\n") ? -1 : 0;
}

void probe_main(uintptr_t fdt_pa)
{
    uint64_t el, sctlr, daif;
    __asm__ volatile("mrs %0, CurrentEL" : "=r"(el));
    __asm__ volatile("mrs %0, sctlr_el2" : "=r"(sctlr));
    __asm__ volatile("mrs %0, daif" : "=r"(daif));
    if (el != 8 || (sctlr&UINT64_C(0x02001005)) || (daif&0x3c0) != 0x3c0) park();
    /* _start already bounds this trusted readable header/window against the
     * entire live loader image. Decoder checks do not discover readability. */
    const uint8_t *fdt = (const uint8_t *)fdt_pa;
    uint32_t size = ((uint32_t)fdt[4]<<24) | ((uint32_t)fdt[5]<<16) | ((uint32_t)fdt[6]<<8) | fdt[7];
    struct rpi5_fdt_cpus cpus;
    struct rpi5_fdt_memory memory;
    struct rpi5_range watchdog;
    struct rpi5_uart_clocks clocks;
    struct rpi5_range ram[8], live[] = {{(uintptr_t)__probe_start,(uintptr_t)__probe_end},
        {fdt_pa,fdt_pa+size}};
    uint64_t mpidr;
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(frequency));
    __asm__ volatile("mrs %0, mpidr_el1" : "=r"(mpidr));
    if (frequency < 1000000 || frequency > 1000000000 ||
        rpi5_fdt_structure(fdt,size) || rpi5_fdt_phandles(fdt,size) ||
        rpi5_fdt_probe_mmio(fdt,size) || rpi5_fdt_uart_clocks(fdt,size,&clocks) ||
        rpi5_fdt_watchdog(fdt,size,&watchdog) || watchdog.start != PM ||
        rpi5_fdt_cpus(fdt,size,&cpus) || cpus.count != 4 || cpus.enabled_mask != 15 ||
        rpi5_fdt_psci_smc(fdt,size) || rpi5_fdt_memory(fdt,size,&memory) ||
        rpi5_fdt_reservation_plan(fdt,size,&reservations) || rpi5_fdt_pcie_rp1(fdt,size,&binding)) park();
    for (unsigned i = 0; i < memory.count; i++) ram[i] = (struct rpi5_range){memory.start[i],memory.end[i]};
    if (rpi5_ranges_validate_live(ram,memory.count,live,2)) park();
    for (size_t i = 0; i < reservations.fixed.count; i++) for (unsigned j = 0; j < 2; j++)
        if (live[j].start < reservations.fixed.extent[i].end &&
            reservations.fixed.extent[i].start < live[j].end) park();
    /* No allocator/kernel/dynamic pool is started in this standalone image.
     * Fixed firmware reservations and both live extents stay protected. */
    if ((mpidr&UINT64_C(0xff00ffffff)) != cpus.affinity[0] ||
        rpi5_psci_query(0x8400000a,0xc4000004) != 0) park();
    for (unsigned i = 1; i < 4; i++) if (rpi5_psci_query(0xc4000004,cpus.affinity[i]) != 1) park();
    if (rpi5_uart_set_exact(UART,clocks.uart_hz,115200,UART_BUDGET) != RPI5_UART_OK ||
        !text("RPI5XNU:ACCESS:ENTRY EL2 READONLY_CANDIDATE NO_XNU NO_CPU_ON\r\n")) park();
    const struct rpi5_pcie_access_io io = {0,arm,guard,now_us,before,load,after};
    if (rpi5_pcie_access_init(&session,&binding,&io)) park();
    original_fdt = fdt_pa;
    admitted = 1;
}

void probe_el1_main(uintptr_t fdt_pa)
{
    uint64_t el, sctlr, daif;
    __asm__ volatile("mrs %0, CurrentEL" : "=r"(el));
    __asm__ volatile("mrs %0, sctlr_el1" : "=r"(sctlr));
    __asm__ volatile("mrs %0, daif" : "=r"(daif));
    if (!admitted || original_fdt != fdt_pa || el != 4 ||
        (sctlr&UINT64_C(0x02001005)) || (daif&0x3c0) != 0x3c0) park();
    /* Unchanged entry code set HCR_EL2 to RW only: no VM, DC, VHE or IRQ
     * routing. Never try to read privileged HCR_EL2 from EL1 to "verify" it. */
    if (!text("RPI5XNU:ACCESS:EL1 MMU_CACHE_OFF DAIF_MASKED PRIMARY_ONLY\r\n")) park();
    int rc = rpi5_pcie_access_capture(&session,&observed);
    stage = 0;
    if (!text("RPI5XNU:ACCESS:RESULT RC=") || !hex((uint64_t)(int64_t)rc) ||
        !text(" CALLBACKS=") || !hex(session.completed_callbacks) || !text("\r\n")) park();
    if (!rc) {
        (void)(text("RPI5XNU:ACCESS:OBSERVED READS=30 PCIE_WRITES=0 CONFIG_ACCESS=0 DMA=0 NIC_READY=0 ELAPSED_US=") &&
            hex(observed.elapsed_us) && text("\r\n"));
    }
    (void)text("RPI5XNU:ACCESS:STOP NO_RELOAD WAIT_FOR_RESET DESTINATION_UNPROVEN\r\n");
    (void)rpi5_uart_drain(UART,UART_BUDGET);
    park();
}

void probe_exception(uint64_t vector, uint64_t esr, uint64_t elr,
    uint64_t far, uint64_t spsr, uint64_t el)
{
    /* Fatal handler from unchanged entry vectors; no fixup/eret or watchdog
     * reload. If even UART reporting fails, autonomous reset remains intended. */
    (void)(text("RPI5XNU:ACCESS:FAULT STAGE=") && hex(stage) && text(" VECTOR=") && hex(vector) &&
        text(" EL=") && hex(el) && text(" ESR=") && hex(esr) && text(" ELR=") && hex(elr) &&
        text(" FAR=") && hex(far) && text(" SPSR=") && hex(spsr) && text(" FATAL_NO_RELOAD\r\n"));
    park();
}
void probe_secondary_main(uint64_t slot) { (void)slot; park(); }
