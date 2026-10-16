/* SPDX-License-Identifier: BSD-2-Clause */
#include <dispatch/dispatch.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

/* Explicit native-only counter double. Target uses the actual XNU commpage. */
uintptr_t rpi5_native_once_generation;
static dispatch_once_t predicates[128];
static unsigned calls[128], values[128][4];
static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t condition = PTHREAD_COND_INITIALIZER;
static unsigned ready;

static void *worker(void *argument)
{
    (void)argument;
    pthread_mutex_lock(&mutex);
    ready++;
    pthread_cond_broadcast(&condition);
    while (ready < 8) pthread_cond_wait(&condition, &mutex);
    pthread_mutex_unlock(&mutex);
    for (unsigned i = 0; i < 128; i++) {
        dispatch_once(&predicates[i], ^{
            calls[i]++;
            for (unsigned j = 0; j < 4; j++) values[i][j] = i * 17 + j + 1;
            if (i % 16 == 0) usleep(1000);
        });
        for (unsigned j = 0; j < 4; j++)
            if (values[i][j] != i * 17 + j + 1) return (void *)1;
    }
    return NULL;
}

static void count_context(void *context) { (*(unsigned *)context)++; }

int main(void)
{
    pthread_t threads[8];
    for (unsigned i = 0; i < 8; i++)
        if (pthread_create(&threads[i], NULL, worker, NULL)) return 1;
    for (unsigned i = 0; i < 8; i++) {
        void *result;
        if (pthread_join(threads[i], &result) || result) return 2;
    }
    for (unsigned i = 0; i < 128; i++) if (calls[i] != 1) return 3;
    /* Advance only after all workers join: no artificial concurrent mutation
     * of the original volatile commpage-read expression in this host fixture. */
    rpi5_native_once_generation = 4;
    for (unsigned i = 0; i < 128; i++) dispatch_once(&predicates[i], ^{ _exit(80); });
    dispatch_once_t function_predicate = 0;
    unsigned context = 0;
    for (unsigned i = 0; i < 16; i++) dispatch_once_f(&function_predicate, &context, count_context);
    if (context != 1) return 4;
    pid_t child = fork();
    if (child < 0) return 5;
    if (!child) {
        struct rlimit limit = {0, 0};
        if (setrlimit(RLIMIT_CORE, &limit)) _exit(81);
        signal(SIGILL, SIG_DFL); signal(SIGTRAP, SIG_DFL);
        static dispatch_once_t recursive;
        dispatch_once(&recursive, ^{ dispatch_once(&recursive, ^{ _exit(82); }); });
        _exit(83);
    }
    int status;
    if (waitpid(child, &status, 0) != child || !WIFSIGNALED(status) ||
        (WTERMSIG(status) != SIGILL && WTERMSIG(status) != SIGTRAP)) return 6;
    puts("APPLE_DISPATCH_ONCE PASS THREADS=8 PREDICATES=128 PUBLICATION_WORDS=512 CONTEXT=1 RECURSIVE_TRAP=1 NATIVE_COUNTER_DOUBLE");
    return 0;
}
