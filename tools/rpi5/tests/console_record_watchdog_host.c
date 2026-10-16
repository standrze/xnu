/* SPDX-License-Identifier: BSD-2-Clause; actual service body, explicit host PM/clock. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uintptr_t vm_offset_t;
#include "loader/rpi5/ramroot_confirmation.h"
#include "loader/rpi5/pcie_watchdog_gate.h"
#include "actual_watchdog_globals.inc"
static uint64_t fake_now,published;
static uint32_t fake_route;
static unsigned writes,barriers,notices,roots,restart_ready;
static bool thread_context,armed,call_present;
static struct rpi5_pcie_watchdog_gate rpi5_pcie_wdog_gate;
#define DSB_SY 0
#define __builtin_arm_rsr64(name) fake_now
#define __builtin_arm_dsb(scope) ((void)(scope),++barriers)
static bool rpi5_terminal_console_thread_owner(void){return thread_context&&armed&&call_present;}
static uint32_t rpi5_mmio_read32(vm_offset_t base,unsigned offset){assert(base==1&&offset==RPI5_PM_RSTC);return fake_route;}
static void rpi5_mmio_write32(vm_offset_t base,unsigned offset,uint32_t value){assert(thread_context&&armed&&call_present);assert(base==1&&offset==RPI5_PM_WDOG&&value==(RPI5_WDOG_PASSWORD|RPI5_WDOG_INTERVAL));writes++;}
bool mockfs_rpi5_root_snapshot(uint32_t *nodes,uint64_t *bytes){return rpi5_root_confirmation_snapshot(&published,nodes,bytes);}
static void kprintf(const char *fmt,...){assert(writes&&barriers==writes&&thread_context);if(strstr(fmt,":ROOT_READY "))roots++;if(strstr(fmt,":WATCHDOG_READY "))notices++;}
static void rpi5_restart_diagnostic_boot_ready(void){assert(thread_context&&writes);restart_ready++;}
#include "actual_watchdog_service.inc"
static void reset(void){
    rpi5_pm_base=1;rpi5_wdog_deadline=190;rpi5_wdog_last_counter=10;rpi5_wdog_reload_ticks=5;
    rpi5_wdog_reloads=0;rpi5_wdog_soak_seconds=0;rpi5_wdog_terminal_enabled=true;
    rpi5_wdog_terminal_reported=false;rpi5_wdog_terminal_report_after=15;rpi5_wdog_root_reports=0;
    fake_now=10;fake_route=RPI5_PM_FULL_RESET;published=0;writes=barriers=notices=roots=restart_ready=0;
    thread_context=armed=call_present=true;memset(&rpi5_pcie_wdog_gate,0,sizeof(rpi5_pcie_wdog_gate));
}
static void tick(uint64_t now){fake_now=now;pe_rpi5_watchdog_timer_tick(true);}
int main(void){
    reset();assert(rpi5_root_confirmation_publish(&published,33,2031616,true));
    tick(14);assert(!writes);thread_context=false;tick(15);assert(!writes&&!notices&&rpi5_wdog_deadline==190);
    thread_context=true;armed=false;tick(16);assert(!writes&&!notices&&rpi5_wdog_deadline==190);
    armed=true;call_present=false;tick(17);assert(!writes&&!notices&&rpi5_wdog_deadline==190);
    call_present=true;tick(18);assert(writes==1&&notices==1&&restart_ready==1&&roots==1);
    tick(22);assert(writes==1);tick(23);tick(28);tick(33);assert(writes==4&&roots==3&&notices==1&&restart_ready==1);
    tick(190);assert(writes==4&&rpi5_wdog_deadline==190);
    reset();fake_route=0;tick(15);assert(!writes&&!notices&&!rpi5_wdog_deadline);
    reset();rpi5_pcie_wdog_gate.busy=1;tick(15);assert(!writes&&!notices&&rpi5_wdog_deadline==190);
    reset();rpi5_pcie_wdog_gate.owner=&published;tick(15);assert(!writes&&!notices&&rpi5_wdog_deadline==190);
    puts("CONSOLE_WATCHDOG PASS ACTUAL_SERVICE_GATE IRQ_UNARMED_MISSING_OWNER_NO_FEED EPOCH_UNCHANGED MAX3 NO_HARDWARE");
}
