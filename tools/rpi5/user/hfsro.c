/* SPDX-License-Identifier: BSD-2-Clause */
/* Uses the pinned Apple mount-argument header and native Darwin statfs ABI.
 * No raw disk write, formatting, journal override, mount update or force flag. */
#include "runtime.h"
#include "hfsro.h"
#include <hfs_mount.h>
#include <sys/disk.h>

_Static_assert(sizeof(struct hfs_mount_args) == 48, "Darwin LP64 HFS mount arguments");
_Static_assert(offsetof(struct hfs_mount_args, flags) == 32, "HFS flags ABI");
_Static_assert(offsetof(struct hfs_mount_args, journal_disable) == 44, "HFS journal ABI");
_Static_assert(sizeof(struct statfs) == 2168, "Darwin statfs64 ABI");
_Static_assert(offsetof(struct statfs, f_flags) == 64, "statfs64 flags ABI");
_Static_assert(offsetof(struct statfs, f_mntfromname) == 1112, "statfs64 source ABI");

static const char mountpoint[] = "/mnt/hfs";
static const unsigned readonly_flags = MNT_RDONLY | MNT_NOSUID | MNT_NODEV;

static void clear(void *buffer, size_t size)
{
    /* Volatile stores keep freestanding large-struct initialization from
     * introducing an unresolved compiler-generated bzero/libc call. */
    volatile unsigned char *p = buffer;
    while (size--) *p++ = 0;
}

static int field_equal(const char *value, size_t size, const char *expected)
{
    for (size_t i = 0; i < size; i++) {
        if (value[i] != expected[i]) return 0;
        if (!value[i]) return 1;
    }
    return 0;
}

static int partition_path(const char *path)
{
    const char prefix[] = "/dev/disk";
    for (size_t i = 0; i < sizeof prefix - 1; i++)
        if (path[i] != prefix[i]) return 0;
    path += sizeof prefix - 1;
    if (*path < '0' || *path > '9') return 0;
    unsigned disk = (unsigned)(*path++ - '0');
    if (*path >= '0' && *path <= '9') {
        if (!disk) return 0; /* Reject aliases with leading zeroes. */
        disk = disk * 10 + (unsigned)(*path++ - '0');
    }
    return disk <= 31 && rt_equal(path, "s2");
}

static long inspect_mount(struct statfs *info)
{
    return rt_call(345, (long)mountpoint, (long)info, 0, 0, 0, 0);
}

static int mounted(const struct statfs *info, const char *device)
{
    return field_equal(info->f_fstypename, sizeof info->f_fstypename, "hfs") &&
        field_equal(info->f_mntonname, sizeof info->f_mntonname, mountpoint) &&
        field_equal(info->f_mntfromname, sizeof info->f_mntfromname, device) &&
        (info->f_flags & readonly_flags) == readonly_flags;
}

static long readonly_device(const char *device)
{
    long fd = rt_open(device, RT_RDONLY);
    if (fd < 0) return fd;
    uint32_t size = 0, writable = 1;
    uint64_t blocks = 0;
    long rc = rt_call(54, fd, DKIOCGETBLOCKSIZE, (long)&size, 0, 0, 0);
    if (!rc) rc = rt_call(54, fd, DKIOCGETBLOCKCOUNT, (long)&blocks, 0, 0, 0);
    if (!rc) rc = rt_call(54, fd, DKIOCISWRITABLE, (long)&writable, 0, 0, 0);
    long closed = rt_close((int)fd);
    if (rc) return rc;
    if (closed) return closed;
    return size == 512 && blocks && blocks <= (UINT64_C(1) << 32) && !writable ? 0 : -22;
}

int hfsro_main(int argc, char **argv)
{
    if (argc != 3 || !partition_path(argv[2]) ||
        !(rt_equal(argv[1], "mount") || rt_equal(argv[1], "status") || rt_equal(argv[1], "unmount"))) {
        rt_put(2, "usage: hfsro mount|status|unmount /dev/diskNs2 (N=0..31; /mnt/hfs only)\n");
        return 2;
    }
    const char *device = argv[2];
    struct statfs info;
    clear(&info, sizeof info);
    long rc = inspect_mount(&info);
    if (rc) { rt_error("hfsro statfs64", rc); return 1; }
    if (rt_equal(argv[1], "mount")) {
        /* Only cover the fixed directory on the immutable RAM root. Never
         * turn an existing mount into an update or cover another filesystem. */
        if (!field_equal(info.f_fstypename, sizeof info.f_fstypename, "mockfs") ||
            !field_equal(info.f_mntonname, sizeof info.f_mntonname, "/")) {
            rt_error("hfsro covered-root guard", -22); return 1;
        }
        rc = readonly_device(device);
        if (rc) { rt_error("hfsro device read-only guard", rc); return 1; }
        struct hfs_mount_args args;
        clear(&args, sizeof args);
        args.fspec = (char *)device;
        args.hfs_uid = (uid_t)-1;
        args.hfs_gid = (gid_t)-1;
        args.hfs_mask = (mode_t)-1;
        args.flags = HFSFSMNT_EXTENDED_ARGS;
        rc = rt_call(167, (long)"hfs", (long)mountpoint, readonly_flags, (long)&args, 0, 0);
        if (rc) { rt_error("hfsro mount", rc); return 1; }
        rc = inspect_mount(&info);
        if (rc || !mounted(&info, device)) {
            rt_error("hfsro mounted identity/read-only guard", rc ? rc : -22); return 1;
        }
        rt_put(1, "RPI5XNU:HFSRO:MOUNTED");
    } else {
        if (!mounted(&info, device)) { rt_error("hfsro mounted identity/read-only guard", -22); return 1; }
        if (rt_equal(argv[1], "unmount")) {
            rc = rt_call(159, (long)mountpoint, 0, 0, 0, 0, 0);
            if (rc) { rt_error("hfsro unmount", rc); return 1; }
            rc = inspect_mount(&info);
            if (rc || !field_equal(info.f_fstypename, sizeof info.f_fstypename, "mockfs") ||
                !field_equal(info.f_mntonname, sizeof info.f_mntonname, "/")) {
                rt_error("hfsro post-unmount guard", rc ? rc : -22); return 1;
            }
            rt_put(1, "RPI5XNU:HFSRO:UNMOUNTED");
        } else rt_put(1, "RPI5XNU:HFSRO:STATUS");
    }
    rt_put(1, " DEVICE="); rt_put(1, device);
    rt_put(1, " PATH=/mnt/hfs READONLY=1\n");
    return 0;
}
