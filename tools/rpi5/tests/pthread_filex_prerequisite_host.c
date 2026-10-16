/* SPDX-License-Identifier: BSD-2-Clause
 * Host behavioral oracle for the FILEX pthread prerequisite.
 *
 * This deliberately runs the host's pthread runtime.  It defines the behavior
 * the Raspberry Pi target must later reproduce; it is not target evidence.
 */
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>

enum { THREADS = 6, ITERATIONS = 4096 };

static pthread_mutex_t contention_lock = PTHREAD_MUTEX_INITIALIZER;
static unsigned contention_counter;
static int *errno_slots[THREADS];

static void *contention_worker(void *argument)
{
	uintptr_t index = (uintptr_t)argument;
	errno_slots[index] = &errno;
	errno = 200 + (int)index;
	for (unsigned i = 0; i < ITERATIONS; i++) {
		if (pthread_mutex_lock(&contention_lock)) return (void *)1;
		contention_counter++;
		if (pthread_mutex_unlock(&contention_lock)) return (void *)2;
		if (errno != 200 + (int)index) return (void *)3;
	}
	return 0;
}

static int atfork_sequence;
static void atfork_prepare(void) { atfork_sequence = atfork_sequence * 10 + 1; }
static void atfork_parent(void) { atfork_sequence = atfork_sequence * 10 + 2; }
static void atfork_child(void) { atfork_sequence = atfork_sequence * 10 + 3; }

static pthread_mutex_t cancel_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cancel_condition = PTHREAD_COND_INITIALIZER;
static int cancel_ready;
static int cancel_cleanup_ran;

static void cancel_unlock(void *argument)
{
	pthread_mutex_t *lock = argument;
	cancel_cleanup_ran = 1;
	(void)pthread_mutex_unlock(lock);
}

static void *cancel_worker(void *unused)
{
	(void)unused;
	if (pthread_mutex_lock(&cancel_lock)) return (void *)4;
	pthread_cleanup_push(cancel_unlock, &cancel_lock);
	cancel_ready = 1;
	if (pthread_cond_broadcast(&cancel_condition)) abort();
	for (;;) {
		int error = pthread_cond_wait(&cancel_condition, &cancel_lock);
		if (error) abort();
	}
	pthread_cleanup_pop(1);
	return 0;
}

static int recursive_case(void)
{
	pthread_mutexattr_t attributes;
	pthread_mutex_t lock;
	if (pthread_mutexattr_init(&attributes) ||
	    pthread_mutexattr_settype(&attributes, PTHREAD_MUTEX_RECURSIVE) ||
	    pthread_mutex_init(&lock, &attributes) ||
	    pthread_mutexattr_destroy(&attributes)) return 10;
	if (pthread_mutex_lock(&lock) || pthread_mutex_lock(&lock) ||
	    pthread_mutex_unlock(&lock) || pthread_mutex_unlock(&lock) ||
	    pthread_mutex_destroy(&lock)) return 11;
	return 0;
}

static int contention_and_tls_case(void)
{
	pthread_t threads[THREADS];
	for (uintptr_t i = 0; i < THREADS; i++) {
		if (pthread_create(&threads[i], 0, contention_worker, (void *)i)) return 20;
	}
	for (unsigned i = 0; i < THREADS; i++) {
		void *result = 0;
		if (pthread_join(threads[i], &result) || result) return 21;
		if (!errno_slots[i] || errno_slots[i] == &errno) return 22;
		for (unsigned j = 0; j < i; j++) {
			if (errno_slots[i] == errno_slots[j]) return 23;
		}
	}
	return contention_counter == THREADS * ITERATIONS ? 0 : 24;
}

static int atfork_case(void)
{
	int descriptors[2];
	if (pipe(descriptors) || pthread_atfork(atfork_prepare, atfork_parent,
	    atfork_child)) return 30;
	pid_t child = fork();
	if (child < 0) return 31;
	if (child == 0) {
		close(descriptors[0]);
		int value = atfork_sequence;
		ssize_t count = write(descriptors[1], &value, sizeof(value));
		_exit(count == sizeof(value) && value == 13 ? 0 : 32);
	}
	close(descriptors[1]);
	int child_sequence = 0, status = 0;
	ssize_t count = read(descriptors[0], &child_sequence, sizeof(child_sequence));
	close(descriptors[0]);
	if (waitpid(child, &status, 0) != child || count != sizeof(child_sequence) ||
	    child_sequence != 13 || atfork_sequence != 12 || !WIFEXITED(status) ||
	    WEXITSTATUS(status)) return 33;
	return 0;
}

static int cancellation_case(void)
{
	pthread_t thread;
	if (pthread_mutex_lock(&cancel_lock)) return 40;
	if (pthread_create(&thread, 0, cancel_worker, 0)) return 41;
	while (!cancel_ready) {
		if (pthread_cond_wait(&cancel_condition, &cancel_lock)) return 42;
	}
	if (pthread_mutex_unlock(&cancel_lock) || pthread_cancel(thread)) return 43;
	void *result = 0;
	if (pthread_join(thread, &result) || result != PTHREAD_CANCELED ||
	    !cancel_cleanup_ran) return 44;
	if (pthread_mutex_trylock(&cancel_lock)) return 45;
	if (pthread_mutex_unlock(&cancel_lock)) return 46;
	return 0;
}

int main(void)
{
	int result;
	if ((result = recursive_case()) || (result = contention_and_tls_case()) ||
	    (result = atfork_case()) || (result = cancellation_case())) return result;
	printf("PTHREAD_FILEX_HOST_ORACLE PASS RECURSIVE=1 CONTENTION=%u "
	    "TLS_ERRNO=%u ATFORK=1 CANCEL=1 HOST_ONLY\n",
	    contention_counter, THREADS);
	return 0;
}
