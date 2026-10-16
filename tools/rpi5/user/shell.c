/* SPDX-License-Identifier: BSD-2-Clause */
#include "runtime.h"
#include "parser.h"

static char cwd[1024] = "/";
static int last_status, leave_shell;
static const char help[] =
    "Pi 5 XNU experimental shell: cd pwd help status exit\n"
    "Programs: echo cat ls wc sleep uname true false hexdump\n"
    "Syntax: quotes, escapes, | ; && || < > >>. $? and $PWD expand per line.\n"
    "Use sh -c 'commands' or sh /etc/demo.sh. Root is read-only.\n"
    "No job control, background jobs, globbing, command substitution or editing history.\n";

static int builtin(struct sh_command *c)
{
    const char *name = c->argv[0];
    if (rt_equal(name, "pwd")) { rt_put(1, cwd); rt_put(1, "\n"); return 0; }
    if (rt_equal(name, "help")) { rt_put(1, help); return 0; }
    if (rt_equal(name, "status")) { rt_number(1, (unsigned)last_status); rt_put(1, "\n"); return 0; }
    if (rt_equal(name, "exit")) {
        if (c->argc != 1) { rt_put(2, "exit: no arguments supported\n"); return 2; }
        leave_shell = 1; return last_status;
    }
    if (rt_equal(name, "cd")) {
        char next[1024];
        if (c->argc > 2 || sh_path(next, sizeof(next), cwd, c->argc == 2 ? c->argv[1] : "/")) {
            rt_put(2, "cd: invalid or long path\n"); return 2;
        }
        long result = rt_chdir(next);
        if (result < 0) { rt_error("cd", result); return 1; }
        rt_copy(cwd, sizeof(cwd), next); return 0;
    }
    return -1;
}
static int is_builtin(const char *s)
{
    return rt_equal(s, "cd") || rt_equal(s, "pwd") || rt_equal(s, "help") ||
           rt_equal(s, "status") || rt_equal(s, "exit");
}
static int redirect(struct sh_command *c)
{
    const char *paths[] = {c->input, c->output};
    for (int i = 0; i < 2; i++) {
        if (!paths[i]) continue;
        long fd = rt_open(paths[i], i ? RT_WRONLY | RT_CREAT | (c->append ? RT_APPEND : RT_TRUNC) : RT_RDONLY);
        if (fd < 0) { rt_error(paths[i], fd); return -1; }
        long result = rt_dup2((int)fd, i);
        if (fd != i) rt_close((int)fd);
        if (result < 0) { rt_error("dup2", result); return -1; }
    }
    return 0;
}
static _Noreturn void execute(struct sh_command *c)
{
    int result = builtin(c);
    if (result >= 0) rt_exit(result);
    char path[1024], pwd_env[1030];
    const char *name = c->argv[0];
    int slash = 0;
    for (const char *p = name; *p; p++) if (*p == '/') slash = 1;
    if (slash) {
        if (sh_path(path, sizeof(path), cwd, name)) rt_exit(126);
    } else {
        if (rt_len(name) + 6 > sizeof(path)) rt_exit(126);
        rt_copy(path, sizeof(path), "/bin/");
        rt_copy(path + 5, sizeof(path) - 5, name);
    }
    rt_copy(pwd_env, sizeof(pwd_env), "PWD=");
    rt_copy(pwd_env + 4, sizeof(pwd_env) - 4, cwd);
    char *env[] = {pwd_env, "PATH=/bin", "HOME=/", "TERM=dumb", 0};
    long error = rt_call(59, (long)path, (long)c->argv, (long)env, 0, 0, 0);
    rt_error(name, error);
    rt_exit(error == -2 ? 127 : 126);
}
static int pipeline(struct sh_command *commands, int count)
{
    if (count == 1 && is_builtin(commands[0].argv[0])) {
        /* Save/restore real descriptors so redirection cannot strand the shell. */
        long in = rt_call(41, 0, 0, 0, 0, 0, 0), out = rt_call(41, 1, 0, 0, 0, 0, 0);
        if (in < 0 || out < 0) {
            if (in >= 0) rt_close((int)in);
            if (out >= 0) rt_close((int)out);
            rt_put(2, "shell: cannot save descriptors\n"); return 1;
        }
        int status = redirect(commands) ? 1 : builtin(commands);
        rt_dup2((int)in, 0); rt_dup2((int)out, 1);
        rt_close((int)in); rt_close((int)out);
        return status;
    }
    long children[SH_COMMANDS]; int started = 0, previous = -1, failed = 0;
    for (int i = 0; i < count; i++) {
        int next[2] = {-1, -1};
        if (i + 1 < count && rt_pipe(next) < 0) { rt_put(2, "pipe failed\n"); failed = 1; break; }
        long pid = rt_fork();
        if (pid == 0) {
            if (previous >= 0 && rt_dup2(previous, 0) < 0) rt_exit(126);
            if (next[1] >= 0 && rt_dup2(next[1], 1) < 0) rt_exit(126);
            if (previous >= 0) rt_close(previous);
            if (next[0] >= 0) rt_close(next[0]);
            if (next[1] >= 0) rt_close(next[1]);
            if (redirect(&commands[i])) rt_exit(1);
            execute(&commands[i]);
        }
        if (next[1] >= 0) rt_close(next[1]);
        if (previous >= 0) rt_close(previous);
        previous = next[0];
        if (pid < 0) { rt_error("fork", pid); failed = 1; break; }
        children[started++] = pid;
    }
    if (previous >= 0) rt_close(previous);
    int result = 1;
    for (int i = 0; i < started; i++) {
        int status = 0;
        if (rt_wait(children[i], &status) < 0) { failed = 1; continue; }
        if (i + 1 == started) result = (status & 127) ? 128 + (status & 127) : (status >> 8) & 255;
    }
    return failed ? 1 : result;
}
static void run_line(const char *line)
{
    struct sh_line parsed;
    const char *error = sh_parse(&parsed, line, last_status, cwd);
    if (error) { rt_put(2, "syntax: "); rt_put(2, error); rt_put(2, "\n"); last_status = 2; return; }
    enum sh_link previous = SH_NEXT;
    for (int i = 0; i < parsed.count && !leave_shell;) {
        int end = i;
        while (parsed.commands[end].link == SH_PIPE) end++;
        if (!((previous == SH_AND && last_status != 0) || (previous == SH_OR && last_status == 0)))
            last_status = pipeline(&parsed.commands[i], end - i + 1);
        previous = parsed.commands[end].link; i = end + 1;
    }
}
int shell_main(int argc, char **argv, char **env)
{
    for (char **e = env; e && *e; e++) {
        const char *p = *e;
        if (p[0] == 'P' && p[1] == 'W' && p[2] == 'D' && p[3] == '=' && p[4] == '/')
            (void)rt_copy(cwd, sizeof(cwd), p + 4);
    }
    if (argc == 3 && rt_equal(argv[1], "-c")) { run_line(argv[2]); return last_status; }
    int fd = 0, interactive = argc == 1;
    if (!interactive) {
        if (argc != 2) { rt_put(2, "usage: sh [-c command | script]\n"); return 2; }
        long opened = rt_open(argv[1], RT_RDONLY);
        if (opened < 0) { rt_error(argv[1], opened); return 1; }
        fd = (int)opened;
    }
    int first = 1;
    if (interactive) rt_put(1, "RPI5XNU:SHELL:READY\nType help for commands.\nxnu:/# ");
    while (!leave_shell) {
        char line[1024]; size_t n = 0; int overflow = 0, eof = 0;
        if (interactive && first) {
            while (rt_input_ready(2) == 0) rt_put(1, "\nRPI5XNU:SHELL:READY\nxnu:/# ");
        }
        for (;;) {
            char ch; long got = rt_read(fd, &ch, 1);
            if (got == -4) continue;
            if (got <= 0) { eof = 1; if (got < 0) rt_error("read", got); break; }
            first = 0;
            if (ch == '\n' || ch == '\r') break;
            if (ch == 21 || ch == 3) { n = 0; overflow = 0; continue; }
            if (ch == 8 || ch == 127) { if (n) n--; continue; }
            if (n + 1 == sizeof(line)) overflow = 1;
            else line[n++] = ch;
        }
        line[n] = 0;
        if (overflow) { rt_put(2, "line too long\n"); last_status = 2; }
        else if (n) run_line(line);
        if (eof) break;
        if (interactive && !leave_shell) { rt_put(1, "xnu:"); rt_put(1, cwd); rt_put(1, "# "); }
    }
    if (fd != 0) rt_close(fd);
    return last_status;
}
