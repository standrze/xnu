/* SPDX-License-Identifier: BSD-2-Clause */
/* The real original Mach wrapper, with a test-only trap callback. */
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <mach/mach.h>
#include <stdint.h>
#include <stdio.h>

kern_return_t fixture_thread_switch(mach_port_t,int,mach_msg_timeout_t);
static mach_port_t want_thread;
static int want_option;
static mach_msg_timeout_t want_time;
static kern_return_t want_result;
static unsigned calls;
kern_return_t fixture_syscall_thread_switch(mach_port_t thread,int option,mach_msg_timeout_t time)
{
    assert(thread==want_thread&&option==want_option&&time==want_time);
    calls++;return want_result;
}
int main(int argc,char **argv)
{
    (void)argv;
    const mach_port_t threads[]={MACH_PORT_NULL,1,0x12345678,UINT32_MAX};
    const int options[]={INT_MIN,-1,0,1,2,3,INT_MAX};
    const mach_msg_timeout_t times[]={0,1,UINT32_MAX};
    const kern_return_t results[]={KERN_SUCCESS,KERN_INVALID_ARGUMENT,KERN_ABORTED,KERN_FAILURE};
    for(unsigned a=0;a<4;a++)for(unsigned b=0;b<7;b++)for(unsigned c=0;c<3;c++)for(unsigned d=0;d<4;d++){
        want_thread=threads[a];want_option=options[b];want_time=times[c];want_result=results[d];errno=EDOM;
        kern_return_t result=fixture_thread_switch(want_thread,want_option,want_time);
        assert(result==want_result&&errno==EDOM);
    }
    if(calls!=(argc>1?335u:336u))return 37;
    puts("APPLE_THREAD_SWITCH PASS CASES=336 ORIGINAL_WRAPPER TEST_ONLY_MACH_TRAP NO_KERNEL_EXECUTION");
    return 0;
}
