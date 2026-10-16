/* SPDX-License-Identifier: BSD-2-Clause */
/* Original Apple emitter, genuine six-argument XNU sysctl trap and cerror/TSD.
 * sysctlbyname's private __sysctl name is not the public sysctl symbol. */
#include "SYS.h"
__SYSCALL2(___sysctl, sysctl, 6, cerror_nocancel)
.subsections_via_symbols
