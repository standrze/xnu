/* SPDX-License-Identifier: BSD-2-Clause */
/* Syscall doubles only. Never mounts or opens a real disk. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <hfs_mount.h>
#include <sys/disk.h>
#include "../user/runtime.h"
#include "../user/hfsro.h"

static const char *mode, *device, *operation;
static unsigned stats, opens, closes, ioctls, mounts, unmounts;
static int is_mounted;
static int is(const char *name) { return !strcmp(mode, name); }
int rt_equal(const char *a, const char *b) { return !strcmp(a, b); }
long rt_open(const char *path, int flags)
{
    assert(!strcmp(path, device) && flags == RT_RDONLY);
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
        memset(info, 0, sizeof(*info));
        strcpy(info->f_fstypename, is_mounted ? "hfs" : "mockfs");
        strcpy(info->f_mntonname, is_mounted ? "/mnt/hfs" : "/");
        strcpy(info->f_mntfromname, is_mounted ? device : "md0");
        info->f_flags = MNT_RDONLY | MNT_NOSUID | MNT_NODEV;
        if (is("from") && is_mounted) strcpy(info->f_mntfromname, "/dev/disk31s2");
        if (is("target") && is_mounted) strcpy(info->f_mntonname, "/other");
        if (is("type")) strcpy(info->f_fstypename, "apfs");
        if (is("flags") && is_mounted) info->f_flags &= ~MNT_RDONLY;
        if (is("unterminated") && is_mounted) memset(info->f_fstypename, 'h', sizeof info->f_fstypename);
        if (is("unmount-still-mounted") && stats == 2) strcpy(info->f_fstypename, "hfs");
        return 0;
    }
    if (n == 54) {
        assert(a == 77 && !d); ioctls++;
        if (is("ioctl")) return -5;
        if ((unsigned long)b == DKIOCGETBLOCKSIZE) *(uint32_t *)c = is("blocksize") ? 4096 : 512;
        else if ((unsigned long)b == DKIOCGETBLOCKCOUNT)
            *(uint64_t *)c = is("zero-blocks") ? 0 : is("large-blocks") ? (UINT64_C(1) << 32) + 1 : 524288;
        else { assert((unsigned long)b == DKIOCISWRITABLE); *(uint32_t *)c = is("writable"); }
        return 0;
    }
    if (n == 167) {
        assert(!is_mounted && !strcmp((char *)a, "hfs") && !strcmp((char *)b, "/mnt/hfs"));
        assert(c == (MNT_RDONLY | MNT_NOSUID | MNT_NODEV));
        const struct hfs_mount_args *args = (void *)d;
        assert(!strcmp(args->fspec, device));
        assert(args->hfs_uid == (uid_t)-1 && args->hfs_gid == (gid_t)-1 && args->hfs_mask == (mode_t)-1);
        assert(!args->hfs_encoding && !args->hfs_timezone.tz_minuteswest && !args->hfs_timezone.tz_dsttime);
        assert(args->flags == HFSFSMNT_EXTENDED_ARGS);
        assert(!args->journal_tbuffer_size && !args->journal_flags && !args->journal_disable);
        mounts++;
        if (is("mount")) return -5;
        if (is("interrupt")) return -4;
        is_mounted = 1; return 0;
    }
    assert(n == 159 && !strcmp((char *)a, "/mnt/hfs") && !b && !c && !d);
    unmounts++;
    assert(is_mounted);
    if (is("unmount")) return -16;
    is_mounted = 0; return 0;
}
int rt_write_all(int fd, const void *p, size_t n) { return fwrite(p, 1, n, fd == 1 ? stdout : stderr) == n ? 0 : -1; }
void rt_put(int fd, const char *text) { (void)rt_write_all(fd, text, strlen(text)); }
void rt_error(const char *text, long value) { fprintf(stderr, "%s: errno %ld\n", text, -value); }
int main(int argc, char **argv)
{
    mode = getenv("HFSRO_FIXTURE"); if (!mode) mode = "";
    device = argc == 3 ? argv[2] : "";
    operation = argc > 1 ? argv[1] : "";
    is_mounted = strcmp(operation, "mount") != 0 || is("already-mounted");
    if (is("not-mounted")) is_mounted = 0;
    int rc = hfsro_main(argc, argv);
    fprintf(stderr, "FIXTURE STATS=%u OPENS=%u CLOSES=%u IOCTLS=%u MOUNTS=%u UNMOUNTS=%u\n",
            stats, opens, closes, ioctls, mounts, unmounts);
    return rc;
}
