/* SPDX-License-Identifier: BSD-2-Clause
 * Project-owned startup and variadic ABI adapters for the single-threaded,
 * static zsh experiment. All libc algorithms are separately source-built.
 */
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/time.h>
#include <sys/select.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdlib.h>
#include <unistd.h>
#include <mach/mach.h>
#include "stack_logging_internal.h"
#ifdef DARWIN_ZSH_DIAGNOSTICS
#include <sys/ucontext.h>
static void trace(const char *message)
{
    const char *end = message;
    while (*end) end++;
    write(2, message, (size_t)(end - message));
}
static void trace_hex(uint64_t value)
{
    char text[17];
    static const char digits[] = "0123456789abcdef";
    for (int i = 0; i < 16; i++) text[i] = digits[(value >> (60 - 4 * i)) & 15];
    text[16] = '\n'; write(2, text, sizeof(text));
}
static void fault_trace(int sig, siginfo_t *info, void *context)
{
    ucontext_t *u = context;
    trace("DARWIN:ZSH:FAULT:SIGNAL="); trace_hex(sig);
    trace("PC="); trace_hex(u->uc_mcontext->__ss.__pc);
    trace("LR="); trace_hex(u->uc_mcontext->__ss.__lr);
    trace("FAR="); trace_hex((uintptr_t)info->si_addr);
    trace("X0="); trace_hex(u->uc_mcontext->__ss.__x[0]);
    trace("X1="); trace_hex(u->uc_mcontext->__ss.__x[1]);
    _exit(128 + sig);
}
#else
#define trace(message) ((void)0)
#endif

char **environ;
/* Optional Apple allocation diagnostics are not enabled for this guest. */
malloc_logger_t *__syscall_logger;
char *__progname;
static uintptr_t main_tsd[128];
static int main_errno;
mach_port_t mach_task_self_;
vm_size_t vm_page_size = 16384;
int vm_page_shift = 14;
vm_size_t vm_page_mask = 16383;
extern mach_port_t darwin_task_self(void);
extern void _thread_set_tsd_base(void *);
extern int zsh_main(int, char **);
extern int darwin_open(const char *, int, mode_t);
extern int darwin_ioctl(int, unsigned long, uintptr_t);
extern int darwin_fcntl(int, int, uintptr_t);
extern int __platform_sigaction(int, const struct sigaction *, struct sigaction *);
extern int getentropy(void *, size_t);
extern int __gettimeofday(struct timeval *, struct timezone *);

char ***_NSGetEnviron(void) { return &environ; }

/* Project SDK ABI bridge: this bounded guest never enables dynamically
 * oversized fd_sets. Refuse unsupported descriptors instead of permitting
 * the SDK inline macros to overwrite the caller's fixed-size object. */
int __darwin_check_fd_set_overflow(int descriptor, const void *set, int unlimited)
{
    (void)unlimited;
    if (descriptor < 0) return 0;
    if (!set || descriptor >= FD_SETSIZE) abort();
    return 1;
}

int gettimeofday(struct timeval *time, void *zone)
{
    return __gettimeofday(time, zone);
}

/* The caller's unnamed arguments are on the stack in Apple's arm64 ABI;
 * raw system call stubs require them in registers. Never directly export
 * an ordinary fixed-argument stub as one of these variadic C functions.
 */
int open(const char *path, int flags, ...)
{
    mode_t mode = 0;
    if (flags & O_CREAT) {
        va_list args; va_start(args, flags);
        mode = (mode_t)va_arg(args, int); va_end(args);
    }
    return darwin_open(path, flags, mode);
}

int ioctl(int fd, unsigned long request, ...)
{
    uintptr_t arg = 0;
    /* Darwin's parameter-less ioctl requests must not read a missing arg. */
    if ((request & IOC_VOID) == 0 || (request & IOCPARM_MASK << 16) != 0) {
        va_list args; va_start(args, request);
        arg = va_arg(args, uintptr_t); va_end(args);
    }
    return darwin_ioctl(fd, request, arg);
}

int fcntl(int fd, int command, ...)
{
    uintptr_t arg = 0;
    switch (command) {
    case F_GETFD: case F_GETFL: case F_GETOWN: break;
    default: {
        va_list args; va_start(args, command);
        arg = va_arg(args, uintptr_t); va_end(args);
        break;
    }
    }
    return darwin_fcntl(fd, command, arg);
}

/* The static experiment has no dyld or pthread-created threads. Install
 * real kernel TSD before Apple errno/setjmp routines can read it. */
_Noreturn void darwin_static_start(uintptr_t *stack)
{
    trace("DARWIN:ZSH:ENTRY\n");
    int argc = (int)stack[0];
    char **argv = (char **)(stack + 1);
    environ = argv + argc + 1;
    __progname = argc ? argv[0] : (char *)"zsh";
    main_tsd[0] = (uintptr_t)main_tsd;
    main_tsd[1] = (uintptr_t)&main_errno;
    /* A real random cookie, not a fabricated successful entropy result. */
    _thread_set_tsd_base(main_tsd);
    trace("DARWIN:ZSH:TSD\n");
    mach_task_self_ = darwin_task_self();
    if (getentropy(&main_tsd[7], sizeof(main_tsd[7])) < 0)
        _exit(126);
    trace("DARWIN:ZSH:ENTROPY\n");
#ifdef DARWIN_ZSH_DIAGNOSTICS
    struct sigaction action = {0};
    action.sa_sigaction = fault_trace;
    action.sa_flags = SA_SIGINFO;
    sigaction(SIGSEGV, &action, 0);
    sigaction(SIGBUS, &action, 0);
    sigaction(SIGILL, &action, 0);
#endif
    trace("DARWIN:ZSH:MAIN\n");
    /* Allocator/stdio initialization is added once its pinned source
     * configuration exposes the exact static initializer contract. */
    exit(zsh_main(argc, argv));
}
