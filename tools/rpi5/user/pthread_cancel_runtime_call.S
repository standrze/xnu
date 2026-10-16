/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual kernel cancellation-state operation used by Apple's callback. */
#include "SYS.h"
__SYSCALL2(___pthread_canceled, __pthread_canceled, 1, cerror_nocancel)
.subsections_via_symbols
