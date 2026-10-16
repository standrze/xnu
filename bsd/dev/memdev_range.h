/* SPDX-License-Identifier: APSL-2.0 */
#ifndef MEMDEV_RANGE_H
#define MEMDEV_RANGE_H

#include <stdint.h>

/* memdev stores its length in 4 KiB units, independently of VM page size. */
static inline uint64_t
memdev_size_bytes(uint32_t pages)
{
	return (uint64_t)pages << 12;
}

/* Return false before multiplying an untrusted block number by its size. */
static inline int
memdev_block_offset(uint64_t block, uint32_t block_size, uint64_t *offset)
{
	if (block_size == 0 || block > UINT64_MAX / block_size) {
		return 0;
	}
	*offset = block * block_size;
	return 1;
}

/* A request at EOF succeeds with zero bytes; past EOF is invalid. */
static inline int
memdev_available_bytes(uint64_t offset, uint64_t size, uint64_t *available)
{
	if (offset > size) {
		return 0;
	}
	*available = size - offset;
	return 1;
}

#endif /* MEMDEV_RANGE_H */
