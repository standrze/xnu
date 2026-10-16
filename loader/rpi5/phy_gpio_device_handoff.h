/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PHY_GPIO_DEVICE_HANDOFF_H
#define RPI5_PHY_GPIO_DEVICE_HANDOFF_H
#include "rp1_device_handoff.h"
/* Compose the original six-page handoff with exactly three 16KiB GPIO32
 * resource pages declared by the fresh original RP1 FDT. Device classification
 * only: no GPIO ownership, reset permission, mapping or MMIO. Output atomic. */
int rpi5_phy_gpio_device_handoff(const void *,size_t,const struct rpi5_memory_types *,struct rpi5_memory_types *);
#endif
