/* SPDX-License-Identifier: BSD-2-Clause */
/* Narrow selection of Apple's generated ordinary syscall emitter. */
#include "SYS.h"
__SYSCALL2(_writev, writev, 3, cerror_nocancel)
.subsections_via_symbols
