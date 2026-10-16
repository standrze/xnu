/* SPDX-License-Identifier: BSD-2-Clause
 * Selected static-runtime startup, not a replacement claim for all libSystem.
 * Genuine mach_init/DYLD owns the initial pthread; normal __pthread_init owns
 * registration, keys, locks, main stack, pointer munging and real thread port.
 */
#include <pthread.h>
#include <pthread/private.h>
#include "exports_internal.h"
#include "_libkernel_init.h"
#include <stdlib.h>
#include <unistd.h>
#include "pthread_static_entry_core.h"

extern char **environ, *__progname;
extern int rpi5_pthread_smoke_main(int, char **);
unsigned rpi5_pthread_startup_stage;
static int process_argc;
static char **process_argv;
char ***_NSGetArgv(void) { return &process_argv; }
int *_NSGetArgc(void) { return &process_argc; }
char **_NSGetProgname(void) { return &__progname; }

static int has_key(char **vector, const char *key)
{
    for (; *vector; vector++) {
        const char *s = *vector, *k = key;
        while (*k && *k == *s) { k++; s++; }
        if (!*k && *s == '=' && s[1]) return 1;
    }
    return 0;
}

_Noreturn void darwin_static_start(uintptr_t *stack)
{
    struct rpi5_process_vectors vectors;
    /* XNU supplied trusted initial stack; bounds exclude unbounded scans. */
    if (rpi5_process_vectors_parse(stack, 8192, &vectors)) _exit(120);
    process_argc = vectors.argc;
    process_argv = vectors.argv;
    environ = vectors.envp;
    __progname = vectors.argc ? vectors.argv[0] : (char *)"pthreadprobe";
    /* Version 4 is the highest complete real callback set in this runtime.
     * There is no dynamic symbol resolver or invented typed-malloc service. */
    static const struct _libkernel_functions kernel = {
        .version = 4, .dlsym = 0, .malloc = malloc, .free = free,
        .realloc = realloc, ._pthread_exit_if_canceled = _pthread_exit_if_canceled,
        .pthread_clear_qos_tsd = _pthread_clear_qos_tsd,
        .pthread_current_stack_contains_np = pthread_current_stack_contains_np,
    };
    static const struct _libpthread_functions threads = {
        .version = 2, .exit = exit, .malloc = malloc, .free = free,
    };
    __libkernel_init(&kernel, (const char **)environ,
                     (const char **)vectors.apple, 0);
    rpi5_pthread_startup_stage = 1;
    (void)write(1, "PTHREAD:KERNEL_READY\n", 21);
    if (!has_key(vectors.apple, "main_stack") ||
        !has_key(vectors.apple, "ptr_munge") ||
        !has_key(vectors.apple, "th_port")) _exit(121);
    /* Original libplatform's VARIANT_STATIC product has no platform-init
     * entry. Its selected providers are statically bound, not fake callbacks. */
    if (__pthread_init(&threads, (const char **)environ,
                       (const char **)vectors.apple, 0)) _exit(122);
    rpi5_pthread_startup_stage = 2;
    (void)write(1, "PTHREAD:MAIN_READY\n", 19);
    /* Preserved selected libc is static/lazy; allocator frontend serializes
     * actual zone creation. This is not modern Libc/libmalloc init coverage. */
    void *allocation = malloc(32);
    if (!allocation) _exit(123);
    free(allocation);
    __pthread_late_init((const char **)environ, (const char **)vectors.apple, 0);
    extern rpi5_initializer begin[] __asm("section$start$__DATA$__mod_init_func");
    extern rpi5_initializer end[] __asm("section$end$__DATA$__mod_init_func");
    if (rpi5_run_initializers(begin, end)) _exit(124);
    rpi5_pthread_startup_stage = 3;
    exit(rpi5_pthread_smoke_main(vectors.argc, vectors.argv));
}
