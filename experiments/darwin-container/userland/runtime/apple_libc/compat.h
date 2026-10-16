/* Project build/ABI compatibility for pinned old Apple C sources. */
#ifndef DARWIN_STATIC_APPLE_COMPAT_H
#define DARWIN_STATIC_APPLE_COMPAT_H
#include <stdint.h>
#include <sys/types.h>
#include <sys/param.h>
#include <stddef.h>
#include <limits.h>
#include <stdarg.h>
#include <stdbool.h>
#include <machine/limits.h>
#define _BSD_VA_LIST_ va_list
#define restrict __restrict
#define __ct_rune_t __darwin_ct_rune_t
#define _RUNE_MAGIC_1 "RuneMagi"
#ifndef OFF_MAX
#define OFF_MAX LLONG_MAX
#endif
struct __sFILE;
extern int __srefill(struct __sFILE *);
#include <dirent.h>
extern void _seekdir(DIR *, long);
extern long apple_getdirentries64(int, char *, unsigned long, long *);
#ifndef __P
#define __P(x) x
#endif
#ifndef ALIGNBYTES
#define ALIGNBYTES (sizeof(void *) - 1)
#define ALIGN(p) (((uintptr_t)(p) + ALIGNBYTES) & ~ALIGNBYTES)
#endif
#endif
