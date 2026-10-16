/* SPDX-License-Identifier: BSD-2-Clause
 * Static build-only compatibility. Upstream RES_DEBUG_DISABLED also expands
 * Aerror/Perror function declarations, so disable only the debug-print macros.
 * Their real error handlers remain compiled. No resolver algorithm changes.
 */
#ifndef DARWIN_RESOLVER_BUILD_H
#define DARWIN_RESOLVER_BUILD_H
#include <sys/cdefs.h>
#include <stdint.h>
#include <stdlib.h>
/* Exact private prototype used by Libnotify-121 notifyutil/notifyutil.c:70. */
extern uint32_t notify_register_plain(const char *, int *);
#ifndef __FBSDID
#define __FBSDID(value)
#endif
#ifndef __weak_reference
#define __weak_reference(source, alias)
#endif
#ifndef __P
#define __P(arguments) arguments
#endif
#define _RES_DEBUG_H_
#define DprintC(condition, format, ...) ((void)0)
#define Dprint(format, ...) ((void)0)
#define DprintQ(condition, text, query, size) ((void)0)
#endif
