/* SPDX-License-Identifier: BSD-2-Clause */
/* Compile-only source-identification annotations absent from the public SDK.
 * No service, authentication, logging or success-return implementation. */
#include <sys/cdefs.h>
#ifndef __FBSDID
#define __FBSDID(value)
#endif
#ifndef __RCSID
#define __RCSID(value)
#endif

/* Libc-391's siglist.c still exports this object, while the modern public
 * signal.h no longer declares it for its paired strsignal.c. */
extern const int sys_nsig;
