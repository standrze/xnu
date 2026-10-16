/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_FDT_SANITIZE_H
#define RPI5_FDT_SANITIZE_H
#include <stddef.h>
/* Privately owned writable COPY only. Validate exact framing/structure and
 * unique /chosen seed properties before changing anything. Erase the values
 * of rng-seed, kaslr-seed and random-seed without changing layout/resource
 * data. Require the qualified 64-byte rng-seed property. No entropy or source
 * freshness claim; caller wipes the entire copy on failure before releasing. */
int rpi5_fdt_sanitize_boot_seeds(void *copy, size_t bytes);
#endif
