/* SPDX-License-Identifier: BSD-2-Clause */
/* Test-only allocator hooks. */
#include <stddef.h>
void *IOMallocData(size_t);
void IOFreeData(void *,size_t);
