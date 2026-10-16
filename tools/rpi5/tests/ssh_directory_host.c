/* SPDX-License-Identifier: BSD-2-Clause */
/* Test-only filesystem, allocation and syscall doubles. No target execution. */
#include <dirent.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
/* The original XNU dirent_private.h is force-included by the recorded build. */

DIR *fixture_opendir(const char *);
DIR *fixture_opendir2(const char *, int);
DIR *fixture_fdopendir(int);
int fixture_closedir(DIR *);
int fixture_fdclosedir(DIR *);
struct dirent *fixture_readdir(DIR *);
int fixture_readdir_r(DIR *, struct dirent *, struct dirent **);
long fixture_telldir(DIR *);
void fixture_seekdir(DIR *, long);
void fixture_rewinddir(DIR *);
bool fixture_filldir(DIR *, bool);
/* Preserve the original normal Libc variant's alias spelling in the doubles. */
int fixture_open(const char *,int,...) __asm("_fixture_open$NOCANCEL");
int fixture_openat(int,const char *,int,...) __asm("_fixture_openat$NOCANCEL");
int fixture_close(int) __asm("_fixture_close$NOCANCEL");
int fixture_fcntl(int,int,...) __asm("_fixture_fcntl$NOCANCEL");

#define CHECK(x) do { if (!(x)) { fprintf(stderr,"check:%d:%s errno=%d\n",__LINE__,#x,errno); exit(31); } } while (0)
#define ENTRIES 192
int fixture_isthreaded = 1;
static unsigned position[2], read_calls, close_calls, open_calls, nentries;
static int read_error, fstat_error, fcntl_error, open_error, union_mode, eof_flags, regular_file;
static int invalid_record, duplicate_names, deleted_first, long_first;
static size_t alloc_calls, fail_alloc, live;
static void *allocations[1024];
static unsigned seen[ENTRIES];
static pthread_mutex_t results_lock=PTHREAD_MUTEX_INITIALIZER;

void *fixture_malloc(size_t size) {
    ++alloc_calls;
    if (fail_alloc && alloc_calls==fail_alloc) { errno=ENOMEM; return NULL; }
    void *p=malloc(size); CHECK(p!=NULL);
    for (unsigned i=0;i<1024;++i) if (!allocations[i]) { allocations[i]=p; ++live; return p; }
    CHECK(0); return NULL;
}
void fixture_free(void *p) {
    if (!p) return;
    for (unsigned i=0;i<1024;++i) if (allocations[i]==p) { allocations[i]=NULL; --live; free(p); return; }
    CHECK(0);
}
void *fixture_reallocf(void *p,size_t size) {
    if (!p) return fixture_malloc(size);
    unsigned slot=0; while (slot<1024 && allocations[slot]!=p) ++slot; CHECK(slot<1024);
    ++alloc_calls;
    if (fail_alloc && alloc_calls==fail_alloc) { fixture_free(p); errno=ENOMEM; return NULL; }
    void *q=realloc(p,size); CHECK(q); allocations[slot]=q; return q;
}
static unsigned slot(int fd) { CHECK(fd==17 || fd==18); return (unsigned)(fd-17); }
int fixture_open(const char *name,int flags,...) {
    CHECK(!strcmp(name,"directory")); CHECK((flags&(O_DIRECTORY|O_RDONLY|O_CLOEXEC))==(O_DIRECTORY|O_RDONLY|O_CLOEXEC));
    ++open_calls; if (open_error) { errno=open_error; return -1; } position[0]=0; return 17;
}
int fixture_openat(int fd,const char *name,int flags,...) {
    CHECK(fd==17 && !strcmp(name,".")); CHECK(flags==(O_RDONLY|O_CLOEXEC));
    ++open_calls; if (open_error) { errno=open_error; return -1; } position[1]=0; return 18;
}
int fixture_close(int fd) { (void)slot(fd); ++close_calls; errno=EBADF; return 0; }
int fixture_fcntl(int fd,int command,...) {
    CHECK(fd==17 && command==F_SETFD); va_list ap; va_start(ap,command); CHECK(va_arg(ap,int)==FD_CLOEXEC); va_end(ap);
    if (fcntl_error) { errno=fcntl_error; return -1; } return 0;
}
int fixture_fstat(int fd,struct stat *st) {
    CHECK(fd==17); if (fstat_error) { errno=fstat_error; return -1; }
    memset(st,0,sizeof(*st)); st->st_mode=regular_file?S_IFREG:S_IFDIR; return 0;
}
int fixture_fstatfs(int fd,struct statfs *st) {
    CHECK(fd==17); memset(st,0,sizeof(*st)); st->f_flags=union_mode?MNT_UNION:0; return 0;
}
off_t fixture_lseek(int fd,off_t offset,int whence) {
    unsigned i=slot(fd);
    if (whence==SEEK_CUR) { CHECK(offset==0); return position[i]; }
    CHECK(whence==SEEK_SET && offset>=0 && (uint64_t)offset<=nentries);
    position[i]=(unsigned)offset; return offset;
}
size_t fixture_getdirentries64(int fd,void *buffer,size_t capacity,off_t *base) {
    unsigned i=slot(fd); ++read_calls;
    if (read_error) { errno=read_error; return (size_t)-1; }
    CHECK(capacity>=1024 && base); *base=position[i];
    size_t used=0; unsigned count=0;
    while (position[i]<nentries && count<3) {
        struct dirent entry; memset(&entry,0,sizeof(entry));
        unsigned index=position[i]++;
        entry.d_ino=index+1; entry.d_seekoff=position[i]; entry.d_type=DT_REG;
        if(deleted_first && index==0)entry.d_ino=0;
        if (duplicate_names) { index=index%3; if (position[i]==1)entry.d_type=DT_WHT; }
        int n=snprintf(entry.d_name,sizeof(entry.d_name),"entry-%03u",index); CHECK(n>0);
        entry.d_namlen=(uint16_t)n; entry.d_reclen=(uint16_t)((offsetof(struct dirent,d_name)+(size_t)n+1+3)&~3u);
        if(long_first && index==0) {
            memset(entry.d_name,'x',sizeof(entry.d_name));entry.d_name[sizeof(entry.d_name)-1]=0;
            entry.d_namlen=(uint16_t)(sizeof(entry.d_name)-(long_first==1));
            entry.d_reclen=sizeof(entry);
        }
        CHECK(used+entry.d_reclen<=capacity-4);
        memcpy((char *)buffer+used,&entry,entry.d_reclen); used+=entry.d_reclen; ++count;
    }
    if (used && invalid_record) ((struct dirent *)buffer)->d_reclen=0;
    if (eof_flags && position[i]==nentries) {
        getdirentries64_flags_t end=GETDIRENTRIES64_EOF;
        memcpy((char *)buffer+capacity-sizeof(end),&end,sizeof(end));
    }
    return used;
}

static void reset(unsigned entries) {
    CHECK(live==0); memset(position,0,sizeof(position)); read_calls=close_calls=open_calls=0;
    read_error=fstat_error=fcntl_error=open_error=union_mode=regular_file=invalid_record=duplicate_names=deleted_first=long_first=0;
    eof_flags=1; nentries=entries; alloc_calls=fail_alloc=0; memset(seen,0,sizeof(seen));
}
static unsigned entry_index(struct dirent *entry) {
    unsigned n=9999; CHECK(entry && sscanf(entry->d_name,"entry-%u",&n)==1 && n<nentries); return n;
}
static void *reader(void *opaque) {
    DIR *dir=opaque; struct dirent entry,*result;
    for (;;) {
        result=(struct dirent *)(uintptr_t)1; errno=ERANGE;
        CHECK(fixture_readdir_r(dir,&entry,&result)==0 && errno==ERANGE);
        if (!result) break;
        CHECK(result==&entry); unsigned n=entry_index(result);
        CHECK(pthread_mutex_lock(&results_lock)==0); ++seen[n]; CHECK(pthread_mutex_unlock(&results_lock)==0);
    }
    return NULL;
}
static unsigned leak_oracle(void) {
    unsigned leaks=0;
    reset(6); union_mode=1;
    DIR *dir=fixture_opendir("directory"); CHECK(dir);
    fixture_rewinddir(dir); CHECK(fixture_closedir(dir)==0);
    leaks+=(unsigned)live;
    for(unsigned i=0;i<1024;++i)if(allocations[i])fixture_free(allocations[i]);
    reset(6); union_mode=1; read_error=EIO;
    CHECK(!fixture_opendir("directory") && errno==EIO && close_calls==2);
    leaks+=(unsigned)live;
    for(unsigned i=0;i<1024;++i)if(allocations[i])fixture_free(allocations[i]);
    return leaks;
}
int main(int argc,char **argv) {
    if(argc>1 && (!strcmp(argv[1],"leak-oracle") || !strcmp(argv[1],"original-leaks"))) {
        unsigned leaks=leak_oracle();
        unsigned expected=!strcmp(argv[1],"original-leaks")?2:0;
        if(leaks!=expected)return 38;
        printf("APPLE_DIRECTORY LEAKS=%u ORIGINAL_ERRNO_PRESERVED\n",leaks); return 0;
    }
    reset(12); DIR *dir=fixture_opendir("directory"); CHECK(dir && dir->__dd_len==2048);
    long beginning=fixture_telldir(dir); CHECK(beginning>=0 && beginning==fixture_telldir(dir));
    CHECK(entry_index(fixture_readdir(dir))==0 && dir->__dd_len==8192);
    long after_first=fixture_telldir(dir); CHECK(entry_index(fixture_readdir(dir))==1);
    fixture_seekdir(dir,after_first); CHECK(entry_index(fixture_readdir(dir))==1);
    for (unsigned i=2;i<8;++i) CHECK(entry_index(fixture_readdir(dir))==i);
    fixture_seekdir(dir,beginning); CHECK(entry_index(fixture_readdir(dir))==0);
    fixture_seekdir(dir,1234567); CHECK(entry_index(fixture_readdir(dir))==1);
    fixture_rewinddir(dir); CHECK(entry_index(fixture_readdir(dir))==0);
    CHECK(fixture_closedir(dir)==0 && live==0 && close_calls==1);

    reset(ENTRIES); dir=fixture_opendir("directory"); CHECK(dir);
    pthread_t threads[4]; for(unsigned i=0;i<4;++i)CHECK(!pthread_create(&threads[i],NULL,reader,dir));
    for(unsigned i=0;i<4;++i)CHECK(!pthread_join(threads[i],NULL));
    for(unsigned i=0;i<ENTRIES;++i)CHECK(seen[i]==1);
    CHECK(read_calls==ENTRIES/3); CHECK(fixture_closedir(dir)==0 && live==0);

    reset(6); position[0]=3; dir=fixture_fdopendir(17); CHECK(dir && read_calls==1);
    CHECK(entry_index(fixture_readdir(dir))==3 && read_calls==1);
    CHECK(fixture_fdclosedir(dir)==17 && close_calls==0 && live==0);
    reset(0); dir=fixture_opendir("directory"); CHECK(dir); errno=EDOM;
    struct dirent entry,*result=(void *)(uintptr_t)1;
    CHECK(fixture_readdir_r(dir,&entry,&result)==0 && result==NULL && errno==EDOM);
    CHECK(fixture_closedir(dir)==0 && live==0);
    reset(9); union_mode=1; dir=fixture_opendir("directory"); CHECK(dir);
    void *old=dir->__dd_buf; size_t before=live; read_error=EIO;
    CHECK(!fixture_filldir(dir,false) && errno==EIO && dir->__dd_buf==old && live==before);
    CHECK(fixture_closedir(dir)==0 && live==0);
    reset(6); eof_flags=0; dir=fixture_opendir("directory"); CHECK(dir);
    for(unsigned i=0;i<6;++i) CHECK(entry_index(fixture_readdir(dir))==i);
    CHECK(!fixture_readdir(dir) && read_calls==3); CHECK(fixture_closedir(dir)==0 && live==0);

    reset(9); union_mode=duplicate_names=1; dir=fixture_opendir("directory"); CHECK(dir);
    CHECK((dir->__dd_flags&__DTF_READALL)!=0 && read_calls==4);
    unsigned total=0; while((result=fixture_readdir(dir))) { CHECK(entry_index(result)!=0); ++total; }
    CHECK(total==2); fixture_rewinddir(dir); total=0; while(fixture_readdir(dir))++total; CHECK(total==2);
    CHECK(fixture_closedir(dir)==0 && live==0);

    reset(6); open_error=EACCES; CHECK(!fixture_opendir("directory") && errno==EACCES && live==0);
    reset(6); fstat_error=EBADF; CHECK(!fixture_fdopendir(17) && errno==EBADF && close_calls==0 && live==0);
    reset(6); regular_file=1; CHECK(!fixture_fdopendir(17) && errno==ENOTDIR && close_calls==0 && live==0);
    reset(6); fcntl_error=EIO; CHECK(!fixture_fdopendir(17) && errno==EIO && live==0);
    reset(6); read_error=EINVAL; CHECK(!fixture_fdopendir(17) && errno==ENOTDIR && close_calls==0 && live==0);
    reset(6); fail_alloc=1; CHECK(!fixture_opendir("directory") && errno==ENOMEM && close_calls==1 && live==0);
    reset(6); fail_alloc=2; CHECK(!fixture_opendir("directory") && errno==ENOMEM && close_calls==1 && live==0);
    reset(6); dir=fixture_opendir("directory"); CHECK(dir); fail_alloc=alloc_calls+1;
    CHECK(entry_index(fixture_readdir(dir))==0 && dir->__dd_len==2048); fail_alloc=alloc_calls+1;
    CHECK(fixture_telldir(dir)==-1 && errno==ENOMEM); fail_alloc=0; CHECK(fixture_closedir(dir)==0 && live==0);
    reset(6); dir=fixture_opendir("directory"); CHECK(dir); read_error=EIO; result=(void *)(uintptr_t)1;
    CHECK(fixture_readdir_r(dir,&entry,&result)==EIO && errno==EIO);
    /* On an error return the original API leaves result unspecified. */
    CHECK(fixture_closedir(dir)==0 && live==0);
    reset(6); dir=fixture_opendir("directory"); CHECK(dir); invalid_record=1;
    CHECK(!fixture_readdir(dir)); CHECK(fixture_closedir(dir)==0 && live==0);
    reset(3); deleted_first=1; dir=fixture_opendir("directory"); CHECK(dir);
    CHECK(entry_index(fixture_readdir(dir))==1); CHECK(fixture_closedir(dir)==0 && live==0);
    for(int mode=1;mode<=2;++mode) {
        reset(3); long_first=mode; dir=fixture_opendir("directory"); CHECK(dir);
        struct { uint64_t before; struct dirent entry; uint64_t after; } guarded;
        memset(&guarded,0,sizeof(guarded));guarded.before=guarded.after=UINT64_C(0x123456789abcdef0);
        CHECK(fixture_readdir_r(dir,&guarded.entry,&result)==0 && result==&guarded.entry);
        if(mode==1)CHECK(strlen(result->d_name)==sizeof(result->d_name)-1);
        else CHECK(entry_index(result)==1);
        CHECK(guarded.before==UINT64_C(0x123456789abcdef0) && guarded.after==guarded.before);
        CHECK(fixture_closedir(dir)==0 && live==0);
    }
    if(argc>1)return 37;
    puts("APPLE_DIRECTORY PASS WHOLE_FAMILY=6 THREADS=4 ENTRIES=192 TEST_ONLY_FILESYSTEM TARGET_NOT_RUN");
    return 0;
}
