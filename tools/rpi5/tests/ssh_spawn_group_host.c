/* SPDX-License-Identifier: BSD-2-Clause */
/* Original/explicit errno-derived Apple bodies; kernel/process/signal/I/O are doubles. */
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <pthread.h>
#include <spawn.h>
#include <spawn_private.h>
#include <sys/spawn_internal.h>
#include <sys/wait.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int fixture_system(const char *);
int fixture_posix_spawn(pid_t *,const char *,const posix_spawn_file_actions_t *,const posix_spawnattr_t *,char *const [],char *const []);
int fixture_posix_spawnattr_init(posix_spawnattr_t *);
int fixture_posix_spawnattr_destroy(posix_spawnattr_t *);
int fixture_posix_spawnattr_setflags(posix_spawnattr_t *,short);
int fixture_posix_spawnattr_getflags(const posix_spawnattr_t *,short *);
int fixture_posix_spawnattr_setsigdefault(posix_spawnattr_t *,const sigset_t *);
int fixture_posix_spawnattr_getsigdefault(const posix_spawnattr_t *,sigset_t *);
int fixture_posix_spawnattr_setsigmask(posix_spawnattr_t *,const sigset_t *);
int fixture_posix_spawnattr_getsigmask(const posix_spawnattr_t *,sigset_t *);
int fixture_posix_spawn_file_actions_init(posix_spawn_file_actions_t *);
int fixture_posix_spawn_file_actions_destroy(posix_spawn_file_actions_t *);
int fixture_posix_spawn_file_actions_addclose(posix_spawn_file_actions_t *,int);
int fixture_posix_spawn_file_actions_adddup2(posix_spawn_file_actions_t *,int,int);
int fixture_posix_spawn_file_actions_addopen(posix_spawn_file_actions_t *,int,const char *,int,mode_t);
extern bool (*fixture_posix_spawn_with_filter)(pid_t *,const char *,char *const *,char *const *,struct _posix_spawn_args_desc *,int *);

static int alloc_fail, trap_error, trap_calls, wait_error, wait_interrupts, wait_calls;
static atomic_int live, cancel_calls;
static int access_error, signal_sets, mask_sets, mode, filter_calls;
static int spawn_expect_actions, spawn_expect_flags;
static sigset_t current_mask;
static struct sigaction dispositions[NSIG];
int fixture___unix_conforming;
static char *environment[]={"TEST_ONLY=1",NULL};
static char **environment_pointer=environment;
char ***fixture__NSGetEnviron(void){return &environment_pointer;}
void *fixture_malloc(size_t n){if(alloc_fail){alloc_fail=0;errno=ENOMEM;return NULL;}void *p=malloc(n);if(p)live++;return p;}
void fixture_free(void *p){if(p)live--;free(p);}
void *fixture_realloc(void *p,size_t n){if(alloc_fail){alloc_fail=0;errno=ENOMEM;return NULL;}void *q=realloc(p,n);if(q&&!p)live++;return q;}
void *fixture_reallocf(void *p,size_t n){void *q=fixture_realloc(p,n);if(!q&&p)fixture_free(p);return q;}
int fixture_access(const char *s,int flags){assert(!strcmp(s,"/bin/sh")&&flags==F_OK);return access_error?-1:0;}
void fixture_pthread_testcancel(void){cancel_calls++;}
int fixture_sigaction(int sig,const struct sigaction *a,struct sigaction *old){assert(sig==SIGINT||sig==SIGQUIT);if(old)*old=dispositions[sig];if(a){dispositions[sig]=*a;signal_sets++;}return 0;}
int fixture_sigprocmask(int how,const sigset_t *s,sigset_t *old){if(old)*old=current_mask;if(s){if(how==SIG_BLOCK)current_mask|=*s;else{assert(how==SIG_SETMASK);current_mask=*s;}mask_sets++;}return 0;}
pid_t fixture_wait4(pid_t pid,int *status,int options,struct rusage *usage){assert(pid==73&&options==0&&!usage);wait_calls++;if(wait_interrupts){wait_interrupts--;errno=EINTR;return -1;}if(wait_error){errno=wait_error;return -1;}*status=0x2300;return pid;}
int fixture___execve(const char *s,char *const *argv,char *const *env){(void)s;(void)argv;(void)env;abort();}
int fixture___posix_spawn(pid_t *pid,const char *path,struct _posix_spawn_args_desc *ad,char *const argv[],char *const env[]){
    trap_calls++;assert(path&&argv&&env==environment);
    if(mode==1){assert(!strcmp(path,"/bin/sh")&&!strcmp(argv[0],"sh")&&!strcmp(argv[1],"-c")&&!strcmp(argv[2],"no-execution")&&!argv[3]);
        assert(ad&&ad->attrp&&ad->attr_size==sizeof(struct _posix_spawnattr));
        assert(ad->attrp->psa_flags==spawn_expect_flags&&ad->attrp->psa_sigmask==1u);
        assert(dispositions[SIGINT].sa_handler==SIG_IGN&&dispositions[SIGQUIT].sa_handler==SIG_IGN);
        assert(current_mask==(1u|(1u<<(SIGCHLD-1))));}
    if(spawn_expect_actions){assert(ad&&ad->file_actions&&ad->file_actions->psfa_act_count==spawn_expect_actions);
        assert(ad->file_actions_size==PSF_ACTIONS_SIZE(spawn_expect_actions));}
    if(trap_error){errno=trap_error;return -1;}if(pid)*pid=73;return 0;
}
static bool handled(pid_t *p,const char *s,char *const *a,char *const *e,struct _posix_spawn_args_desc *d,int *ret){(void)p;(void)s;(void)a;(void)e;(void)d;filter_calls++;*ret=-1;errno=EACCES;return true;}
static bool pass(pid_t *p,const char *s,char *const *a,char *const *e,struct _posix_spawn_args_desc *d,int *ret){(void)p;(void)s;(void)a;(void)e;(void)d;(void)ret;filter_calls++;return false;}
static void reset(void){assert(live==0);alloc_fail=trap_error=trap_calls=wait_error=wait_interrupts=wait_calls=access_error=cancel_calls=signal_sets=mask_sets=filter_calls=spawn_expect_actions=0;mode=0;fixture_posix_spawn_with_filter=NULL;fixture___unix_conforming=0;current_mask=1u;memset(dispositions,0,sizeof dispositions);dispositions[SIGINT].sa_handler=SIG_DFL;dispositions[SIGQUIT].sa_handler=SIG_DFL;spawn_expect_flags=POSIX_SPAWN_SETSIGMASK|POSIX_SPAWN_SETSIGDEF;}
static void attrs(void){
    reset();posix_spawnattr_t a=NULL;short flags=99;sigset_t mask=0x14,got=0;
    assert(fixture_posix_spawnattr_init(&a)==0&&a&&live==1);struct _posix_spawnattr *p=a;
    assert(p->psa_flags==0&&p->psa_sigmask==0&&p->psa_sigdefault==0&&p->psa_ports==NULL);
    assert(fixture_posix_spawnattr_setflags(&a,POSIX_SPAWN_SETSIGMASK)==0&&fixture_posix_spawnattr_getflags(&a,&flags)==0&&flags==POSIX_SPAWN_SETSIGMASK);
    assert(fixture_posix_spawnattr_setsigmask(&a,&mask)==0&&fixture_posix_spawnattr_getsigmask(&a,&got)==0&&got==mask);
    assert(fixture_posix_spawnattr_setsigdefault(&a,&mask)==0&&fixture_posix_spawnattr_getsigdefault(&a,&got)==0&&got==mask);
    assert(fixture_posix_spawnattr_destroy(&a)==0&&!a&&live==0);
    assert(fixture_posix_spawnattr_destroy(&a)==EINVAL&&fixture_posix_spawnattr_destroy(NULL)==EINVAL);
    assert(fixture_posix_spawnattr_setflags(&a,0)==EINVAL&&fixture_posix_spawnattr_getflags(NULL,&flags)==EINVAL);
    alloc_fail=1;assert(fixture_posix_spawnattr_init(&a)==ENOMEM&&!a&&live==0);
}
static void actions(void){
    reset();posix_spawn_file_actions_t a=NULL;assert(fixture_posix_spawn_file_actions_init(&a)==0&&a&&live==1);
    struct _posix_spawn_file_actions *p=a;assert(p->psfa_act_count==0);
    assert(fixture_posix_spawn_file_actions_addclose(&a,-1)==EBADF&&p->psfa_act_count==0);
    assert(fixture_posix_spawn_file_actions_adddup2(&a,0,OPEN_MAX)==EBADF&&p->psfa_act_count==0);
    assert(fixture_posix_spawn_file_actions_addopen(&a,4,"/never-opened",0,0600)==0);
    assert(p->psfa_act_acts[0].psfaa_type==PSFA_OPEN&&!strcmp(p->psfa_act_acts[0].psfaa_openargs.psfao_path,"/never-opened"));
    assert(fixture_posix_spawn_file_actions_addclose(&a,5)==0&&fixture_posix_spawn_file_actions_adddup2(&a,6,7)==0);
    p=a;assert(p->psfa_act_acts[1].psfaa_type==PSFA_CLOSE&&p->psfa_act_acts[2].psfaa_dup2args.psfad_newfiledes==7);
    int capacity=p->psfa_act_alloc;
    for(int i=p->psfa_act_count;i<capacity;i++)assert(fixture_posix_spawn_file_actions_addclose(&a,i)==0);
    p=a;int count=p->psfa_act_count;alloc_fail=1;assert(fixture_posix_spawn_file_actions_addclose(&a,9)==ENOMEM&&p->psfa_act_count==count);
    assert(fixture_posix_spawn_file_actions_addclose(&a,9)==0);p=a;assert(p->psfa_act_count==count+1&&p->psfa_act_alloc>count);
    pid_t pid=0;char *argv[]={"test",NULL};spawn_expect_actions=count+1;errno=EDOM;
    assert(fixture_posix_spawn(&pid,"/never-executed",&a,NULL,argv,environment)==0&&pid==73&&errno==EDOM);
    assert(fixture_posix_spawn_file_actions_destroy(&a)==0&&!a&&live==0);
    assert(fixture_posix_spawn_file_actions_destroy(&a)==EINVAL&&fixture_posix_spawn_file_actions_addclose(NULL,0)==EINVAL);
    alloc_fail=1;assert(fixture_posix_spawn_file_actions_init(&a)==ENOMEM&&!a);
}
static void spawning(void){
    reset();pid_t pid=999;char *argv[]={"test",NULL};errno=EDOM;
    assert(fixture_posix_spawn(&pid,"/never-executed",NULL,NULL,argv,environment)==0&&pid==73&&errno==EDOM);
    trap_error=ENOENT;pid=999;assert(fixture_posix_spawn(&pid,"/never-executed",NULL,NULL,argv,environment)==ENOENT&&pid==999&&errno==EDOM);
    trap_error=ENOMEM;assert(fixture_posix_spawn(NULL,"/never-executed",NULL,NULL,argv,environment)==ENOMEM&&errno==EDOM);
    trap_error=0;assert(fixture_posix_spawn(NULL,"/never-executed",NULL,NULL,argv,environment)==0&&errno==EDOM);
    int before=trap_calls;fixture_posix_spawn_with_filter=handled;
    assert(fixture_posix_spawn(NULL,"/never-executed",NULL,NULL,argv,environment)==EACCES&&errno==EDOM&&trap_calls==before&&filter_calls==1);
    fixture_posix_spawn_with_filter=pass;
    assert(fixture_posix_spawn(NULL,"/never-executed",NULL,NULL,argv,environment)==0&&trap_calls==before+1&&filter_calls==2);
    fixture_posix_spawn_with_filter=NULL;posix_spawnattr_t a=NULL;assert(fixture_posix_spawnattr_init(&a)==0);
    assert(fixture_posix_spawn(NULL,"/never-executed",NULL,&a,argv,environment)==0);assert(fixture_posix_spawnattr_destroy(&a)==0);
}
static void systems(void){
    reset();assert(fixture_system(NULL)==1&&cancel_calls==1&&trap_calls==0&&fixture___unix_conforming==1);
    reset();access_error=1;assert(fixture_system(NULL)==0&&cancel_calls==1&&trap_calls==0);
    reset();mode=1;assert(fixture_system("no-execution")==0x2300&&wait_calls==1&&signal_sets==4&&mask_sets==2&&cancel_calls==1);
    assert(live==0&&current_mask==1u&&dispositions[SIGINT].sa_handler==SIG_DFL&&dispositions[SIGQUIT].sa_handler==SIG_DFL);
    reset();mode=1;wait_interrupts=3;assert(fixture_system("no-execution")==0x2300&&wait_calls==4);
    reset();mode=1;wait_error=ECHILD;assert(fixture_system("no-execution")==-1&&errno==ECHILD&&live==0);
    for(int i=0;i<2;i++){reset();mode=1;trap_error=i?EAGAIN:ENOMEM;errno=EDOM;assert(fixture_system("no-execution")==-1&&errno==trap_error&&wait_calls==0&&live==0&&signal_sets==4);}
    reset();mode=1;trap_error=ENOENT;assert(fixture_system("no-execution")==0x7f00&&wait_calls==0&&live==0);
    reset();mode=1;alloc_fail=1;assert(fixture_system("no-execution")==-1&&errno==ENOMEM&&trap_calls==0&&signal_sets==0&&live==0);
    reset();mode=1;dispositions[SIGINT].sa_handler=dispositions[SIGQUIT].sa_handler=SIG_IGN;spawn_expect_flags=POSIX_SPAWN_SETSIGMASK;
    assert(fixture_system("no-execution")==0x2300&&dispositions[SIGINT].sa_handler==SIG_IGN&&live==0);
    reset();mode=1;errno=ERANGE;assert(fixture_system("no-execution")==0x2300&&errno==ERANGE&&live==0);
}
static void *worker(void *unused){(void)unused;for(int i=0;i<32;i++)assert(fixture_system("no-execution")==0x2300);return NULL;}
static void threaded(void){reset();mode=1;fixture___unix_conforming=1;pthread_t threads[4];
    for(int i=0;i<4;i++)assert(pthread_create(&threads[i],NULL,worker,NULL)==0);
    for(int i=0;i<4;i++)assert(pthread_join(threads[i],NULL)==0);
    assert(live==0&&trap_calls==128&&wait_calls==128&&cancel_calls==128&&signal_sets==512&&mask_sets==256&&current_mask==1u);
}
static int errno_contract(int expected_stale){
    int bad=0;
    for(int i=0;i<2;i++){
        reset();mode=1;trap_error=i?EAGAIN:ENOMEM;errno=EDOM;
        int rc=fixture_system("no-execution"),observed=errno;
        assert(rc==-1&&wait_calls==0&&live==0&&signal_sets==4&&mask_sets==2);
        assert(current_mask==1u&&dispositions[SIGINT].sa_handler==SIG_DFL&&dispositions[SIGQUIT].sa_handler==SIG_DFL);
        if(observed!=(expected_stale?EDOM:trap_error))bad++;
    }
    return bad?32:0;
}
int main(int argc,char **argv){
    if(argc==2&&!strcmp(argv[1],"original-errno")){
        int rc=errno_contract(1);if(rc)return rc;
        puts("APPLE_SYSTEM ORIGINAL_FAILURE_OBSERVED ENOMEM EAGAIN RETURN_MINUS_ONE STALE_EDOM TEST_ONLY_KERNEL_SIGNAL_IO");return 0;
    }
    if(argc==2&&!strcmp(argv[1],"require-errno"))return errno_contract(0);
    attrs();actions();spawning();systems();threaded();
    if(trap_calls!=(argc>1?129:128))return 31;
    puts("APPLE_SPAWN PASS ATTRIBUTES ACTIONS SPAWN SYSTEM THREADS=4 ITERATIONS=32 APPLE_BODIES_SYSTEM_ERRNO_CORRECTION TEST_ONLY_KERNEL_SIGNAL_IO");return 0;}
