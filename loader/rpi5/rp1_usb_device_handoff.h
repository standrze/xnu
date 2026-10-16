/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_USB_DEVICE_HANDOFF_H
#define RPI5_RP1_USB_DEVICE_HANDOFF_H

#include "memory_type.h"

/* Declaration only, after the host PCIe Device handoff. Add the existing RP1
 * clock/GEM declarations plus exactly the 1-MiB USB0 controller window from
 * this Pi 5 FDT's validated RP1 aperture. This does not assert assignment,
 * memory-decode enablement, clocks, reset state, controller ownership, DMA,
 * interrupts, or permission to access any register. The kernel independently
 * requires its same-boot live checks and exact Device-map ownership.
 * Stable/disjoint input/output; failure preserves output. No MMIO, allocation,
 * or other side effects. */
int rpi5_rp1_usb_device_handoff(const void *, size_t,
    const struct rpi5_memory_types *, struct rpi5_memory_types *);

#endif
