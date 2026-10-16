/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef BCM2712_FIRMWARE_FDT_H
#define BCM2712_FIRMWARE_FDT_H
#include <libkern/c++/OSData.h>
/* Refcount-one, independent, sanitized kernel-private copy. Not a registry
 * property, provider/driver, power/clock/ownership admission or hardware probe.
 * Caller retains it for all raw-FDT option decoding and releases normally. */
OSData *rpi5_copy_boot_firmware_fdt();
#endif
