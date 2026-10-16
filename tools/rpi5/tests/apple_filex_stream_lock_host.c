/* SPDX-License-Identifier: BSD-2-Clause */

#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdatomic.h>
#include <string.h>
#include <unistd.h>

#include <stdio.h>
#include "local.h"

extern void apple_candidate_flockfile(FILE *);
extern int apple_candidate_ftrylockfile(FILE *);
extern void apple_candidate_funlockfile(FILE *);
extern int apple_candidate_fwide(FILE *, int);

enum {
	worker_count = 6,
	worker_iterations = 4096,
};

static FILE candidate_stream;
static struct __sFILEX candidate_extra;
static uint64_t protected_count;
static atomic_int worker_failure;

static void *
worker(void *argument)
{
	intptr_t index = (intptr_t)argument;
	int wanted_errno = EAGAIN + (int)index;

	for (int iteration = 0; iteration < worker_iterations; ++iteration) {
		errno = wanted_errno;
		apple_candidate_flockfile(&candidate_stream);
		apple_candidate_flockfile(&candidate_stream);
		if (apple_candidate_ftrylockfile(&candidate_stream) != 0)
			atomic_store(&worker_failure, 1);
		++protected_count;
		apple_candidate_funlockfile(&candidate_stream);
		apple_candidate_funlockfile(&candidate_stream);
		apple_candidate_funlockfile(&candidate_stream);
		if (errno != wanted_errno)
			atomic_store(&worker_failure, 1);
	}
	return NULL;
}

int
main(void)
{
	static const char success[] =
	    "APPLE_FILEX_HOST PASS THREADS=6 ITERATIONS=4096 RECURSIVE=3 "
	    "ORIENTATION=1 ERRNO=1 HOST_ONLY\n";
	pthread_t workers[worker_count];

	memset(&candidate_stream, 0, sizeof(candidate_stream));
	memset(&candidate_extra, 0, sizeof(candidate_extra));
	candidate_stream._extra = &candidate_extra;
	candidate_extra.fl_mutex =
	    (pthread_mutex_t)PTHREAD_RECURSIVE_MUTEX_INITIALIZER;

	if (apple_candidate_fwide(&candidate_stream, 1) != 1 ||
	    apple_candidate_fwide(&candidate_stream, -1) != 1)
		return 20;

	for (intptr_t index = 0; index < worker_count; ++index) {
		if (pthread_create(&workers[index], NULL, worker,
		    (void *)index) != 0)
			return 21;
	}
	for (int index = 0; index < worker_count; ++index) {
		if (pthread_join(workers[index], NULL) != 0)
			return 22;
	}
	if (atomic_load(&worker_failure) ||
	    protected_count != (uint64_t)worker_count * worker_iterations)
		return 23;
	if (write(STDOUT_FILENO, success, sizeof(success) - 1) !=
	    (ssize_t)(sizeof(success) - 1))
		return 24;
	return 0;
}
