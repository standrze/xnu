/* SPDX-License-Identifier: BSD-2-Clause
 * Static executable entry adapter. The original Apple command receives the
 * actual argc/argv and original Apple getopt/err see the same real argv.
 */
#include <errno.h>
#include <pthread.h>
static char **command_argv;
extern int darwin_network_command_main(int, char **);

/* Real process-local storage for this single-thread executable. Thread creation
 * and pthread_exit are unavailable; process exit reclaims all process memory.
 * Key deletion does not run destructors, as specified by the pthread API.
 */
static struct { int used; void *value; void (*destructor)(void *); } keys[16];

int pthread_key_create(pthread_key_t *key, void (*destructor)(void *))
{
    if (!key) return EINVAL;
    for (unsigned int i = 0; i < 16; i++) {
        if (keys[i].used) continue;
        keys[i].used = 1;
        keys[i].value = 0;
        keys[i].destructor = destructor;
        *key = (pthread_key_t)(i + 1);
        return 0;
    }
    return EAGAIN;
}

int pthread_setspecific(pthread_key_t key, const void *value)
{
    if (key < 1 || key > 16 || !keys[key - 1].used) return EINVAL;
    keys[key - 1].value = (void *)value;
    return 0;
}

void *pthread_getspecific(pthread_key_t key)
{
    if (key < 1 || key > 16 || !keys[key - 1].used) return 0;
    return keys[key - 1].value;
}

int pthread_key_delete(pthread_key_t key)
{
    if (key < 1 || key > 16 || !keys[key - 1].used) return EINVAL;
    keys[key - 1].used = 0;
    keys[key - 1].value = 0;
    keys[key - 1].destructor = 0;
    return 0;
}

char ***_NSGetArgv(void)
{
    return &command_argv;
}

int zsh_main(int argc, char **argv)
{
    command_argv = argv;
    return darwin_network_command_main(argc, argv);
}
