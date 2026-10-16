/* SPDX-License-Identifier: BSD-2-Clause */
/* Explicit syscall doubles. No real mount, device, filesystem or SD access. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <hfs_mount.h>
#include <sys/disk.h>
#include "../user/runtime.h"
#include "../user/hfsrw.h"

static const char *mode;
static unsigned stats, opens, closes, ioctls, mounts, unmounts;
static int active;
static int is(const char *name) { return !strcmp(mode, name); }
int rt_equal(const char *a, const char *b) { return !strcmp(a, b); }
long rt_open(const char *path, int flags)
{
    assert(!strcmp(path, "/dev/disk0s2") && flags == RT_RDONLY);
    opens++;
    return is("open") ? -6 : 77;
}
long rt_close(int fd) { assert(fd == 77); closes++; return is("close") ? -5 : 0; }
long rt_call(long n, long a, long b, long c, long d, long e, long f)
{
    assert(!e && !f);
    if (n == 345) {
        assert(!strcmp((char *)a, "/mnt/hfs") && !c && !d);
        stats++;
        if (is("stat") || (is("poststat") && stats == 2)) return -5;
        struct statfs *info = (void *)b;
        memset(info, 0, sizeof *info);
        strcpy(info->f_fstypename, active ? "hfs" : "mockfs");
        strcpy(info->f_mntonname, active ? "/mnt/hfs" : "/");
        strcpy(info->f_mntfromname, active ? "/dev/disk0s2" : "md0");
        info->f_flags = active ? MNT_NOSUID | MNT_NODEV : MNT_RDONLY;
        if (is("root-writable") && !active) info->f_flags = 0;
        if (is("type")) strcpy(info->f_fstypename, "apfs");
        if (is("target")) strcpy(info->f_mntonname, "/other");
        if (is("from") && active) strcpy(info->f_mntfromname, "/dev/disk0s1");
        if (is("readonly") && active) info->f_flags |= MNT_RDONLY;
        if (is("noexec") && active) info->f_flags |= MNT_NOEXEC;
        if (is("flags") && active) info->f_flags &= ~MNT_NODEV;
        if (is("unterminated")) memset(info->f_fstypename, 'h', sizeof info->f_fstypename);
        if (is("unmount-still-mounted") && stats == 2) strcpy(info->f_fstypename, "hfs");
        return 0;
    }
    if (n == 54) {
        assert(a == 77 && !d); ioctls++;
        if (is("ioctl") || (is("count-ioctl") && ioctls == 2) ||
            (is("writable-ioctl") && ioctls == 3)) return -5;
        if ((unsigned long)b == DKIOCGETBLOCKSIZE) *(uint32_t *)c = is("blocksize") ? 4096 : 512;
        else if ((unsigned long)b == DKIOCGETBLOCKCOUNT) *(uint64_t *)c = is("capacity") ? 262145 : 262144;
        else {
            assert((unsigned long)b == DKIOCISWRITABLE);
            *(uint32_t *)c = is("protected") ? 0 : is("malformed-writable") ? 2 : 1;
        }
        return 0;
    }
    if (n == 167) {
        assert(!active && !strcmp((char *)a, "hfs") && !strcmp((char *)b, "/mnt/hfs"));
        assert(c == (MNT_NOSUID | MNT_NODEV)); /* No FORCE, UPDATE or journal bypass. */
        const struct hfs_mount_args *args = (void *)d;
        assert(!strcmp(args->fspec, "/dev/disk0s2"));
        assert(args->hfs_uid == (uid_t)-1 && args->hfs_gid == (gid_t)-1 && args->hfs_mask == (mode_t)-1);
        assert(!args->hfs_encoding && !args->hfs_timezone.tz_minuteswest && !args->hfs_timezone.tz_dsttime);
        assert(args->flags == HFSFSMNT_EXTENDED_ARGS);
        assert(!args->journal_tbuffer_size && !args->journal_flags && !args->journal_disable);
        mounts++;
        if (is("mount")) return -5;
        if (is("interrupt")) return -4;
        active = 1;
        return 0;
    }
    assert(n == 159 && !strcmp((char *)a, "/mnt/hfs") && !b && !c && !d);
    assert(active);
    unmounts++;
    if (is("sync-failure")) return -5;
    if (is("busy")) return -16;
    active = 0;
    return 0;
}
void rt_put(int fd, const char *text) { fputs(text, fd == 1 ? stdout : stderr); }
void rt_error(const char *text, long value) { fprintf(stderr, "%s: errno %ld\n", text, -value); }
int main(int argc, char **argv)
{
    mode = getenv("HFSRW_FIXTURE"); if (!mode) mode = "";
    active = argc > 1 && strcmp(argv[1], "mount");
    if (is("already-mounted")) active = 1;
    if (is("not-mounted")) active = 0;
    int rc = hfsrw_main(argc, argv);
    fprintf(stderr, "FIXTURE STATS=%u OPENS=%u CLOSES=%u IOCTLS=%u MOUNTS=%u UNMOUNTS=%u\n",
        stats, opens, closes, ioctls, mounts, unmounts);
    return rc;
}
