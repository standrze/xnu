/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef DARWIN_UTILITY_BUILD_H
#define DARWIN_UTILITY_BUILD_H
#include <sys/cdefs.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/time.h>
extern char *user_from_uid(uid_t, int);
extern char *group_from_gid(gid_t, int);
#include <limits.h>
#ifndef LINE_MAX
/* Historical command buffer bound; modern SDK leaves this indeterminate. */
#define LINE_MAX 2048
#endif
#ifndef __RCSID
#define __RCSID(value)
#endif
#ifndef __COPYRIGHT
#define __COPYRIGHT(value)
#endif
#ifndef __FBSDID
#define __FBSDID(value)
#endif
#ifndef __P
#define __P(args) args
#endif
#ifndef __weak_reference
#define __weak_reference(source, alias)
#endif
#endif
