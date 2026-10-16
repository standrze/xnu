/* SPDX-License-Identifier: BSD-2-Clause */
/* Included only in a distinct pe_fiq copy, after the actual watchdog owner. */
#if !defined(ARM64_BOARD_CONFIG_BCM2712) || !DEVELOPMENT || !RPI5_PCI_WDOG_LEASE || !RPI5_PCIE_IRQ_MASK
#error "PCIe IRQ mask owner requires the opt-in BCM2712 DEVELOPMENT watchdog build"
#endif
#include <kern/thread.h>
#include <pexpert/arm/rpi5_pcie_irq_api.h>

static struct rpi5_pcie_watchdog_gate rpi5_pcie_irq_gate;
static struct rpi5_pcie_irq_mask rpi5_pcie_irq_session;
static thread_t rpi5_pcie_irq_thread;
static vm_offset_t rpi5_pcie_irq_mapping;
static const void *rpi5_pcie_irq_identity;
static bool rpi5_pcie_irq_claiming;

static int rpi5_pcie_irq_owner(void *context)
{
    return context != &rpi5_pcie_irq_gate || !rpi5_pcie_irq_identity ||
        ml_at_interrupt_context() || current_thread() != rpi5_pcie_irq_thread ||
        !rpi5_pcie_irq_mapping || rpi5_gicd_base != rpi5_pcie_irq_mapping ||
        __atomic_load_n(&rpi5_pcie_irq_gate.owner, __ATOMIC_ACQUIRE) != rpi5_pcie_irq_identity ||
        (rpi5_pcie_irq_claiming && (__builtin_arm_rsr64("DAIF") & 0xc0) != 0xc0) ? -1 : 0;
}
static bool rpi5_pcie_irq_read_allowed(uint32_t offset)
{
    if (offset == 4) return true;
    for (unsigned i = 0; i < 3; i++) {
        unsigned bank = i < 2 ? i+5 : 8;
        if (offset == 0x100+4*bank || offset == 0x200+4*bank || offset == 0x300+4*bank) return true;
    }
    return false;
}
static int rpi5_pcie_irq_read(void *owner, uint32_t offset, uint32_t *out)
{
    if (!out || rpi5_pcie_irq_owner(owner) || !rpi5_pcie_irq_read_allowed(offset)) return -1;
    __builtin_arm_dsb(DSB_SY);
    uint32_t value = rpi5_mmio_read32(rpi5_pcie_irq_mapping, offset);
    __builtin_arm_dsb(DSB_SY);
    if (rpi5_pcie_irq_owner(owner)) return -1;
    *out = value;
    return 0; /* A CPU abort/hang never returns an invented error. */
}
static int rpi5_pcie_irq_write(void *owner, uint32_t offset, uint32_t value)
{
    if (!rpi5_pcie_irq_claiming || rpi5_pcie_irq_owner(owner) ||
        !((offset == 0x194 || offset == 0x198) ? value == UINT32_MAX :
          offset == 0x1a0 && value == UINT32_C(0x7e0))) return -1;
    __builtin_arm_dsb(DSB_SY);
    rpi5_mmio_write32(rpi5_pcie_irq_mapping, offset, value);
    __builtin_arm_dsb(DSB_SY);
    return rpi5_pcie_irq_owner(owner);
}
static int rpi5_pcie_irq_order(void *owner)
{
    if (rpi5_pcie_irq_owner(owner)) return -1;
    __builtin_arm_dsb(DSB_SY);
    return rpi5_pcie_irq_owner(owner);
}

bool pe_rpi5_pcie_irq_claim(const void *owner, const struct rpi5_pcie_fdt *binding,
    struct rpi5_pcie_irq_observation *out)
{
    if (!owner || !binding || !out || ml_at_interrupt_context() || !current_thread() || !rpi5_gicd_base ||
        (__builtin_arm_rsr64("DAIF") & 0xc0) != 0xc0 || !pe_rpi5_watchdog_check_pcie(owner) ||
        !rpi5_pcie_watchdog_gate_claim(&rpi5_pcie_irq_gate, owner)) return false;
    rpi5_pcie_irq_thread = current_thread(); rpi5_pcie_irq_mapping = rpi5_gicd_base;
    /* One retained reference until reset, including failed claims. A departed
     * thread's recycled address must not authorize a later unrelated caller. */
    thread_reference(rpi5_pcie_irq_thread);
    rpi5_pcie_irq_identity = owner;
    rpi5_pcie_irq_claiming = true;
    const struct rpi5_pcie_irq_io io = {&rpi5_pcie_irq_gate, RPI5_GICD_PHYS, RPI5_GICD_SIZE,
        rpi5_pcie_irq_owner, rpi5_pcie_irq_read, rpi5_pcie_irq_write, rpi5_pcie_irq_order};
    struct rpi5_pcie_irq_observation result;
    bool ok = rpi5_pcie_irq_init(&rpi5_pcie_irq_session, binding, &io) == 0 &&
        rpi5_pcie_irq_begin(&rpi5_pcie_irq_session, &result) == 0 && pe_rpi5_watchdog_check_pcie(owner);
    rpi5_pcie_irq_claiming = false;
    if (ok) *out = result;
    else rpi5_pcie_irq_session.state = RPI5_PCIE_IRQ_QUARANTINED;
    rpi5_pcie_watchdog_gate_leave(&rpi5_pcie_irq_gate);
    return ok;
}
bool pe_rpi5_pcie_irq_check(const void *owner, struct rpi5_pcie_irq_observation *out)
{
    if (!owner || !out || ml_at_interrupt_context() ||
        !rpi5_pcie_watchdog_gate_owner(&rpi5_pcie_irq_gate, owner)) return false;
    bool ok = false;
    if (current_thread() == rpi5_pcie_irq_thread) {
        struct rpi5_pcie_irq_observation result;
        ok = pe_rpi5_watchdog_check_pcie(owner) &&
            rpi5_pcie_irq_check(&rpi5_pcie_irq_session, &result) == 0 && pe_rpi5_watchdog_check_pcie(owner);
        if (ok) *out = result;
        else rpi5_pcie_irq_session.state = RPI5_PCIE_IRQ_QUARANTINED;
    }
    rpi5_pcie_watchdog_gate_leave(&rpi5_pcie_irq_gate);
    return ok;
}
