/* SPDX-License-Identifier: BSD-2-Clause
 * Original providers with explicit syscall/process doubles; no actual exec,
 * signals, socket access or directory mutation. Host errno/alloc are genuine.
 */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/ucred.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

extern int fixture_getpeereid(int,uid_t *,gid_t *);
extern int fixture_raise(int);
extern pid_t fixture_waitpid(pid_t,int *,int);
extern int fixture_execl(const char *,const char *,...);
extern int fixture_execv(const char *,char *const *);
extern int fixture_execvP(const char *,const char *,char *const *);
extern int fixture_rmdir(const char *);
extern uint64_t fixture_get_remove_counter(void);
extern const char *fixture_getprogname(void);
static int mode,calls;
static char *name="real-source-host-fixture";
static char *environment[]={"PATH=/first:/second",0};
static char **environment_pointer=environment;
char **fixture_NSGetProgname(void) { return &name; }
char ***fixture_NSGetEnviron(void) { return &environment_pointer; }
char *fixture_getenv(const char *key) { assert(!strcmp(key,"PATH"));return "/first:/second"; }

int fixture_getsockopt(int fd,int level,int option,void *value,socklen_t *length)
{
    calls++; assert(fd==42 && level==0 && option==LOCAL_PEERCRED && *length==sizeof(struct xucred));
    if(mode==1) { errno=EBADF;return -1; }
    struct xucred *x=value;memset(x,0,sizeof(*x));x->cr_version=mode==2?99:XUCRED_VERSION;
    x->cr_uid=501;x->cr_gid=20;return 0;
}
pthread_t fixture_pthread_self(void) { return (pthread_t)(uintptr_t)0x1234; }
int fixture_pthread_kill(pthread_t t,int sig)
{ calls++;assert(t==(pthread_t)(uintptr_t)0x1234 && sig==7);return mode==0?0:mode==1?ENOTSUP:EINVAL; }
pid_t fixture_getpid(void) { assert(mode==1);return 77; }
int fixture_kill(pid_t pid,int sig) { calls++;assert(mode==1 && pid==77 && sig==7);errno=EPERM;return -1; }
pid_t fixture_wait4(pid_t pid,int *status,int options,void *usage)
{ calls++;assert(pid==81 && !usage);if(options==WNOHANG)return 0;errno=ECHILD;*status=123;return -1; }
int fixture_rmdir_trap(const char *path)
{ calls++;assert(!strcmp(path,"/unexecuted"));if(mode){errno=EACCES;return -1;}return 0; }
ssize_t fixture_write(int fd,const void *buf,size_t n)
{ (void)buf;assert(fd==2);return (ssize_t)n; }
int fixture_stat(const char *path,struct stat *out)
{ assert(mode==3 && !strcmp(path,"/first/tool"));memset(out,0,sizeof(*out));return 0; }
int fixture_execve(const char *path,char *const argv[],char *const envp[])
{
    calls++;assert(envp==environment && argv && argv[0]);
    if(mode==0) { assert(!strcmp(path,"/direct") && !strcmp(argv[0],"tool"));errno=E2BIG; }
    else if(mode==1) {
        if(calls==1) { assert(!strcmp(path,"/script"));errno=ENOEXEC; }
        else { assert(calls==2 && !strcmp(path,"/bin/sh"));assert(!strcmp(argv[1],"/script"));errno=EACCES; }
    } else if(mode==2) {
        assert(!strcmp(path,calls==1?"/first/tool":"/second/tool"));errno=ENOENT;
    } else { assert(mode==3);assert(!strcmp(path,calls==1?"/first/tool":"/second/tool"));errno=calls==1?EACCES:ENOENT; }
    return -1;
}
int main(void)
{
    uid_t u;gid_t g;
    for(mode=0;mode<3;mode++) {
        u=999;g=888;calls=0;errno=0;int result=fixture_getpeereid(42,&u,&g);
        assert(calls==1);
        if(!mode)assert(!result && u==501 && g==20);
        else assert(result==-1 && u==999 && g==888 && errno==(mode==1?EBADF:EINVAL));
    }
    for(mode=0;mode<3;mode++) {
        calls=0;errno=0;int result=fixture_raise(7);
        if(!mode)assert(result==0 && calls==1);
        else assert(result==-1 && errno==(mode==1?EPERM:EINVAL) && calls==(mode==1?2:1));
    }
    int status=999;calls=0;errno=0;
    assert(fixture_waitpid(81,&status,0x80000000)==-1 && errno==EINVAL && !calls && status==999);
    assert(fixture_waitpid(81,&status,WNOHANG)==0 && calls==1 && status==999);
    assert(fixture_waitpid(81,&status,0)==-1 && errno==ECHILD && calls==2 && status==123);
    uint64_t before=fixture_get_remove_counter();mode=1;calls=0;
    assert(fixture_rmdir("/unexecuted")==-1 && errno==EACCES && fixture_get_remove_counter()==before);
    mode=0;assert(!fixture_rmdir("/unexecuted") && fixture_get_remove_counter()==before+1 && calls==2);
    assert(fixture_getprogname()==name);
    char *argv[]={"tool","argument",0};calls=0;mode=0;
    assert(fixture_execv("/direct",argv)==-1 && errno==E2BIG && calls==1);
    calls=0;assert(fixture_execl("/direct","tool","argument",(char *)0)==-1 && errno==E2BIG && calls==1);
    calls=0;mode=1;assert(fixture_execvP("/script","/unused",argv)==-1 && errno==EACCES && calls==2);
    calls=0;mode=2;assert(fixture_execvP("tool","/first:/second",argv)==-1 && errno==ENOENT && calls==2);
    calls=0;mode=3;assert(fixture_execvP("tool","/first:/second",argv)==-1 && errno==EACCES && calls==2);
    calls=0;assert(fixture_execvP("","/first:/second",argv)==-1 && errno==ENOENT && calls==0);
    puts("APPLE_SSH_PROCESS PASS PEER=3 RAISE=3 WAIT=3 RMDIR=2 EXEC=6 PROGNAME=1 SYSCALL_PROCESS_DOUBLES");
    return 0;
}
