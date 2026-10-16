/* Project-owned ABI spellings for historical Apple Libc POSIX sources. */
#ifndef DARWIN_APPLE_POSIX_COMPAT_H
#define DARWIN_APPLE_POSIX_COMPAT_H
#include "../apple_libc/compat.h"
#include <time.h>
#include <unistd.h>
#include <errno.h>
#include <limits.h>
/* XNU USER_HZ, shared by historical times() and sysconf(_SC_CLK_TCK). */
#ifndef CLK_TCK
#define CLK_TCK 100
#endif
#ifndef FREAD
#define FREAD 0x0001
#define FWRITE 0x0002
#endif
#endif
