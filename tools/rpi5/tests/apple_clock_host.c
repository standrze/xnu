/* SPDX-License-Identifier: BSD-2-Clause */
/* Deterministic native boundary doubles. Never linked into a target provider. */
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/sysctl.h>
#include <sys/time.h>
#include <time.h>
#include <mach/mach_time.h>
#include <mach/mach_error.h>

static int fail_time,fail_usage,fail_scale,zero_boot,setting_calls;
static unsigned sysctl_calls,fail_sysctl;
static uint64_t ticks=27;
static mach_timebase_info_data_t scale={500,27};
int gettimeofday(struct timeval *restrict tv,void *restrict tz)
{(void)tz;tv->tv_sec=123;tv->tv_usec=456789;if(fail_time){errno=EIO;return -1;}return 0;}
int getrusage(int who,struct rusage *r)
{assert(who==RUSAGE_SELF);memset(r,0,sizeof *r);r->ru_utime=(struct timeval){2,700000};r->ru_stime=(struct timeval){3,600000};if(fail_usage){errno=EIO;return -1;}return 0;}
int sysctlbyname(const char *name,void *old,size_t *len,void *newp,size_t newlen)
{assert(!strcmp(name,"kern.boottime")&&old&&len&&*len==sizeof(struct timeval)&&!newp&&!newlen);*(struct timeval *)old=(struct timeval){120,123456};sysctl_calls++;if(sysctl_calls==fail_sysctl||fail_sysctl==UINT32_MAX){errno=EACCES;return -1;}return 0;}
int settimeofday(const struct timeval *tv,const struct timezone *tz)
{assert(!tz);assert(tv->tv_sec==23&&tv->tv_usec>=0&&tv->tv_usec<1000000);setting_calls++;return 0;}
uint64_t mach_boottime_usec(void){return zero_boot?0:UINT64_C(120123456);}
kern_return_t mach_timebase_info(mach_timebase_info_t out){*out=scale;return fail_scale?KERN_FAILURE:KERN_SUCCESS;}
uint64_t mach_continuous_time(void){return ticks;}
uint64_t mach_continuous_approximate_time(void){return ticks;}
uint64_t mach_absolute_time(void){return ticks;}
uint64_t mach_approximate_time(void){return ticks;}
uint64_t __thread_selfusage(void){return ticks;}

static const clockid_t raw[]={CLOCK_MONOTONIC_RAW,CLOCK_MONOTONIC_RAW_APPROX,
    CLOCK_UPTIME_RAW,CLOCK_UPTIME_RAW_APPROX,CLOCK_THREAD_CPUTIME_ID};
static struct timespec sentinel(void){return (struct timespec){345,678};}
static int unchanged(struct timespec t){return t.tv_sec==345&&t.tv_nsec==678;}
static void basic(void)
{
    struct timespec t;
    assert(!clock_gettime(CLOCK_REALTIME,&t)&&t.tv_sec==123&&t.tv_nsec==456789000);
    assert(clock_gettime_nsec_np(CLOCK_REALTIME)==UINT64_C(123456789000));
    assert(!clock_gettime(CLOCK_MONOTONIC,&t)&&t.tv_sec==3&&t.tv_nsec==333333000);
    zero_boot=1;assert(!clock_gettime(CLOCK_MONOTONIC,&t)&&t.tv_sec==3&&t.tv_nsec==333333000);zero_boot=0;
    assert(!clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t)&&t.tv_sec==6&&t.tv_nsec==300000000);
    for(unsigned i=0;i<5;i++){
        errno=EBUSY;assert(!clock_gettime(raw[i],&t)&&t.tv_sec==0&&t.tv_nsec==500&&errno==EBUSY);
        assert(clock_gettime_nsec_np(raw[i])==500);
        assert(!clock_getres(raw[i],&t)&&t.tv_sec==0&&t.tv_nsec==19);
    }
    for(int i=0;i<3;i++){
        clockid_t c=i==0?CLOCK_REALTIME:i==1?CLOCK_MONOTONIC:CLOCK_PROCESS_CPUTIME_ID;
        assert(!clock_getres(c,&t)&&t.tv_sec==0&&t.tv_nsec==1000);
    }
    t=sentinel();errno=0;assert(clock_gettime((clockid_t)-1,&t)==-1&&errno==EINVAL&&unchanged(t));
    t=sentinel();assert(clock_getres((clockid_t)-1,&t)==-1&&unchanged(t));
    fail_scale=1;t=sentinel();errno=0;assert(clock_gettime(raw[0],&t)==-1&&errno==EINVAL&&unchanged(t));fail_scale=0;
    t=(struct timespec){23,987654321};assert(!clock_settime(CLOCK_REALTIME,&t)&&setting_calls==1);
    assert(clock_settime(CLOCK_MONOTONIC,&t)==-1&&setting_calls==1);
}
static void errors(int original)
{
    struct timespec t=sentinel();fail_time=1;errno=0;
    assert(clock_gettime(CLOCK_REALTIME,&t)==-1&&errno==EIO);
    assert(unchanged(t)==!original);
    t=sentinel();assert(clock_gettime(CLOCK_MONOTONIC,&t)==-1&&errno==EIO);assert(unchanged(t)==!original);
    assert(clock_gettime_nsec_np(CLOCK_REALTIME)==0&&clock_gettime_nsec_np(CLOCK_MONOTONIC)==0);fail_time=0;
    t=sentinel();fail_usage=1;assert(clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t)==-1&&errno==EIO);
    assert(unchanged(t)==!original);assert(clock_gettime_nsec_np(CLOCK_PROCESS_CPUTIME_ID)==0);fail_usage=0;
    ticks=0;
    for(unsigned i=0;i<5;i++){
        t=sentinel();errno=EBUSY;int r=clock_gettime(raw[i],&t);
        if(original)assert(r==-1&&unchanged(t));
        else assert(!r&&t.tv_sec==0&&t.tv_nsec==0&&errno==EBUSY);
    }
    ticks=27;
    for(unsigned which=1;which<=2;which++){
        zero_boot=1;sysctl_calls=0;fail_sysctl=which;t=sentinel();errno=0;
        int rc=clock_gettime(CLOCK_MONOTONIC,&t);
        if(original)assert(!rc&&!unchanged(t)&&errno==EACCES);
        else assert(rc==-1&&unchanged(t)&&errno==EACCES&&sysctl_calls==which);
        zero_boot=0;fail_sysctl=0;
    }
    zero_boot=1;sysctl_calls=0;fail_sysctl=UINT32_MAX;t=sentinel();errno=0;
    int fallback_rc=clock_gettime(CLOCK_MONOTONIC,&t);
    if(original)assert(!fallback_rc&&t.tv_sec==123&&t.tv_nsec==456789000&&sysctl_calls==2);
    else assert(fallback_rc==-1&&unchanged(t)&&errno==EACCES&&sysctl_calls==1);
    sysctl_calls=0;errno=0;uint64_t fallback_ns=clock_gettime_nsec_np(CLOCK_MONOTONIC);
    if(original)assert(fallback_ns==UINT64_C(123456789000)&&sysctl_calls==2);
    else assert(!fallback_ns&&errno==EACCES&&sysctl_calls==1);
    zero_boot=0;fail_sysctl=0;
    t=(struct timespec){23,-1};int before=setting_calls;
    int r=clock_settime(CLOCK_REALTIME,&t);
    if(original)assert(!r&&setting_calls==before+1);
    else assert(r==-1&&errno==EINVAL&&setting_calls==before);
    if(!original){
        assert(!clock_getres(CLOCK_REALTIME,NULL));
        assert(!clock_getres(CLOCK_UPTIME_RAW,NULL));
        assert(clock_getres((clockid_t)-1,NULL)==-1&&errno==EINVAL);
        scale.denom=0;t=sentinel();assert(clock_gettime(raw[0],&t)==-1&&errno==EINVAL&&unchanged(t));
        assert(clock_getres(raw[0],&t)==-1&&errno==EINVAL);scale=(mach_timebase_info_data_t){2,2};
        ticks=UINT64_MAX-1;assert(clock_gettime_nsec_np(raw[0])==UINT64_MAX-1);
        scale=(mach_timebase_info_data_t){2,1};errno=0;assert(!clock_gettime_nsec_np(raw[0])&&errno==EOVERFLOW);
        t=sentinel();assert(clock_gettime(raw[0],&t)==-1&&errno==EOVERFLOW&&unchanged(t));
        scale=(mach_timebase_info_data_t){500,27};ticks=27;
        t=(struct timespec){23,1000000000};before=setting_calls;
        assert(clock_settime(CLOCK_REALTIME,&t)==-1&&errno==EINVAL&&setting_calls==before);
    }
}
static void scales(void)
{
    const mach_timebase_info_data_t ratios[]={{0,1},{1,1},{2,2},{3,2},{500,27},
        {UINT32_MAX,UINT32_MAX},{UINT32_MAX,UINT32_MAX-1},{UINT32_MAX,1},{1,UINT32_MAX}};
    const uint64_t edges[]={0,1,2,27,UINT32_MAX,UINT64_MAX,UINT64_MAX-1,
        UINT64_C(12297829382473034411)};
    uint64_t random=UINT64_C(0xa0761d6478bd642f);
    for(unsigned r=0;r<sizeof ratios/sizeof *ratios;r++){
        scale=ratios[r];
        uint64_t resolution=scale.numer/scale.denom+(scale.numer%scale.denom!=0);
        struct timespec res;assert(!clock_getres(CLOCK_UPTIME_RAW,&res)&&
            (uint64_t)res.tv_sec==resolution/1000000000&&res.tv_nsec==(long)(resolution%1000000000));
        for(unsigned i=0;i<4104;i++){
            random=random*UINT64_C(6364136223846793005)+UINT64_C(1442695040888963407);
            ticks=i<8?edges[i]:random;
            __uint128_t expected=(__uint128_t)ticks*scale.numer/scale.denom;
            errno=0;uint64_t ns=clock_gettime_nsec_np(CLOCK_UPTIME_RAW);
            struct timespec t=sentinel();errno=EBUSY;int rc=clock_gettime(CLOCK_UPTIME_RAW,&t);
            if(expected>UINT64_MAX)assert(!ns&&rc==-1&&errno==EOVERFLOW&&unchanged(t));
            else assert(ns==(uint64_t)expected&&!rc&&errno==EBUSY&&
                (uint64_t)t.tv_sec==(uint64_t)expected/1000000000&&t.tv_nsec==(long)((uint64_t)expected%1000000000));
        }
    }
    scale=(mach_timebase_info_data_t){500,27};ticks=27;
}
int main(int argc,char **argv)
{
    assert(argc==2);int original=!strcmp(argv[1],"original");
    assert(original||!strcmp(argv[1],"derived"));basic();errors(original);if(!original)scales();
    puts(original?"APPLE_CLOCK ORIGINAL PASS":"APPLE_CLOCK DERIVED PASS");return 0;
}
