/* SPDX-License-Identifier: BSD-2-Clause */
/* Darwin compiler's aggregate-zero lowering, absent libc in this helper. */
#include <stddef.h>
void bzero(void *target, size_t bytes)
{
    unsigned char *data=target;
    for (size_t i=0;i<bytes;i++) data[i]=0;
}
