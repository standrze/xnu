/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_BOOTSTRAP_H
#define RPI5_BOOTSTRAP_H
#include "ranges.h"
struct rpi5_bootstrap_mapping {
    uint64_t physical_start, physical_end, virtual_start, virtual_end, entries;
    uint32_t table_pages;
};
/* Model current 16 KiB start.s mapping, zero virtual slide. Usable RAM must be
 * one caller-proven reservation-free extent, not raw advertised memory. Required
 * ranges include all early boot data. Pure arithmetic; atomic output. */
int rpi5_bootstrap_mapping(uint64_t phys_base, uint64_t virt_base,
    uint64_t mem_size, uint64_t header_pa, struct rpi5_range usable,
    const struct rpi5_range *required, size_t count, struct rpi5_bootstrap_mapping *out);
#endif
