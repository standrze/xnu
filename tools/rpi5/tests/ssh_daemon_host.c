/* SPDX-License-Identifier: BSD-2-Clause
 * Native-only oracle: no real fork, signal change, Mach message or filesystem.
 * Whole original daemon source calls the spies below. Its exact original
 * failure behavior is recorded, including no SIGHUP restore on fork failure.
 */
#include <mach/mach.h>
#include <servers/bootstrap.h>
#include <errno.h>
#include <fcntl.h>
#include <setjmp.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int fixture_daemon(int,int);
int fixture_open(const char *,int,...) __asm("_fixture_open$NOCANCEL");
int fixture_close(int) __asm("_fixture_close$NOCANCEL");
mach_port_t fixture_bootstrap_port;
mach_port_t fixture_mach_task_self_=99;
static jmp_buf parent_exit;
static struct sigaction saved;
static int fork_value,session_value,signal_value,open_value,bootstrap_failure;
static int signals,forks,sessions,changes,opens,duplicates,closes,parents,ports,sets,exits;
static int test_bad,exit_status,observed_errno,case_count;
static char order[64];static size_t used;
#define REQUIRE(x) do {if(!(x)) {fprintf(stderr,"daemon oracle line %d case %d\n",__LINE__,case_count);exit(test_bad?37:41);}}while(0)
static void note(char c){REQUIRE(used+1<sizeof(order));order[used++]=c;order[used]=0;}

int fixture_sigaction(int sig,const struct sigaction *a,struct sigaction *old)
{
    REQUIRE(sig==SIGHUP);signals++;note('s');
    if(signals==1){REQUIRE(a && a->sa_handler==SIG_IGN && a->sa_flags==0);if(old)*old=saved;errno=EINTR;return signal_value;}
    REQUIRE(signals==2 && a && a->sa_handler==saved.sa_handler && !old);
    REQUIRE(a->sa_flags==saved.sa_flags && !memcmp(&a->sa_mask,&saved.sa_mask,sizeof(saved.sa_mask)));
    errno=EACCES;return 0;
}
pid_t fixture_fork(void){forks++;note('f');errno=EAGAIN;return fork_value;}
pid_t fixture_setsid(void){sessions++;note('i');errno=EPERM;return session_value;}
void fixture__exit(int value){exits++;exit_status=value;note('e');longjmp(parent_exit,1);}
int fixture_chdir(const char *path){changes++;note('d');REQUIRE(!strcmp(path,"/"));errno=ENOENT;return -1;}
int fixture_open(const char *path,int flags,...){opens++;note('o');REQUIRE(!strcmp(path,"/dev/null") && flags==O_RDWR);errno=ENOENT;return open_value;}
int fixture_dup2(int fd,int target){REQUIRE(fd==open_value && target==duplicates);duplicates++;note('u');errno=EBADF;return -1;}
int fixture_close(int fd){closes++;note('c');REQUIRE(fd==open_value && fd>2);errno=EBADF;return -1;}
kern_return_t fixture_bootstrap_parent(mach_port_t previous,mach_port_t *parent)
{
    parents++;note('b');REQUIRE(parent && previous==(parents==1?10:parents==2?20:30));
    if(bootstrap_failure==parents){errno=ESRCH;return KERN_FAILURE;}
    *parent=parents==1?20:30;return KERN_SUCCESS;
}
kern_return_t fixture_mach_port_deallocate(ipc_space_t task,mach_port_name_t port)
{
    ports++;note('p');REQUIRE(task==99 && port==(ports==1?10:20));return KERN_SUCCESS;
}
kern_return_t fixture_task_set_special_port(task_t task,int which,mach_port_t port)
{
    sets++;note('t');REQUIRE(task==99 && which==TASK_BOOTSTRAP_PORT && port==30);return KERN_FAILURE;
}
static void reset(void)
{
    memset(&saved,0,sizeof(saved));saved.sa_handler=SIG_DFL;
    sigemptyset(&saved.sa_mask);sigaddset(&saved.sa_mask,SIGUSR1);saved.sa_flags=SA_RESTART;
    fixture_bootstrap_port=10;signals=forks=sessions=changes=opens=duplicates=closes=parents=ports=sets=exits=0;
    used=0;order[0]=0;errno=EDOM;
}
static void check(int nochange,int noclose)
{
    reset();case_count++;
    int result=-99;
    if(setjmp(parent_exit)==0){result=fixture_daemon(nochange,noclose);observed_errno=errno;}
    REQUIRE(forks==1 && parents>=1 && order[0]=='s' && order[1]=='b');
    REQUIRE(parents==(bootstrap_failure?bootstrap_failure:3));
    REQUIRE(ports==(bootstrap_failure?bootstrap_failure-1:2));
    REQUIRE(sets==(!bootstrap_failure));
    REQUIRE(fixture_bootstrap_port==(bootstrap_failure?10:30));
    if(fork_value>0){REQUIRE(exits==1 && exit_status==0 && sessions==0 && signals==1);return;}
    REQUIRE(exits==0);
    if(fork_value==-1){REQUIRE(result==-1 && observed_errno==EAGAIN && sessions==0 && signals==1);return;}
    REQUIRE(sessions==1 && signals==(signal_value==-1?1:2));
    if(session_value==-1){REQUIRE(result==-1 && observed_errno==EPERM && !changes && !opens);return;}
    REQUIRE(result==(test_bad?7:0));REQUIRE(changes==!nochange && opens==!noclose);
    REQUIRE(duplicates==(!noclose && open_value!=-1?3:0));
    REQUIRE(closes==(!noclose && open_value>2));
}
int main(int argc,char **argv)
{
    test_bad=argc>1 && !strcmp(argv[1],"bad-expectation");
    /* 128 child cases: all optional actions, saved signal success/failure,
     * session success/failure, and four actual descriptor classes. */
    for(int dir=0;dir<2;dir++)for(int close=0;close<2;close++)
    for(int signal=0;signal<2;signal++)for(int session=0;session<2;session++)
    for(int fd=0;fd<4;fd++)for(int failure=0;failure<2;failure++){
        fork_value=0;session_value=session?-1:123;signal_value=signal?-1:0;
        open_value=fd==0?-1:fd==1?0:fd==2?2:7;bootstrap_failure=failure?2:0;
        check(dir,close);
    }
    /* All three bootstrap failure positions and success, both signal outcomes,
     * parent exit and fork refusal, all optional caller flags. */
    for(int failure=0;failure<4;failure++)for(int signal=0;signal<2;signal++)
    for(int branch=0;branch<2;branch++)for(int flags=0;flags<3;flags++){
        fork_value=branch?55:-1;signal_value=signal?-1:0;bootstrap_failure=failure;
        session_value=123;open_value=7;check(flags&1,flags&2);
    }
    REQUIRE(case_count==176);
    puts("APPLE_DAEMON PASS CASES=176 WHOLE_CURRENT_TU BOOTSTRAP_ENABLED PROCESS_MACH_SIGNAL_FS_SPIES_ONLY");
    return 0;
}
