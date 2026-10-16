/* SPDX-License-Identifier: BSD-2-Clause */
/* Genuine Darwin wait/wake traps. The kernel owns ULF_NO_ERRNO conversion;
 * ordinary carry-set failures follow the real cerror/TSD errno path. */
#include "SYS.h"
__SYSCALL2(___psynch_mutexwait, psynch_mutexwait, 5, cerror_nocancel)
__SYSCALL2(___psynch_mutexdrop, psynch_mutexdrop, 5, cerror_nocancel)
__SYSCALL2(___ulock_wait, ulock_wait, 4, cerror_nocancel)
__SYSCALL2(___ulock_wait2, ulock_wait2, 5, cerror_nocancel)
__SYSCALL2(___ulock_wake, ulock_wake, 3, cerror_nocancel)
.subsections_via_symbols
