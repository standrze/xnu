/*
 * Copyright (c) 2019 Apple Inc. All rights reserved.
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

#include <miscfs/mockfs/mockfs.h>
#include <miscfs/mockfs/mockfs_vnops.h>
#include <sys/ubc.h>
#include <sys/mount_internal.h>
#include <sys/vnode_internal.h>
#include <sys/dirent.h>
#include <sys/fcntl.h>
#include <vfs/vfs_support.h>

#include <libkern/libkern.h>
#include <kern/debug.h>
#include <limits.h>

/*
 * VOPFUNC macro; why do we have so many distinct definitions of this?
 */
#define VOPFUNC int (*)(void *)

/*
 * VNOP functions that mockfs implements.  See xnu/bsd/sys/vnode_if.h for information on what
 *   each function does in generic terms.
 */
int mockfs_lookup(struct vnop_lookup_args * ap);
int mockfs_getattr(struct vnop_getattr_args * ap);
int mockfs_read(struct vnop_read_args * ap);
int mockfs_strategy(struct vnop_strategy_args * ap);
int mockfs_pagein(struct vnop_pagein_args * ap);
int mockfs_reclaim(__unused struct vnop_reclaim_args * ap);
int mockfs_blockmap(struct vnop_blockmap_args * ap);

#if MOCKFS_RPI5_RAMROOT
static int
mockfs_ramroot_open(struct vnop_open_args *ap)
{
	mockfs_mount_t data = (mockfs_mount_t)ap->a_vp->v_mount->mnt_data;
	if (!data->ramroot_count) { return err_open(ap); }
	return (ap->a_mode & FWRITE) ? EROFS : 0;
}

static int
mockfs_ramroot_close(struct vnop_close_args *ap)
{
	mockfs_mount_t data = (mockfs_mount_t)ap->a_vp->v_mount->mnt_data;
	return data->ramroot_count ? 0 : err_close(ap);
}

static int
mockfs_ramroot_readdir(struct vnop_readdir_args *ap)
{
	mockfs_fsnode_t directory = ap->a_vp->v_data;
	mockfs_mount_t data = (mockfs_mount_t)directory->mnt->mnt_data;
	struct uio *uio = ap->a_uio;
	off_t position = 0, requested = uio_offset(uio);
	int emitted = 0, error = 0;
	if (!data->ramroot_count) { return err_readdir(ap); }
	if (ap->a_vp->v_type != VDIR) { return ENOTDIR; }
	if (requested < 0 || (ap->a_flags & (VNODE_READDIR_EXTENDED | VNODE_READDIR_REQSEEKOFF))) { return EINVAL; }
	if (ap->a_eofflag) { *ap->a_eofflag = 0; }
	if (ap->a_numdirent) { *ap->a_numdirent = 0; }
	uint32_t i;
	for (i = 0; i < data->ramroot_count + 2; i++) {
		mockfs_fsnode_t node;
		const char *name;
		if (i == 0) { node = directory; name = "."; }
		else if (i == 1) { node = directory->parent ? directory->parent : directory; name = ".."; }
		else {
			node = data->ramroot_nodes[i - 2];
			if (node->parent != directory) { continue; }
			name = node->name;
		}
		struct dirent entry;
		bzero(&entry, sizeof(entry));
		entry.d_fileno = node->fileid;
		entry.d_type = node->type == MOCKFS_FILE ? DT_REG : DT_DIR;
		entry.d_namlen = (uint8_t)strlen(name); /* Validated at most 63 bytes. */
		entry.d_reclen = (uint16_t)((sizeof(entry) - sizeof(entry.d_name)) +
		    ((entry.d_namlen + 1 + 3) & ~3));
		strlcpy(entry.d_name, name, sizeof(entry.d_name));
		if (position < requested) {
			position += entry.d_reclen;
			if (position > requested) { return EINVAL; }
			continue;
		}
		if (uio_resid(uio) < entry.d_reclen) {
			if (!emitted) { error = EINVAL; }
			break;
		}
		error = uiomove((caddr_t)&entry, entry.d_reclen, uio);
		if (error) { break; }
		position += entry.d_reclen;
		emitted++;
	}
	if (requested > position) { return EINVAL; }
	uio_setoffset(uio, position);
	if (ap->a_numdirent) { *ap->a_numdirent = emitted; }
	if (ap->a_eofflag && i == data->ramroot_count + 2) { *ap->a_eofflag = 1; }
	return error;
}
#endif

/*
 * struct vnop_lookup_args {
 *   struct vnodeop_desc *a_desc; // We don't care about this (for now)
 *   vnode_t a_dvp;               // vnode for the directory we are performing the lookup in
 *   vnode_t *a_vpp;              // Return parameter: the vnode we matched the lookup to
 *   struct componentname *a_cnp; // Description of the file we are looking for
 *   vfs_context_t a_context;     // We don't care about this (for now)
 * };
 *
 * mockfs_lookup:
 *   Given a vnode for a directory (a_dvp) and a file description (a_cnp), looks for a file matching
 *   the description in the directory, and give a vnode with an iocount for the file (*a_vpp), if the
 *   file was found.  For mockfs, because we realistically have 3 vnodes, the filesystem information
 *   is extremely sparse, so the details on naming are all implemented in mockfs_lookup; the generic VFS
 *   information is enough for us to distinguish between all 3 files.  Any lookup not done in the root
 *   vnode fails, by definition.  Each vnode has the following names in relation to the root vnode:
 *
 *   The root vnode:
 *     "sbin"
 *
 *   The devfs vnode:
 *     "dev"
 *
 *   The executable vnode
 *     "launchd"
 *
 * Returns 0 on success, or an error.
 */
int
mockfs_lookup(struct vnop_lookup_args * ap)
{
	char held_char;
	int rvalue;
	int op;
	mockfs_fsnode_t fsnode;
	mockfs_fsnode_t target_fsnode;
	vnode_t dvp;
	vnode_t * vpp;
	vfs_context_t ctx;
	struct componentname * cnp;

	rvalue = 0;
	dvp = ap->a_dvp;
	vpp = ap->a_vpp;
	cnp = ap->a_cnp;
	ctx = ap->a_context;
	op = cnp->cn_nameiop;
	fsnode = (mockfs_fsnode_t) dvp->v_data;
	target_fsnode = NULL;

#if MOCKFS_RPI5_RAMROOT
	mockfs_mount_t data = (mockfs_mount_t)fsnode->mnt->mnt_data;
	if (data->ramroot_count) {
		*vpp = NULL;
		if (op != LOOKUP) { return EROFS; }
		if (dvp->v_type != VDIR) { return ENOTDIR; }
		if (cnp->cn_namelen == 1 && cnp->cn_nameptr[0] == '.') { target_fsnode = fsnode; }
		else if (cnp->cn_namelen == 2 && !memcmp(cnp->cn_nameptr, "..", 2)) {
			target_fsnode = fsnode->parent ? fsnode->parent : fsnode;
		} else {
			for (uint32_t i = 1; i < data->ramroot_count; i++) {
				mockfs_fsnode_t node = data->ramroot_nodes[i];
				if (node->parent == fsnode && strlen(node->name) == (size_t)cnp->cn_namelen &&
				    !memcmp(node->name, cnp->cn_nameptr, cnp->cn_namelen)) {
					target_fsnode = node;
					break;
				}
			}
		}
		return target_fsnode ? mockfs_fsnode_vnode(target_fsnode, vpp) : ENOENT;
	}
#endif

	if ((op == LOOKUP) && (fsnode->type == MOCKFS_ROOT)) {
		/*
		 * Okay, we're looking in the root directory, so we aren't necessarily
		 *   going to fail.  What are we looking for?
		 */

		held_char = cnp->cn_nameptr[cnp->cn_namelen];
		cnp->cn_nameptr[cnp->cn_namelen] = '\0';

		/*
		 * We'll resolve sbin to /, and launchd to the executable for the moment, so that I don't
		 *   accidentally commit a change to the init_process pathname.  We map from name to node type
		 *   here, as mockfs doesn't current use names; just unique types.
		 */
		if (!strncmp(cnp->cn_nameptr, "sbin", 5)) {
			target_fsnode = fsnode;
		} else if (!strncmp(cnp->cn_nameptr, "dev", 4)) {
			mockfs_fsnode_child_by_type(fsnode, MOCKFS_DEV, &target_fsnode);
		} else if (!strncmp(cnp->cn_nameptr, "launchd", 8)) {
			mockfs_fsnode_child_by_type(fsnode, MOCKFS_FILE, &target_fsnode);
		} else {
			rvalue = ENOENT;
		}

		cnp->cn_nameptr[cnp->cn_namelen] = held_char;

		if (target_fsnode) {
			rvalue = mockfs_fsnode_vnode(target_fsnode, vpp);
		}
	} else {
		/*
		 * We aren't looking in root; the query may actually be reasonable, but we're not
		 *   going to support it.
		 */
		rvalue = ENOENT;
	}

	return rvalue;
}

/*
 * struct vnop_getattr_args {
 *   struct vnodeop_desc *a_desc; // We don't care about this (for now)
 *   vnode_t a_vp;                // Pointer to the vnode we are interested in
 *   struct vnode_attr *a_vap;    // Details the requested attributes, and used to return attributes
 *   vfs_context_t a_context;     // We don't care about this (for now)
 * };
 *
 * mockfs_getattr:
 *   Given a vnode (a_vp), returns the attributes requested for that vnode (*a_vap).  For mockfs, we don't care
 *   about the majority of attributes (we are not a fully featured filesystem).  We will return a minimal set of
 *   attributes for any request, regardless of which attributes were requested, to ensure that we look like a sane
 *   file, and so that permissions are set appropriately to allow execution of the executable vnode.
 *
 * Returns 0 on success, or an error.
 */
int
mockfs_getattr(struct vnop_getattr_args * ap)
{
	/*
	 * For the moment, we don't actually care about most attributes.  We'll
	 *   deal with actually managing attributes as part of the general cleanup.
	 */
	vnode_t vp;
	mockfs_fsnode_t fsnode;
	struct vnode_attr * vap;

	vp = ap->a_vp;
	fsnode = (mockfs_fsnode_t)vp->v_data;
	vap = ap->a_vap;
#if MOCKFS_RPI5_RAMROOT
	if (((mockfs_mount_t)fsnode->mnt->mnt_data)->ramroot_count) {
		/* Preserve va_active: VFS requested attributes, not a zeroed request. */
		VATTR_RETURN(vap, va_type, vp->v_type);
		VATTR_RETURN(vap, va_mode, (mode_t)fsnode->mode);
		VATTR_RETURN(vap, va_uid, 0);
		VATTR_RETURN(vap, va_gid, 0);
		VATTR_RETURN(vap, va_nlink, vp->v_type == VDIR ? 2 : 1);
		VATTR_RETURN(vap, va_fileid, fsnode->fileid);
		VATTR_RETURN(vap, va_parentid, fsnode->parent ? fsnode->parent->fileid : fsnode->fileid);
		VATTR_RETURN(vap, va_fsid, (uint32_t)fsnode->mnt->mnt_vfsstat.f_fsid.val[0]);
		VATTR_RETURN(vap, va_total_size, fsnode->size);
		VATTR_RETURN(vap, va_data_size, fsnode->size);
		uint64_t allocated = (fsnode->size + RPI5_RFS_PAGE - 1) & ~(uint64_t)(RPI5_RFS_PAGE - 1);
		VATTR_RETURN(vap, va_total_alloc, allocated);
		VATTR_RETURN(vap, va_data_alloc, allocated);
		VATTR_RETURN(vap, va_iosize, RPI5_RFS_PAGE);
		return 0;
	}
#endif
	bzero(vap, sizeof(*vap));
	VATTR_RETURN(vap, va_nlink, 1); /* Simply assert that someone has at least one link to us */
	VATTR_RETURN(vap, va_mode, VREAD | VWRITE | VEXEC);
	VATTR_RETURN(vap, va_fileid, fsnode->type);
	VATTR_RETURN(vap, va_total_size, fsnode->size);
	VATTR_RETURN(vap, va_total_alloc, fsnode->size);
	VATTR_RETURN(vap, va_data_size, fsnode->size);
	VATTR_RETURN(vap, va_data_alloc, fsnode->size);

	return 0;
}

/*
 * struct vnop_read_args {
 *   struct vnodeop_desc *a_desc; // We don't care about this (for now)
 *   vnode_t a_vp;                // Pointer to the vnode we are interested in
 *   struct uio *a_uio;           // Description of the request
 *   int a_ioflag;                // IO flags (we don't care about these)
 *   vfs_context_t a_context;     // We don't care about this (for now)
 * };
 *
 * mockfs_read:
 *   Given a vnode (a_vp), a set of flags (a_ioflag), and a description of a read request (a_uio), executes the read
 *   request and returns the resulting data through the description (a_uio).  mockfs has very little to do here; we
 *   merely mandate that any read attempt MUST be on VREG (our MOCKFS_FILE object), as it is the only vnode that has
 *   a backing store that can support a read (the other node types being purely in-memory hacks).  Because we do not
 *   support VNOP_OPEN, we can probably assume that the kernel is the only entity that will ever issue a VNOP_READ
 *   (as part of the exec path) to a mockfs vnode.
 *
 * Returns 0 on success, or an error.
 */
int
mockfs_read(struct vnop_read_args * ap)
{
	int rvalue;
	vnode_t vp;
	mockfs_fsnode_t fsnode;

	vp = ap->a_vp;
	fsnode = (mockfs_fsnode_t) vp->v_data;

	/*
	 * We're just an ugly frontend for the devnode, so we shouldn't need to do much for reads;
	 *   pass the work to cluster_read.
	 */
	if (vp->v_type == VREG) {
		rvalue = cluster_read(vp, ap->a_uio, fsnode->size, ap->a_ioflag);
	} else {
		/*
		 * You've tried to read from a nonregular file; I hate you.
		 */
		rvalue = ENOTSUP;
	}

	return rvalue;
}

/*
 * struct vnop_reclaim_args {
 *   struct vnodeop_desc *a_desc; // We don't care about this (for now)
 *   vnode_t a_vp;                // Pointer to the vnode we are reclaiming
 *   vfs_context_t a_context;     // We don't care about this (for now)
 * };
 *
 * mockfs_reclaim:
 *   Given a vnode (a_vp), performs any cleanup needed to allow VFS to reclaim the vnode.  Because the mockfs tree
 *   is always in memory, we have very little to do as part of reclaim, so we'll just zero a few pointers and let
 *   VFS reclaim the vnode.
 */
int
mockfs_reclaim(struct vnop_reclaim_args * ap)
{
	int rvalue;
	vnode_t vp;
	mockfs_fsnode_t fsnode;

	vp = ap->a_vp;
	fsnode = (mockfs_fsnode_t) vnode_fsnode(vp);
	rvalue = mockfs_fsnode_drop_vnode(fsnode);

	return rvalue;
}

/*
 * struct vnop_strategy_args {
 *   struct vnodeop_desc *a_desc; // We don't care about this (for now)
 *   struct buf *a_bp;            // Description of the desired IO
 * };
 *
 * mockfs_strategy:
 *   Given an IO description (a_bp), does any preparations required by the filesystem, and then passes the IO off to
 *   the appropriate device.  mockfs doesn't need to do anything to prepare for the IO, so we simply pass it off to
 *   our backing device.
 *
 * Returns 0 on success, or an error.
 */
int
mockfs_strategy(struct vnop_strategy_args * ap)
{
	int rvalue;
	vnode_t dvp;

	/*
	 * We'll avoid checking for a memory-backed device here; we already do this for blockmap, which will be
	 *   called as part of the IO path.
	 */

	dvp = vfs_devvp(buf_vnode(ap->a_bp)->v_mount);

	if (dvp) {
		rvalue = buf_strategy(dvp, ap);
		vnode_put(dvp);
	} else {
		/*
		 * I'm not certain this is the BEST error to return for this case.
		 */
		rvalue = EIO;
	}

	return rvalue;
}

/*
 * struct vnop_pagein_args {
 *   struct vnodeop_desc *a_desc; // We don't care about this (for now)
 *   vnode_t a_vp;                // Pointer to the vnode we are interested in
 *   upl_t a_pl;                  // Describes the pages that need to be paged in
 *   upl_offset_t a_pl_offset;    // Offset in the UPL to start placing data at
 *   off_t a_f_offset;            // File offset to begin paging in at
 *   size_t a_size;               // Bytes of data to page in
 *   int a_flags;                 // UPL flags (we don't care about these)
 *   vfs_context_t a_context;     // We don't care about this (for now)
 * };
 *
 * mockfs_pagegin:
 *   Given a vnode (a_vp), and a region, described by an offset (a_f_offset) and a size (a_size), pages the region
 *   into the given UPL (a_pl), starting at the UPL offset (a_pl_offset).  For mockfs, we don't have anything significant
 *   to do for pagein, so we largely serve as a wrapper to the cluster_pagein routine.
 *
 * Returns 0 on success, or an error.
 */
int
mockfs_pagein(struct vnop_pagein_args * ap)
{
	mockfs_fsnode_t fsnode;
	mockfs_mount_t mockfs_mnt;

	/*
	 * Nothing special needed from us; just nab the filesize and kick the work over to cluster_pagein.
	 */
	fsnode = (mockfs_fsnode_t) ap->a_vp->v_data;
	mockfs_mnt = ((mockfs_mount_t) fsnode->mnt->mnt_data);

	/*
	 * If we represent a memory backed device, we should be pointing directly to the backing store; we should never
	 *   see a pagein in this case.
	 */
	if (mockfs_mnt->mockfs_memory_backed) {
		panic("mockfs_pagein called for a memory-backed device");
	}

	if (ap->a_size > INT_MAX) {
		panic("mockfs_pagein size exceeds cluster_pagein's int contract");
	}
	return cluster_pagein(ap->a_vp, ap->a_pl, ap->a_pl_offset, ap->a_f_offset, (int)ap->a_size, fsnode->size, ap->a_flags);
}

/*
 * struct vnop_blockmap_args {
 *   struct vnodeop_desc *a_desc; // We don't care about this (for now)
 *   vnode_t a_vp;                // Pointer to the vnode we are interested in
 *   off_t a_foffset;             // File offset we are interested in
 *   size_t a_size;               // Size of the region we are interested in
 *   daddr64_t *a_bpn;            // Return parameter: physical block number the region we are interest in starts at
 *   size_t *a_run;               // Return parameter: number of contiguous bytes of data
 *   void *a_poff;                // Unused, as far as I know
 *   int a_flags;                 // Used to distinguish reads and writes; we don't care
 *   vfs_context_t a_context;     // We don't care about this (for now)
 * };
 *
 * mockfs_blockmap:
 *   Given a vnode (a_vp), and a region, described by an offset (a_foffset), and a size (a_size), tells the caller
 *   which physical block (on the backing device) the region begins at (*a_bpn), and how many bytes can be read
 *   before the first discontinuity (*a_run).  For mockfs, because only VREG files are eligible for IO, and because
 *   all VREG files are simply a frontend for the backing device, this mapping will always be one to one, and all we
 *   need to do is convert the physical offset to the physical block number.
 *
 * Returns 0 on success, or an error.
 */
int
mockfs_blockmap(struct vnop_blockmap_args * ap)
{
	int rvalue;
	off_t foffset;
	size_t * run;
	uint32_t blksize;
	daddr64_t * bpn;
	vnode_t vp;
	mockfs_fsnode_t fsnode;

	rvalue = 0;
	foffset = ap->a_foffset;
	run = ap->a_run;
	bpn = ap->a_bpn;
	vp = ap->a_vp;
	fsnode = (mockfs_fsnode_t) vp->v_data;
	blksize = vp->v_mount->mnt_devblocksize;

#if MOCKFS_RPI5_RAMROOT
	if (((mockfs_mount_t)fsnode->mnt->mnt_data)->ramroot_count) {
		uint64_t allocated = (fsnode->size + RPI5_RFS_PAGE - 1) & ~(uint64_t)(RPI5_RFS_PAGE - 1);
		if (vp->v_type != VREG) { return ENOTSUP; }
		if ((ap->a_flags & VNODE_WRITE) || foffset < 0 || !blksize ||
		    (uint64_t)foffset >= allocated || (uint64_t)foffset % blksize) { return EINVAL; }
		if (bpn) { *bpn = (daddr64_t)((fsnode->data_offset + (uint64_t)foffset) / blksize); }
		if (run) { *run = (size_t)(allocated - (uint64_t)foffset); }
		return 0;
	}
#endif

	/*
	 * If we represent a memory backed device, we should be pointing directly to the backing store; all IO should
	 *   be satisfied from the UBC, and any called to blockmap (inidicating an attempted IO to the backing store)
	 *   is therefore disallowed.
	 */
	if (((mockfs_mount_t) fsnode->mnt->mnt_data)->mockfs_memory_backed) {
		printf("mockfs_blockmap called for a memory-backed device\n");
	}

	/*
	 * This will ultimately be simple; the vnode must be VREG (init), and the mapping will be 1 to 1.
	 *   This also means that their request should always be contiguous, so the run calculation is easy!
	 */
	if (vp->v_type == VREG) {
		*bpn = foffset / blksize;
		*run = fsnode->size - foffset;

		if (ap->a_size > *run) {
			/* We've been asked for more data than the backing device can provide; we're done. */
			panic("mockfs_blockmap was asked for a region that extended past the end of the backing device");
		}
	} else {
		rvalue = ENOTSUP;
	}

	return rvalue;
}

int(**mockfs_vnodeop_p)(void *);
const struct vnodeopv_entry_desc mockfs_vnodeop_entries[] = {
	{ .opve_op = &vnop_default_desc, .opve_impl = (VOPFUNC)(void (*)(void)) vn_default_error }, /* default */
	{ .opve_op = &vnop_lookup_desc, .opve_impl = (VOPFUNC) mockfs_lookup }, /* lookup */
	{ .opve_op = &vnop_create_desc, .opve_impl = (VOPFUNC) err_create },/* create */
#if MOCKFS_RPI5_RAMROOT
	{ .opve_op = &vnop_open_desc, .opve_impl = (VOPFUNC) mockfs_ramroot_open },
#else
	{ .opve_op = &vnop_open_desc, .opve_impl = (VOPFUNC) err_open }, /* open */
#endif
	{ .opve_op = &vnop_mknod_desc, .opve_impl = (VOPFUNC) err_mknod }, /* mknod */
#if MOCKFS_RPI5_RAMROOT
	{ .opve_op = &vnop_close_desc, .opve_impl = (VOPFUNC) mockfs_ramroot_close },
#else
	{ .opve_op = &vnop_close_desc, .opve_impl = (VOPFUNC) err_close }, /* close */
#endif
	{ .opve_op = &vnop_access_desc, .opve_impl = (VOPFUNC) err_access }, /* access */
	{ .opve_op = &vnop_getattr_desc, .opve_impl = (VOPFUNC) mockfs_getattr }, /* getattr */
	{ .opve_op = &vnop_setattr_desc, .opve_impl = (VOPFUNC) err_setattr }, /* setattr */
	{ .opve_op = &vnop_read_desc, .opve_impl = (VOPFUNC) mockfs_read }, /* read */
	{ .opve_op = &vnop_write_desc, .opve_impl = (VOPFUNC) err_write }, /* write */
	{ .opve_op = &vnop_ioctl_desc, .opve_impl = (VOPFUNC) err_ioctl }, /* ioctl */
	{ .opve_op = &vnop_select_desc, .opve_impl = (VOPFUNC) err_select }, /* select */
	{ .opve_op = &vnop_mmap_desc, .opve_impl = (VOPFUNC) err_mmap }, /* mmap */
	{ .opve_op = &vnop_fsync_desc, .opve_impl = (VOPFUNC) nop_fsync }, /* fsync */
	{ .opve_op = &vnop_remove_desc, .opve_impl = (VOPFUNC) err_remove }, /* remove */
	{ .opve_op = &vnop_link_desc, .opve_impl = (VOPFUNC) err_link }, /* link */
	{ .opve_op = &vnop_rename_desc, .opve_impl = (VOPFUNC) err_rename }, /* rename */
	{ .opve_op = &vnop_mkdir_desc, .opve_impl = (VOPFUNC) err_mkdir }, /* mkdir */
	{ .opve_op = &vnop_rmdir_desc, .opve_impl = (VOPFUNC) err_rmdir }, /* rmdir */
	{ .opve_op = &vnop_symlink_desc, .opve_impl = (VOPFUNC) err_symlink }, /* symlink */
#if MOCKFS_RPI5_RAMROOT
	{ .opve_op = &vnop_readdir_desc, .opve_impl = (VOPFUNC) mockfs_ramroot_readdir },
#else
	{ .opve_op = &vnop_readdir_desc, .opve_impl = (VOPFUNC) err_readdir }, /* readdir */
#endif
	{ .opve_op = &vnop_readlink_desc, .opve_impl = (VOPFUNC) err_readlink }, /* readlink */
	{ .opve_op = &vnop_inactive_desc, .opve_impl = (VOPFUNC) err_inactive }, /* inactive */
	{ .opve_op = &vnop_reclaim_desc, .opve_impl = (VOPFUNC) mockfs_reclaim }, /* reclaim */
	{ .opve_op = &vnop_strategy_desc, .opve_impl = (VOPFUNC) mockfs_strategy }, /* strategy */
	{ .opve_op = &vnop_pathconf_desc, .opve_impl = (VOPFUNC) err_pathconf }, /* pathconf */
	{ .opve_op = &vnop_advlock_desc, .opve_impl = (VOPFUNC) err_advlock }, /* advlock */
	{ .opve_op = &vnop_bwrite_desc, .opve_impl = (VOPFUNC) err_bwrite }, /* bwrite */
	{ .opve_op = &vnop_pagein_desc, .opve_impl = (VOPFUNC) mockfs_pagein }, /* pagein */
	{ .opve_op = &vnop_pageout_desc, .opve_impl = (VOPFUNC) err_pageout }, /* pageout */
	{ .opve_op = &vnop_copyfile_desc, .opve_impl = (VOPFUNC) err_copyfile }, /* copyfile */
	{ .opve_op = &vnop_blktooff_desc, .opve_impl = (VOPFUNC) err_blktooff }, /* blktooff */
	{ .opve_op = &vnop_offtoblk_desc, .opve_impl = (VOPFUNC) err_offtoblk }, /* offtoblk */
	{ .opve_op = &vnop_blockmap_desc, .opve_impl = (VOPFUNC) mockfs_blockmap }, /* blockmap */
	{ .opve_op = (struct vnodeop_desc *) NULL, .opve_impl = (VOPFUNC) NULL }
};

const struct vnodeopv_desc mockfs_vnodeop_opv_desc = {
	.opv_desc_vector_p = &mockfs_vnodeop_p,
	.opv_desc_ops = mockfs_vnodeop_entries
};
