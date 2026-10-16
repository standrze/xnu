/* SPDX-License-Identifier: BSD-2-Clause */
/* Native files/hash/cleanup, synthetic mockfs statfs. Not Pi SVC/VFS evidence. */
#include "../user/runtime.h"
#include <sys/stat.h>
#include <sys/mount.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int rootidentity_main(void);
static const char *prefix, *scenario;
static int calls, fail_at, owned[256], violations;
static int is(const char *name) { return !strcmp(scenario,name); }
static long answer(long rc) { return rc<0?-errno:rc; }

long rt_call(long number,long a,long b,long c,long d,long e,long f)
{
    (void)d; (void)e; (void)f; calls++;
    if (fail_at==calls && number!=6) return -EIO;
    if (number==345) {
        int overlay=!strcmp((const char *)a,"/dev");
        if (!overlay && strcmp((const char *)a,"/")) { violations++; return -EINVAL; }
        struct statfs *s=(void *)b; memset(s,0,sizeof(*s));
        s->f_bsize=s->f_iosize=16384; s->f_files=IDENTITY_NODES; s->f_blocks=IDENTITY_BLOCKS;
        s->f_flags=MNT_RDONLY|MNT_ROOTFS; strcpy(s->f_fstypename,"mockfs"); strcpy(s->f_mntonname,"/");
        if (overlay) {
            s->f_flags=0; s->f_files=99; s->f_blocks=1;
            strcpy(s->f_fstypename,is("devfs-name")?"mockfs":"devfs");
            strcpy(s->f_mntonname,is("devfs-path")?"/":"/dev");
        }
        if (is("statfs-guard")) ((char *)s)[sizeof(*s)]^=1;
        if (is("statfs-name")) memset(s->f_fstypename,'x',sizeof(s->f_fstypename));
        if (is("statfs-path")) memset(s->f_mntonname,'x',sizeof(s->f_mntonname));
        if (is("statfs-flags")) s->f_flags=0;
        if (is("statfs-nodes")) s->f_files++;
        if (is("statfs-free")) s->f_bfree=1;
        if (is("statfs-blocks")) s->f_blocks=UINT64_MAX;
        if (is("statfs-extent")) s->f_blocks++;
        return 0;
    }
    if (number==340 || number==5) {
        char path[4096];
        if (snprintf(path,sizeof(path),"%s%s",prefix,(const char *)a)>=(int)sizeof(path)) return -ENAMETOOLONG;
        if (number==340) {
            struct stat *s=(void *)b; long rc=answer(lstat(path,s));
            if (!rc && S_ISDIR(s->st_mode)) s->st_size=0;
            if (!rc && is("metadata-guard")) ((char *)s)[sizeof(*s)]^=1;
            if (!rc && is("metadata-mode")) s->st_mode=0;
            if (!rc && is("metadata-size")) s->st_size=-1;
            return rc;
        }
        if (b!=(O_RDONLY|O_NOFOLLOW|O_NONBLOCK) || c) { violations++; return -EINVAL; }
        if (is("fd-stdio")) return 1;
        int fd=open(path,(int)b);
        if (fd<0) return -errno;
        if (fd<3 || fd>=256 || owned[fd]) { violations++; close(fd); return -EIO; }
        owned[fd]=1; return fd;
    }
    if (a<3 || a>=256 || !owned[a]) { violations++; return -EBADF; }
    if (number==339) {
        long rc=answer(fstat((int)a,(void *)b));
        if (!rc && is("fstat-inode")) ((struct stat *)b)->st_ino++;
        if (!rc && is("fstat-guard")) ((char *)b)[sizeof(struct stat)]^=1;
        return rc;
    }
    if (number==3) {
        size_t count=(size_t)c;
        if (is("partial") && count>17) count=17;
        if (is("one-byte") && count>1) count=1;
        long rc=answer(read((int)a,(void *)b,count));
        if (rc>0 && is("payload")) ((char *)b)[0]^=1;
        if (rc>0 && is("read-guard")) ((char *)b)[4096]^=1;
        if (rc>0 && is("read-overrun")) rc=c+1;
        if (!rc && is("extra-eof")) rc=1;
        return rc;
    }
    if (number==6) {
        owned[a]=0; long rc=answer(close((int)a));
        return fail_at==calls?-EINTR:rc;
    }
    violations++; return -EINVAL;
}

void rt_put(int fd,const char *s) { (void)fd; fputs(s,stdout); }
void rt_number(int fd,unsigned long n) { (void)fd; printf("%lu",n); }
void rt_error(const char *s,long n) { printf("%s:%ld\n",s,n); }
int rt_equal(const char *a,const char *b) { return !strcmp(a,b); }
size_t rt_len(const char *s) { return strlen(s); }
int main(int argc,char **argv)
{
    if (argc!=4) return 3;
    prefix=argv[1]; scenario=argv[2]; fail_at=atoi(argv[3]);
    int rc=rootidentity_main(), leaks=0;
    for (unsigned i=0;i<256;i++) leaks+=owned[i];
    printf("NATIVE:CALLS=%d:LEAKS=%d:VIOLATIONS=%d\n",calls,leaks,violations);
    return leaks || violations?99:rc;
}
