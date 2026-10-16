/* SPDX-License-Identifier: BSD-2-Clause */
/* Explicit in-memory syscall model, never real mounts/devices/files. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/disk.h>
#include <fcntl.h>
#include "../user/runtime.h"
#include "../user/hfswrite.h"

static const char *mode;
static const char *const paths[]={"/mnt/hfs/xnu-gate4-small.bin","/mnt/hfs/xnu-gate4-empty.bin",
    "/mnt/hfs/xnu-gate4-cross-page.bin","/mnt/hfs/xnu-gate4-overwrite.bin","/mnt/hfs/xnu-gate4-extend.bin"};
static struct { unsigned char data[65536]; size_t size,position; int exists,opened,write; } files[5];
static unsigned stats,deviceOpens,fileOpens,closes,ioctls,writes,syncs;
static int is(const char *value) { return !strcmp(mode,value); }
static int indexof(const char *path) {
    for(int i=0;i<5;i++) if(!strcmp(path,paths[i])) return i;
    assert(!"Unexpected path"); return -1;
}
int rt_equal(const char *a,const char *b) { return !strcmp(a,b); }
void rt_put(int fd,const char *text) { fputs(text,fd==1 ? stdout : stderr); }
void rt_error(const char *text,long rc) { fprintf(stderr,"%s: errno %ld\n",text,-rc); }
long rt_open(const char *path,int flags) {
    if(!strcmp(path,"/dev/disk0s2")) { assert(flags==RT_RDONLY); deviceOpens++; return is("device-open") ? -6 : 77; }
    int i=indexof(path); fileOpens++; assert(flags==(RT_RDONLY|O_NOFOLLOW));
    assert(files[i].exists && !files[i].opened); files[i].opened=1; files[i].write=0; files[i].position=0;
    return 100+i;
}
long rt_close(int fd) {
    closes++;
    if(fd==77) return is("device-close") ? -5 : 0;
    int i=fd-100; assert(i>=0 && i<5 && files[i].opened); files[i].opened=0;
    return is("file-close") || (is("late-close") && syncs==7) ? -5 : 0;
}
long rt_write(int fd,const void *data,size_t count) {
    int i=fd-100; assert(i>=0 && i<5 && files[i].opened && files[i].write); writes++;
    if(is("write") || (is("append-write") && i==4 && syncs==6)) return -5;
    if(is("zero-write")) return 0;
    if(is("partial")) count=(count+1)/2;
    if(is("stalled-partial")) count=1;
    assert(count<=65536-files[i].position);
    memcpy(files[i].data+files[i].position,data,count); files[i].position+=count;
    if(files[i].position>files[i].size) files[i].size=files[i].position;
    return (long)count;
}
long rt_read(int fd,void *data,size_t count) {
    int i=fd-100; assert(i>=0 && i<5 && files[i].opened && !files[i].write);
    if(is("read")) return -5;
    if(is("short-eof")) return 0;
    size_t left=files[i].size-files[i].position; if(count>left) count=left;
    if(is("partial") && count) count=(count+1)/2;
    if(is("extra-eof") && !count) { *(unsigned char *)data=0; return 1; }
    memcpy(data,files[i].data+files[i].position,count); files[i].position+=count;
    if((is("corrupt") || (is("late-corrupt") && syncs==7)) && count) ((unsigned char *)data)[0]^=1;
    return (long)count;
}
long rt_call(long number,long a,long b,long c,long d,long e,long f) {
    assert(!d && !e && !f);
    if(number==345) {
        stats++; assert(!strcmp((char *)a,"/mnt/hfs") && !c);
        if(is("stat")) return -5;
        struct statfs *info=(void *)b; memset(info,0,sizeof *info);
        strcpy(info->f_fstypename,is("type") ? "mockfs" : "hfs");
        strcpy(info->f_mntonname,is("target") ? "/other" : "/mnt/hfs");
        strcpy(info->f_mntfromname,is("source") ? "/dev/disk0s1" : "/dev/disk0s2");
        info->f_flags=MNT_NOSUID|MNT_NODEV;
        if(is("readonly")) info->f_flags|=MNT_RDONLY;
        if(is("flags")) info->f_flags=0;
        if(is("unterminated")) memset(info->f_fstypename,'h',sizeof info->f_fstypename);
        return 0;
    }
    if(number==54) {
        assert(a==77); ioctls++; if(is("ioctl")) return -5;
        if((unsigned long)b==DKIOCGETBLOCKSIZE) *(uint32_t *)c=is("blocksize") ? 4096 : 512;
        else if((unsigned long)b==DKIOCGETBLOCKCOUNT) *(uint64_t *)c=is("capacity") ? 1048576 : 262144;
        else { assert((unsigned long)b==DKIOCISWRITABLE); *(uint32_t *)c=!is("write-protect"); }
        return 0;
    }
    if(number==5) {
        assert(c==0600); int i=indexof((char *)a); fileOpens++;
        assert((b&(RT_WRONLY|O_NOFOLLOW))==(RT_WRONLY|O_NOFOLLOW));
        if(is("file-open") || is("exists") ||
           (is("overwrite-open") && i==3 && !(b&O_CREAT)) ||
           (is("append-open") && i==4 && !(b&O_CREAT))) return -17;
        assert(!files[i].opened);
        if(b&O_CREAT) { assert(b&O_EXCL); assert(!files[i].exists); files[i].exists=1; }
        else assert(files[i].exists && (i==3 || i==4));
        if(b&O_TRUNC) { assert(i==3); files[i].size=0; }
        files[i].position=(b&O_APPEND) ? files[i].size : 0;
        files[i].opened=1; files[i].write=1; return 100+i;
    }
    assert(number==95 && !b && !c && a>=100 && a<105); syncs++;
    return is("fsync") || (is("late-fsync") && syncs==7) ? -5 : 0;
}
int main(int argc,char **argv) {
    mode=getenv("HFSWRITE_FIXTURE"); if(!mode) mode="";
    int rc=hfswrite_main(argc,argv);
    for(unsigned i=0;i<5;i++) assert(!files[i].opened);
    if(rc==0) {
        const size_t lengths[]={32,0,33034,257,4633}; const unsigned seeds[]={1,2,3,6,5};
        assert(syncs==7 && deviceOpens==1 && ioctls==3);
        for(unsigned i=0;i<5;i++) {
            assert(files[i].exists && files[i].size==lengths[i]);
            for(size_t j=0;j<lengths[i];j++)
                assert(files[i].data[j]==(unsigned char)(((j*73+19+seeds[i])^(j>>8))&255));
        }
    }
    fprintf(stderr,"FIXTURE STATS=%u DEVICE_OPENS=%u FILE_OPENS=%u CLOSES=%u IOCTLS=%u WRITES=%u SYNCS=%u\n",
        stats,deviceOpens,fileOpens,closes,ioctls,writes,syncs);
    return rc;
}
