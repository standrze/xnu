/* SPDX-License-Identifier: BSD-2-Clause */
#include "SYS.h"
__SYSCALL2(_socket, socket, 3, cerror_nocancel)
__SYSCALL2(___sendto, sendto, 6, cerror_nocancel)
__SYSCALL2(___proc_info, proc_info, 6, cerror_nocancel)
__SYSCALL2(_close$NOCANCEL, close_nocancel, 1, cerror_nocancel)
__SYSCALL2(_fcntl$NOCANCEL, fcntl_nocancel, 3, cerror_nocancel)
__SYSCALL2(_connect$NOCANCEL, connect_nocancel, 3, cerror_nocancel)
.subsections_via_symbols
