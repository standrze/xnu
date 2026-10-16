/* SPDX-License-Identifier: APSL-2.0 */
/* Opt-in BCM2712 DEVELOPMENT test for broadcast kernel-VA invalidation. */

#include <pexpert/arm64/board_config.h>

#if defined(ARM64_BOARD_CONFIG_BCM2712) && DEVELOPMENT

#include <arm/cpu_data.h>
#include <arm/cpu_data_internal.h>
#include <arm/cpu_internal.h>
#include <arm/machine_routines.h>
#include <kern/clock.h>
#include <kern/debug.h>
#include <kern/processor.h>
#include <kern/sched_prim.h>
#include <kern/thread.h>
#include <machine/atomic.h>
#include <vm/pmap.h>
#include <vm/vm_kern_xnu.h>
#include <arm64/rpi5_gate3_test.h>

extern _Atomic uint64_t ml_cpu_up_processors;

typedef struct {
	volatile uint64_t *address;
	_Atomic uint32_t done[4];
	uint64_t observed[4];
	uint32_t sequence;
} rpi5_tlb_observation_t;
static rpi5_tlb_observation_t rpi5_tlb_test_observation;
static bool rpi5_tlb_xcall_timed_out;

typedef struct {
	vm_offset_t address;
	_Atomic uint64_t expected_pa;
	_Atomic bool expected_writable;
	_Atomic uint32_t epoch;
	_Atomic uint32_t seen[4];
	_Atomic uint32_t ready;
	_Atomic uint32_t errors;
	_Atomic bool stop;
	_Atomic bool started[4];
	_Atomic bool done[4];
} rpi5_tlb_stress_t;
static rpi5_tlb_stress_t rpi5_tlb_stress_context;
static bool rpi5_tlb_stress_timed_out;
/* 0 = idle, 1 = running, 2 = passed, 3 = failed. */
static _Atomic uint32_t rpi5_tlb_status;
static _Atomic bool rpi5_tlb_started;

static void
rpi5_tlb_stress_reader(void *parameter, wait_result_t result __unused)
{
	unsigned int cpu = (unsigned int)(uintptr_t)parameter;
	rpi5_tlb_stress_t *stress = &rpi5_tlb_stress_context;
	thread_bind(cpu_to_processor((int)cpu));
	thread_block(THREAD_CONTINUE_NULL);
	if (getCpuDatap()->cpu_number != cpu) {
		os_atomic_inc(&stress->errors, relaxed);
	}
	os_atomic_inc(&stress->ready, release);
	while (!os_atomic_load(&stress->stop, acquire)) {
		uint32_t before = os_atomic_load(&stress->epoch, acquire);
		if (before == 0 || (before & 1U)) {
			continue;
		}
		uint64_t expected = os_atomic_load(&stress->expected_pa, acquire);
		bool writable = os_atomic_load(&stress->expected_writable, acquire);
		pmap_paddr_t observed = mmu_kvtop(stress->address);
		pmap_paddr_t writable_pa = mmu_kvtop_wpreflight(stress->address);
		uint32_t after = os_atomic_load(&stress->epoch, acquire);
		if (before == after) {
			if (observed != expected ||
			    writable_pa != (writable ? expected : 0)) {
				os_atomic_inc(&stress->errors, relaxed);
				os_atomic_store(&stress->stop, true, release);
			}
			os_atomic_store(&stress->seen[cpu], after, release);
		}
	}
	os_atomic_store(&stress->done[cpu], true, release);
	thread_terminate_self();
}

static bool
rpi5_tlb_stress_wait(_Atomic uint32_t *counter, uint32_t target)
{
	uint64_t frequency = __builtin_arm_rsr64("CNTFRQ_EL0");
	uint64_t begin = __builtin_arm_rsr64("CNTVCT_EL0");
	if (frequency == 0 || frequency > UINT64_MAX / 2U) {
		return false;
	}
	while (os_atomic_load(counter, acquire) < target) {
		if (os_atomic_load(&rpi5_tlb_stress_context.errors, acquire) != 0 ||
		    __builtin_arm_rsr64("CNTVCT_EL0") - begin > frequency * 2U) {
			return false;
		}
		delay(100);
	}
	return true;
}

static bool
rpi5_tlb_stress_run(vm_offset_t address, ppnum_t page_a, ppnum_t page_b,
    ppnum_t *mapped_page)
{
	rpi5_tlb_stress_t *stress = &rpi5_tlb_stress_context;
	stress->address = address;
	os_atomic_store(&stress->expected_pa, ptoa(page_a), relaxed);
	os_atomic_store(&stress->expected_writable, true, relaxed);
	for (unsigned int cpu = 1; cpu < 4; cpu++) {
		thread_t thread;
		kern_return_t kr = kernel_thread_start(rpi5_tlb_stress_reader,
		    (void *)(uintptr_t)cpu, &thread);
		if (kr != KERN_SUCCESS) {
			kprintf("RPI5XNU:TLB:FAIL STAGE=STRESS_THREAD CPU=%u KR=%d\n",
			    cpu, kr);
			goto stop;
		}
		thread_deallocate(thread);
		os_atomic_store(&stress->started[cpu], true, release);
	}
	if (!rpi5_tlb_stress_wait(&stress->ready, 3)) {
		kprintf("RPI5XNU:TLB:FAIL STAGE=STRESS_READY\n");
		goto stop;
	}
	os_atomic_store(&stress->epoch, 2, release);
	for (uint32_t round = 0; round <= 64; round++) {
		uint32_t published = 2 + round * 2;
		if (round != 0) {
			ppnum_t next = (round & 1U) ? page_b : page_a;
			os_atomic_store(&stress->epoch, published - 1U, release);
			pmap_remove(kernel_pmap, address, address + PAGE_SIZE);
			*mapped_page = 0;
			kern_return_t kr = pmap_enter(kernel_pmap, address, next,
			    VM_PROT_READ | VM_PROT_WRITE, VM_PROT_NONE,
			    VM_WIMG_USE_DEFAULT, FALSE, PMAP_MAPPING_TYPE_INFER);
			if (kr != KERN_SUCCESS) {
				kprintf("RPI5XNU:TLB:FAIL STAGE=STRESS_REMAP ROUND=%u KR=%d\n",
				    round, kr);
				goto stop;
			}
			*mapped_page = next;
			if (round & 1U) {
				pmap_protect(kernel_pmap, address, address + PAGE_SIZE,
				    VM_PROT_READ);
			}
			os_atomic_store(&stress->expected_pa, ptoa(next), release);
			os_atomic_store(&stress->expected_writable,
			    (round & 1U) == 0, release);
			os_atomic_store(&stress->epoch, published, release);
		}
		for (unsigned int cpu = 1; cpu < 4; cpu++) {
			if (!rpi5_tlb_stress_wait(&stress->seen[cpu], published)) {
				kprintf("RPI5XNU:TLB:FAIL STAGE=STRESS_STALE ROUND=%u CPU=%u ERRORS=%u\n",
				    round, cpu, os_atomic_load(&stress->errors, acquire));
				goto stop;
			}
		}
	}
	os_atomic_store(&stress->stop, true, release);
	for (unsigned int cpu = 1; cpu < 4; cpu++) {
		uint32_t attempts = 0;
		while (!os_atomic_load(&stress->done[cpu], acquire) && attempts++ < 10000) {
			delay(100);
		}
		if (!os_atomic_load(&stress->done[cpu], acquire)) {
			rpi5_tlb_stress_timed_out = true;
			return false;
		}
	}
	return os_atomic_load(&stress->errors, acquire) == 0;
stop:
	os_atomic_store(&stress->stop, true, release);
	for (unsigned int cpu = 1; cpu < 4; cpu++) {
		uint32_t attempts = 0;
		while (!os_atomic_load(&stress->done[cpu], acquire) &&
		    os_atomic_load(&stress->started[cpu], acquire) &&
		    attempts++ < 10000) {
			delay(100);
		}
		if (os_atomic_load(&stress->started[cpu], acquire) &&
		    !os_atomic_load(&stress->done[cpu], acquire)) {
			rpi5_tlb_stress_timed_out = true;
		}
	}
	return false;
}

static void
rpi5_tlb_read_on_target(void *parameter)
{
	rpi5_tlb_observation_t *test = parameter;
	unsigned int cpu = getCpuDatap()->cpu_number;
	if (cpu > 0 && cpu < 4) {
		test->observed[cpu] = *test->address;
		os_atomic_store(&test->done[cpu], test->sequence, release);
	}
}

static void
rpi5_tlb_write_preflight_on_target(void *parameter)
{
	rpi5_tlb_observation_t *test = parameter;
	unsigned int cpu = getCpuDatap()->cpu_number;
	if (cpu > 0 && cpu < 4) {
		test->observed[cpu] = mmu_kvtop_wpreflight((vm_offset_t)test->address);
		os_atomic_store(&test->done[cpu], test->sequence, release);
	}
}

static bool
rpi5_tlb_observe(rpi5_tlb_observation_t *test, uint32_t sequence,
    uint64_t expected, bool permission)
{
	test->sequence = sequence;
	for (unsigned int cpu = 1; cpu < 4; cpu++) {
		os_atomic_store(&test->done[cpu], 0, relaxed);
		kern_return_t kr = cpu_xcall((int)cpu, permission ?
		    rpi5_tlb_write_preflight_on_target : rpi5_tlb_read_on_target, test);
		if (kr != KERN_SUCCESS) {
			/* Do not release the callback's VA on an ambiguous enqueue failure. */
			rpi5_tlb_xcall_timed_out = true;
			kprintf("RPI5XNU:TLB:FAIL STAGE=XCALL CPU=%u KR=%d\n", cpu, kr);
			return false;
		}
		unsigned int attempts = 0;
		while (os_atomic_load(&test->done[cpu], acquire) != sequence &&
		    attempts++ < 2000) {
			delay(1000);
		}
		if (os_atomic_load(&test->done[cpu], acquire) != sequence) {
			rpi5_tlb_xcall_timed_out = true;
			kprintf("RPI5XNU:TLB:FAIL STAGE=TIMEOUT CPU=%u SEQ=%u\n",
			    cpu, sequence);
			return false;
		}
		if (test->observed[cpu] != expected) {
			kprintf("RPI5XNU:TLB:FAIL STAGE=STALE CPU=%u SEQ=%u GOT=0x%llx WANT=0x%llx\n",
			    cpu, sequence, test->observed[cpu], expected);
			return false;
		}
	}
	return true;
}

static void
rpi5_tlb_test_thread(void *parameter __unused, wait_result_t result __unused)
{
	uint64_t trial_begin = __builtin_arm_rsr64("CNTVCT_EL0");
	/* This test must originate from the boot core, not a secondary that
	 * happens to run the newly created worker first. */
	thread_bind(master_processor);
	thread_block(THREAD_CONTINUE_NULL);

	unsigned int attempts = 0;
	while ((os_atomic_load(&ml_cpu_up_processors, acquire) & UINT64_C(0xf)) !=
	    UINT64_C(0xf) && attempts++ < 1000) {
		delay(10000);
	}
	if ((os_atomic_load(&ml_cpu_up_processors, acquire) & UINT64_C(0xf)) !=
	    UINT64_C(0xf)) {
		os_atomic_store(&rpi5_tlb_status, 3, release);
		kprintf("RPI5XNU:TLB:FAIL STAGE=ONLINE\n");
		kprintf("RPI5XNU:TLB:FAIL\n");
		thread_terminate_self();
	}

	vm_offset_t first = 0, second = 0;
	kern_return_t kr = kmem_alloc(kernel_map, &first, PAGE_SIZE,
	    KMA_ZERO | KMA_KOBJECT, VM_KERN_MEMORY_DIAG);
	if (kr != KERN_SUCCESS) {
		os_atomic_store(&rpi5_tlb_status, 3, release);
		kprintf("RPI5XNU:TLB:FAIL STAGE=ALLOC_A KR=%d\n", kr);
		kprintf("RPI5XNU:TLB:FAIL\n");
		thread_terminate_self();
	}
	kr = kmem_alloc(kernel_map, &second, PAGE_SIZE,
	    KMA_ZERO | KMA_KOBJECT, VM_KERN_MEMORY_DIAG);
	if (kr != KERN_SUCCESS) {
		os_atomic_store(&rpi5_tlb_status, 3, release);
		kprintf("RPI5XNU:TLB:FAIL STAGE=ALLOC_B KR=%d\n", kr);
		kprintf("RPI5XNU:TLB:FAIL\n");
		kmem_free(kernel_map, first, PAGE_SIZE);
		thread_terminate_self();
	}

	const uint64_t value_a = UINT64_C(0x56c0aa11d4b372e9);
	const uint64_t value_b = UINT64_C(0xa93f55ee2b4c8d16);
	*(volatile uint64_t *)first = value_a;
	*(volatile uint64_t *)second = value_b;
	ppnum_t page_a = pmap_find_phys(kernel_pmap, first);
	ppnum_t page_b = pmap_find_phys(kernel_pmap, second);
	rpi5_tlb_observation_t *test = &rpi5_tlb_test_observation;
	test->address = (volatile uint64_t *)first;
	bool passed = page_a != 0 && page_b != 0 && page_a != page_b;
	ppnum_t mapped_page = page_a;
	bool mapping_writable = true;
	if (!passed) {
		kprintf("RPI5XNU:TLB:FAIL STAGE=PHYS A=%u B=%u\n", page_a, page_b);
	}
	if (passed) {
		passed = rpi5_tlb_observe(test, 1, value_a, false);
	}
	for (uint32_t round = 1; passed && round <= 16; round++) {
		ppnum_t next = (round & 1) ? page_b : page_a;
		uint64_t expected = (round & 1) ? value_b : value_a;
		pmap_remove(kernel_pmap, first, first + PAGE_SIZE);
		mapped_page = 0;
		kr = pmap_enter(kernel_pmap, first, next, VM_PROT_READ | VM_PROT_WRITE,
		    VM_PROT_NONE, VM_WIMG_USE_DEFAULT, FALSE, PMAP_MAPPING_TYPE_INFER);
		if (kr != KERN_SUCCESS) {
			kprintf("RPI5XNU:TLB:FAIL STAGE=REMAP ROUND=%u KR=%d\n", round, kr);
			passed = false;
			break;
		}
		mapped_page = next;
		passed = rpi5_tlb_observe(test, round + 1, expected, false);
	}
	for (uint32_t round = 0; passed && round < 8; round++) {
		uint32_t sequence = 18 + round * 3;
		passed = rpi5_tlb_observe(test, sequence, ptoa(page_a), true);
		if (!passed) {
			break;
		}
		pmap_protect(kernel_pmap, first, first + PAGE_SIZE, VM_PROT_READ);
		mapping_writable = false;
		passed = rpi5_tlb_observe(test, sequence + 1, 0, true);
		if (!passed) {
			break;
		}
		pmap_remove(kernel_pmap, first, first + PAGE_SIZE);
		mapped_page = 0;
		kr = pmap_enter(kernel_pmap, first, page_a,
		    VM_PROT_READ | VM_PROT_WRITE, VM_PROT_NONE,
		    VM_WIMG_USE_DEFAULT, FALSE, PMAP_MAPPING_TYPE_INFER);
		if (kr != KERN_SUCCESS) {
			kprintf("RPI5XNU:TLB:FAIL STAGE=PERMISSION_RESTORE ROUND=%u KR=%d\n",
			    round, kr);
			passed = false;
			break;
		}
		mapped_page = page_a;
		mapping_writable = true;
		passed = rpi5_tlb_observe(test, sequence + 2, ptoa(page_a), true);
	}
	if (passed) {
		passed = rpi5_tlb_stress_run(first, page_a, page_b, &mapped_page);
	}
	if (rpi5_tlb_xcall_timed_out || rpi5_tlb_stress_timed_out) {
		/* A delayed callback may still dereference the test VA. Keep both
		 * mappings and the static callback context alive until reset. */
		os_atomic_store(&rpi5_tlb_status, 3, release);
		kprintf("RPI5XNU:TLB:FAIL STAGE=CALLBACK_TIMEOUT\n");
		kprintf("RPI5XNU:TLB:FAIL\n");
		thread_terminate_self();
	}
	if (mapped_page != page_a || !mapping_writable) {
		if (mapped_page != 0) {
			pmap_remove(kernel_pmap, first, first + PAGE_SIZE);
		}
		kr = pmap_enter(kernel_pmap, first, page_a, VM_PROT_READ | VM_PROT_WRITE,
		    VM_PROT_NONE, VM_WIMG_USE_DEFAULT, FALSE, PMAP_MAPPING_TYPE_INFER);
		if (kr != KERN_SUCCESS) {
			kprintf("RPI5XNU:TLB:FAIL STAGE=RESTORE KR=%d\n", kr);
			passed = false;
			mapped_page = 0;
		} else {
			mapped_page = page_a;
			mapping_writable = true;
		}
	}
	if (mapped_page == page_a) {
		kmem_free(kernel_map, first, PAGE_SIZE);
	}
	kmem_free(kernel_map, second, PAGE_SIZE);
	kprintf("RPI5XNU:TLB:TIMING TICKS=%llu FREQ=%llu\n",
	    __builtin_arm_rsr64("CNTVCT_EL0") - trial_begin,
	    __builtin_arm_rsr64("CNTFRQ_EL0"));
	if (passed) {
		kprintf("RPI5XNU:TLB:DETAIL REMAP_ROUNDS=16 PERMISSION_ROUNDS=8 STRESS_ROUNDS=64 STRESS_PERMISSION_ROUNDS=32 CPUS=1-3\n");
		kprintf("RPI5XNU:TLB:PASS\n");
	} else {
		kprintf("RPI5XNU:TLB:FAIL\n");
	}
	/* The coordinator must not start USER_TLB before this PASS/FAIL is logged. */
	os_atomic_store(&rpi5_tlb_status, passed ? 2 : 3, release);
	thread_terminate_self();
}

void
rpi5_gate3_start_tlb_test(void)
{
	if (!os_atomic_cmpxchg(&rpi5_tlb_started, false, true, acq_rel)) {
		return;
	}
	os_atomic_store(&rpi5_tlb_status, 1, release);
	thread_t worker;
	kern_return_t kr = kernel_thread_start(rpi5_tlb_test_thread, NULL, &worker);
	if (kr != KERN_SUCCESS) {
		os_atomic_store(&rpi5_tlb_status, 3, release);
		kprintf("RPI5XNU:TLB:FAIL STAGE=THREAD KR=%d\n", kr);
		kprintf("RPI5XNU:TLB:FAIL\n");
		return;
	}
	thread_deallocate(worker);
}

uint32_t
rpi5_gate3_tlb_status(void)
{
	return os_atomic_load(&rpi5_tlb_status, acquire);
}

#endif /* ARM64_BOARD_CONFIG_BCM2712 && DEVELOPMENT */
