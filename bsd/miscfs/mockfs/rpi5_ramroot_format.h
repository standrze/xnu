/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RAMROOT_FORMAT_H
#define RPI5_RAMROOT_FORMAT_H
#include <stdint.h>

/* v1: unchanged launchd Mach-O at offset zero, page-aligned file extents,
 * and one final 16 KiB metadata page. All integers little endian.
 * The shared parser reads bytes, never casts potentially unaligned structs.
 */
#define RPI5_RFS_PAGE 16384u
#define RPI5_RFS_MAX (64u * 1024u * 1024u)
#define RPI5_RFS_NODES 32u
#define RPI5_RFS_HEADER 32u
#define RPI5_RFS_RECORD 128u
#define RPI5_RFS_NAME 64u
#define RPI5_RFS_DIR 1u
#define RPI5_RFS_FILE 2u

static inline uint32_t
rpi5_rfs_u32(const uint8_t *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
	       (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static inline uint64_t
rpi5_rfs_u64(const uint8_t *p)
{
	return rpi5_rfs_u32(p) | (uint64_t)rpi5_rfs_u32(p + 4) << 32;
}

static inline const uint8_t *
rpi5_rfs_entry(const uint8_t *table, uint32_t index)
{
	return table + RPI5_RFS_HEADER + index * RPI5_RFS_RECORD;
}

static inline int
rpi5_rfs_equal(const uint8_t *a, const char *b)
{
	for (uint32_t i = 0; i < RPI5_RFS_NAME; i++) {
		if (a[i] != (uint8_t)b[i]) { return 0; }
		if (!a[i]) { return 1; }
	}
	return 0;
}

static inline int
rpi5_rfs_magic(const uint8_t *p)
{
	const char *magic = "RPI5RFS1";
	for (uint32_t i = 0; i < 8; i++) {
		if (p[i] != (uint8_t)magic[i]) { return 0; }
	}
	return 1;
}

/* 0 valid, -1 malformed. Caller must provide a complete metadata page.
 * No count is published before the entire tree and all extents validate.
 */
static inline int
rpi5_rfs_validate(const uint8_t *table, uint64_t bytes, uint32_t *count_out)
{
	uint32_t count = rpi5_rfs_u32(table + 12), dev = 0, launchd = 0;
	if (!rpi5_rfs_magic(table) || rpi5_rfs_u32(table + 8) != 1 ||
	    count < 4 || count > RPI5_RFS_NODES || bytes < 2 * RPI5_RFS_PAGE ||
	    bytes > RPI5_RFS_MAX || bytes % RPI5_RFS_PAGE ||
	    rpi5_rfs_u64(table + 16) != bytes || rpi5_rfs_u64(table + 24)) {
		return -1;
	}
	for (uint32_t i = 0; i < count; i++) {
		const uint8_t *e = rpi5_rfs_entry(table, i);
		uint32_t parent = rpi5_rfs_u32(e), type = rpi5_rfs_u32(e + 4);
		uint64_t offset = rpi5_rfs_u64(e + 8), size = rpi5_rfs_u64(e + 16);
		uint32_t mode = rpi5_rfs_u32(e + 24), len = 0;
		if (rpi5_rfs_u32(e + 28)) { return -1; }
		while (len < RPI5_RFS_NAME && e[32 + len]) {
			uint8_t c = e[32 + len++];
			if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
			    (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.')) {
				return -1;
			}
		}
		if (len == RPI5_RFS_NAME || (i && (!len ||
		    rpi5_rfs_equal(e + 32, ".") || rpi5_rfs_equal(e + 32, "..")))) {
			return -1;
		}
		for (uint32_t j = 32 + len; j < RPI5_RFS_RECORD; j++) {
			if (e[j]) { return -1; }
		}
		if (!i) {
			if (parent || type != RPI5_RFS_DIR || len) { return -1; }
		} else if (parent >= i ||
		    rpi5_rfs_u32(rpi5_rfs_entry(table, parent) + 4) != RPI5_RFS_DIR) {
			return -1; /* Earlier parents imply an acyclic, root-connected tree. */
		}
		if (type == RPI5_RFS_DIR) {
			if (size || offset || mode != 0555) { return -1; }
		} else if (type == RPI5_RFS_FILE) {
			if ((mode != 0444 && mode != 0555) || offset % RPI5_RFS_PAGE ||
			    offset > bytes - RPI5_RFS_PAGE ||
			    size > bytes - RPI5_RFS_PAGE - offset) { return -1; }
			uint64_t allocated = (size + RPI5_RFS_PAGE - 1) & ~(uint64_t)(RPI5_RFS_PAGE - 1);
			if (allocated > bytes - RPI5_RFS_PAGE - offset) { return -1; }
			for (uint32_t j = 0; j < i; j++) {
				const uint8_t *old = rpi5_rfs_entry(table, j);
				if (rpi5_rfs_u32(old + 4) != RPI5_RFS_FILE) { continue; }
				uint64_t start = rpi5_rfs_u64(old + 8);
				uint64_t span = (rpi5_rfs_u64(old + 16) + RPI5_RFS_PAGE - 1) &
				    ~(uint64_t)(RPI5_RFS_PAGE - 1);
				if (allocated && span && offset < start + span && start < offset + allocated) { return -1; }
			}
		} else { return -1; }
		for (uint32_t j = 1; j < i; j++) {
			const uint8_t *old = rpi5_rfs_entry(table, j);
			if (rpi5_rfs_u32(old) == parent &&
			    rpi5_rfs_equal(e + 32, (const char *)old + 32)) { return -1; }
		}
		if (i && parent == 0 && rpi5_rfs_equal(e + 32, "dev")) {
			if (type != RPI5_RFS_DIR) { return -1; }
			dev = i;
		}
		if (i && type == RPI5_RFS_FILE && rpi5_rfs_equal(e + 32, "launchd")) {
			const uint8_t *p = rpi5_rfs_entry(table, parent);
			if (parent && rpi5_rfs_u32(p) == 0 && rpi5_rfs_equal(p + 32, "sbin")) {
				if (offset || !size || mode != 0555) { return -1; }
				launchd = i;
			}
		}
	}
	if (!dev || !launchd) { return -1; }
	for (uint32_t i = 1; i < count; i++) {
		if (rpi5_rfs_u32(rpi5_rfs_entry(table, i)) == dev) { return -1; }
	}
	for (uint32_t i = RPI5_RFS_HEADER + count * RPI5_RFS_RECORD; i < RPI5_RFS_PAGE; i++) {
		if (table[i]) { return -1; }
	}
	*count_out = count;
	return 0;
}
#endif
