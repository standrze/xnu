/* SPDX-License-Identifier: BSD-2-Clause
 * Focused host check for project argv/key ABI glue, not guest route evidence.
 * Test builds rename pthread symbols so host runtime keys are never intercepted.
 */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
extern char ***_NSGetArgv(void);
extern int zsh_main(int, char **);
static int destructor_calls;

static void destructor(void *value)
{
    (void)value;
    destructor_calls++;
}

int darwin_network_command_main(int argc, char **argv)
{
    assert(*_NSGetArgv() == argv);
    return argc;
}

int main(void)
{
    char *argv[] = {"route", "-n", "get", "default", NULL};
    assert(zsh_main(4, argv) == 4);
    pthread_key_t keys[16], extra;
    int values[16];
    for (int i = 0; i < 16; i++) {
        values[i] = i;
        assert(pthread_key_create(&keys[i], destructor) == 0);
        assert(pthread_getspecific(keys[i]) == NULL);
        assert(pthread_setspecific(keys[i], &values[i]) == 0);
        assert(pthread_getspecific(keys[i]) == &values[i]);
    }
    assert(pthread_key_create(&extra, destructor) == EAGAIN);
    assert(pthread_setspecific(0, values) == EINVAL);
    assert(pthread_getspecific(17) == NULL);
    assert(pthread_key_delete(17) == EINVAL);
    assert(pthread_key_delete(keys[5]) == 0);
    assert(pthread_key_delete(keys[5]) == EINVAL);
    assert(pthread_setspecific(keys[5], values) == EINVAL);
    assert(pthread_key_create(&extra, destructor) == 0);
    assert(pthread_getspecific(extra) == NULL);
    assert(destructor_calls == 0); /* key_delete does not invoke destructors */
    puts("NETWORK_COMMAND_START_OK argv key-storage capacity delete reuse");
    return 0;
}
