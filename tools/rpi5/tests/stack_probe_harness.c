/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <signal.h>
#include <stdint.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

extern int rpi5_test_probe(void *stack_top, uint64_t size);

int main(void)
{
	size_t page = (size_t)sysconf(_SC_PAGESIZE);
	assert(page >= 4096 && page % 4096 == 0);
	char *area = mmap(NULL, 6 * page, PROT_READ | PROT_WRITE,
	    MAP_PRIVATE | MAP_ANON, -1, 0);
	assert(area != MAP_FAILED);
	assert(mprotect(area + 2 * page, page, PROT_NONE) == 0);
	void *top = area + 6 * page;
	uint64_t valid[] = {0, 1, 15, 16, 4095, 4096, 4097, page, 3 * page};
	for (size_t i = 0; i < sizeof(valid) / sizeof(valid[0]); i++) {
		assert(rpi5_test_probe(top, valid[i]) == 0);
	}
	/* Probe loads must not modify either side of the protected page. */
	for (size_t i = 0; i < 6 * page; i++) {
		if (i < 2 * page || i >= 3 * page) assert(area[i] == 0);
	}
	/* The second request ends below the guard in readable memory. A probe
	 * that checked only the endpoint would miss the intervening guard.
	 */
	uint64_t invalid[] = {3 * page + 1, 5 * page};
	for (size_t i = 0; i < sizeof(invalid) / sizeof(invalid[0]); i++) {
		pid_t child = fork();
		assert(child >= 0);
		if (child == 0) {
			struct rlimit limit = {0, 0};
			if (setrlimit(RLIMIT_CORE, &limit) != 0) _exit(3);
			(void)rpi5_test_probe(top, invalid[i]);
			_exit(2);
		}
		int status;
		assert(waitpid(child, &status, 0) == child);
		assert(WIFSIGNALED(status));
		assert(WTERMSIG(status) == SIGSEGV || WTERMSIG(status) == SIGBUS);
	}
	assert(munmap(area, 6 * page) == 0);
	return 0;
}
