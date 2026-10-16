/* SPDX-License-Identifier: BSD-2-Clause */
#include "runtime.h"

static _Noreturn void init_main(void)
{
    long console = rt_open("/dev/console", RT_RDWR);
    if (console < 0) for (;;) rt_sleep(2);
    for (int i = 0; i < 3; i++) if (rt_dup2((int)console, i) < 0) for (;;) rt_sleep(2);
    if (console > 2) rt_close((int)console);
    rt_put(1, "RPI5XNU:INIT:READY\n");
    for (;;) {
        long shell = rt_fork();
        if (shell == 0) {
            char *argv[] = {"/bin/sh", 0};
            char *env[] = {"PATH=/bin", "PWD=/", "HOME=/", "TERM=dumb", 0};
            long result = rt_call(59, (long)argv[0], (long)argv, (long)env, 0, 0, 0);
            rt_error("init exec sh", result); rt_exit(126);
        }
        if (shell < 0) { rt_error("init fork", shell); rt_sleep(2); continue; }
        rt_put(1, "RPI5XNU:INIT:SHELL_PID="); rt_number(1, (unsigned long)shell); rt_put(1, "\n");
        int status;
        long child;
        do { child = rt_wait(-1, &status); } while (child > 0 && child != shell);
        rt_put(1, "RPI5XNU:INIT:RESPAWN\n");
        rt_sleep(1);
    }
}
_Noreturn void user_start(uintptr_t *stack)
{
    if (rt_getpid() == 1) init_main();
    if (stack[0] > 64) rt_exit(126);
    int argc = (int)stack[0]; char **argv = (char **)(stack + 1);
    if (!argc || !argv[0]) rt_exit(126);
    char **env = argv + argc + 1;
    const char *name = rt_basename(argv[0]);
    rt_exit(rt_equal(name, "sh") ? shell_main(argc, argv, env) : utility_main(name, argc, argv, env));
}
