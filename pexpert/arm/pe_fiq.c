/*
 * Copyright (c) 2021 Apple Inc. All rights reserved.
 */

#include <stdint.h>
#include <arm64/proc_reg.h>
#include <kern/clock.h>
#include <kern/debug.h>
#include <mach/mach_time.h>
#include <machine/atomic.h>
#include <machine/machine_routines.h>
#include <pexpert/device_tree.h>
#include <pexpert/arm64/board_config.h>


#if HAS_GIC_V3
#define GICR_WAKE_TIMEOUT_NS (1000000000ULL) // timeout for redistributor wakeup (default 1s)
MACHINE_TIMEOUT(gicr_wake_timeout_ns, "gicr-wake-timeout", GICR_WAKE_TIMEOUT_NS, MACHINE_TIMEOUT_UNIT_NSEC, NULL);

static vm_offset_t gicd_base;
static vm_offset_t gicr_base;
static vm_offset_t gicr_size;

static uint32_t
_gic_read32(vm_offset_t addr)
{
	return *((volatile uint32_t *) addr);
}

static uint64_t
_gic_read64(vm_offset_t addr)
{
	return *((volatile uint64_t *) addr);
}

static void
_gic_write32(vm_offset_t addr, uint32_t value)
{
	*((volatile uint32_t *) addr) = value;
}

#define gicd_read32(offset) (_gic_read32(gicd_base + (offset)))
#define gicd_write32(offset, data) (_gic_write32(gicd_base + (offset), (data)))
#define gicr_read32(offset) (_gic_read32(gicr_pe_base + (offset)))
#define gicr_write32(offset, data) (_gic_write32(gicr_pe_base + (offset), (data)))
#define gicr_read64(offset) (_gic_read64(gicr_pe_base + (offset)))

static vm_offset_t
find_gicr_pe_base()
{
	// We only care about aff1 and aff0
	uint32_t phys_id = __builtin_arm_rsr64("MPIDR_EL1") & (MPIDR_AFF1_MASK | MPIDR_AFF0_MASK);

	for (vm_offset_t offset = 0; offset < gicr_size; offset += GICR_PE_SIZE) {
		vm_offset_t gicr_pe_base = gicr_base + offset;
		uint64_t gicr_typer = gicr_read64(GICR_TYPER);
		uint32_t aff_value = (uint32_t) (gicr_typer >> GICR_TYPER_AFFINITY_VALUE_SHIFT) & (MPIDR_AFF1_MASK | MPIDR_AFF0_MASK);

		if (phys_id == aff_value) {
			return gicr_pe_base;
		}

		if (gicr_typer & GICR_TYPER_LAST) {
			break;
		}
	}

	panic("%s: cannot find GICR base for core %u", __func__, ml_get_cpu_number(phys_id));
}

void
pe_init_fiq()
{
	int error;
	DTEntry entry;

	// gicd_base is 0x0 only before it's initialized by the boot processor.
	// Avoid calling SecureDT* routines on secondary processors to avoid
	// race conditions because they are not thread-safe.
	if (!gicd_base) {
		// Find GIC DT node
		error = SecureDTLookupEntry(NULL, "/arm-io/gic", &entry);
		if (error != kSuccess) {
			panic("%s: cannot find GIC node in DT", __func__);
		}

		// Find "reg" property
		void const *prop;
		unsigned int prop_size;
		error = SecureDTGetProperty(entry, "reg", &prop, &prop_size);
		if (error != kSuccess) {
			panic("%s: cannot find GIC MMIO regions in DT", __func__);
		}

		// Need at least GICD base, GICD size, GICR base and GICR size
		if (prop_size < 4 * sizeof(uint64_t)) {
			panic("%s: incorrect reg property size in GIC DT node; expecting 32 bytes but got %u bytes", __func__, prop_size);
		}

		vm_offset_t soc_base_phys = pe_arm_get_soc_base_phys();

		uint64_t const gicd_base_prop = ((uint64_t const *) prop)[0];
		uint64_t const gicd_size_prop = ((uint64_t const *) prop)[1];
		uint64_t const gicr_base_prop = ((uint64_t const *) prop)[2];
		uint64_t const gicr_size_prop = ((uint64_t const *) prop)[3];

		// Find GICD base address
		gicd_base = ml_io_map(soc_base_phys + gicd_base_prop, gicd_size_prop);

		if (!gicd_base) {
			panic("%s: cannot map GICD region", __func__);
		}

		// Find GICR base address
		gicr_base = ml_io_map(soc_base_phys + gicr_base_prop, gicr_size_prop);

		if (!gicr_base) {
			panic("%s: cannot map GICR region", __func__);
		}

		gicr_size = gicr_size_prop;
	}

	// Find the redistributor for this processor
	vm_offset_t gicr_pe_base = find_gicr_pe_base();

	// Mark this PE to be awake
	uint32_t gicr_waker = gicr_read32(GICR_WAKER);
	if (gicr_waker & GICR_WAKER_CHILDRENASLEEP) {
		gicr_waker &= ~GICR_WAKER_PROCESSORSLEEP;

		gicr_write32(GICR_WAKER, gicr_waker);

		uint64_t gicr_wake_deadline;
		nanoseconds_to_deadline(os_atomic_load(&gicr_wake_timeout_ns, relaxed), &gicr_wake_deadline);
		while (gicr_read32(GICR_WAKER) & GICR_WAKER_CHILDRENASLEEP) {
			// Spin
			if (gicr_wake_timeout_ns > 0 && mach_absolute_time() > gicr_wake_deadline) {
				panic("%s: core %u timed out waiting for redistributor to wake up",
				    __func__, ml_get_cpu_number_local());
			}
		}
	}

	// Configure timers and legacy FIQ to be group 0
	gicr_write32(GICR_IGROUPR0, 0x81FFFFFF);

	// Enable PPI 27
	gicr_write32(GICR_ISENABLER0, (1 << 27));

	// Enable system register access
	uint64_t icc_sre = __builtin_arm_rsr64("ICC_SRE_EL1");
	icc_sre |= ICC_SRE_SRE;
	__builtin_arm_wsr64("ICC_SRE_EL1", icc_sre);
	__builtin_arm_isb(ISB_SY);

	// Set priority masks and binary point for group 0
	__builtin_arm_wsr64("ICC_BPR0_EL1", 0);
	__builtin_arm_wsr64("ICC_PMR_EL1", 0xFF);

	// Set EOI mode of this processor
	uint64_t icc_ctlr = __builtin_arm_rsr64("ICC_CTLR_EL1");
	icc_ctlr &= ~ICC_CTLR_EOIMODE;
	__builtin_arm_wsr64("ICC_CTLR_EL1", icc_ctlr);

	// Enable the forwarding of the vtimer interrupt
	uint32_t gicd_ctlr = gicd_read32(GICD_CTLR);
	gicd_ctlr |= GICD_CTLR_ENABLEGRP0;
	gicd_write32(GICD_CTLR, gicd_ctlr);
	__builtin_arm_wsr64("ICC_IGRPEN0_EL1", 1);
	__builtin_arm_isb(ISB_SY);
}
#elif defined(ARM64_BOARD_CONFIG_BCM2712)
/* BCM2712 exposes a GIC-400 (GICv2), not the GICv3 system-register
 * interface above.  The firmware has made virtual-timer PPI 27 Group 1. */
#define RPI5_GICD_PHYS UINT64_C(0x107fff9000)
#define RPI5_GICD_SIZE UINT64_C(0x1000)
#define RPI5_GICC_PHYS UINT64_C(0x107fffa000)
#define RPI5_GICC_SIZE UINT64_C(0x2000)
#define RPI5_GICD_CTLR 0x000
#define RPI5_GICD_ISENABLER0 0x100
#define RPI5_GICD_ISPENDR0 0x200
#define RPI5_GICD_ISACTIVER0 0x300
#define RPI5_GICD_IPRIORITYR0 0x400
#define RPI5_GICD_ITARGETSR0 0x800
#define RPI5_GICD_SGIR 0xf00
#define RPI5_GICC_CTLR 0x000
#define RPI5_GICC_PMR 0x004
#define RPI5_GICC_IAR 0x00c
#define RPI5_GICC_EOIR 0x010
#define RPI5_GICC_RPR 0x014
#define RPI5_TIMER_PPI 27U
#define RPI5_IPI_SGI 1U
#define RPI5_PM_PHYS UINT64_C(0x107d200000)
#define RPI5_PM_REG_SIZE UINT64_C(0x308)
#define RPI5_PM_MAP_SIZE UINT64_C(0x4000)
#define RPI5_PM_RSTC 0x1c
#define RPI5_PM_WDOG 0x24
#define RPI5_PM_FULL_RESET 0x20U
#define RPI5_WDOG_PASSWORD UINT32_C(0x5a000000)
#define RPI5_WDOG_INTERVAL (15U << 16)
#define RPI5_WDOG_WINDOW_SECONDS 120U
#define RPI5_WDOG_RELOAD_SECONDS 5U
#define RPI5_WDOG_MAX_RELOADS 24U
#define RPI5_TERMINAL_WDOG_SECONDS 3600U
#define RPI5_SOAK_MAX_SECONDS (8U * 60U * 60U)

static vm_offset_t rpi5_gicd_base;
static vm_offset_t rpi5_gicc_base;
static vm_offset_t rpi5_pm_base;
static uint64_t rpi5_wdog_deadline;
static uint64_t rpi5_wdog_last_counter;
static uint64_t rpi5_wdog_reload_ticks;
static unsigned rpi5_wdog_reloads;
static uint32_t rpi5_wdog_soak_seconds;
static bool rpi5_wdog_terminal_enabled;
static uint64_t rpi5_wdog_soak_start_counter;
static uint64_t rpi5_wdog_soak_grace_ticks;

static uint32_t
rpi5_mmio_read32(vm_offset_t base, unsigned offset)
{
	return *(volatile uint32_t *)(base + offset);
}

static void
rpi5_mmio_write32(vm_offset_t base, unsigned offset, uint32_t value)
{
	*(volatile uint32_t *)(base + offset) = value;
}

/* GICC and interrupt IDs 0..31 are banked by the GIC for each CPU. */
static void
rpi5_init_local_gic(void)
{
	/* Never change firmware security ownership. In the Pi's non-secure
	 * GICv2 view IGROUPR0 does not expose the secure bank's classification:
	 * the board run read zero here even though this EL1 can receive PPI27
	 * from GICC_IAR. Validate the accessible Group 1 enable/readback below
	 * and fail closed if the first acknowledged IRQ is not PPI27. */
	/* The timer path owns only PPI27. Do not silently accept another enabled
	 * PPI for which XNU has no handler. */
	if (rpi5_mmio_read32(rpi5_gicd_base, RPI5_GICD_ISENABLER0) &
	    (UINT32_C(0xffff0000) & ~(1U << RPI5_TIMER_PPI))) {
		panic("BCM2712: unexpected enabled PPI");
	}
	/* PPI priority is banked per CPU. PMR 0xff admits priority 0x80. */
	unsigned priority_word = RPI5_GICD_IPRIORITYR0 + (RPI5_TIMER_PPI & ~3U);
	unsigned shift = (RPI5_TIMER_PPI & 3U) * 8U;
	uint32_t priority = rpi5_mmio_read32(rpi5_gicd_base, priority_word);
	priority = (priority & ~(UINT32_C(0xff) << shift)) | (UINT32_C(0x80) << shift);
	rpi5_mmio_write32(rpi5_gicd_base, priority_word, priority);
	rpi5_mmio_write32(rpi5_gicc_base, RPI5_GICC_PMR, 0xff);
	/* Force combined EOI/deactivation: a single EOIR write completes IRQ27. */
	uint32_t cpu_ctl = rpi5_mmio_read32(rpi5_gicc_base, RPI5_GICC_CTLR);
	rpi5_mmio_write32(rpi5_gicc_base, RPI5_GICC_CTLR,
	    (cpu_ctl & ~(1U << 9)) | 1U);
	rpi5_mmio_write32(rpi5_gicd_base, RPI5_GICD_ISENABLER0,
	    1U << RPI5_TIMER_PPI);
	uint32_t dist_ctl = rpi5_mmio_read32(rpi5_gicd_base, RPI5_GICD_CTLR);
	rpi5_mmio_write32(rpi5_gicd_base, RPI5_GICD_CTLR, dist_ctl | 1U);
	__builtin_arm_dsb(DSB_SY);
	if ((rpi5_mmio_read32(rpi5_gicc_base, RPI5_GICC_CTLR) & ((1U << 9) | 1U)) != 1U ||
	    (rpi5_mmio_read32(rpi5_gicd_base, RPI5_GICD_CTLR) & 1U) == 0 ||
	    (rpi5_mmio_read32(rpi5_gicd_base, RPI5_GICD_ISENABLER0) &
	    (1U << RPI5_TIMER_PPI)) == 0) {
		panic("BCM2712: GIC-400 refused timer IRQ configuration");
	}
	__builtin_arm_isb(ISB_SY);
	kprintf("BCM2712 GIC-400 timer PPI27 configured\n");
}

void
pe_init_fiq(void)
{
	DTEntry entry;
	void const *property = NULL;
	unsigned int size = 0;
	uint64_t const *reg;
	uint64_t const *watchdog_reg;
	DTEntry watchdog_entry;
	vm_offset_t soc_base;

	if (rpi5_gicc_base != 0) {
		rpi5_init_local_gic();
		return;
	}
	if (SecureDTLookupEntry(NULL, "/arm-io/gic", &entry) != kSuccess ||
	    SecureDTGetProperty(entry, "reg", &property, &size) != kSuccess ||
	    size != 4 * sizeof(uint64_t)) {
		panic("BCM2712: missing or malformed GIC DT reg");
	}
	reg = property;
	soc_base = pe_arm_get_soc_base_phys();
	if (soc_base != UINT64_C(0x107c000000) ||
	    reg[0] != RPI5_GICD_PHYS - soc_base || reg[1] != RPI5_GICD_SIZE ||
	    reg[2] != RPI5_GICC_PHYS - soc_base || reg[3] != RPI5_GICC_SIZE) {
		panic("BCM2712: unsupported GIC address profile");
	}
	if (SecureDTLookupEntry(NULL, "/arm-io/watchdog", &watchdog_entry) != kSuccess ||
	    SecureDTGetProperty(watchdog_entry, "compatible", &property, &size) != kSuccess ||
	    size != sizeof("brcm,bcm2712-pm") ||
	    __builtin_memcmp(property, "brcm,bcm2712-pm", size) != 0 ||
	    SecureDTGetProperty(watchdog_entry, "reg", &property, &size) != kSuccess ||
	    size != 2 * sizeof(uint64_t)) {
		panic("BCM2712: missing or malformed PM watchdog DT profile");
	}
	watchdog_reg = property;
	if (watchdog_reg[0] != RPI5_PM_PHYS - soc_base ||
	    watchdog_reg[1] != RPI5_PM_REG_SIZE) {
		panic("BCM2712: unsupported PM watchdog address profile");
	}
	rpi5_gicd_base = ml_io_map(RPI5_GICD_PHYS, RPI5_GICD_SIZE);
	rpi5_gicc_base = ml_io_map(RPI5_GICC_PHYS, RPI5_GICC_SIZE);
	rpi5_pm_base = ml_io_map(RPI5_PM_PHYS, RPI5_PM_MAP_SIZE);
	if (rpi5_gicd_base == 0 || rpi5_gicc_base == 0 || rpi5_pm_base == 0) {
		panic("BCM2712: cannot map GIC-400");
	}
	/* This merely observes the firmware's already-enabled full-reset route.
	 * The kernel never writes RSTC, RSTS, or boot-selection registers. */
	if ((rpi5_mmio_read32(rpi5_pm_base, RPI5_PM_RSTC) & 0x30U) == RPI5_PM_FULL_RESET) {
		uint64_t frequency = __builtin_arm_rsr64("CNTFRQ_EL0");
		uint64_t now = __builtin_arm_rsr64("CNTVCT_EL0");
		if (frequency != 0 && frequency <= UINT64_MAX / RPI5_WDOG_WINDOW_SECONDS &&
		    now <= UINT64_MAX - frequency * RPI5_WDOG_WINDOW_SECONDS) {
			rpi5_wdog_last_counter = now;
			rpi5_wdog_reload_ticks = frequency * RPI5_WDOG_RELOAD_SECONDS;
			rpi5_wdog_deadline = now + frequency * RPI5_WDOG_WINDOW_SECONDS;
		}
	}
	rpi5_init_local_gic();
}

bool
pe_rpi5_watchdog_enable_soak(uint32_t seconds)
{
	if (seconds < 60 || seconds > RPI5_SOAK_MAX_SECONDS ||
	    rpi5_pm_base == 0 || rpi5_wdog_deadline == 0 ||
	    rpi5_wdog_terminal_enabled ||
	    (rpi5_mmio_read32(rpi5_pm_base, RPI5_PM_RSTC) & 0x30U) != RPI5_PM_FULL_RESET) {
		return false;
	}
	uint64_t frequency = __builtin_arm_rsr64("CNTFRQ_EL0");
	uint64_t now = __builtin_arm_rsr64("CNTVCT_EL0");
	if (frequency == 0 || frequency > UINT64_MAX / seconds ||
	    now > UINT64_MAX - frequency * seconds) {
		return false;
	}
	rpi5_wdog_deadline = now + frequency * seconds;
	rpi5_wdog_soak_seconds = seconds;
	rpi5_wdog_soak_start_counter = now;
	rpi5_wdog_soak_grace_ticks = frequency * 10U;
	kprintf("RPI5XNU:SOAK:ARM SECONDS=%u\n", seconds);
	return true;
}

bool
pe_rpi5_watchdog_enable_terminal(void)
{
	if (rpi5_pm_base == 0 || rpi5_wdog_deadline == 0 ||
	    rpi5_wdog_soak_seconds != 0 || rpi5_wdog_terminal_enabled ||
	    (rpi5_mmio_read32(rpi5_pm_base, RPI5_PM_RSTC) & 0x30U) != RPI5_PM_FULL_RESET) {
		return false;
	}
	uint64_t frequency = __builtin_arm_rsr64("CNTFRQ_EL0");
	uint64_t now = __builtin_arm_rsr64("CNTVCT_EL0");
	if (frequency == 0 || frequency > UINT64_MAX / RPI5_TERMINAL_WDOG_SECONDS ||
	    now > UINT64_MAX - frequency * RPI5_TERMINAL_WDOG_SECONDS) {
		return false;
	}
	rpi5_wdog_deadline = now + frequency * RPI5_TERMINAL_WDOG_SECONDS;
	rpi5_wdog_terminal_enabled = true;
	kprintf("RPI5XNU:TERMINAL:WATCHDOG SECONDS=%u\n", RPI5_TERMINAL_WDOG_SECONDS);
	return true;
}

bool
pe_rpi5_watchdog_soak_active(void)
{
	return rpi5_wdog_soak_seconds != 0 && rpi5_wdog_deadline != 0;
}

bool
pe_rpi5_watchdog_terminal_active(void)
{
	return rpi5_wdog_terminal_enabled && rpi5_wdog_deadline != 0 &&
	    __builtin_arm_rsr64("CNTVCT_EL0") < rpi5_wdog_deadline;
}

void
pe_rpi5_watchdog_timer_tick(bool healthy)
{
	if (rpi5_pm_base == 0 || rpi5_wdog_deadline == 0 ||
	    (rpi5_wdog_soak_seconds == 0 && !rpi5_wdog_terminal_enabled &&
	    rpi5_wdog_reloads >= RPI5_WDOG_MAX_RELOADS)) {
		return;
	}
	uint64_t now = __builtin_arm_rsr64("CNTVCT_EL0");
	if (rpi5_wdog_soak_seconds != 0 && !healthy) {
		if (now >= rpi5_wdog_soak_start_counter &&
		    now - rpi5_wdog_soak_start_counter < rpi5_wdog_soak_grace_ticks) {
			return;
		}
		kprintf("RPI5XNU:SOAK:FAIL STAGE=HEARTBEAT\n");
		rpi5_wdog_deadline = 0;
		return;
	}
	if (rpi5_wdog_soak_seconds != 0 && now >= rpi5_wdog_deadline) {
		kprintf("RPI5XNU:SOAK:PASS SECONDS=%u\n", rpi5_wdog_soak_seconds);
		rpi5_wdog_deadline = 0;
		return;
	}
	if (now <= rpi5_wdog_last_counter || now >= rpi5_wdog_deadline ||
	    now - rpi5_wdog_last_counter < rpi5_wdog_reload_ticks) {
		return;
	}
	if ((rpi5_mmio_read32(rpi5_pm_base, RPI5_PM_RSTC) & 0x30U) != RPI5_PM_FULL_RESET) {
		rpi5_wdog_deadline = 0;
		return;
	}
	rpi5_mmio_write32(rpi5_pm_base, RPI5_PM_WDOG,
	    RPI5_WDOG_PASSWORD | RPI5_WDOG_INTERVAL);
	__builtin_arm_dsb(DSB_SY);
	rpi5_wdog_last_counter = now;
	rpi5_wdog_reloads++;
	if (rpi5_wdog_terminal_enabled &&
	    (rpi5_wdog_reloads == 1 || rpi5_wdog_reloads % 12 == 0)) {
		kprintf("RPI5XNU:TERMINAL:WATCHDOG_KICK RELOADS=%u\n",
		    rpi5_wdog_reloads);
	}
}

uint32_t
pe_rpi5_irq_acknowledge(void)
{
	if (rpi5_gicc_base == 0) {
		panic("BCM2712: IRQ before GIC initialization");
	}
	return rpi5_mmio_read32(rpi5_gicc_base, RPI5_GICC_IAR);
}

void
pe_rpi5_irq_complete(uint32_t iar)
{
	if ((iar & 0x3ffU) != RPI5_TIMER_PPI &&
	    (iar & 0x3ffU) != RPI5_IPI_SGI) {
		panic("BCM2712: EOI for unsupported IRQ");
	}
	/* Preserve the full IAR, including the SGI source CPU field. */
	__builtin_arm_dsb(DSB_SY);
	rpi5_mmio_write32(rpi5_gicc_base, RPI5_GICC_EOIR, iar);
	__builtin_arm_isb(ISB_SY);
	if ((iar & 0x3ffU) == RPI5_IPI_SGI) {
		return;
	}
	static unsigned rpi5_eoi_reported;
	if (!rpi5_eoi_reported) {
		rpi5_eoi_reported = 1;
		kprintf("BCM2712 EOI state enable=0x%x pending=0x%x active=0x%x rpr=0x%x cctl=0x%x\n",
		    rpi5_mmio_read32(rpi5_gicd_base, RPI5_GICD_ISENABLER0),
		    rpi5_mmio_read32(rpi5_gicd_base, RPI5_GICD_ISPENDR0),
		    rpi5_mmio_read32(rpi5_gicd_base, RPI5_GICD_ISACTIVER0),
		    rpi5_mmio_read32(rpi5_gicc_base, RPI5_GICC_RPR),
		    rpi5_mmio_read32(rpi5_gicc_base, RPI5_GICC_CTLR));
	}
}

/* Read the banked SGI/PPI target bytes; MPIDR affinity is not a GIC target ID. */
uint32_t
pe_rpi5_sgi_local_target(void)
{
	uint32_t mask = 0;
	if (rpi5_gicd_base == 0) {
		return 0;
	}
	for (unsigned offset = 0; offset < 0x20; offset += 4) {
		uint32_t targets = rpi5_mmio_read32(rpi5_gicd_base,
		    RPI5_GICD_ITARGETSR0 + offset);
		mask |= targets | (targets >> 8) | (targets >> 16) |
		    (targets >> 24);
	}
	mask &= 0xffU;
	return mask != 0 && (mask & (mask - 1U)) == 0 ? mask : 0;
}

/* The caller must have installed the CPU's signal handler before arming it. */
bool
pe_rpi5_sgi_enable_local(void)
{
	if (rpi5_gicc_base == 0 || pe_rpi5_sgi_local_target() == 0) {
		return false;
	}
	/* Group 1 forwarding is the accessible non-secure view. IGROUPR0
	 * readback is not reliable here; firmware owns that classification. */
	if ((rpi5_mmio_read32(rpi5_gicc_base, RPI5_GICC_CTLR) & 1U) == 0 ||
	    (rpi5_mmio_read32(rpi5_gicd_base, RPI5_GICD_CTLR) & 1U) == 0) {
		return false;
	}
	unsigned priority_word = RPI5_GICD_IPRIORITYR0 + (RPI5_IPI_SGI & ~3U);
	unsigned shift = (RPI5_IPI_SGI & 3U) * 8U;
	uint32_t priority = rpi5_mmio_read32(rpi5_gicd_base, priority_word);
	priority = (priority & ~(UINT32_C(0xff) << shift)) |
	    (UINT32_C(0x80) << shift);
	rpi5_mmio_write32(rpi5_gicd_base, priority_word, priority);
	rpi5_mmio_write32(rpi5_gicd_base, RPI5_GICD_ISENABLER0,
	    1U << RPI5_IPI_SGI);
	__builtin_arm_dsb(DSB_SY);
	return (rpi5_mmio_read32(rpi5_gicd_base, RPI5_GICD_ISENABLER0) &
	    (1U << RPI5_IPI_SGI)) != 0;
}

/* A single observed GIC CPU-interface bit selects one destination. */
bool
pe_rpi5_sgi_send(uint32_t target_mask)
{
	if (rpi5_gicd_base == 0 || target_mask == 0 ||
	    (target_mask & ~0xffU) != 0 ||
	    (target_mask & (target_mask - 1U)) != 0) {
		return false;
	}
	/* TargetListFilter=0, CPUTargetList in bits 23:16, SGI ID in 3:0. */
	__builtin_arm_dsb(DSB_ISHST);
	rpi5_mmio_write32(rpi5_gicd_base, RPI5_GICD_SGIR,
	    (target_mask << 16) | RPI5_IPI_SGI);
	return true;
}
#else
void
pe_init_fiq()
{
}
#endif
