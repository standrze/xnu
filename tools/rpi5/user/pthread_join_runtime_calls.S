/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual XNU custom-stack join wait; Apple SYS.h preserves kernel errors. */
#include "SYS.h"
__SYSCALL2(___bsdthread_create, bsdthread_create, 5, cerror_nocancel)
__SYSCALL2(___semwait_signal_nocancel, __semwait_signal_nocancel, 6, cerror_nocancel)
.subsections_via_symbols
