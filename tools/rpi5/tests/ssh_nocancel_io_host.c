/* Native original variadic open policy; every I/O callback is a test double. */
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <sys/types.h>

extern int fixture_open(const char *,int,...);
extern int fixture_openat(int,const char *,int,...);
extern bool (*fixture_check_suffix)(const char *);
extern int (*fixture_open_shim)(int,int,const char *,int,mode_t,
    int (*)(int),int (*)(const char *,int,mode_t),int (*)(int,const char *,int,mode_t),int (*)(int,int,long));
static const char *path="fixture-only-no-io";
static int want_fd,want_flags,calls,checks,shims,result=7,err,shim_result=19;
static mode_t want_mode;
static bool suffix;
int fixture_open_trap(const char *p,int flags,mode_t mode) {
    assert(p==path&&flags==want_flags&&mode==want_mode);calls++;errno=err;return result;
}
int fixture_openat_trap(int fd,const char *p,int flags,mode_t mode) {
    assert(fd==want_fd);return fixture_open_trap(p,flags,mode);
}
int fixture_close_trap(int fd) { (void)fd;assert(0);return -1; }
int fixture_fcntl_trap(int fd,int cmd,long arg) { (void)fd;(void)cmd;(void)arg;assert(0);return -1; }
static bool check(const char *p) { assert(p==path);checks++;return suffix; }
static int shim(int opened,int fd,const char *p,int flags,mode_t mode,
    int (*close_fn)(int),int (*open_fn)(const char *,int,mode_t),
    int (*openat_fn)(int,const char *,int,mode_t),int (*fcntl_fn)(int,int,long)) {
    assert(opened==result&&fd==want_fd&&p==path&&flags==want_flags&&mode==want_mode);
    assert(close_fn==fixture_close_trap&&fcntl_fn==fixture_fcntl_trap);
    if(fd==-1)assert(open_fn==fixture_open_trap&&!openat_fn);
    else assert(!open_fn&&openat_fn==fixture_openat_trap);
    shims++;errno=EINTR;return shim_result;
}
static void reset(void) { calls=checks=shims=err=0;want_mode=0;want_fd=-1;want_flags=O_RDONLY;result=7; }
int main(void) {
    assert(!fixture_check_suffix&&!fixture_open_shim);
    reset();assert(fixture_open(path,want_flags)==7&&calls==1);
    reset();want_flags=O_WRONLY|O_CREAT;want_mode=0641;
    assert(fixture_open(path,want_flags,(int)want_mode)==7&&calls==1);
    reset();want_fd=23;assert(fixture_openat(want_fd,path,want_flags)==7&&calls==1);
    reset();want_fd=23;want_flags=O_RDWR|O_CREAT;want_mode=0604;
    assert(fixture_openat(want_fd,path,want_flags,(int)want_mode)==7&&calls==1);
    fixture_check_suffix=check;fixture_open_shim=shim;
    reset();result=-1;err=ENOENT;suffix=true;
    assert(fixture_open(path,want_flags)==-1&&errno==ENOENT&&!checks&&!shims);
    reset();suffix=false;assert(fixture_open(path,want_flags)==7&&checks==1&&!shims);
    reset();suffix=true;want_flags=O_WRONLY|O_CREAT;want_mode=0620;
    assert(fixture_open(path,want_flags,(int)want_mode)==19&&errno==EINTR&&checks==1&&shims==1);
    reset();suffix=true;want_fd=34;want_flags=O_RDWR|O_CREAT;want_mode=0600;
    assert(fixture_openat(want_fd,path,want_flags,(int)want_mode)==19&&checks==1&&shims==1);
    puts("APPLE_SSH_NOCANCEL_IO PASS OPEN=8 ORIGINAL_VARIADIC_AND_COMPAT_POLICY IO_DOUBLES");
    return 0;
}
