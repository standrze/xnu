/* SPDX-License-Identifier: BSD-2-Clause */
#include "ssh_runtime_build.h"
#ifdef RPI5_APPLE_ASPRINTF
/* Select OpenSSH's original missing-provider bodies for this one unit; the
 * preserved global configure result and the real vsnprintf stay unchanged. */
#include "includes.h"
#undef HAVE_VASPRINTF
#undef HAVE_ASPRINTF
#endif
#ifdef RPI5_APPLE_DATE
/* Apple's current printdate body ends with exit(). Its original forward
 * declaration lacks noreturn, which matters after main is renamed for the
 * static startup ABI. Declaration only: original algorithm/body unchanged. */
static void printdate(const char *) __attribute__((__noreturn__));
#endif
