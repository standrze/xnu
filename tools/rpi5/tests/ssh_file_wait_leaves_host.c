/* Native original-source behavior with explicit pselect/signal syscall doubles. */
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <signal.h>
#include "libc_hooks.h"

extern char *fixture_strchrnul(const char *,int);
extern void fixture_set_hooks(const libc_hooks_t *,libc_hooks_t *,size_t);
extern int fixture_pselect(int,fd_set *,fd_set *,fd_set *,const struct timespec *,const sigset_t *);
static unsigned notifications;
static const char *expected_string;
static void noticed(const char *p) { assert(p==expected_string); notifications++; }
static int p_calls,s_calls,m_calls,p_result,p_errno,s_result,s_errno,mask_error;
static const struct timespec *expected_time;
static const sigset_t *expected_mask;
static sigset_t saved_mask;
int fixture_pselect_trap(int n,fd_set *r,fd_set *w,fd_set *e,const struct timespec *t,const sigset_t *m) {
    (void)n;assert(!r&&!w&&!e);assert(t==expected_time&&m==expected_mask);
    p_calls++;errno=p_errno;return p_result;
}
int fixture_select_trap(int n,fd_set *r,fd_set *w,fd_set *e,struct timeval *t) {
    (void)n;assert(!r&&!w&&!e);s_calls++;
    if(expected_time) { assert(t&&t->tv_sec==expected_time->tv_sec&&t->tv_usec==expected_time->tv_nsec/1000); }
    else assert(!t);
    errno=s_errno;return s_result;
}
int fixture_sigmask(int how,const sigset_t *m,sigset_t *old) {
    assert(how==SIG_SETMASK);m_calls++;
    if(m_calls==1) { assert(m==expected_mask&&old);*old=saved_mask;return mask_error; }
    assert(m_calls==2&&m&&*m==saved_mask&&!old);errno=EBUSY;return 0;
}
static void reset(void) {
    p_calls=s_calls=m_calls=mask_error=0;p_result=2;p_errno=0;s_result=3;s_errno=0;
    expected_time=NULL;expected_mask=NULL;saved_mask=0x20;
}
static void oversize(size_t tail) {
    size_t size=sizeof(libc_hooks_t)+tail;
    unsigned char *memory=malloc(size);assert(memory);memset(memory,0xA5,size);
    fixture_set_hooks(NULL,(libc_hooks_t *)memory,size);
    for(size_t i=sizeof(libc_hooks_t);i<size;i++)assert(memory[i]==0);
    free(memory);
}
int main(int argc,char **argv) {
    if(argc==2&&strcmp(argv[1],"original-oversize")==0) { oversize(32);return 0; }
    libc_hooks_t hooks={.version=libc_hooks_version,.will_read_cstring=noticed},old={0};
    fixture_set_hooks(&hooks,&old,sizeof(old));assert(!old.will_read_cstring);
    unsigned cases=0;
    for(unsigned alignment=0;alignment<16;alignment++)for(unsigned length=0;length<=64;length++) {
        /* Deliberately accessible word padding: this tests results, not a stronger
           byte-granular ASan contract for the original optimized word reader. */
        unsigned char *memory=calloc(1,16+64+16);assert(memory);
        char *s=(char *)memory+alignment;memset(s,'a',length);s[length]=0;
        expected_string=s;
        int chars[]={0,'a','z',0x161};
        for(unsigned c=0;c<4;c++) {
            char *expected=(chars[c]&255)=='a'&&length?s:s+length;
            assert(fixture_strchrnul(s,chars[c])==expected);cases++;
        }
        free(memory);
    }
    assert(notifications==cases);oversize(1);oversize(8);oversize(32);oversize(48);
    hooks.will_read_cstring=NULL;fixture_set_hooks(&hooks,&old,sizeof(old));assert(old.will_read_cstring==noticed);
    char absent[16]="absent";expected_string=absent;
    assert(fixture_strchrnul(expected_string,'z')==expected_string+6);
    assert(notifications==cases);
    reset();errno=0;assert(fixture_pselect(FD_SETSIZE+1,NULL,NULL,NULL,NULL,NULL)==-1&&errno==EINVAL&&!p_calls);
    reset();assert(fixture_pselect(0,NULL,NULL,NULL,NULL,NULL)==2&&p_calls==1&&!s_calls&&!m_calls);
    reset();p_result=-1;p_errno=EBADF;assert(fixture_pselect(0,NULL,NULL,NULL,NULL,NULL)==-1&&errno==EBADF&&!s_calls);
    reset();p_result=-1;p_errno=ENOSYS;s_result=-1;s_errno=EINTR;
    assert(fixture_pselect(0,NULL,NULL,NULL,NULL,NULL)==-1&&errno==EINTR&&s_calls==1&&!m_calls);
    struct timespec ts={7,123456789};sigset_t mask=0x80;
    reset();expected_time=&ts;expected_mask=&mask;p_result=-1;p_errno=ENOSYS;s_result=-1;s_errno=EINTR;
    assert(fixture_pselect(0,NULL,NULL,NULL,&ts,&mask)==-1&&errno==EINTR&&m_calls==2&&s_calls==1);
    assert(ts.tv_sec==7&&ts.tv_nsec==123456789);
    reset();expected_mask=&mask;p_result=-1;p_errno=ENOSYS;mask_error=EINVAL;
    assert(fixture_pselect(0,NULL,NULL,NULL,NULL,&mask)==EINVAL&&m_calls==1&&!s_calls);
    reset();expected_time=&ts;expected_mask=&mask;p_result=-1;p_errno=ENOSYS;
    assert(fixture_pselect(0,NULL,NULL,NULL,&ts,&mask)==3&&m_calls==2&&s_calls==1);
    printf("APPLE_SSH_FILE_WAIT PASS STRCHRNUL=%u HOOK_TAILS=4 PSELECT=7 SYSCALL_DOUBLES\n",cases);
    return 0;
}
