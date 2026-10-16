/* SPDX-License-Identifier: BSD-2-Clause */
/* Fixed catalog, read-only mounted-root evidence. Not authentication against a
 * malicious kernel. The caller must independently compare the self digest and
 * filesystem extent with the installed package; there is no circular self pin.
 * Finite userland calls do not contain a hung kernel syscall.
 */
#include "runtime.h"
#include <sys/mount.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <limits.h>
#include "bearssl_hash.h"

struct identity_entry {
    const char *path;
    unsigned mode;
    uint64_t bytes;
    const char *sha256; /* NULL only for this executable. */
};
#include "rootidentity_catalog.h"

_Static_assert(sizeof(struct stat) == 144, "Darwin stat64 ABI");
_Static_assert(sizeof(struct statfs) == 2168, "Darwin statfs64 ABI");
_Static_assert(offsetof(struct statfs, f_files) == 32, "Darwin statfs files");
_Static_assert(offsetof(struct statfs, f_fstypename) == 72, "Darwin statfs names");

static unsigned identity_calls;
static long identity_call(long number, long a, long b, long c)
{
    /* Reserve the last call for the one owned descriptor's close. */
    if (identity_calls >= (number==6?2048u:2047u)) return -5;
    identity_calls++;
    long rc = rt_call(number,a,b,c,0,0,0);
    if (rc < 0) rt_error("ROOTIDENTITY:SYSCALL",rc);
    return rc;
}

static void identity_number(const char *label, uint64_t value)
{
    rt_put(1,label); rt_number(1,value);
}

static void digest_hex(const unsigned char bytes[32], char hex[65])
{
    const char digits[]="0123456789abcdef";
    for (unsigned i=0;i<32;i++) {
        hex[2*i]=digits[bytes[i]>>4]; hex[2*i+1]=digits[bytes[i]&15];
    }
    hex[64]=0;
}

static int fixed_name(const char *actual, size_t capacity, const char *expected)
{
    size_t size=rt_len(expected);
    if (size>=capacity) return 0;
    for (size_t i=0;i<=size;i++) if (actual[i]!=expected[i]) return 0;
    return 1;
}

#define GUARDED(type) struct { uint64_t before[2]; type data; uint64_t after[2]; }
#define GUARD_INIT { {UINT64_C(0xc3c3c3c3c3c3c3c3),UINT64_C(0xc3c3c3c3c3c3c3c3)}, {0}, \
    {UINT64_C(0x3c3c3c3c3c3c3c3c),UINT64_C(0x3c3c3c3c3c3c3c3c)} }
#define INTACT(p) ((p).before[0]==UINT64_C(0xc3c3c3c3c3c3c3c3) && \
    (p).before[1]==UINT64_C(0xc3c3c3c3c3c3c3c3) && \
    (p).after[0]==UINT64_C(0x3c3c3c3c3c3c3c3c) && (p).after[1]==UINT64_C(0x3c3c3c3c3c3c3c3c))

static int identity_file(const struct identity_entry *entry)
{
    if (rt_equal(entry->path,"/dev")) {
        /* XNU mounts devfs over the archive's empty /dev. Its dynamic directory
         * length is not the underlying RAM-root record's zero size. Verify the
         * overlay explicitly; do not claim to read the covered archive node. */
        GUARDED(struct statfs) overlay=GUARD_INIT;
        if (identity_call(345,(long)"/dev",(long)&overlay.data,0) || !INTACT(overlay) ||
            !fixed_name(overlay.data.f_fstypename,sizeof(overlay.data.f_fstypename),"devfs") ||
            !fixed_name(overlay.data.f_mntonname,sizeof(overlay.data.f_mntonname),"/dev")) return -1;
        rt_put(1,"ROOTIDENTITY:OVERLAY:/dev:devfs\n"); return 0;
    }
    GUARDED(struct stat) metadata=GUARD_INIT;
    if (identity_call(340,(long)entry->path,(long)&metadata.data,0) || !INTACT(metadata) ||
        metadata.data.st_mode!=entry->mode || metadata.data.st_size<0 ||
        (entry->sha256 && (uint64_t)metadata.data.st_size!=entry->bytes)) return -1;
    uint64_t bytes=(uint64_t)metadata.data.st_size;
    if ((entry->mode&S_IFMT)==S_IFDIR) {
        if (bytes) return -1;
        rt_put(1,"ROOTIDENTITY:DIR:"); rt_put(1,entry->path);
        identity_number(":MODE=",entry->mode); rt_put(1,"\n"); return 0;
    }
    if ((entry->mode&S_IFMT)!=S_IFREG || bytes>2*1024*1024) return -1;
    long fd=identity_call(5,(long)entry->path,O_RDONLY|O_NOFOLLOW|O_NONBLOCK,0);
    if (fd<3 || fd>INT_MAX) return -1;
    int ok=0;
    GUARDED(struct stat) opened=GUARD_INIT;
    if (identity_call(339,fd,(long)&opened.data,0) || !INTACT(opened) ||
        opened.data.st_mode!=metadata.data.st_mode || opened.data.st_size!=metadata.data.st_size ||
        opened.data.st_dev!=metadata.data.st_dev || opened.data.st_ino!=metadata.data.st_ino) goto done;
    br_sha256_context hash; br_sha256_init(&hash);
    typedef unsigned char identity_buffer[4096];
    GUARDED(identity_buffer) buffer=GUARD_INIT;
    uint64_t offset=0;
    for (unsigned step=0; offset<bytes && step<1024; step++) {
        size_t size=bytes-offset>sizeof(buffer.data)?sizeof(buffer.data):(size_t)(bytes-offset);
        long n=identity_call(3,fd,(long)buffer.data,size);
        if (!INTACT(buffer) || n<=0 || (unsigned long)n>size) goto done;
        br_sha256_update(&hash,buffer.data,(size_t)n); offset+=(uint64_t)n;
    }
    if (offset!=bytes || identity_call(3,fd,(long)buffer.data,1)!=0 || !INTACT(buffer)) goto done;
    unsigned char digest[32]; char hex[65];
    br_sha256_out(&hash,digest); digest_hex(digest,hex);
    if (entry->sha256 && !rt_equal(entry->sha256,hex)) goto done;
    rt_put(1,"ROOTIDENTITY:FILE:"); rt_put(1,entry->path);
    identity_number(":MODE=",entry->mode); identity_number(":BYTES=",bytes);
    rt_put(1,":SHA256="); rt_put(1,hex); rt_put(1,"\n"); ok=1;
done:
    if (identity_call(6,fd,0,0)) ok=0; /* Never retry uncertain close. */
    return ok?0:-1;
}

int rootidentity_main(void)
{
    identity_calls=0;
    rt_put(1,"ROOTIDENTITY:BEGIN:FIXED_CATALOG_V1\n");
    GUARDED(struct statfs) mount=GUARD_INIT;
    if (identity_call(345,(long)"/",(long)&mount.data,0) || !INTACT(mount) ||
        mount.data.f_bsize!=16384 || mount.data.f_iosize!=16384 ||
        mount.data.f_files!=sizeof(identity_catalog)/sizeof(identity_catalog[0]) ||
        !(mount.data.f_flags&MNT_RDONLY) || !(mount.data.f_flags&MNT_ROOTFS) ||
        mount.data.f_bfree || mount.data.f_bavail || mount.data.f_ffree ||
        mount.data.f_blocks<2 || mount.data.f_blocks>4096 ||
        !fixed_name(mount.data.f_fstypename,sizeof(mount.data.f_fstypename),"mockfs") ||
        !fixed_name(mount.data.f_mntonname,sizeof(mount.data.f_mntonname),"/")) goto failed;
    rt_put(1,"ROOTIDENTITY:MOUNT:mockfs:/:READONLY");
    identity_number(":NODES=",mount.data.f_files);
    identity_number(":BYTES=",mount.data.f_blocks*mount.data.f_bsize); rt_put(1,"\n");
    for (unsigned i=0;i<sizeof(identity_catalog)/sizeof(identity_catalog[0]);i++)
        if (identity_file(&identity_catalog[i])) goto failed;
    rt_put(1,"ROOTIDENTITY:PASS:COMPARE_SELF_AND_EXTENT_EXTERNALLY\n");
    return 0;
failed:
    rt_put(1,"ROOTIDENTITY:FAIL\n"); return 1;
}
