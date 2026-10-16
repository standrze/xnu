/* Project static-init and dispatch glue. Algorithms stay in pinned Apple
 * Libc/libplatform source. No installed host libc is linked.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <errno.h>
#include <dirent.h>
#include <unistd.h>
#include <signal.h>
extern FILE __sF[3];
FILE *__stdinp = &__sF[0];
FILE *__stdoutp = &__sF[1];
FILE *__stderrp = &__sF[2];
void *memcpy(void *dst, const void *src, size_t size) { return memmove(dst, src, size); }
void bcopy(const void *src, void *dst, size_t size) { (void)memmove(dst, src, size); }
char *index(const char *text, int character) { return strchr(text, character); }
int ffs(int value) { return __builtin_ffs(value); }
int alphasort(const struct dirent **a, const struct dirent **b) {
    return strcoll((*a)->d_name, (*b)->d_name);
}
void abort(void) {
    /* Real process termination: default SIGABRT is restored before raising. */
    struct sigaction action;
    sigset_t mask = (sigset_t)1 << (SIGABRT - 1);
    memset(&action, 0, sizeof(action));
    action.sa_handler = SIG_DFL;
    sigaction(SIGABRT, &action, 0);
    sigprocmask(SIG_UNBLOCK, &mask, 0);
    kill(getpid(), SIGABRT);
    _exit(128 + SIGABRT);
}
void __assert_rtn(const char *function, const char *file, int line, const char *expression) {
    fprintf(stderr, "Assertion failed: %s (%s:%d, %s)\n", expression, file, line,
            function && function != (const char *)-1 ? function : "unknown");
    abort();
}
