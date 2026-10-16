/* SPDX-License-Identifier: APSL-2.0 */
#ifndef MOCKFS_PAGING_POLICY_H
#define MOCKFS_PAGING_POLICY_H

/* The direct pager mapping assumes 4 KiB page units and a 32-bit base.
 * BCM2712 DEVELOPMENT uses 16 KiB VM pages; read through md0 instead.
 */
#if defined(ARM64_BOARD_CONFIG_BCM2712) && defined(DEVELOPMENT) && DEVELOPMENT
#define MOCKFS_DIRECT_MEMDEV_PAGER 0
#define MOCKFS_RPI5_RAMROOT 1
#else
#define MOCKFS_DIRECT_MEMDEV_PAGER 1
#define MOCKFS_RPI5_RAMROOT 0
#endif

static inline int
mockfs_use_direct_memdev_pager(int is_memdev)
{
	return MOCKFS_DIRECT_MEMDEV_PAGER && is_memdev;
}

#endif /* MOCKFS_PAGING_POLICY_H */
