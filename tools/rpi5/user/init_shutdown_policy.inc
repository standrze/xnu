/* SPDX-License-Identifier: BSD-2-Clause */
/* Project PID1 only. Genuine Darwin48/52/7 ABI through the existing rt_call.
 * No handler, trampoline, SIG_IGN, thread library or kernel exception.
 * A TERM arriving during fork can cross that ONE in-flight fork; after its
 * first observation this process never forks or exits again. */
#define INIT_TERM_MASK (UINT32_C(1) << 14)
#define INIT_SIG_BLOCK 1
#define INIT_SIG_SETMASK 3
#define INIT_WNOHANG 1

static _Noreturn void init_stopped(const char *reason)
{
    rt_put(1, reason);
    for (;;) {
        /* Bound each reap pass so an orphan stream cannot starve sleep. The
         * original kernel ultimately suspends init after shutting down peers. */
        for (unsigned i = 0; i < 64; i++) {
            int status = 0;
            long child = rt_call(7, -1, (long)&status, INIT_WNOHANG, 0, 0, 0);
            if (child <= 0) break;
        }
        (void)rt_sleep(1);
    }
}

static void init_check_shutdown(void)
{
    uint32_t pending = 0;
    if (rt_call(52, (long)&pending, 0, 0, 0, 0, 0) != 0)
        init_stopped("RPI5XNU:INIT:STOPPING SIGNAL_QUERY_FAILED\n");
    if (pending & INIT_TERM_MASK)
        init_stopped("RPI5XNU:INIT:STOPPING SIGTERM NO_RESPAWN\n");
}

static void init_pause(void)
{
    init_check_shutdown();
    long result = rt_sleep(1);
    init_check_shutdown();
    if (result != 0 && result != -4)
        init_stopped("RPI5XNU:INIT:STOPPING SLEEP_FAILED\n");
}

static _Noreturn void init_main(void)
{
    uint32_t block = INIT_TERM_MASK, saved = 0, actual = 0;
    /* Install protection before any readiness, console opening or child.
     * An installation error cannot make a runnable shell or exit PID1. */
    if (rt_call(48, INIT_SIG_BLOCK, (long)&block, (long)&saved, 0, 0, 0) != 0)
        for (;;) (void)rt_sleep(1);
    if (rt_call(48, INIT_SIG_BLOCK, 0, (long)&actual, 0, 0, 0) != 0 ||
            actual != (saved | INIT_TERM_MASK))
        init_stopped("RPI5XNU:INIT:STOPPING MASK_VERIFY_FAILED\n");
    init_check_shutdown();
    long console = rt_open("/dev/console", RT_RDWR);
    if (console < 0) init_stopped("RPI5XNU:INIT:STOPPING CONSOLE_FAILED\n");
    for (int i = 0; i < 3; i++)
        if (rt_dup2((int)console, i) < 0)
            init_stopped("RPI5XNU:INIT:STOPPING CONSOLE_FAILED\n");
    if (console > 2) (void)rt_close((int)console);
    init_check_shutdown();
    rt_put(1, "RPI5XNU:INIT:SHUTDOWN_READY SIGTERM_BLOCKED POLLED NO_RESPAWN_AFTER_OBSERVATION\n");
    rt_put(1, "RPI5XNU:INIT:READY\n");
    for (;;) {
        init_check_shutdown();
        long shell = rt_fork();
        if (shell == 0) {
            /* fork inherits the blocked mask; exec preserves it. Restore the
             * complete previous mask, not just the TERM bit, before exec. */
            uint32_t child_mask = 0;
            if (rt_call(48, INIT_SIG_SETMASK, (long)&saved, 0, 0, 0, 0) != 0 ||
                    rt_call(48, INIT_SIG_BLOCK, 0, (long)&child_mask, 0, 0, 0) != 0 ||
                    child_mask != saved)
                rt_exit(126);
            char *argv[] = {"/bin/sh", 0};
            char *env[] = {"PATH=/bin", "PWD=/", "HOME=/", "TERM=dumb", 0};
            long result = rt_call(59, (long)argv[0], (long)argv, (long)env, 0, 0, 0);
            rt_error("init exec sh", result); rt_exit(126);
        }
        init_check_shutdown();
        if (shell < 0) { rt_error("init fork", shell); init_pause(); continue; }
        rt_put(1, "RPI5XNU:INIT:SHELL_PID="); rt_number(1, (unsigned long)shell); rt_put(1, "\n");
        int done = 0;
        while (!done) {
            init_check_shutdown();
            for (unsigned i = 0; i < 64; i++) {
                int status = 0;
                long child = rt_call(7, -1, (long)&status, INIT_WNOHANG, 0, 0, 0);
                init_check_shutdown();
                if (child == shell || child == -10) { done = 1; break; }
                if (child == 0) break;
                if (child < 0 && child != -4)
                    init_stopped("RPI5XNU:INIT:STOPPING WAIT_FAILED\n");
            }
            if (!done) init_pause();
        }
        init_check_shutdown();
        rt_put(1, "RPI5XNU:INIT:RESPAWN\n");
        init_pause();
    }
}
