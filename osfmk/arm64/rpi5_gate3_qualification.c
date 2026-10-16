/* SPDX-License-Identifier: APSL-2.0 */
/* Opt-in, sequential pre-soak Gate 3 qualification on BCM2712 DEVELOPMENT. */

#include <pexpert/arm64/board_config.h>

#if defined(ARM64_BOARD_CONFIG_BCM2712) && DEVELOPMENT

#include <arm/cpu_internal.h>
#include <arm/machine_routines.h>
#include <arm64/rpi5_gate3_test.h>
#include <kern/debug.h>
#include <kern/thread.h>
#include <machine/atomic.h>

#define RPI5_GATE3_TRIAL_TIMEOUT_SECONDS 45U
#define RPI5_GATE3_QUALIFICATION_SOAK_SECONDS (8U * 60U * 60U)

static _Atomic bool rpi5_qualification_started;

static uint32_t
rpi5_qualification_wait(uint32_t (*status)(void))
{
	uint64_t frequency = __builtin_arm_rsr64("CNTFRQ_EL0");
	uint64_t begin = __builtin_arm_rsr64("CNTVCT_EL0");
	if (frequency == 0 ||
	    frequency > UINT64_MAX / RPI5_GATE3_TRIAL_TIMEOUT_SECONDS) {
		return 0;
	}
	for (;;) {
		uint32_t state = status();
		if (state == 2 || state == 3) {
			return state;
		}
		if (__builtin_arm_rsr64("CNTVCT_EL0") - begin >
		    frequency * RPI5_GATE3_TRIAL_TIMEOUT_SECONDS) {
			return 0;
		}
		delay(1000);
	}
}

static void
rpi5_qualification_fail(const char *stage, uint32_t status)
{
	kprintf("RPI5XNU:QUALIFICATION:FAIL STAGE=%s STATUS=%u\n", stage, status);
	kprintf("RPI5XNU:QUALIFICATION:FAIL\n");
}

static void
rpi5_qualification_thread(void *parameter __unused, wait_result_t result __unused)
{
	uint32_t state = rpi5_gate3_xnupost_status();
	if (state != 2) {
		rpi5_qualification_fail("XNUPOST", state);
		thread_terminate_self();
	}
	/* The first PID 1 console write begins immediately after BSD launches it.
	 * Leave a short window for that line before printing stage markers: the
	 * console and polled kprintf paths can otherwise interleave bytes. */
	delay(250000);
	kprintf("RPI5XNU:QUALIFICATION:START STAGE=SMP_CONCURRENCY\n");
	rpi5_gate3_start_concurrency_test();
	state = rpi5_qualification_wait(rpi5_gate3_concurrency_status);
	if (state != 2) {
		rpi5_qualification_fail("SMP_CONCURRENCY", state);
		thread_terminate_self();
	}
	kprintf("RPI5XNU:QUALIFICATION:START STAGE=TLB\n");
	rpi5_gate3_start_tlb_test();
	state = rpi5_qualification_wait(rpi5_gate3_tlb_status);
	if (state != 2) {
		kprintf("RPI5XNU:CROSS_CORE_INVALIDATION:FAIL\n");
		rpi5_qualification_fail("TLB", state);
		thread_terminate_self();
	}
	kprintf("RPI5XNU:QUALIFICATION:START STAGE=USER_TLB\n");
	rpi5_gate3_start_user_tlb_test();
	state = rpi5_qualification_wait(rpi5_gate3_user_tlb_status);
	if (state != 2) {
		kprintf("RPI5XNU:CROSS_CORE_INVALIDATION:FAIL\n");
		rpi5_qualification_fail("USER_TLB", state);
		thread_terminate_self();
	}
	kprintf("RPI5XNU:CROSS_CORE_INVALIDATION:PASS\n");
	if (!rpi5_gate3_enable_soak(RPI5_GATE3_QUALIFICATION_SOAK_SECONDS)) {
		rpi5_qualification_fail("SOAK_ARM", 0);
		thread_terminate_self();
	}
	kprintf("RPI5XNU:QUALIFICATION:PRE_SOAK_PASS\n");
	thread_terminate_self();
}

void
rpi5_gate3_start_qualification(void)
{
	if (!os_atomic_cmpxchg(&rpi5_qualification_started, false, true, acq_rel)) {
		return;
	}
	thread_t worker;
	kern_return_t kr = kernel_thread_start(rpi5_qualification_thread, NULL, &worker);
	if (kr != KERN_SUCCESS) {
		rpi5_qualification_fail("THREAD", (uint32_t)kr);
		return;
	}
	thread_deallocate(worker);
}

#endif /* ARM64_BOARD_CONFIG_BCM2712 && DEVELOPMENT */
