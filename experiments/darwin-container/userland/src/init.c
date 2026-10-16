/* SPDX-License-Identifier: BSD-2-Clause */
#include "runtime.h"
#ifdef DARWIN_AGENT_INIT
#include "agent_protocol.h"
#endif

/* Darwin signal.h/syscalls.master: a 32-bit sigset_t, SIGTERM 15,
 * sigprocmask 48 (SIG_BLOCK 1 / SIG_SETMASK 3), sigpending 52.
 * Keep SIGTERM pending in PID1 while normal shutdown kills the shell and
 * wakes wait4. Never exit or respawn after observing that shutdown request.
 * This avoids requiring a signal trampoline or sigreturn in this runtime.
 */
static const uint32_t shutdown_mask = UINT32_C(1) << (15 - 1);

static void init_check_shutdown(void)
{
    uint32_t pending = 0;
    long result = rt_call(52, (long)&pending, 0, 0, 0, 0, 0);
    if (result < 0) {
        rt_error("init sigpending", result);
        for (;;) rt_sleep(2);
    }
    if ((pending & shutdown_mask) != 0) {
        rt_put(1, "DARWIN:INIT:SHUTDOWN\n");
        /* kern_shutdown suspends init once other processes are gone. */
        for (;;) rt_sleep(60);
    }
}

static _Noreturn void init_main(void)
{
    long console = rt_open("/dev/console", RT_RDWR);
    if (console < 0) for (;;) rt_sleep(2);
    for (int i = 0; i < 3; i++) if (rt_dup2((int)console, i) < 0) for (;;) rt_sleep(2);
    if (console > 2) rt_close((int)console);
    uint32_t previous_mask = 0;
    long result = rt_call(48, 1, (long)&shutdown_mask, (long)&previous_mask, 0, 0, 0);
    if (result < 0) {
        rt_error("init block SIGTERM", result);
        for (;;) rt_sleep(2);
    }
#ifdef DARWIN_WRITABLE_STORAGE
    if (workload_mount()) {
        rt_put(2, "DARWIN:STORAGE:FAILED; workload not started\n");
        for (;;) rt_sleep(60);
    }
#endif
#ifdef DARWIN_AUTO_NETWORK
    long network_child = rt_fork();
    if (network_child == 0) {
        result = rt_call(48, 3, (long)&previous_mask, 0, 0, 0, 0);
        if (result < 0) rt_exit(126);
        char *argv[] = {"/bin/dhcpctl", 0};
        char *env[] = {"PATH=/bin:/sbin", "HOME=/data", 0};
        result = rt_call(59, (long)argv[0], (long)argv, (long)env, 0, 0, 0);
        rt_error("init exec dhcpctl", result);
        rt_exit(126);
    }
    int network_status = -1;
    long network_wait = -1;
    if (network_child > 0) {
        do { network_wait = rt_wait(network_child, &network_status); } while (network_wait == -4);
    }
    int network_ready = network_wait == network_child && network_child > 0 && network_status == 0;
    rt_put(1, network_ready ? "DARWIN:WORKSPACE:NETWORK_READY\n" :
                             "DARWIN:WORKSPACE:NETWORK_FAILED; shell remains available\n");
#endif
    rt_put(1, "DARWIN:INIT:READY\n");
    for (;;) {
        init_check_shutdown();
        long shell = rt_fork();
        if (shell == 0) {
            /* Dispositions remain default; do not leak PID1's blocked TERM. */
            result = rt_call(48, 3, (long)&previous_mask, 0, 0, 0, 0);
            if (result < 0) { rt_error("init restore child signals", result); rt_exit(126); }
#ifdef DARWIN_AGENT_INIT
            char *argv[] = {"/sbin/darwin-agent", 0};
#elif defined(DARWIN_ZSH_INIT)
#ifdef DARWIN_WRITABLE_STORAGE
            /* Normal startup enables Apple's history-file load/save path. */
            char *argv[] = {"/bin/zsh", "-i", 0};
#else
            char *argv[] = {"/bin/zsh", "-f", "-i", 0};
#endif
#else
            char *argv[] = {"/bin/sh", 0};
#endif
#ifdef DARWIN_APPLE_USERLAND
#ifdef DARWIN_WRITABLE_STORAGE
#ifdef DARWIN_PTY_INIT
            char *env[] = {"PATH=/bin:/sbin", "PWD=/data", "HOME=/data", "TERM=vt100",
                           "TERMINFO=/etc/terminfo", "HISTFILE=/data/.zsh_history", "HISTSIZE=1000",
                           "SAVEHIST=1000", "PS1=darwin-zsh%# ",
#ifdef DARWIN_AUTO_NETWORK
                           network_ready ? "DARWIN_NETWORK_STATUS=ready" : "DARWIN_NETWORK_STATUS=failed",
#endif
                           0};
#else
            char *env[] = {"PATH=/bin:/sbin", "PWD=/", "HOME=/data", "TERM=dumb",
                           "TERMINFO=/etc/terminfo", "HISTFILE=/data/.zsh_history", "HISTSIZE=1000",
                           "SAVEHIST=1000", "PS1=darwin-zsh%# ", 0};
#endif
#else
            char *env[] = {"PATH=/bin:/sbin", "PWD=/", "HOME=/", "TERM=dumb",
                           "TERMINFO=/etc/terminfo", "PS1=darwin-zsh%# ", 0};
#endif
#else
            char *env[] = {"PATH=/bin", "PWD=/", "HOME=/", "TERM=dumb", 0};
#endif
#ifdef DARWIN_PTY_INIT
            rt_exit(terminal_main(env));
#endif
            result = rt_call(59, (long)argv[0], (long)argv, (long)env, 0, 0, 0);
#ifdef DARWIN_AGENT_INIT
            rt_error("init exec agent", result); rt_exit(126);
#elif defined(DARWIN_ZSH_INIT)
            rt_error("init exec zsh", result); rt_exit(126);
#else
            rt_error("init exec sh", result); rt_exit(126);
#endif
        }
        if (shell < 0) { rt_error("init fork", shell); rt_sleep(2); continue; }
#ifdef DARWIN_AGENT_INIT
        rt_put(1, "DARWIN:INIT:AGENT_PID=");
#else
        rt_put(1, "DARWIN:INIT:SHELL_PID=");
#endif
        rt_number(1, (unsigned long)shell); rt_put(1, "\n");
        int status;
        long child;
        do { child = rt_wait(-1, &status); } while (child > 0 && child != shell);
        init_check_shutdown();
#ifdef DARWIN_AGENT_INIT
        /* A failed managed session must never silently start a new agent. */
        rt_put(1, "DARWIN:INIT:AGENT_STOPPED\n");
        for (;;) rt_sleep(60);
#elif defined(DARWIN_ZSH_INIT)
        rt_put(1, "DARWIN:INIT:ZSH_STOPPED:WAIT_STATUS=");
        rt_number(1, (unsigned)status); rt_put(1, "\n");
#ifdef DARWIN_WRITABLE_STORAGE
        /* zsh's normal exit has saved history. Unmount before guest poweroff. */
        result = rt_call(159, (long)"/data", 0, 0, 0, 0, 0);
        if (result) rt_error("workload unmount before poweroff", result);
        else (void)poweroff_main(1);
#endif
        /* Preserve the first failure instead of repeatedly crashing a shell. */
        for (;;) rt_sleep(60);
#else
        rt_put(1, "DARWIN:INIT:RESPAWN\n");
        rt_sleep(1);
#endif
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
#ifdef DARWIN_AGENT_INIT
    if (rt_equal(name, "darwin-agent")) rt_exit(agent_main());
    if (name[0] == 'a' && name[1] == 'g' && name[2] == 'e' && name[3] == 'n' && name[4] == 't' && name[5] == '-')
        rt_exit(agent_fixture_main(name, argc, argv));
#endif
    rt_exit(rt_equal(name, "sh") ? shell_main(argc, argv, env) : utility_main(name, argc, argv, env));
}
