/* SPDX-License-Identifier: BSD-2-Clause
 * Exact new accessor bodies; only inherited owner/MMIO/counter/FDT context is
 * native RAM/spies. No original pe_serial/pe_fiq or device is substituted into
 * a target image. Production whole-owner compilation is separately required.
 */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "pexpert/pexpert/arm/pl011.h"
#include "loader/rpi5/pcie_watchdog_gate.h"
#include "loader/rpi5/fdt.h"
#define ARM64_BOARD_CONFIG_BCM2712 1
#define DEVELOPMENT 1
#define PL011_UART 1
#define RPI5_PCI_WDOG_LEASE 1
#define DSB_SY 0
#define RPI5_PM_RSTC 0x1c
#define RPI5_PM_WDOG 0x24
#define RPI5_PM_FULL_RESET 0x20U
#define RPI5_WDOG_INTERVAL (15U << 16)
static struct {void *next;} pl011_uart_serial_functions;
static void *gPESF;
static volatile pl011_registers_t regs,*pl011_registers;
static bool uart_initted,serial_do_transmit,uart_hibernation;
static uintptr_t rpi5_pm_base;
static struct rpi5_pcie_watchdog_gate rpi5_pcie_wdog_gate;
static uint64_t rpi5_wdog_deadline;
static bool rpi5_wdog_terminal_enabled;
static uint64_t ticks,step,frequency;
static unsigned counter_calls,barriers,mmios,mode,fdts;
static uint32_t count0,count1,route0,route1;
static int tree;
static uint64_t fake_counter(const char *name)
{
    if(!strcmp(name,"CNTFRQ_EL0"))return frequency;
    assert(!strcmp(name,"CNTVCT_EL0"));counter_calls++;
    if(mode==1 && counter_calls==2)return ticks-1;
    if(mode==2 && counter_calls==3)gPESF=0;
    if(mode==3 && counter_calls==3)pl011_registers=0;
    if(mode==4 && counter_calls==3)regs.uartcr.raw=0;
    if(mode==5 && counter_calls==3)regs.uartdmacr.raw=1;
    if(mode==6 && counter_calls==3)regs.uartfr.raw=0x88;
    if(mode==7 && counter_calls==5)ticks+=1000000;
    ticks+=step;return ticks;
}
static void fake_order(unsigned ignored){(void)ignored;barriers++;}
static uint32_t rpi5_mmio_read32(uintptr_t base,unsigned offset)
{
    assert(base==rpi5_pm_base && base==0x1234000);mmios++;
    if(mmios==1){assert(offset==RPI5_PM_RSTC);return route0;}
    if(mmios==2){assert(offset==RPI5_PM_WDOG);return count0;}
    if(mmios==3){assert(offset==RPI5_PM_WDOG);return count1;}
    assert(mmios==4 && offset==RPI5_PM_RSTC);return route1;
}
bool rpi5_firmware_fdt_view(const void **p,size_t *n)
{fdts++;if(mode==8)return false;*p=&tree;*n=64;return true;}
int rpi5_fdt_probe_mmio(const void *p,size_t n)
{assert(p==&tree && n==64);return mode==9?-1:0;}
int rpi5_fdt_uart_clocks(const void *p,size_t n,struct rpi5_uart_clocks *clocks)
{assert(p==&tree && n==64);clocks->uart_hz=mode==10?1:1843200;clocks->apb_hz=1;return mode==11?-1:0;}
#define __builtin_arm_rsr64 fake_counter
#define __builtin_arm_dsb fake_order
#include "pexpert/arm/rpi5_restart_diag_uart.inc"
#include "pexpert/arm/rpi5_restart_diag_pm.inc"
static void init(void)
{
    memset((void *)&regs,0,sizeof regs);regs.uartcr.raw=0x301;regs.uartlcr_h.raw=0x70;
    regs.uartibrd.raw=1;regs.uartfr.raw=0x80;regs.uartdr.raw=0xfeedbeef;
    pl011_registers=&regs;gPESF=&pl011_uart_serial_functions;pl011_uart_serial_functions.next=0;
    uart_initted=serial_do_transmit=true;uart_hibernation=false;
    rpi5_pm_base=0x1234000;memset(&rpi5_pcie_wdog_gate,0,sizeof rpi5_pcie_wdog_gate);
    rpi5_wdog_deadline=10000000;rpi5_wdog_terminal_enabled=true;
    ticks=1000;step=1;frequency=1000000;counter_calls=barriers=mmios=mode=fdts=0;
    count0=15U<<16;count1=count0-1;route0=route1=0x20;
}
static void bad_snapshot(void)
{
    struct rpi5_restart_diag_snapshot out;memset(&out,0xa5,sizeof out);
    unsigned char before[sizeof out];memcpy(before,&out,sizeof out);
    assert(rpi5_restart_diag_snapshot(&out)==-1 && !memcmp(before,&out,sizeof out));
}
int main(void)
{
    init();assert(rpi5_restart_diag_uart("abc",3)==0 && regs.uartdr.raw=='c' && barriers==1);
    char max[256];memset(max,'x',sizeof max);init();assert(!rpi5_restart_diag_uart(max,sizeof max));
    assert(counter_calls==259 && regs.uartdr.raw=='x');
    init();assert(rpi5_restart_diag_uart(0,1)==-1 && !counter_calls);
    assert(rpi5_restart_diag_uart("a",0)==-1 && rpi5_restart_diag_uart("a",257)==-1);
    init();assert(rpi5_restart_diag_uart((const char *)(UINTPTR_MAX-1),3)==-1);
    for(unsigned k=1;k<=11;k++){init();mode=k;int rc=rpi5_restart_diag_uart("abc",3);assert(rc==-1);}
    init();regs.uartfr.raw=0x20;step=0;assert(rpi5_restart_diag_uart("a",1)==-1 && counter_calls==1000001);
    init();regs.uartfr.raw=0x88;step=1000;assert(rpi5_restart_diag_uart("a",1)==-1);
    init();step=100000;assert(rpi5_restart_diag_uart("a",1)==-1 && regs.uartdr.raw==0xfeedbeef);
    init();uart_initted=false;assert(rpi5_restart_diag_uart("a",1)==-1);
    init();serial_do_transmit=false;assert(rpi5_restart_diag_uart("a",1)==-1);
    init();uart_hibernation=true;assert(rpi5_restart_diag_uart("a",1)==-1);
    init();pl011_uart_serial_functions.next=&tree;assert(rpi5_restart_diag_uart("a",1)==-1);
    init();regs.uartimsc.raw=1;assert(rpi5_restart_diag_uart("a",1)==-1);
    init();regs.uartfbrd.raw=64;assert(rpi5_restart_diag_uart("a",1)==-1);
    init();frequency=0;assert(rpi5_restart_diag_uart("a",1)==-1);
    init();ticks=UINT64_MAX-1;assert(rpi5_restart_diag_uart("a",1)==-1);
    struct rpi5_restart_diag_snapshot out;
    init();assert(!rpi5_restart_diag_snapshot(&out));
    assert(out.full_reset_route==1 && out.watchdog_count_before==count0 && out.watchdog_remaining_ticks==count1 &&
        out.cntfrq==1000000 && out.cntvct_before==1001 && out.cntvct==1002 && out.terminal_deadline==10000000 &&
        out.watchdog_nominal_hz==65536 && !out.watchdog_rate_bound_proven && mmios==4 && barriers==2 &&
        !rpi5_pcie_wdog_gate.busy && !rpi5_pcie_wdog_gate.owner);
    init();rpi5_pcie_wdog_gate.busy=1;bad_snapshot();assert(!mmios && rpi5_pcie_wdog_gate.busy==1);
    init();rpi5_pcie_wdog_gate.owner=&tree;bad_snapshot();assert(!mmios && !rpi5_pcie_wdog_gate.busy);
    init();rpi5_pm_base=0;bad_snapshot();assert(!mmios);
    init();rpi5_wdog_terminal_enabled=false;bad_snapshot();assert(!rpi5_pcie_wdog_gate.busy);
    init();rpi5_wdog_deadline=0;bad_snapshot();
    init();rpi5_wdog_deadline=1002;bad_snapshot();
    init();frequency=99;bad_snapshot();
    init();frequency=UINT64_MAX;bad_snapshot();
    init();mode=1;bad_snapshot();
    init();step=10000;bad_snapshot();
    init();route0=UINT32_MAX;bad_snapshot();
    init();route1=0x21;bad_snapshot();
    init();route0=route1=0;bad_snapshot();
    init();count0=UINT32_MAX;bad_snapshot();
    init();count1=UINT32_MAX;bad_snapshot();
    init();count0=(15U<<16)+1;bad_snapshot();
    init();count1=count0+1;bad_snapshot();
    init();count1=2U<<16;bad_snapshot();
    puts("RESTART_DIAG_ACCESS PASS ACTUAL_BODIES RAM_ONLY NO_PM_WRITES NO_CONSOLE_LOCKS RATE_BOUND_UNKNOWN");
    return 0;
}
