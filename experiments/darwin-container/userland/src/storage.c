/* SPDX-License-Identifier: BSD-2-Clause
 * Mount only the VZ workload profile's explicit data disk; no formatting/raw writes.
 */
#include "runtime.h"
#include <sys/mount.h>
#include <hfs_mount.h>
_Static_assert(sizeof(struct hfs_mount_args)==48, "Darwin arm64 HFS mount ABI");
_Static_assert(sizeof(struct statfs)==2168, "Darwin arm64 statfs64 ABI");

int workload_mount(void)
{
    struct hfs_mount_args args={0};
    args.fspec="/dev/disk0";
    args.hfs_uid=(uid_t)-1; args.hfs_gid=(gid_t)-1; args.hfs_mask=(mode_t)-1;
    args.flags=HFSFSMNT_EXTENDED_ARGS;
    long result=-2;
    /* IOService publication is asynchronous to the read-only RAM-root boot. */
    for (unsigned attempt=0; attempt<10; attempt++) {
        long disk=rt_open(args.fspec, RT_RDONLY);
        if (disk>=0) {
            rt_close((int)disk);
            result=rt_call(167, (long)"hfs", (long)"/data", MNT_NOSUID|MNT_NODEV, (long)&args, 0, 0);
            if (!result) break;
            if (result!=-19 && result!=-2) break;
        } else result=disk;
        rt_sleep(1);
    }
    if (result) { rt_error("workload mount /dev/disk0", result); return 1; }
    struct statfs info;
    for (size_t i=0; i<sizeof info; i++) ((volatile unsigned char *)&info)[i]=0;
    result=rt_call(345, (long)"/data", (long)&info, 0, 0, 0, 0);
    if (result || !rt_equal(info.f_fstypename, "hfs") || !rt_equal(info.f_mntonname, "/data") ||
        !rt_equal(info.f_mntfromname, "/dev/disk0") || (info.f_flags&MNT_RDONLY)) {
        rt_error("workload mounted identity", result ? result : -22); return 1;
    }
    rt_put(1, "DARWIN:STORAGE:MOUNTED /dev/disk0 /data HFS READWRITE\n");
    return 0;
}
