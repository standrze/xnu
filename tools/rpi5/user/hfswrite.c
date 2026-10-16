/* SPDX-License-Identifier: BSD-2-Clause */
/* Distinct opt-in write-trial userland only; absent from default builds.
 * Five fixed disposable HFS files, no raw device writes/mount/format/unlink.
 * A successful batch means fsync + same-boot readback, NEVER durability. */
#include "runtime.h"
#include "hfswrite.h"
#include <sys/mount.h>
#include <sys/disk.h>
#include <fcntl.h>

_Static_assert(sizeof(struct statfs)==2168,"Darwin statfs64 ABI");
static const char *const files[]={
    "/mnt/hfs/xnu-gate4-small.bin","/mnt/hfs/xnu-gate4-empty.bin",
    "/mnt/hfs/xnu-gate4-cross-page.bin","/mnt/hfs/xnu-gate4-overwrite.bin",
    "/mnt/hfs/xnu-gate4-extend.bin"};

static int field(const char *value,size_t capacity,const char *expected)
{
    for(size_t i=0;i<capacity;i++) {
        if(value[i]!=expected[i]) return 0;
        if(!value[i]) return 1;
    }
    return 0;
}
static unsigned char pattern(size_t offset,unsigned seed)
{
    return (unsigned char)(((offset*73+19+seed)^(offset>>8))&255);
}
static long guarded_mount(void)
{
    struct statfs info;
    volatile unsigned char *zero=(void *)&info;
    for(size_t i=0;i<sizeof info;i++) zero[i]=0;
    long rc=rt_call(345,(long)"/mnt/hfs",(long)&info,0,0,0,0);
    if(rc) return rc;
    if(!field(info.f_fstypename,sizeof info.f_fstypename,"hfs") ||
       !field(info.f_mntonname,sizeof info.f_mntonname,"/mnt/hfs") ||
       !field(info.f_mntfromname,sizeof info.f_mntfromname,"/dev/disk0s2") ||
       (info.f_flags&(MNT_RDONLY|MNT_NOSUID|MNT_NODEV))!=(MNT_NOSUID|MNT_NODEV)) return -22;
    long fd=rt_open("/dev/disk0s2",RT_RDONLY);
    if(fd<0) return fd;
    uint32_t blocksize=0,writable=0;
    uint64_t blocks=0;
    rc=rt_call(54,fd,DKIOCGETBLOCKSIZE,(long)&blocksize,0,0,0);
    if(!rc) rc=rt_call(54,fd,DKIOCGETBLOCKCOUNT,(long)&blocks,0,0,0);
    if(!rc) rc=rt_call(54,fd,DKIOCISWRITABLE,(long)&writable,0,0,0);
    long closed=rt_close((int)fd);
    if(rc) return rc;
    if(closed) return closed;
    return blocksize==512 && blocks==262144 && writable==1 ? 0 : -22;
}
static long readcheck(unsigned file,size_t length,unsigned seed)
{
    long fd=rt_open(files[file],RT_RDONLY|O_NOFOLLOW);
    if(fd<0) return fd;
    unsigned char bytes[512]; size_t offset=0; long rc=0;
    for(unsigned attempts=0;offset<length && attempts<1024;attempts++) {
        size_t want=length-offset; if(want>sizeof bytes) want=sizeof bytes;
        long count=rt_read((int)fd,bytes,want);
        if(count<=0 || (unsigned long)count>want) { rc=count<0 ? count : -5; break; }
        for(long i=0;i<count;i++) if(bytes[i]!=pattern(offset+(size_t)i,seed)) { rc=-5; break; }
        if(rc) break;
        offset+=(size_t)count;
    }
    if(!rc && offset!=length) rc=-5;
    if(!rc) { long tail=rt_read((int)fd,bytes,1); if(tail) rc=tail<0 ? tail : -5; }
    long closed=rt_close((int)fd);
    return rc ? rc : closed;
}
static long writefile(unsigned file,size_t offset,size_t length,unsigned seed,int flags)
{
    long fd=rt_call(5,(long)files[file],RT_WRONLY|O_NOFOLLOW|flags,0600,0,0,0);
    if(fd<0) return fd;
    unsigned char bytes[512]; size_t done=0; long rc=0;
    while(done<length) {
        size_t count=length-done; if(count>sizeof bytes) count=sizeof bytes;
        for(size_t i=0;i<count;i++) bytes[i]=pattern(offset+done+i,seed);
        size_t sent=0;
        for(unsigned attempts=0;sent<count && attempts<16;attempts++) {
            long progress=rt_write((int)fd,bytes+sent,count-sent);
            if(progress<=0 || (unsigned long)progress>count-sent) { rc=progress<0 ? progress : -5; break; }
            sent+=(size_t)progress;
        }
        if(!rc && sent!=count) rc=-5;
        if(rc) break;
        done+=count;
    }
    if(!rc) rc=rt_call(95,fd,0,0,0,0,0); /* fsync, not a durability assertion. */
    long closed=rt_close((int)fd);
    return rc ? rc : closed;
}

int hfswrite_main(int argc,char **argv)
{
    if(argc!=2 || !rt_equal(argv[1],"exercise")) {
        rt_put(2,"usage: hfswrite exercise (five fixed files on /mnt/hfs only)\n"); return 2;
    }
    long rc=guarded_mount();
    if(rc) { rt_error("hfswrite mount/device guard",rc); return 1; }
    static const size_t initial[]={32,0,33034,1024,512};
    for(unsigned i=0;i<5;i++) {
        rc=writefile(i,0,initial[i],i+1,O_CREAT|O_EXCL);
        if(!rc) rc=readcheck(i,initial[i],i+1);
        if(rc) { rt_error("hfswrite create/fsync/readback",rc); return 1; }
    }
    rc=writefile(3,0,257,6,O_TRUNC);
    if(!rc) rc=readcheck(3,257,6);
    if(!rc) rc=writefile(4,512,4121,5,O_APPEND);
    if(!rc) rc=readcheck(4,4633,5);
    if(rc) { rt_error("hfswrite overwrite/append/fsync/readback",rc); return 1; }
    rt_put(1,"RPI5XNU:HFSWRITE:BATCH_FSYNCED FILES=5 RAW_WRITES=0 DURABILITY_VERIFIED=0\n");
    return 0;
}
