/* SPDX-License-Identifier: APSL-2.0 */
/* Opt-in BCM2712 DEVELOPMENT test for cross-core user-ASID invalidation. */

#include <pexpert/arm64/board_config.h>

#if defined(ARM64_BOARD_CONFIG_BCM2712) && DEVELOPMENT

#include <arm/cpu_data.h>
#include <arm/cpu_data_internal.h>
#include <arm/cpu_internal.h>
#include <arm/machine_routines.h>
#include <arm64/rpi5_gate3_test.h>
#include <kern/debug.h>
#include <kern/processor.h>
#include <kern/sched_prim.h>
#include <kern/thread.h>
#include <machine/atomic.h>
#include <vm/pmap.h>
#include <vm/vm_map_xnu.h>
#include <vm/vm_kern_xnu.h>

#define RPI5_USER_TLB_ROUNDS 64U
#define RPI5_USER_TLB_VA PAGE_SIZE

extern _Atomic uint64_t ml_cpu_up_processors;

typedef struct {
	pmap_t pmap;
	_Atomic uint64_t expected_pa;
	_Atomic uint32_t epoch;
	_Atomic uint32_t ready;
	_Atomic uint32_t seen[4];
	_Atomic uint32_t errors;
	_Atomic uint32_t switch_flush_errors;
	_Atomic bool stop;
	_Atomic bool started[4];
	_Atomic bool done[4];
} rpi5_user_tlb_context_t;

static rpi5_user_tlb_context_t rpi5_user_tlb;
static _Atomic bool rpi5_user_tlb_started;
static _Atomic uint32_t rpi5_user_tlb_status;

static void
rpi5_user_tlb_reader(void *parameter, wait_result_t result __unused)
{
	unsigned int cpu = (unsigned int)(uintptr_t)parameter;
	rpi5_user_tlb_context_t *test = &rpi5_user_tlb;
	thread_bind(cpu_to_processor((int)cpu));
	thread_block(THREAD_CONTINUE_NULL);
	if (getCpuDatap()->cpu_number != cpu) {
		os_atomic_inc(&test->errors, relaxed);
	}
	os_atomic_inc(&test->ready, release);
	uint32_t last_epoch = 0;
	while (!os_atomic_load(&test->stop, acquire)) {
		uint32_t before = os_atomic_load(&test->epoch, acquire);
		if (before == 0 || (before & 1U) || before == last_epoch) {
			delay(100);
			continue;
		}
		/* Keep interrupts and preemption off while TTBR0 refers to the
		 * temporary pmap, as in pmap_test_access(). Only AT S1E0R is used:
		 * no user VA is dereferenced while it can be unmapped. */
		thread_t thread = current_thread();
		pmap_t old_pmap = vm_map_pmap(thread->map);
		boolean_t interrupts_enabled = ml_set_interrupts_enabled(FALSE);
		mp_disable_preemption();
		uint64_t flushes_before = rpi5_pmap_switch_local_flush_count();
		pmap_switch(test->pmap, thread);
		uint64_t flushes_after = rpi5_pmap_switch_local_flush_count();
		uint64_t expected = os_atomic_load(&test->expected_pa, acquire);
		pmap_paddr_t observed = mmu_uvtop(RPI5_USER_TLB_VA);
		pmap_switch(old_pmap, thread);
		mp_enable_preemption();
		ml_set_interrupts_enabled(interrupts_enabled);
		if (before > 2 && flushes_after != flushes_before) {
			os_atomic_inc(&test->switch_flush_errors, relaxed);
			os_atomic_inc(&test->errors, relaxed);
			os_atomic_store(&test->stop, true, release);
		}
		uint32_t after = os_atomic_load(&test->epoch, acquire);
		if (before == after) {
			if (observed != expected) {
				os_atomic_inc(&test->errors, relaxed);
				os_atomic_store(&test->stop, true, release);
			}
			last_epoch = after;
			os_atomic_store(&test->seen[cpu], after, release);
		}
	}
	os_atomic_store(&test->done[cpu], true, release);
	thread_terminate_self();
}

static bool
rpi5_user_tlb_wait(_Atomic uint32_t *counter, uint32_t target, uint32_t seconds)
{
	uint64_t frequency = __builtin_arm_rsr64("CNTFRQ_EL0");
	uint64_t begin = __builtin_arm_rsr64("CNTVCT_EL0");
	if (frequency == 0 || frequency > UINT64_MAX / seconds) {
		return false;
	}
	while (os_atomic_load(counter, acquire) < target) {
		if (os_atomic_load(&rpi5_user_tlb.errors, acquire) != 0 ||
		    __builtin_arm_rsr64("CNTVCT_EL0") - begin > frequency * seconds) {
			return false;
		}
		delay(100);
	}
	return true;
}

static bool
rpi5_user_tlb_stop_workers(void)
{
	rpi5_user_tlb_context_t *test = &rpi5_user_tlb;
	os_atomic_store(&test->stop, true, release);
	bool all_done = true;
	for (unsigned int cpu = 1; cpu < 4; cpu++) {
		if (!os_atomic_load(&test->started[cpu], acquire)) {
			continue;
		}
		uint32_t attempts = 0;
		while (!os_atomic_load(&test->done[cpu], acquire) && attempts++ < 10000) {
			delay(100);
		}
		if (!os_atomic_load(&test->done[cpu], acquire)) {
			all_done = false;
		}
	}
	return all_done;
}

static void
rpi5_user_tlb_test_thread(void *parameter __unused, wait_result_t result __unused)
{
	uint64_t trial_begin = __builtin_arm_rsr64("CNTVCT_EL0");
	bool passed = false;
	thread_bind(master_processor);
	thread_block(THREAD_CONTINUE_NULL);
	uint32_t attempts = 0;
	while ((os_atomic_load(&ml_cpu_up_processors, acquire) & UINT64_C(0xf)) !=
	    UINT64_C(0xf) && attempts++ < 1000) {
		delay(10000);
	}
	if ((os_atomic_load(&ml_cpu_up_processors, acquire) & UINT64_C(0xf)) !=
	    UINT64_C(0xf)) {
		kprintf("RPI5XNU:USER_TLB:FAIL STAGE=ONLINE\n");
		goto finish;
	}
	vm_offset_t first = 0, second = 0;
	pmap_t user_pmap = PMAP_NULL;
	bool workers_done = true;
	kern_return_t kr = kmem_alloc(kernel_map, &first, PAGE_SIZE,
	    KMA_ZERO | KMA_KOBJECT, VM_KERN_MEMORY_DIAG);
	if (kr != KERN_SUCCESS) {
		kprintf("RPI5XNU:USER_TLB:FAIL STAGE=ALLOC_A KR=%d\n", kr);
		goto cleanup;
	}
	kr = kmem_alloc(kernel_map, &second, PAGE_SIZE,
	    KMA_ZERO | KMA_KOBJECT, VM_KERN_MEMORY_DIAG);
	if (kr != KERN_SUCCESS) {
		kprintf("RPI5XNU:USER_TLB:FAIL STAGE=ALLOC_B KR=%d\n", kr);
		goto cleanup;
	}
	ppnum_t page_a = pmap_find_phys(kernel_pmap, first);
	ppnum_t page_b = pmap_find_phys(kernel_pmap, second);
	if (page_a == 0 || page_b == 0 || page_a == page_b) {
		kprintf("RPI5XNU:USER_TLB:FAIL STAGE=PHYS A=%u B=%u\n", page_a, page_b);
		goto cleanup;
	}
	user_pmap = pmap_create_options(NULL, 0, PMAP_CREATE_64BIT);
	if (user_pmap == PMAP_NULL) {
		kprintf("RPI5XNU:USER_TLB:FAIL STAGE=PMAP_CREATE\n");
		goto cleanup;
	}
	kr = pmap_enter(user_pmap, RPI5_USER_TLB_VA, page_a, VM_PROT_READ,
	    VM_PROT_NONE, VM_WIMG_USE_DEFAULT, FALSE, PMAP_MAPPING_TYPE_INFER);
	if (kr != KERN_SUCCESS) {
		kprintf("RPI5XNU:USER_TLB:FAIL STAGE=PMAP_ENTER KR=%d\n", kr);
		goto cleanup;
	}
	rpi5_user_tlb_context_t *test = &rpi5_user_tlb;
	test->pmap = user_pmap;
	os_atomic_store(&test->expected_pa, ptoa(page_a), release);
	for (unsigned int cpu = 1; cpu < 4; cpu++) {
		thread_t reader;
		kr = kernel_thread_start(rpi5_user_tlb_reader,
		    (void *)(uintptr_t)cpu, &reader);
		if (kr != KERN_SUCCESS) {
			kprintf("RPI5XNU:USER_TLB:FAIL STAGE=THREAD CPU=%u KR=%d\n", cpu, kr);
			goto cleanup;
		}
		thread_deallocate(reader);
		os_atomic_store(&test->started[cpu], true, release);
	}
	if (!rpi5_user_tlb_wait(&test->ready, 3, 10)) {
		kprintf("RPI5XNU:USER_TLB:FAIL STAGE=READY\n");
		goto cleanup;
	}
	os_atomic_store(&test->epoch, 2, release);
	for (unsigned int cpu = 1; cpu < 4; cpu++) {
		if (!rpi5_user_tlb_wait(&test->seen[cpu], 2, 2)) {
			kprintf("RPI5XNU:USER_TLB:FAIL STAGE=INITIAL CPU=%u\n", cpu);
			goto cleanup;
		}
	}
	for (uint32_t round = 1; round <= RPI5_USER_TLB_ROUNDS; round++) {
		ppnum_t next = (round & 1U) ? page_b : page_a;
		uint32_t even = 2 + round * 2;
		os_atomic_store(&test->epoch, even - 1U, release);
		pmap_remove(user_pmap, RPI5_USER_TLB_VA,
		    RPI5_USER_TLB_VA + PAGE_SIZE);
		kr = pmap_enter(user_pmap, RPI5_USER_TLB_VA, next, VM_PROT_READ,
		    VM_PROT_NONE, VM_WIMG_USE_DEFAULT, FALSE, PMAP_MAPPING_TYPE_INFER);
		if (kr != KERN_SUCCESS) {
			kprintf("RPI5XNU:USER_TLB:FAIL STAGE=REMAP ROUND=%u KR=%d\n",
			    round, kr);
			goto cleanup;
		}
		os_atomic_store(&test->expected_pa, ptoa(next), release);
		os_atomic_store(&test->epoch, even, release);
		for (unsigned int cpu = 1; cpu < 4; cpu++) {
			if (!rpi5_user_tlb_wait(&test->seen[cpu], even, 2)) {
				kprintf("RPI5XNU:USER_TLB:FAIL STAGE=STALE ROUND=%u CPU=%u ERRORS=%u\n",
				    round, cpu, os_atomic_load(&test->errors, acquire));
				goto cleanup;
			}
		}
	}
	passed = os_atomic_load(&test->errors, acquire) == 0;
cleanup:
	workers_done = rpi5_user_tlb_stop_workers();
	if (os_atomic_load(&rpi5_user_tlb.switch_flush_errors, acquire) != 0) {
		passed = false;
		kprintf("RPI5XNU:USER_TLB:FAIL STAGE=SWITCH_FLUSH COUNT=%u\n",
		    os_atomic_load(&rpi5_user_tlb.switch_flush_errors, acquire));
	}
	if (!workers_done) {
		/* A delayed worker may still be using the user pmap; retain its
		 * page-table and backing pages until watchdog reset. */
		passed = false;
		kprintf("RPI5XNU:USER_TLB:FAIL STAGE=WORKER_TIMEOUT\n");
	} else {
		if (user_pmap != PMAP_NULL) {
			pmap_remove(user_pmap, RPI5_USER_TLB_VA,
			    RPI5_USER_TLB_VA + PAGE_SIZE);
			pmap_destroy(user_pmap);
		}
		if (first != 0) {
			kmem_free(kernel_map, first, PAGE_SIZE);
		}
		if (second != 0) {
			kmem_free(kernel_map, second, PAGE_SIZE);
		}
	}
	if (passed) {
		kprintf("RPI5XNU:USER_TLB:DETAIL REMAP_ROUNDS=64 CPUS=1-3\n");
	}
	finish:
	kprintf("RPI5XNU:USER_TLB:TIMING TICKS=%llu FREQ=%llu\n",
	    __builtin_arm_rsr64("CNTVCT_EL0") - trial_begin,
	    __builtin_arm_rsr64("CNTFRQ_EL0"));
	kprintf("RPI5XNU:USER_TLB:%s\n", passed ? "PASS" : "FAIL");
	os_atomic_store(&rpi5_user_tlb_status, passed ? 2 : 3, release);
	thread_terminate_self();
}

void
rpi5_gate3_start_user_tlb_test(void)
{
	if (!os_atomic_cmpxchg(&rpi5_user_tlb_started, false, true, acq_rel)) {
		return;
	}
	os_atomic_store(&rpi5_user_tlb_status, 1, release);
	thread_t worker;
	kern_return_t kr = kernel_thread_start(rpi5_user_tlb_test_thread, NULL, &worker);
	if (kr != KERN_SUCCESS) {
		os_atomic_store(&rpi5_user_tlb_status, 3, release);
		kprintf("RPI5XNU:USER_TLB:FAIL STAGE=COORDINATOR KR=%d\n", kr);
		kprintf("RPI5XNU:USER_TLB:FAIL\n");
		return;
	}
	thread_deallocate(worker);
}

uint32_t
rpi5_gate3_user_tlb_status(void)
{
	return os_atomic_load(&rpi5_user_tlb_status, acquire);
}

#endif /* ARM64_BOARD_CONFIG_BCM2712 && DEVELOPMENT */
