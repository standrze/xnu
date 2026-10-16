/* SPDX-License-Identifier: BSD-2-Clause */
#include "SYS.h"
__SYSCALL2(___bsdthread_terminate, bsdthread_terminate, 4, cerror_nocancel)
__SYSCALL2(___disable_threadsignal, __disable_threadsignal, 1, cerror_nocancel)
__SYSCALL2(___pthread_markcancel, __pthread_markcancel, 1, cerror_nocancel)
__SYSCALL2(___thread_selfid, thread_selfid, 0, cerror_nocancel)
__SYSCALL2(___workq_kernreturn, workq_kernreturn, 4, cerror_nocancel)
.subsections_via_symbols
