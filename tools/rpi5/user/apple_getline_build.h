/* SPDX-License-Identifier: BSD-2-Clause */
/* Select only the Apple-distributed OpenSSH getline compatibility body. */
#include "includes.h"
#undef HAVE_GETLINE
/* Modern Darwin declares public getdelim even when this compatibility unit is
 * selected for getline. Keep its private helper private under a unique name. */
#define getdelim rpi5_openssh_getdelim
