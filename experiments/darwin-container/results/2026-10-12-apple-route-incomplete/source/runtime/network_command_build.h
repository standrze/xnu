/* SPDX-License-Identifier: BSD-2-Clause
 * Declaration/constant compatibility for original network_cmds-396.6.
 * No route parsing, address handling or routing-socket algorithm replacement.
 */
#ifndef DARWIN_NETWORK_COMMAND_BUILD_H
#define DARWIN_NETWORK_COMMAND_BUILD_H
#include <sys/cdefs.h>
#ifndef __dead
#define __dead __attribute__((__noreturn__))
#endif
/* Exact public kernel route flags in this XNU's bsd/net/route.h. */
#ifndef RTF_IFREF
#define RTF_IFREF 0x4000000
#endif
#endif
