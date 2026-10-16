/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_DEVICE_HANDOFF_H
#define RPI5_RP1_DEVICE_HANDOFF_H
#include "memory_type.h"
/* Declaration only, after the host PCIe Device handoff. Add exactly the six
 * 16-KiB pages enclosing this Pi5 FDT's GEM and RP1 clocks, not all of BAR1.
 * Does not assert assigned BARs, memory decode, accessible device clocks/reset
 * or any permission to dereference. The kernel independently requires its own
 * same-boot live assignment and exact Device-map ownership. Stable/disjoint
 * input/output; failure preserves output. No MMIO or other side effects. */
int rpi5_rp1_device_handoff(const void *,size_t,
    const struct rpi5_memory_types *,struct rpi5_memory_types *);
#endif
