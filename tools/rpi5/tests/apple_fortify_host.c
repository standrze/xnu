/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>
#include "selected-apis.h"
#include "secure.h"

void *__memcpy_chk(void *,const void *,size_t,size_t);
void *__memmove_chk(void *,const void *,size_t,size_t);
void *__memset_chk(void *,int,size_t,size_t);
char *__strcpy_chk(char *,char *,size_t);
size_t __strlcpy_chk(char *,char *,size_t,size_t);
size_t __strlcat_chk(char *,char *,size_t,size_t);
int __snprintf_chk(char *,size_t,int,size_t,const char *,...);
int __sprintf_chk(char *,int,size_t,const char *,...);
int __snprintf_object_size_chk(char *,size_t,size_t,const char *,...);
int __sprintf_object_size_chk(char *,size_t,const char *,...);
void __chk_init(void);

static char buffer[64], before[64];
static int notify_fd=-1, verify_untouched;
static const char *expected_message;

static void crashed(const char *message)
{
    if(strcmp(message,expected_message)) _exit(80);
    if(verify_untouched && memcmp(buffer,before,sizeof(buffer))) _exit(81);
    if(write(notify_fd,"C",1)!=1) _exit(82);
    /* Return to the genuine caller's hardware trap, not a fake fatal result. */
}

static void invoke_fatal(unsigned which)
{
    strcpy(buffer,"abcdef"); memcpy(before,buffer,sizeof(buffer));
    verify_untouched=1;
    expected_message="detected buffer overflow";
    switch(which) {
    case 0: __memcpy_chk(buffer,"abcdefgh",8,4); break;
    case 1: __memmove_chk(buffer,buffer+1,8,4); break;
    case 2: __memset_chk(buffer,'z',8,4); break;
    case 3: __strcpy_chk(buffer,"abcdefgh",4); break;
    case 4: __strlcpy_chk(buffer,"abcdef",8,4); break;
    case 5: __strlcat_chk(buffer,"abcdef",8,4); break;
    case 6: __snprintf_chk(buffer,8,0,4,"%s","abcdef"); break;
    case 7: __snprintf_object_size_chk(buffer,4,8,"%s","abcdef"); break;
    case 8: verify_untouched=0; __sprintf_chk(buffer,0,4,"%s","abcdef"); break;
    case 9: verify_untouched=0; __sprintf_object_size_chk(buffer,4,"%s","abcdef"); break;
    case 10: expected_message="detected source and destination buffer overlap";
             __strcpy_chk(buffer+1,buffer,63); break;
    case 11: expected_message="detected source and destination buffer overlap";
             __strlcat_chk(buffer,buffer+1,32,64); break;
    case 12: expected_message="detected source and destination buffer overlap";
             __chk_overlap(buffer,8,buffer+4,8); break;
    case 13: expected_message="detected source and destination buffer overlap";
             __chk_overlap(buffer+4,8,buffer,8); break;
    default: _exit(84);
    }
    _exit(85);
}

int main(int argc,char **argv)
{
    if(argc==2 && !strcmp(argv[1],"original-overflow")) {
        /* Original strcpy TU copies outside this real allocation before check. */
        char *p=malloc(4); assert(p);
        __strcpy_chk(p,"0123456789abcdef",4); free(p); return 86;
    }
    __chk_init(); assert(__chk_assert_no_overlap==1);
    char b[64]={0}; unsigned good=0;
    assert(__memcpy_chk(b,"abcdef",7,sizeof(b))==b && !strcmp(b,"abcdef"));++good;
    assert(__memmove_chk(b+1,b,7,sizeof(b)-1)==b+1 && !strcmp(b,"aabcdef"));++good;
    assert(__memset_chk(b,'x',3,sizeof(b))==b && !memcmp(b,"xxx",3));++good;
    assert(__strcpy_chk(b,"abc",4)==b && !strcmp(b,"abc"));++good;
    assert(__strlcpy_chk(b,"abcdef",4,sizeof(b))==6 && !strcmp(b,"abc"));++good;
    assert(__strlcpy_chk(b,"abcdef",0,0)==6 && !strcmp(b,"abc"));++good;
    assert(__strlcat_chk(b,"def",sizeof(b),sizeof(b))==6 && !strcmp(b,"abcdef"));++good;
    assert(__snprintf_chk(b,4,0,sizeof(b),"%s","abcdef")==6 && !strcmp(b,"abc"));++good;
    assert(__snprintf_object_size_chk(b,sizeof(b),sizeof(b),"%s/%d","ok",4)==4 && !strcmp(b,"ok/4"));++good;
    assert(__sprintf_chk(b,0,sizeof(b),"%s/%d","ok",5)==4 && !strcmp(b,"ok/5"));++good;
    assert(__sprintf_object_size_chk(b,sizeof(b),"%s/%d","ok",6)==4 && !strcmp(b,"ok/6"));++good;
    __chk_overlap(b,0,b,8); __chk_overlap(b,8,b,0); __chk_overlap(b,4,b+4,4);++good;
    for(unsigned i=0;i!=14;++i) {
        int fds[2],status=0; assert(pipe(fds)==0);
        pid_t child=fork();assert(child>=0);
        if(!child) {
            struct rlimit no_core={0,0};assert(setrlimit(RLIMIT_CORE,&no_core)==0);
            signal(SIGILL,SIG_DFL);signal(SIGTRAP,SIG_DFL);
            close(fds[0]);notify_fd=fds[1];os_set_crash_callback(crashed);invoke_fatal(i);
        }
        close(fds[1]);char marker=0;
        assert(read(fds[0],&marker,1)==1 && marker=='C');close(fds[0]);
        assert(waitpid(child,&status,0)==child && WIFSIGNALED(status));
        assert(WTERMSIG(status)==SIGILL || WTERMSIG(status)==SIGTRAP);
    }
    printf("APPLE_FORTIFY PASS VALID=%u FATAL=14 STRCPY_PREWRITE=1 ORIGINAL_CALLER_TRAP=1\n",good);
    return 0;
}
