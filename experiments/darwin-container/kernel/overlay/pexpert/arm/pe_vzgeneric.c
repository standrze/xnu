/* SPDX-License-Identifier: APSL-2.0
 * Darwin container project addition, 2026-10-12.
 * Generic EFI VM: discovered GICv3, architectural virtual timer and PSCI HVC.
 */
#include <stdint.h>
#include <arm64/proc_reg.h>
#include <kern/debug.h>
#include <machine/machine_routines.h>
#include <machine/atomic.h>
#include <IOKit/IOPlatformExpert.h>
#include <pexpert/pexpert.h>
#include <pexpert/device_tree.h>
#include <pexpert/arm/protos.h>

static vm_offset_t gicd;
static vm_offset_t gicr;

static uint32_t
read32(vm_offset_t base, unsigned offset)
{
	return *(volatile uint32_t *)(base + offset);
}

static void
write32(vm_offset_t base, unsigned offset, uint32_t value)
{
	*(volatile uint32_t *)(base + offset) = value;
}

static void
wait_clear(vm_offset_t base, unsigned offset, uint32_t mask)
{
	uint64_t deadline = __builtin_arm_rsr64("CNTVCT_EL0") +
	    __builtin_arm_rsr64("CNTFRQ_EL0");
	while (read32(base, offset) & mask) {
		if (__builtin_arm_rsr64("CNTVCT_EL0") >= deadline) {
			panic("VZGENERIC: GIC register timeout offset 0x%x", offset);
		}
	}
}

void
pe_init_fiq(void)
{
	DTEntry node;
	const void *data;
	unsigned size;
	if (gicd) return;
	if (SecureDTLookupEntry(NULL, "/arm-io/interrupt-controller", &node) != kSuccess ||
	    SecureDTGetProperty(node, "reg", &data, &size) != kSuccess ||
	    size != 4 * sizeof(uint64_t)) {
		panic("VZGENERIC: missing GICv3 register contract");
	}
	/* This downstream property contains absolute, not bus-relative, PAs. */
	const uint64_t *reg = data;
	if (!reg[0] || reg[1] < 0x10000 || !reg[2] || reg[3] != 0x20000 ||
	    ((reg[0] | reg[2]) & 0x3fff) || reg[0] >= (1ULL << 36) ||
	    reg[2] >= (1ULL << 36)) {
		panic("VZGENERIC: invalid single-vCPU GICv3 regions");
	}
	gicd = ml_io_map(reg[0], reg[1]);
	gicr = ml_io_map(reg[2], reg[3]);
	if (!gicd || !gicr) panic("VZGENERIC: GIC mapping failed");
	/* Firmware no longer owns this VM. Disable delivery before changing
	 * affinity routing, and do not inherit enabled/pending/active SPIs. */
	uint32_t distributor_control = read32(gicd, 0) & ~3U;
	write32(gicd, 0, distributor_control);
	wait_clear(gicd, 0, 1U << 31);
	unsigned interrupt_banks = (read32(gicd, 4) & 31U) + 1;
	for (unsigned bank = 1; bank < interrupt_banks; bank++) {
		write32(gicd, 0x180 + 4 * bank, UINT32_MAX);
		write32(gicd, 0x280 + 4 * bank, UINT32_MAX);
		write32(gicd, 0x380 + 4 * bank, UINT32_MAX);
	}
	wait_clear(gicd, 0, 1U << 31);
	write32(gicd, 0, distributor_control | (1U << 4));
	wait_clear(gicd, 0, 1U << 31);
	uint64_t typer = *(volatile uint64_t *)(gicr + 0x8);
	uint64_t mpidr = __builtin_arm_rsr64("MPIDR_EL1");
	uint32_t affinity = (uint32_t)(mpidr & 0xffffff) |
	    (uint32_t)((mpidr >> 8) & 0xff000000);
	if ((uint32_t)(typer >> 32) != affinity) {
		panic("VZGENERIC: GIC redistributor does not match boot CPU");
	}
	write32(gicr, 0x14, read32(gicr, 0x14) & ~(1U << 1));
	wait_clear(gicr, 0x14, 1U << 2);
	/* Disable and clear every local interrupt before configuring SGI1/PPI27. */
	write32(gicr, 0x10180, UINT32_MAX);
	wait_clear(gicr, 0, 1U << 3);
	write32(gicr, 0x10280, UINT32_MAX);
	write32(gicr, 0x10380, UINT32_MAX);
	write32(gicr, 0x10080, UINT32_MAX); /* IGROUPR0: all Group 1 non-secure. */
	write32(gicr, 0x10d00, 0); /* IGRPMODR0. */
	for (unsigned offset = 0; offset < 32; offset += 4) {
		write32(gicr, 0x10400 + offset, 0x80808080);
	}
	/* Architectural virtual timer PPI27 is level-sensitive. */
	write32(gicr, 0x10c04, read32(gicr, 0x10c04) & ~(3U << 22));
	__builtin_arm_wsr64("ICC_SRE_EL1", __builtin_arm_rsr64("ICC_SRE_EL1") | 1);
	__builtin_arm_isb(ISB_SY);
	__builtin_arm_wsr64("ICC_CTLR_EL1", __builtin_arm_rsr64("ICC_CTLR_EL1") & ~2ULL);
	__builtin_arm_wsr64("ICC_PMR_EL1", 0xff);
	__builtin_arm_wsr64("ICC_BPR1_EL1", 0);
	/* Non-secure affinity-routed view: ARE_NS=bit4, EnableGrp1A=bit1.
	 * In a single-security-state GIC these bits are ARE and EnableGrp1. */
	write32(gicd, 0, read32(gicd, 0) | (1U << 4) | (1U << 1));
	wait_clear(gicd, 0, 1U << 31);
	write32(gicr, 0x10100, (1U << 27) | (1U << 1));
	__builtin_arm_wsr64("ICC_IGRPEN1_EL1", 1);
	__builtin_arm_isb(ISB_SY);
	kprintf("VZXNU:GIC:READY TIMER=27 SGI=1\n");
}

uint32_t
pe_vz_irq_acknowledge(void)
{
	return (uint32_t)__builtin_arm_rsr64("ICC_IAR1_EL1");
}

void
pe_vz_irq_complete(uint32_t iar)
{
	/* Context-synchronize a preceding CNTV_TVAL rearm before deactivation.
	 * DSB orders memory accesses, not timer system-register side effects. */
	__builtin_arm_isb(ISB_SY);
	__builtin_arm_dsb(DSB_SY);
	__builtin_arm_wsr64("ICC_EOIR1_EL1", iar);
	__builtin_arm_isb(ISB_SY);
}

void
pe_vz_send_self_sgi(void)
{
	uint64_t mpidr = __builtin_arm_rsr64("MPIDR_EL1");
	unsigned aff0 = mpidr & 0xff;
	if (aff0 >= 16) panic("VZGENERIC: unsupported SGI affinity");
	uint64_t value = ((mpidr & 0xff00000000ULL) << 16) |
	    ((mpidr & 0xff0000) << 16) | ((mpidr & 0xff00) << 8) |
	    (1ULL << 24) | (1ULL << aff0);
	__builtin_arm_dsb(DSB_ISH);
	__builtin_arm_wsr64("ICC_SGI1R_EL1", value);
	__builtin_arm_isb(ISB_SY);
}

int
pe_vz_halt_restart(unsigned int type)
{
	DTEntry chosen;
	const void *data;
	unsigned size;
	if (type == kPEPanicSync) return 0;
	if (type != kPEHaltCPU && type != kPEUPSDelayHaltCPU &&
	    type != kPERestartCPU && type != kPEPanicRestartCPU) return -1;
	if (SecureDTLookupEntry(NULL, "/chosen", &chosen) != kSuccess ||
	    SecureDTGetProperty(chosen, "vz-psci-hvc", &data, &size) != kSuccess ||
	    size != sizeof(uint32_t) || *(const uint32_t *)data != 1) {
		panic("VZGENERIC: PSCI HVC was not verified by firmware inventory");
	}
	register uint64_t x0 __asm__("x0") =
	    (type == kPERestartCPU || type == kPEPanicRestartCPU) ? 0x84000009 : 0x84000008;
	__asm__ volatile("dsb sy\n hvc #0" : "+r"(x0) : :
	    "x1", "x2", "x3", "x4", "x5", "x6", "x7", "x8", "x9",
	    "x10", "x11", "x12", "x13", "x14", "x15", "x16", "x17", "memory");
	panic("VZGENERIC: PSCI power operation returned 0x%llx", x0);
}
