/* SPDX-License-Identifier: BSD-2-Clause */
/* Real failure paths for Apple's unmodified terminate_with_reason wrapper. */
#include "SYS.h"
__SYSCALL2(___abort_with_payload, abort_with_payload, 6, cerror_nocancel)
__SYSCALL2(___terminate_with_payload, terminate_with_payload, 7, cerror_nocancel)
.subsections_via_symbols
