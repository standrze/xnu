/* SPDX-License-Identifier: BSD-2-Clause */
/* Explicit host ABI doubles, never used by the real TF-A build. */
#include <stdint.h>
#include <stddef.h>
typedef uint64_t u_register_t;
#define SMC_UNK UINT64_C(0xffffffff)
#define OEN_SIP_START 2
#define OEN_SIP_END 2
#define SMC_TYPE_FAST 1
struct host_context {uint64_t regs[4];unsigned count;};
static uintptr_t host_ret(void *p,unsigned count,uint64_t a,uint64_t b,uint64_t c,uint64_t d)
{
    struct host_context *out=p;out->count=count;out->regs[0]=a;out->regs[1]=b;out->regs[2]=c;out->regs[3]=d;return 0;
}
#define SMC_RET1(h,a) return host_ret(h,1,a,0,0,0)
#define SMC_RET4(h,a,b,c,d) return host_ret(h,4,a,b,c,d)
#define DECLARE_RT_SVC(name,start,end,type,setup,handler) static const void *registered_handler __attribute__((used))=(const void *)(handler)
