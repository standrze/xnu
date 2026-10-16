/* SPDX-License-Identifier: BSD-2-Clause */
/* Distinct opt-in write-trial image only; absent from default userland.
 * No raw writes, format, update, journal override, force or automatic rollback.
 * The provider must separately establish exact-card admission and cache sync;
 * writable-device ioctls and these markers do NOT prove either or durability. */
#if defined(RPI5_HFS_WRITE_TRIAL) && RPI5_HFS_WRITE_TRIAL == 1
#include "runtime.h"
#include "hfsrw.h"
#include <hfs_mount.h>
#include <sys/disk.h>

_Static_assert(sizeof(struct hfs_mount_args) == 48, "Darwin LP64 HFS arguments");
_Static_assert(offsetof(struct hfs_mount_args, flags) == 32, "HFS flags ABI");
_Static_assert(offsetof(struct hfs_mount_args, journal_disable) == 44, "HFS journal ABI");
_Static_assert(sizeof(struct statfs) == 2168, "Darwin statfs64 ABI");
_Static_assert(offsetof(struct statfs, f_flags) == 64, "statfs64 flags ABI");
_Static_assert(offsetof(struct statfs, f_mntfromname) == 1112, "statfs64 source ABI");

static const char device[] = "/dev/disk0s2";
static const char mountpoint[] = "/mnt/hfs";
static const unsigned mountflags = MNT_NOSUID | MNT_NODEV;

static void clear(void *buffer, size_t length)
{
    volatile unsigned char *p = buffer;
    while (length--) *p++ = 0;
}
static int field(const char *value, size_t capacity, const char *expected)
{
    for (size_t i = 0; i < capacity; i++) {
        if (value[i] != expected[i]) return 0;
        if (!value[i]) return 1;
    }
    return 0;
}
static long inspect(struct statfs *info)
{
    clear(info, sizeof *info);
    return rt_call(345, (long)mountpoint, (long)info, 0, 0, 0, 0);
}
static int covered_root(const struct statfs *info)
{
    return field(info->f_fstypename, sizeof info->f_fstypename, "mockfs") &&
        field(info->f_mntonname, sizeof info->f_mntonname, "/") &&
        (info->f_flags & MNT_RDONLY);
}
static int mounted(const struct statfs *info)
{
    return field(info->f_fstypename, sizeof info->f_fstypename, "hfs") &&
        field(info->f_mntonname, sizeof info->f_mntonname, mountpoint) &&
        field(info->f_mntfromname, sizeof info->f_mntfromname, device) &&
        (info->f_flags & (mountflags | MNT_RDONLY | MNT_NOEXEC)) == mountflags;
}
static long writable_partition(void)
{
    /* Read-only descriptor for geometry/admission queries, never raw writes. */
    long fd = rt_open(device, RT_RDONLY);
    if (fd < 0) return fd;
    uint32_t size = 0, writable = 0;
    uint64_t blocks = 0;
    long rc = rt_call(54, fd, DKIOCGETBLOCKSIZE, (long)&size, 0, 0, 0);
    if (!rc) rc = rt_call(54, fd, DKIOCGETBLOCKCOUNT, (long)&blocks, 0, 0, 0);
    if (!rc) rc = rt_call(54, fd, DKIOCISWRITABLE, (long)&writable, 0, 0, 0);
    long closed = rt_close((int)fd);
    if (rc) return rc;
    if (closed) return closed;
    return size == 512 && blocks == 262144 && writable == 1 ? 0 : -22;
}
int hfsrw_main(int argc, char **argv)
{
    if (argc != 2 || !(rt_equal(argv[1], "mount") || rt_equal(argv[1], "status") ||
                        rt_equal(argv[1], "unmount"))) {
        rt_put(2, "usage: hfsrw mount|status|unmount (/dev/disk0s2 at /mnt/hfs only)\n");
        return 2;
    }
    struct statfs info;
    long rc = inspect(&info);
    if (rc) { rt_error("hfsrw statfs64", rc); return 1; }
    const char *marker;
    if (rt_equal(argv[1], "mount")) {
        if (!covered_root(&info)) { rt_error("hfsrw covered-root guard", -22); return 1; }
        rc = writable_partition();
        if (rc) { rt_error("hfsrw writable-partition guard", rc); return 1; }
        struct hfs_mount_args args;
        clear(&args, sizeof args);
        args.fspec = (char *)device;
        args.hfs_uid = (uid_t)-1;
        args.hfs_gid = (gid_t)-1;
        args.hfs_mask = (mode_t)-1;
        args.flags = HFSFSMNT_EXTENDED_ARGS;
        rc = rt_call(167, (long)"hfs", (long)mountpoint, mountflags, (long)&args, 0, 0);
        if (rc) { rt_error("hfsrw mount", rc); return 1; }
        rc = inspect(&info);
        if (rc || !mounted(&info)) {
            rt_error("hfsrw mounted identity/write guard", rc ? rc : -22); return 1;
        }
        marker = "RPI5XNU:HFSRW:MOUNTED";
    } else {
        if (!mounted(&info)) { rt_error("hfsrw mounted identity/write guard", -22); return 1; }
        /* A revoked provider must not produce a fresh writable status marker. */
        rc = writable_partition();
        if (rc) { rt_error("hfsrw writable-partition guard", rc); return 1; }
        if (rt_equal(argv[1], "unmount")) {
            rc = rt_call(159, (long)mountpoint, 0, 0, 0, 0, 0);
            if (rc) { rt_error("hfsrw unmount", rc); return 1; }
            rc = inspect(&info);
            if (rc || !covered_root(&info)) {
                rt_error("hfsrw post-unmount guard", rc ? rc : -22); return 1;
            }
            marker = "RPI5XNU:HFSRW:UNMOUNTED";
        } else marker = "RPI5XNU:HFSRW:STATUS";
    }
    rt_put(1, marker);
    rt_put(1, " DEVICE=/dev/disk0s2 PATH=/mnt/hfs READONLY=0 DURABILITY_VERIFIED=0\n");
    return 0;
}
#endif
