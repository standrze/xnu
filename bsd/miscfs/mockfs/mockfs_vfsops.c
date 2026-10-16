/*
 * Copyright (c) 2012 Apple Inc. All rights reserved.
 *
 * @APPLE_OSREFERENCE_LICENSE_HEADER_START@
 *
 * This file contains Original Code and/or Modifications of Original Code
 * as defined in and that are subject to the Apple Public Source License
 * Version 2.0 (the 'License'). You may not use this file except in
 * compliance with the License. The rights granted to you under the License
 * may not be used to create, or enable the creation or redistribution of,
 * unlawful or unlicensed copies of an Apple operating system, or to
 * circumvent, violate, or enable the circumvention or violation of, any
 * terms of an Apple operating system software license agreement.
 *
 * Please obtain a copy of the License at
 * http://www.opensource.apple.com/apsl/ and read it before using this file.
 *
 * The Original Code and all software distributed under the License are
 * distributed on an 'AS IS' basis, WITHOUT WARRANTY OF ANY KIND, EITHER
 * EXPRESS OR IMPLIED, AND APPLE HEREBY DISCLAIMS ALL SUCH WARRANTIES,
 * INCLUDING WITHOUT LIMITATION, ANY WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE, QUIET ENJOYMENT OR NON-INFRINGEMENT.
 * Please see the License for the specific language governing rights and
 * limitations under the License.
 *
 * @APPLE_OSREFERENCE_LICENSE_HEADER_END@
 */

#include <kern/assert.h>
#include <kern/debug.h>
#include <libkern/libkern.h>
#include <miscfs/mockfs/mockfs.h>
#include <miscfs/mockfs/mockfs_fsnode.h>
#include <miscfs/mockfs/mockfs_paging_policy.h>
#include <miscfs/mockfs/mockfs_vnops.h>
#include <miscfs/specfs/specdev.h>
#include <sys/disk.h>
#include <sys/buf.h>
#include <sys/errno.h>
#include <sys/malloc.h>
#include <sys/mount_internal.h>
#include <sys/vnode_internal.h>

static LCK_GRP_DECLARE(mockfs_mtx_grp, "mockfs-mutex");

#if MOCKFS_RPI5_RAMROOT
static void
mockfs_ramroot_destroy(mockfs_mount_t data)
{
	data->mockfs_root = NULL;
	for (uint32_t i = 0; i < data->ramroot_count; i++) {
		/* Archive topology uses the bounded node table, not legacy children. */
		data->ramroot_nodes[i]->parent = NULL;
		mockfs_fsnode_destroy(data->ramroot_nodes[i]);
	}
}

/* ENOENT means no archive magic: keep the proven raw-executable path.
 * Malformed metadata with the magic is rejected, never partially mounted.
 */
static int
mockfs_ramroot_mount(mount_t mp, vnode_t rvp)
{
	uint64_t bytes = rvp->v_specinfo->si_devsize;
	uint32_t block = mp->mnt_devblocksize, count = 0;
	buf_t bp = NULL;
	mockfs_mount_t data = NULL;
	int error;
	if (bytes < 2 * RPI5_RFS_PAGE || bytes > RPI5_RFS_MAX ||
	    bytes % RPI5_RFS_PAGE) { return ENOENT; }
	if (!block || RPI5_RFS_PAGE % block) { return EINVAL; }
	error = buf_bread(rvp, (daddr64_t)((bytes - RPI5_RFS_PAGE) / block),
	    RPI5_RFS_PAGE, NOCRED, &bp);
	if (error) { goto out; }
	if (buf_resid(bp)) { error = EIO; goto out; }
	const uint8_t *table = (const uint8_t *)buf_dataptr(bp);
	if (!rpi5_rfs_magic(table)) { error = ENOENT; goto out; }
	if (rpi5_rfs_validate(table, bytes, &count)) { error = EINVAL; goto out; }
	data = kalloc_type(struct mockfs_mount, Z_WAITOK | Z_ZERO);
	if (!data) { error = ENOMEM; goto out; }
	for (uint32_t i = 0; i < count; i++) {
		const uint8_t *entry = rpi5_rfs_entry(table, i);
		uint8_t type = rpi5_rfs_u32(entry + 4) == RPI5_RFS_FILE ? MOCKFS_FILE : MOCKFS_DIR;
		if (!i) { type = MOCKFS_ROOT; }
		error = mockfs_fsnode_create(mp, type, &data->ramroot_nodes[i]);
		if (error) { goto out; }
		data->ramroot_count++;
		mockfs_fsnode_t node = data->ramroot_nodes[i];
		node->size = rpi5_rfs_u64(entry + 16);
		node->data_offset = rpi5_rfs_u64(entry + 8);
		node->mode = rpi5_rfs_u32(entry + 24);
		node->fileid = i + 2; /* Stable, nonzero, unique per archive node. */
		memcpy(node->name, entry + 32, sizeof(node->name));
		node->parent = i ? data->ramroot_nodes[rpi5_rfs_u32(entry)] : NULL;
	}
	lck_mtx_init(&data->mockfs_mnt_mtx, &mockfs_mtx_grp, LCK_ATTR_NULL);
	data->mockfs_root = data->ramroot_nodes[0];
	data->ramroot_bytes = bytes;
	/* Direct physical pager remains off: each vnode maps a distinct extent. */
	mp->mnt_data = (typeof(mp->mnt_data))data;
	mp->mnt_flag |= MNT_RDONLY;
	printf("RPI5XNU:RAMROOT:MOUNT NODES=%u BYTES=%llu READONLY\n", count, bytes);
	data = NULL;
	error = 0;
out:
	if (bp) { buf_brelse(bp); }
	if (data) {
		mockfs_ramroot_destroy(data);
		kfree_type(struct mockfs_mount, data);
	}
	return error;
}
#endif

int mockfs_mountroot(mount_t mp, vnode_t rvp, __unused vfs_context_t ctx);

/*
 * Functions that are part of the mockfs_vfsops structure.
 */
int mockfs_unmount(__unused struct mount *mp, __unused int mntflags, __unused vfs_context_t ctx);
int mockfs_root(mount_t mp, vnode_t * vpp, __unused vfs_context_t ctx);
int mockfs_sync(__unused struct mount *mp, __unused int waitfor, __unused vfs_context_t ctx);
int mockfs_init(__unused struct vfsconf * vfsc);

/*
 * mockfs_mountroot:
 *   Given a mount (mp) and a vnode for the root device (rvp), builds a fake filesystem for rvp.  This consists
 *   of three nodes; a directory node (to serve as a mountpoint for devfs), a file node meant to serve as an
 *   executable frontend for rootvp (we will assume that rootvp is an executable, that the kernel can subsequently
 *   run), and the root node for the mockfs filesystem.  The structure of mockfs is memory-backed; only the
 *   contents of the file node refer to the backing device.
 *
 * Returns 0 on success, or an error.
 */
int
mockfs_mountroot(mount_t mp, vnode_t rvp, __unused vfs_context_t ctx)
{
	int rvalue = 0;
#if MOCKFS_RPI5_RAMROOT
	rvalue = mockfs_ramroot_mount(mp, rvp);
	if (rvalue != ENOENT) { return rvalue; }
	rvalue = 0;
#endif
	mockfs_fsnode_t root_fsnode = NULL;
	mockfs_fsnode_t dev_fsnode = NULL;
	mockfs_fsnode_t file_fsnode = NULL;
	mockfs_mount_t mockfs_mount_data = NULL;
	dk_memdev_info_t memdev_info;

	/*
	 * TODO: Validate that the device at least LOOKS like a mach-o (has a sane header); this would prevent us
	 *   from causing EBADMACHO panics further along the boot path.
	 */

	/*
	 * There are no M_MOCKFS* definitions at the moment, just use M_TEMP.
	 */

	mockfs_mount_data = kalloc_type(struct mockfs_mount, Z_WAITOK | Z_ZERO);
	mockfs_fsnode_create(mp, MOCKFS_ROOT, &root_fsnode);
	mockfs_fsnode_create(mp, MOCKFS_DEV, &dev_fsnode);
	mockfs_fsnode_create(mp, MOCKFS_FILE, &file_fsnode);

	if (!root_fsnode || !dev_fsnode || !file_fsnode) {
		rvalue = ENOMEM;
		goto done;
	}

	/*
	 * If rvp is a memory device (with a few caveats), we can point to the same physical memory as the device
	 *   and avoid pointless paging/copying; query the device node for the information we need to determine
	 *   if we can do this.
	 */
	bzero(&memdev_info, sizeof(memdev_info));

	if (!VNOP_IOCTL(rvp, DKIOCGETMEMDEVINFO, (caddr_t)&memdev_info, 0, NULL)) {
		/*
		 * For the moment, we won't try to optimize when mi_phys is true.
		 */
		if (!mockfs_mount_data->mockfs_physical_memory) {
			mockfs_mount_data->mockfs_memory_backed =
			    mockfs_use_direct_memdev_pager(memdev_info.mi_mdev);
			mockfs_mount_data->mockfs_physical_memory = memdev_info.mi_phys;
			mockfs_mount_data->mockfs_memdev_base = memdev_info.mi_base;
			mockfs_mount_data->mockfs_memdev_size = memdev_info.mi_size;
		}
	}

	lck_mtx_init(&mockfs_mount_data->mockfs_mnt_mtx, &mockfs_mtx_grp, LCK_ATTR_NULL);

	/*
	 * All of the needed nodes/structures have been set up; now we just need to establish the relationships
	 *   between the various mockfs nodes.
	 */
	if ((rvalue = mockfs_fsnode_adopt(root_fsnode, dev_fsnode))) {
		goto done;
	}

	if ((rvalue = mockfs_fsnode_adopt(root_fsnode, file_fsnode))) {
		goto done;
	}

	mockfs_mount_data->mockfs_root = root_fsnode;
	mp->mnt_data = (typeof(mp->mnt_data))mockfs_mount_data;

done:
	if (rvalue) {
		if (file_fsnode) {
			mockfs_fsnode_destroy(file_fsnode);
		}
		if (dev_fsnode) {
			mockfs_fsnode_destroy(dev_fsnode);
		}
		if (root_fsnode) {
			mockfs_fsnode_destroy(root_fsnode);
		}
		if (mockfs_mount_data) {
			lck_mtx_destroy(&mockfs_mount_data->mockfs_mnt_mtx, &mockfs_mtx_grp);
			kfree_type(struct mockfs_mount, mockfs_mount_data);
		}
	}

	return rvalue;
}

/*
 * mockfs_unmount:
 *   Given a mount (mp), and associated flags (mntflags), performs the necessary teardown to destroy the mount.
 *
 * Returns 0 on success, or an error.
 */
int
mockfs_unmount(struct mount *mp, int mntflags, __unused vfs_context_t ctx)
{
	int rvalue;
	int vflush_flags;
	mockfs_fsnode_t root_fsnode;
	mockfs_mount_t mockfs_mnt;

	vflush_flags = 0;
	mockfs_mnt = (mockfs_mount_t) mp->mnt_data;

	/*
	 * Reclaim the vnodes for the mount (forcibly, if requested; given that mockfs only support mountroot
	 *   at the moment, this should ALWAYS be forced),
	 */
	if (mntflags & MNT_FORCE) {
		vflush_flags |= FORCECLOSE;
	}

	rvalue = vflush(mp, NULL, vflush_flags);

	if (rvalue) {
		return rvalue;
	}

	/*
	 * Past this point, errors are likely to be unrecoverable, so panic if we're given any excuse; we
	 *   need to teardown the mockfs_mnt data now, so that VFS can cleanup the mount structure.  Note
	 *   that clearing mockfs_root before destroying the fsnode tree is related to an implementation
	 *   detail of mockfs_fsnode_destroy (which will refuse to destroy the root node).
	 */
	root_fsnode = mockfs_mnt->mockfs_root;
	mockfs_mnt->mockfs_root = NULL;
#if MOCKFS_RPI5_RAMROOT
	if (mockfs_mnt->ramroot_count) {
		mockfs_ramroot_destroy(mockfs_mnt);
		rvalue = 0;
	} else
#endif
	{
		rvalue = mockfs_fsnode_destroy(root_fsnode);
	}

	if (rvalue) {
		panic("mockfs_unmount: Failed to destroy the fsnode tree");
	}

	lck_mtx_destroy(&mockfs_mnt->mockfs_mnt_mtx, &mockfs_mtx_grp);
	kfree_type(struct mockfs_mount, mockfs_mnt);
	mp->mnt_data = NULL;

	return rvalue;
}

/*
 * mockfs_root:
 *   Given a mount (mp), returns the root vnode (*vpp) for that mount with an iocount.
 *
 * Returns 0 on success, or an error.
 */
int
mockfs_root(mount_t mp, vnode_t * vpp, __unused vfs_context_t ctx)
{
	int rvalue;

	rvalue = mockfs_fsnode_vnode(((mockfs_mount_t) mp->mnt_data)->mockfs_root, vpp);
	return rvalue;
}

/*
 * mockfs_sync:
 *  Returns success because we're a read-only filesystem.
 *
 * Returns 0.
 */
int
mockfs_sync(__unused struct mount *mp, __unused int waitfor, __unused vfs_context_t ctx)
{
	return 0;
}

int
mockfs_init(__unused struct vfsconf * vfsc)
{
	return 0;
}

#if MOCKFS_RPI5_RAMROOT
/* statfs64 refreshes these attributes through VFS_GETATTR before copying the
 * generic mount identity/flags. The archive occupies a fixed read-only extent;
 * padding and the metadata page are allocated too, not writable free space.
 * Preserve the legacy raw-executable path's unsupported statistics behavior.
 */
static int
mockfs_vfs_getattr(mount_t mp, struct vfs_attr *attributes, __unused vfs_context_t ctx)
{
	if (!mp || !attributes) { return EINVAL; }
	mockfs_mount_t data = (mockfs_mount_t)mp->mnt_data;
	if (!data || !data->ramroot_count) { return ENOTSUP; }
	if (!data->mockfs_root || data->ramroot_count < 4 || data->ramroot_count > RPI5_RFS_NODES ||
	    data->ramroot_bytes < 2 * RPI5_RFS_PAGE || data->ramroot_bytes > RPI5_RFS_MAX ||
	    data->ramroot_bytes % RPI5_RFS_PAGE) { return EIO; }
	uint64_t blocks = data->ramroot_bytes / RPI5_RFS_PAGE;
	VFSATTR_RETURN(attributes, f_bsize, RPI5_RFS_PAGE);
	VFSATTR_RETURN(attributes, f_iosize, RPI5_RFS_PAGE);
	VFSATTR_RETURN(attributes, f_blocks, blocks);
	VFSATTR_RETURN(attributes, f_bused, blocks);
	VFSATTR_RETURN(attributes, f_bfree, 0);
	VFSATTR_RETURN(attributes, f_bavail, 0);
	VFSATTR_RETURN(attributes, f_files, data->ramroot_count);
	VFSATTR_RETURN(attributes, f_ffree, 0);
	VFSATTR_RETURN(attributes, f_fssubtype, 0);
	return 0;
}
#endif

struct vfsops mockfs_vfsops = {
	.vfs_unmount = mockfs_unmount,
	.vfs_root = mockfs_root,
	.vfs_sync = mockfs_sync,
	.vfs_init = mockfs_init,
#if MOCKFS_RPI5_RAMROOT
	.vfs_getattr = mockfs_vfs_getattr,
#endif
};
