/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_GEM_PHYSMAP_ACCOUNTING_H
#define RPI5_GEM_PHYSMAP_ACCOUNTING_H

#include <stdint.h>

/* Read-only evidence from the default-off BCM2712 page-granular physmap build.
 * The interval is the exact, contiguous bootstrap allocation delta spanning
 * both VM-returnable physmap expansions and the intervening direct-KVA
 * protection update.  The latter may allocate L3 tables for ragged edges.
 * Upper-level physmap tables are preallocated before this interval. */
struct rpi5_gem_physmap_accounting {
	uint64_t table_start;
	uint64_t table_end;
	uint64_t table_bytes;
	uint64_t mapped_bytes;
	uint32_t table_pages;
	uint32_t maximum_pages;
	uint32_t edge_pages;
	uint32_t preallocated_upper_pages;
	uint32_t page_bytes;
	uint32_t enabled;
};

#ifdef __cplusplus
extern "C" {
#endif
int rpi5_gem_physmap_accounting(struct rpi5_gem_physmap_accounting *);
#ifdef __cplusplus
}
#endif

#endif
