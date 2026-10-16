/* SPDX-License-Identifier: BSD-2-Clause */
/* Execute the actual derived whole PID1 TU; kernel/process effects are doubles.
 * This is not a target signal/shutdown execution claim. */
#include <assert.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "runtime.h"

static jmp_buf finish;
static unsigned steps, calls, forks, waits, sleeps, stops, ready, execs, exits;
static unsigned term_at, fault_at, child_mode, fork_error, sleep_error, bad_mask;
static unsigned observed, forks_at_observation, stopped_sleeps;
static uint32_t mask, pending, initial;
static int code;
static unsigned total, successful_sleeps, interrupted_sleeps, ready_sleep[3], ready_calls[3];
static unsigned extra_eintr, mutate_mask_at_sleep;
#define EXPECT(x) do { if (!(x)) { fprintf(stderr,"INIT TEST line%d steps%u calls%u mode%u term%u fault%u\n",__LINE__,steps,calls,child_mode,term_at,fault_at); exit(37); } } while (0)
static void step(void)
{
    EXPECT(++steps<10000);
    if (term_at==steps) { EXPECT(mask&(1u<<14));pending|=1u<<14; }
    if (observed) EXPECT(forks==forks_at_observation);
}
static int failed(void) { return fault_at && fault_at==calls; }
long rt_call(long n,long a,long b,long c,long d,long e,long f)
{
    step();++calls;EXPECT(!d&&!e&&!f);
    long result=0;
    if (n==48) {
        EXPECT(a==1||a==3);
        if (failed()) { if(c)*(uint32_t *)c=0xffffffff; result=-5; }
        else {
            if(c)*(uint32_t *)c=mask^(bad_mask&&b==0?1u:0u);
            if(b)mask=a==1?mask|*(uint32_t *)b:*(uint32_t *)b;
        }
    } else if(n==52) {
        EXPECT(!b&&!c);*(uint32_t *)a=failed()?0xffffffff:pending;
        if(failed())result=-5;
        else if(pending&(1u<<14)) { observed=1;forks_at_observation=forks; }
    } else if(n==7) {
        EXPECT(a==-1 && b && c==1);++waits;
        *(int *)b=0;
        if(failed())result=-5;
        else if(stops)result=waits%2?-10:0;
        else result=waits%3==1?99:waits%3==2?0:2+(forks-1);
    } else if(n==59) {
        EXPECT(child_mode && !strcmp((char *)a,"/bin/sh"));
        char **argv=(char **)b,**env=(char **)c;
        EXPECT(mask==initial && !strcmp(argv[0],"/bin/sh") && !argv[1]);
        EXPECT(!strcmp(env[0],"PATH=/bin") && !strcmp(env[1],"PWD=/") && !strcmp(env[2],"HOME=/") && !strcmp(env[3],"TERM=dumb") && !env[4]);
        ++execs;result=-2; /* explicit exec failure, never a host shell */
    } else EXPECT(0);
    step();return result;
}
long rt_fork(void)
{
    step();EXPECT(!observed);EXPECT(successful_sleeps>=1 && ready>=1);++forks;
    if(forks==3&&!term_at&&!fault_at&&!fork_error&&!sleep_error&&!bad_mask)longjmp(finish,1);
    step();return child_mode?0:fork_error?-11:1+(long)forks;
}
long rt_sleep(unsigned seconds)
{
    step();EXPECT(seconds==1);++sleeps;
    if(stops || (fault_at==1 && forks==0)) {
        if(++stopped_sleeps==3)longjmp(finish,1);
    }
    if(fork_error && sleeps==5+extra_eintr)longjmp(finish,1);
    step();
    if(!stops && sleeps<=extra_eintr) { interrupted_sleeps++;return -4; }
    if(sleep_error)return -5;
    if(!stops)successful_sleeps++;
    if(mutate_mask_at_sleep && successful_sleeps==mutate_mask_at_sleep)mask^=1;
    return 0;
}
long rt_open(const char *p,int flags) { step();EXPECT(!strcmp(p,"/dev/console")&&flags==2);step();return 3; }
long rt_dup2(int from,int to) { step();EXPECT(from==3&&to>=0&&to<3);step();return to; }
long rt_close(int fd) { step();EXPECT(fd==3);step();return 0; }
long rt_getpid(void) { return 1; }
void rt_put(int fd,const char *s)
{
    step();EXPECT(fd==1);
    if(strstr(s,"SHUTDOWN_READY")) {
        EXPECT(mask==(initial|(1u<<14)));EXPECT(ready<3 && successful_sleeps>=ready+1);
        EXPECT(!observed && !stops);ready_sleep[ready]=successful_sleeps;ready_calls[ready]=calls;ready++;
    }
    if(strstr(s,"STOPPING")) { EXPECT(!stops);stops++; }
    step();
}
void rt_number(int fd,unsigned long n) { step();EXPECT(fd==1&&n>=2);step(); }
void rt_error(const char *s,long r) { (void)s;EXPECT(r<0);step(); }
_Noreturn void rt_exit(int status) { EXPECT(child_mode);exits++;code=status;longjmp(finish,1); }
const char *rt_basename(const char *p) { return p; }
int rt_equal(const char *a,const char *b) { return !strcmp(a,b); }
int shell_main(int argc,char **argv,char **env) { (void)argc;(void)argv;(void)env;abort(); }
int utility_main(const char *n,int a,char **v,char **e) { (void)n;(void)a;(void)v;(void)e;abort(); }
extern _Noreturn void user_start(uintptr_t *);

static void run(unsigned term,unsigned fault,unsigned child,unsigned fork_fail,unsigned sleep_fail,unsigned bad)
{
    steps=calls=forks=waits=sleeps=stops=ready=execs=exits=observed=stopped_sleeps=0;
    forks_at_observation=0;code=0;successful_sleeps=interrupted_sleeps=0;
    memset(ready_sleep,0,sizeof(ready_sleep));memset(ready_calls,0,sizeof(ready_calls));
    initial=(1u<<1)|(1u<<8);mask=initial;pending=0;
    term_at=term;fault_at=fault;child_mode=child;fork_error=fork_fail;sleep_error=sleep_fail;bad_mask=bad;
    if(!setjmp(finish)) { uintptr_t stack[]={0};user_start(stack); }
    EXPECT(!exits || child);
    EXPECT(!exits || code==126);
    if(stops)EXPECT(stopped_sleeps==3);
    if(observed)EXPECT(stops==1 && forks==forks_at_observation && execs==0);
    ++total;
}
int main(int argc,char **argv)
{
    (void)argv;
    run(0,0,0,0,0,0);unsigned baseline_steps=steps,baseline_calls=calls;
    EXPECT(forks==3 && ready==3 && !stops && !exits);
    EXPECT(ready_sleep[0]==1 && ready_sleep[1]==2 && ready_sleep[2]==3);
    EXPECT(ready_calls[0]<ready_calls[1] && ready_calls[1]<ready_calls[2]);
    /* Every callback boundary after the block took effect, including a TERM
     * arriving inside fork or after a pending read. At most one in-flight
     * fork can cross delivery; none can occur after pending was observed. */
    for(unsigned t=2;t<baseline_steps;t++) { run(t,0,0,0,0,0);EXPECT(observed&&stops&&!exits); }
    for(unsigned fault=1;fault<baseline_calls;fault++) {
        run(0,fault,0,0,0,0);EXPECT(!exits && (stops || fault==1));
    }
    run(0,0,0,1,0,0);EXPECT(forks==4 && ready==3&&!execs&&!exits);
    extra_eintr=2;run(0,0,0,1,0,0);EXPECT(interrupted_sleeps==2 && ready==3 && ready_sleep[0]==1 && forks==4);extra_eintr=0;
    for(unsigned i=1;i<=3;i++) { mutate_mask_at_sleep=i;run(0,0,0,0,0,0);EXPECT(stops && ready==i-1); }mutate_mask_at_sleep=0;
    run(0,0,0,0,1,0);EXPECT(stops==1&&!exits);
    run(0,0,0,0,0,1);EXPECT(stops==1&&forks==0&&ready==0);
    run(0,0,1,0,0,0);EXPECT(execs==1&&exits==1&&mask==initial);
    unsigned child_calls=calls;
    for(unsigned fault=1;fault<child_calls;fault++) {
        run(0,fault,1,0,0,0);
        if(exits)EXPECT(execs==0&&code==126);
        else EXPECT(!execs && (stops||fault==1));
    }
    if(argc>1)return 37;
    printf("INIT_SHUTDOWN_LATE PASS CASES=%u CALLBACK_TERM_POINTS=%u NO_PID1_EXIT NO_RESPAWN_AFTER_OBSERVATION CHILD_MASK_RESTORED MAX_REPORTS3 SUCCESSFUL_SLEEP_ONLY FRESH_FULL_MASK HOST_DOUBLES_ONLY\n",total,baseline_steps-2);
    return 0;
}

