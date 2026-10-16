/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_GEM_PHYSMAP_BOUNDS_H
#define RPI5_GEM_PHYSMAP_BOUNDS_H

#include <stdint.h>

static inline uint64_t
rpi5_gem_table_span_pages(uint64_t start, uint64_t length, uint64_t span)
{
	if (length == 0 || span == 0) {
		return 0;
	}
	const uint64_t full = length / span;
	const uint64_t partial = ((start % span) + (length % span) + span - 1) / span;
	return full + partial;
}

static inline uint32_t
rpi5_gem_partial_edge_pages(uint64_t start, uint64_t end, uint64_t span)
{
	if (end <= start || span == 0) {
		return 0;
	}
	const uint64_t first = start - (start % span);
	const uint64_t last = (end - 1) - ((end - 1) % span);
	const uint32_t leading = (start % span) != 0;
	const uint32_t trailing = (end % span) != 0;
	return leading + trailing - (leading && trailing && first == last);
}

#endif
