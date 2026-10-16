/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_DISPLAY_XNU_ALLOCATE_H
#define RPI5_DISPLAY_XNU_ALLOCATE_H
#include "display_allocate_adapter.h"
/* Distinct direct-reset, same-boot XNU profile. Invoked once before CPU_ON,
 * with sole A76 primary, DAIF masked and MMU/cache off. Four bounded matched
 * transactions, exact fixed32 preflight, one allocation, no release/retry.
 * Only a fully completed and independently validated retained descriptor may
 * pass to XNU. Failed/unknown ownership parks until reset. The entire image,
 * isolated request pages, original FDT and full rounded allocation stay live
 * below topOfKernelData; no later mailbox use or buffer reuse is authorized.
 * Cache enable is permitted only after closed matched transaction ownership.
 * This adapter does not access, map or draw framebuffer memory. */
int rpi5_display_xnu_allocate_run(const void *,size_t,struct rpi5_range,void *,uint64_t,
    struct rpi5_display_allocate_result *,struct rpi5_display_allocate_report *);
#endif
