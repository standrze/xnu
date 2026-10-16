/* SPDX-License-Identifier: BSD-2-Clause */
/* Use the original Apple ordinary syscall emitter and real cerror/TSD path.
 * Fixed argument functions only; no fake result or reset/control syscall. */
#include "SYS.h"
__SYSCALL2(_socket, socket, 3, cerror_nocancel)
__SYSCALL2(_connect, connect, 3, cerror_nocancel)
__SYSCALL2(_sendto, sendto, 6, cerror_nocancel)
__SYSCALL2(_writev, writev, 3, cerror_nocancel)
.subsections_via_symbols
