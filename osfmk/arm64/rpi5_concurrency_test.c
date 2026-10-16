/* SPDX-License-Identifier: APSL-2.0 */
/* Opt-in BCM2712 DEVELOPMENT test for four-CPU XNU concurrency. */

#include <pexpert/arm64/board_config.h>

#if defined(ARM64_BOARD_CONFIG_BCM2712) && DEVELOPMENT

#include <arm/cpu_data.h>
#include <arm/cpu_data_internal.h>
#include <arm/cpu_internal.h>
#include <arm/machine_routines.h>
#include <kern/debug.h>
#include <kern/processor.h>
#include <kern/sched_prim.h>
#include <kern/thread.h>
#include <machine/atomic.h>
#include <arm64/rpi5_gate3_test.h>

#define RPI5_CONCURRENCY_ROUNDS 1000000U

extern _Atomic uint64_t ml_cpu_up_processors;

typedef struct {
	unsigned int target_cpu;
	unsigned int observed_cpu;
	uint32_t increments;
	_Atomic uint32_t progress;
	uint64_t start;
	uint64_t end;
	_Atomic bool done;
} rpi5_concurrency_worker_t;

static rpi5_concurrency_worker_t rpi5_workers[4];
static _Atomic uint32_t rpi5_ready;
static _Atomic uint32_t rpi5_midpoint;
static _Atomic uint32_t rpi5_shared_count;
static _Atomic bool rpi5_go;
static _Atomic bool rpi5_abort;
static _Atomic bool rpi5_started;
/* 0 = idle, 1 = running, 2 = passed, 3 = failed. */
static _Atomic uint32_t rpi5_concurrency_status;

static bool
rpi5_concurrency_wait(_Atomic uint32_t *counter, uint32_t target,
    uint64_t timeout_seconds)
{
	uint64_t frequency = __builtin_arm_rsr64("CNTFRQ_EL0");
	uint64_t begin = __builtin_arm_rsr64("CNTVCT_EL0");
	if (frequency == 0 || frequency > UINT64_MAX / timeout_seconds) {
		return false;
	}
	while (os_atomic_load(counter, acquire) < target) {
		if (os_atomic_load(&rpi5_abort, acquire) ||
		    __builtin_arm_rsr64("CNTVCT_EL0") - begin >
		    frequency * timeout_seconds) {
			return false;
		}
		delay(100);
	}
	return true;
}

static bool
rpi5_concurrency_wait_online(void)
{
	uint64_t frequency = __builtin_arm_rsr64("CNTFRQ_EL0");
	uint64_t begin = __builtin_arm_rsr64("CNTVCT_EL0");
	if (frequency == 0 || frequency > UINT64_MAX / 10U) {
		return false;
	}
	while ((os_atomic_load(&ml_cpu_up_processors, acquire) & UINT64_C(0xf)) !=
	    UINT64_C(0xf)) {
		if (__builtin_arm_rsr64("CNTVCT_EL0") - begin > frequency * 10U) {
			return false;
		}
		delay(1000);
	}
	return true;
}

static bool
rpi5_concurrency_run(rpi5_concurrency_worker_t *worker)
{
	thread_bind(cpu_to_processor((int)worker->target_cpu));
	thread_block(THREAD_CONTINUE_NULL);
	worker->observed_cpu = getCpuDatap()->cpu_number;
	if (worker->observed_cpu != worker->target_cpu) {
		return false;
	}
	os_atomic_inc(&rpi5_ready, release);
	if (worker->target_cpu == 0) {
		if (!rpi5_concurrency_wait(&rpi5_ready, 4, 10)) {
			return false;
		}
		os_atomic_store(&rpi5_go, true, release);
	} else {
		uint64_t frequency = __builtin_arm_rsr64("CNTFRQ_EL0");
		uint64_t begin = __builtin_arm_rsr64("CNTVCT_EL0");
		while (!os_atomic_load(&rpi5_go, acquire)) {
			if (os_atomic_load(&rpi5_abort, acquire) ||
			    frequency == 0 || frequency > UINT64_MAX / 10U ||
			    __builtin_arm_rsr64("CNTVCT_EL0") - begin > frequency * 10U) {
				return false;
			}
			delay(100);
		}
	}
	worker->start = __builtin_arm_rsr64("CNTVCT_EL0");
	uint32_t peer_midpoint[4] = {0};
	for (uint32_t index = 0; index < RPI5_CONCURRENCY_ROUNDS; index++) {
		os_atomic_inc(&rpi5_shared_count, relaxed);
		worker->increments++;
		if ((index & 1023U) == 0 &&
		    getCpuDatap()->cpu_number != worker->target_cpu) {
			return false;
		}
		if ((index & 1023U) == 0) {
			os_atomic_store(&worker->progress, index + 1U, release);
		}
		if (index + 1U == RPI5_CONCURRENCY_ROUNDS / 2U) {
			os_atomic_inc(&rpi5_midpoint, release);
			if (!rpi5_concurrency_wait(&rpi5_midpoint, 4, 10)) {
				return false;
			}
			for (unsigned int cpu = 0; cpu < 4; cpu++) {
				peer_midpoint[cpu] = os_atomic_load(&rpi5_workers[cpu].progress,
				    acquire);
			}
		}
		if (index + 1U == RPI5_CONCURRENCY_ROUNDS * 3U / 4U) {
			for (unsigned int cpu = 0; cpu < 4; cpu++) {
				if (cpu != worker->target_cpu &&
				    !rpi5_concurrency_wait(&rpi5_workers[cpu].progress,
				    peer_midpoint[cpu] + 1U, 10)) {
					return false;
				}
			}
		}
	}
	os_atomic_store(&worker->progress, RPI5_CONCURRENCY_ROUNDS, release);
	worker->end = __builtin_arm_rsr64("CNTVCT_EL0");
	return true;
}

static void
rpi5_concurrency_secondary(void *parameter, wait_result_t result __unused)
{
	rpi5_concurrency_worker_t *worker = parameter;
	if (!rpi5_concurrency_run(worker)) {
		os_atomic_store(&rpi5_abort, true, release);
	}
	os_atomic_store(&worker->done, true, release);
	thread_terminate_self();
}

static void
rpi5_concurrency_primary(void *parameter __unused, wait_result_t result __unused)
{
	uint64_t trial_begin = __builtin_arm_rsr64("CNTVCT_EL0");
	if (!rpi5_concurrency_wait_online()) {
		os_atomic_store(&rpi5_concurrency_status, 3, release);
		kprintf("RPI5XNU:SMP_CONCURRENCY:FAIL STAGE=ONLINE\n");
		kprintf("RPI5XNU:SMP_CONCURRENCY:FAIL\n");
		thread_terminate_self();
	}
	for (unsigned int cpu = 0; cpu < 4; cpu++) {
		rpi5_workers[cpu].target_cpu = cpu;
	}
	for (unsigned int cpu = 1; cpu < 4; cpu++) {
		thread_t thread;
		kern_return_t kr = kernel_thread_start(rpi5_concurrency_secondary,
		    &rpi5_workers[cpu], &thread);
		if (kr != KERN_SUCCESS) {
			os_atomic_store(&rpi5_abort, true, release);
			os_atomic_store(&rpi5_concurrency_status, 3, release);
			kprintf("RPI5XNU:SMP_CONCURRENCY:FAIL STAGE=THREAD CPU=%u KR=%d\n",
			    cpu, kr);
			kprintf("RPI5XNU:SMP_CONCURRENCY:FAIL\n");
			thread_terminate_self();
		}
		thread_deallocate(thread);
	}
	bool passed = rpi5_concurrency_run(&rpi5_workers[0]);
	if (!passed) {
		os_atomic_store(&rpi5_abort, true, release);
	}
	os_atomic_store(&rpi5_workers[0].done, true, release);
	uint64_t frequency = __builtin_arm_rsr64("CNTFRQ_EL0");
	uint64_t begin = __builtin_arm_rsr64("CNTVCT_EL0");
	for (unsigned int cpu = 1; cpu < 4; cpu++) {
		while (!os_atomic_load(&rpi5_workers[cpu].done, acquire)) {
			if (frequency == 0 || frequency > UINT64_MAX / 10U ||
			    __builtin_arm_rsr64("CNTVCT_EL0") - begin > frequency * 10U) {
				passed = false;
				break;
			}
			delay(100);
		}
	}
	uint64_t latest_start = 0;
	uint64_t earliest_end = UINT64_MAX;
	unsigned int observed[4] = { UINT32_MAX, UINT32_MAX, UINT32_MAX, UINT32_MAX };
	for (unsigned int cpu = 0; cpu < 4; cpu++) {
		rpi5_concurrency_worker_t *worker = &rpi5_workers[cpu];
		if (!os_atomic_load(&worker->done, acquire)) {
			/* A timed-out worker may still be writing these plain fields. */
			passed = false;
			continue;
		}
		observed[cpu] = worker->observed_cpu;
		if (worker->observed_cpu != cpu ||
		    worker->increments != RPI5_CONCURRENCY_ROUNDS ||
		    worker->end <= worker->start) {
			passed = false;
		}
		if (worker->start > latest_start) {
			latest_start = worker->start;
		}
		if (worker->end < earliest_end) {
			earliest_end = worker->end;
		}
	}
	passed = passed && !os_atomic_load(&rpi5_abort, acquire) &&
	    latest_start < earliest_end &&
	    os_atomic_load(&rpi5_shared_count, acquire) ==
	    4U * RPI5_CONCURRENCY_ROUNDS;
	kprintf("RPI5XNU:SMP_CONCURRENCY:DETAIL CPUS=%u,%u,%u,%u COUNT=%u OVERLAP=%u\n",
	    observed[0], observed[1], observed[2], observed[3],
	    os_atomic_load(&rpi5_shared_count, acquire),
	    latest_start < earliest_end);
	kprintf("RPI5XNU:SMP_CONCURRENCY:TIMING TICKS=%llu FREQ=%llu\n",
	    __builtin_arm_rsr64("CNTVCT_EL0") - trial_begin,
	    __builtin_arm_rsr64("CNTFRQ_EL0"));
	kprintf("RPI5XNU:SMP_CONCURRENCY:%s\n", passed ? "PASS" : "FAIL");
	/* Publish terminal status only after the terminal serial record. */
	os_atomic_store(&rpi5_concurrency_status, passed ? 2 : 3, release);
	thread_terminate_self();
}

void
rpi5_gate3_start_concurrency_test(void)
{
	if (!os_atomic_cmpxchg(&rpi5_started, false, true, acq_rel)) {
		return;
	}
	os_atomic_store(&rpi5_concurrency_status, 1, release);
	thread_t thread;
	kern_return_t kr = kernel_thread_start(rpi5_concurrency_primary, NULL, &thread);
	if (kr != KERN_SUCCESS) {
		os_atomic_store(&rpi5_concurrency_status, 3, release);
		kprintf("RPI5XNU:SMP_CONCURRENCY:FAIL STAGE=COORDINATOR KR=%d\n", kr);
		kprintf("RPI5XNU:SMP_CONCURRENCY:FAIL\n");
		return;
	}
	thread_deallocate(thread);
}

uint32_t
rpi5_gate3_concurrency_status(void)
{
	return os_atomic_load(&rpi5_concurrency_status, acquire);
}

#endif /* ARM64_BOARD_CONFIG_BCM2712 && DEVELOPMENT */
