/* SPDX-License-Identifier: BSD-2-Clause */
/* Execute the production PE include with explicit register/thread doubles. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "pcie_watchdog_gate.h"
#define ARM64_BOARD_CONFIG_BCM2712 1
#define DEVELOPMENT 1
#define RPI5_PCI_WDOG_LEASE 1
#define RPI5_PCIE_IRQ_MASK 1
#define RPI5_GICD_PHYS UINT64_C(0x107fff9000)
#define RPI5_GICD_SIZE UINT64_C(0x1000)
#define DSB_SY 0
typedef uintptr_t vm_offset_t;
static uint64_t daif = 0xc0;
static int interrupt_context, watchdog_calls, fail_watchdog, reads, writes, barriers;
static int thread_references;
static int owner_id, other_id, thread_id, other_thread_id;
static void *thread = &thread_id;
static uint32_t registers[1024];
static vm_offset_t rpi5_gicd_base;
static bool ml_at_interrupt_context(void) { return interrupt_context != 0; }
void *current_thread(void) { return thread; }
void thread_reference(void *value) { assert(value == &thread_id); thread_references++; }
static uint64_t model_register(const char *name) { assert(!strcmp(name,"DAIF")); return daif; }
#define __builtin_arm_rsr64(name) model_register(name)
#define __builtin_arm_dsb(scope) ((void)(scope), (void)barriers++)
static uint32_t rpi5_mmio_read32(vm_offset_t base, unsigned offset)
{
    assert(base == (uintptr_t)registers && offset < sizeof(registers));
    reads++;
    return registers[offset/4];
}
static void rpi5_mmio_write32(vm_offset_t base, unsigned offset, uint32_t value)
{
    assert(base == (uintptr_t)registers);
    assert((offset == 0x194 || offset == 0x198) ? value == UINT32_MAX : offset == 0x1a0 && value == 0x7e0);
    writes++; registers[(offset-0x80)/4] &= ~value;
}
static bool pe_rpi5_watchdog_check_pcie(const void *owner)
{
    watchdog_calls++;
    return owner == &owner_id && watchdog_calls != fail_watchdog;
}
#include <pexpert/arm/rpi5_pcie_irq_owner.inc>

static struct rpi5_pcie_fdt binding(void)
{
    struct rpi5_pcie_fdt b = {0};
    b.bridge_regs = (struct rpi5_range){UINT64_C(0x1000120000),UINT64_C(0x1000129310)};
    b.bridge_reset_id = 44; b.gic_phandle = 1;
    b.bridge_intid[0] = 265; b.bridge_intid[1] = 266;
    b.mip_intid_base = 160; b.mip_intid_count = 64;
    for (unsigned i = 0; i < 4; i++) b.intx_intid[i] = 261+i;
    return b;
}
static void reset_model(void)
{
    /* Reset test doubles between independent boots; no production release. */
    memset(&rpi5_pcie_irq_gate,0,sizeof(rpi5_pcie_irq_gate));
    memset(&rpi5_pcie_irq_session,0,sizeof(rpi5_pcie_irq_session));
    memset(registers,0,sizeof(registers));
    rpi5_gicd_base = (uintptr_t)registers;
    registers[1] = 15; registers[0x114/4] = UINT32_MAX;
    registers[0x118/4] = UINT32_MAX; registers[0x120/4] = UINT32_MAX;
    registers[0x220/4] = UINT32_MAX; registers[0x320/4] = 0x7f800001;
    daif = 0xc0; thread = &thread_id; interrupt_context = 0;
    watchdog_calls = fail_watchdog = reads = writes = barriers = 0;
    thread_references = 0;
}
int main(void)
{
    struct rpi5_pcie_fdt b = binding();
    struct rpi5_pcie_irq_observation out, sentinel;
    memset(&sentinel,0xa5,sizeof(sentinel));
    reset_model(); daif = 0; out = sentinel;
    assert(!pe_rpi5_pcie_irq_claim(&owner_id,&b,&out) && !reads && !writes && !watchdog_calls);
    assert(!memcmp(&out,&sentinel,sizeof(out)));
    daif = 0xc0; thread = NULL;
    assert(!pe_rpi5_pcie_irq_claim(&owner_id,&b,&out) && !reads && !writes && !watchdog_calls);
    thread = &thread_id;
    daif = 0xc0;
    assert(!pe_rpi5_pcie_irq_claim(&other_id,&b,&out) && !reads && !writes);
    watchdog_calls = 0;
    assert(pe_rpi5_pcie_irq_claim(&owner_id,&b,&out));
    assert(watchdog_calls == 2 && reads == 29 && writes == 3 && barriers >= 64);
    assert(thread_references == 1);
    assert(rpi5_pcie_irq_thread == &thread_id && rpi5_pcie_irq_gate.owner == &owner_id);
    assert(registers[0x120/4] == (UINT32_MAX ^ UINT32_C(0x7e0)));
    unsigned read_before = (unsigned)reads, write_before = (unsigned)writes;
    out = sentinel;
    assert(!pe_rpi5_pcie_irq_claim(&owner_id,&b,&out));
    assert(reads == (int)read_before && writes == (int)write_before && !memcmp(&out,&sentinel,sizeof(out)));
    assert(!pe_rpi5_pcie_irq_check(&other_id,&out) && reads == (int)read_before);
    thread = &other_thread_id;
    assert(!pe_rpi5_pcie_irq_check(&owner_id,&out) && reads == (int)read_before);
    thread = &thread_id; daif = 0; watchdog_calls = 0;
    assert(pe_rpi5_pcie_irq_check(&owner_id,&out));
    assert(watchdog_calls == 2 && reads == (int)read_before+20 && writes == 3);
    uint32_t value;
    read_before = (unsigned)reads;
    assert(rpi5_pcie_irq_read(&owner_id,0x100,&value) == -1 && reads == (int)read_before);
    assert(rpi5_pcie_irq_write(&owner_id,0x1a0,0x7e0) == -1 && writes == 3);
    assert(rpi5_pcie_watchdog_gate_owner(&rpi5_pcie_irq_gate,&owner_id));
    assert(!pe_rpi5_pcie_irq_check(&owner_id,&out)); /* Nonblocking reentry. */
    rpi5_pcie_watchdog_gate_leave(&rpi5_pcie_irq_gate);
    reset_model(); fail_watchdog = 2; out = sentinel;
    assert(!pe_rpi5_pcie_irq_claim(&owner_id,&b,&out));
    assert(writes == 3 && rpi5_pcie_irq_session.state == RPI5_PCIE_IRQ_QUARANTINED);
    assert(!memcmp(&out,&sentinel,sizeof(out)));
    assert(!pe_rpi5_pcie_irq_check(&owner_id,&out) && writes == 3);
    reset_model(); assert(pe_rpi5_pcie_irq_claim(&owner_id,&b,&out));
    rpi5_gicd_base = 0; out = sentinel;
    assert(!pe_rpi5_pcie_irq_check(&owner_id,&out));
    assert(rpi5_pcie_irq_session.state == RPI5_PCIE_IRQ_QUARANTINED && writes == 3);
    assert(!memcmp(&out,&sentinel,sizeof(out)));
    puts("PCIE_IRQ_OWNER_HOST_PASS ACTUAL_PE_BODY=1 THREAD_WDOG_ATOMIC_OUTPUT=1 NO_MMIO=1");
    return 0;
}
