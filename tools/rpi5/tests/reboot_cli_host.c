/* SPDX-License-Identifier: BSD-2-Clause; test-only syscall boundary. */
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <string.h>
#include <sys/types.h>
extern int rpi5_pthread_smoke_main(int, char **);
static int calls, result, options, writes, short_write;
static const char *message;
int rpi5_test_reboot_trap(int how, const char *msg)
{ calls++; options=how; message=msg; errno=EPERM; return result; }
ssize_t rpi5_test_write(int fd,const void *p,size_t n)
{ assert(fd==1||fd==2); assert(p&&n); writes++; return short_write?0:(ssize_t)n; }
int main(void)
{
    char *normal[]={"/sbin/reboot",0};
    char *help[]={"reboot","--help",0};
    char *bad[]={"reboot","-q",0};
    assert(rpi5_pthread_smoke_main(2,help)==0 && !calls);
    short_write=1;assert(rpi5_pthread_smoke_main(2,help)==1&&!calls);short_write=0;
    for(int n=0;n<5;n++)if(n!=1){assert(rpi5_pthread_smoke_main(n,bad)==64&&!calls);}
    result=-1;assert(rpi5_pthread_smoke_main(1,normal)==1&&calls==1&&options==0&&!message&&errno==EPERM);
    result=0;assert(rpi5_pthread_smoke_main(1,normal)==1&&calls==2&&options==0&&!message);
    result=55;assert(rpi5_pthread_smoke_main(1,normal)==1&&calls==3);
    assert(writes==9);
    return 0;
}
