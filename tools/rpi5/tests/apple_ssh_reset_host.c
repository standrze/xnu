/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual corrected OpenSSH buffer objects plus original support code, native
 * libc/ASan/UBSan. Optional allocation failure injection is host-only. */
#define SSHBUF_INTERNAL
#include "includes.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sshbuf.h"
#include "ssherr.h"
#ifdef SSH_RESET_ALLOC_FAULT
static unsigned fail_next,failures;
extern void *probe_recallocarray_real(void *,size_t,size_t,size_t);
void *recallocarray(void *p,size_t old_count,size_t new_count,size_t size)
{
    if(fail_next){fail_next=0;failures++;errno=ENOMEM;return NULL;}
    return probe_recallocarray_real(p,old_count,new_count,size);
}
#endif
static unsigned cases;
static void capacity(size_t cap)
{
    unsigned char bytes[4096];memset(bytes,0xa5,sizeof(bytes));
    struct sshbuf *b=sshbuf_new();assert(b);
    assert(!sshbuf_set_max_size(b,cap));
    for(unsigned round=0;round<3;round++){
        assert(!sshbuf_put(b,bytes,cap));
        assert(sshbuf_put_u8(b,1)==SSH_ERR_NO_BUFFER_SPACE);
        sshbuf_reset(b);
        assert(!sshbuf_len(b) && sshbuf_max_size(b)==cap && sshbuf_alloc(b)<=cap);
        size_t count=sshbuf_alloc(b);const unsigned char *p=sshbuf_ptr(b);
        for(size_t i=0;i<count;i++)assert(p[i]==0);
        assert(!sshbuf_put_u8(b,0x42));unsigned char value=0;
        assert(!sshbuf_get_u8(b,&value) && value==0x42);
        sshbuf_reset(b);
    }
    sshbuf_free(b);cases++;
}
int main(void)
{
    for(size_t cap=1;cap<=512;cap++)capacity(cap);
    capacity(1024);capacity(4096);
    struct sshbuf *b=sshbuf_new();assert(b && !sshbuf_put(b,"parent",6));
    struct sshbuf *child=sshbuf_fromb(b);assert(child);
    sshbuf_reset(b);assert(!sshbuf_len(b));assert(sshbuf_len(child)==6);
    assert(!memcmp(sshbuf_ptr(child),"parent",6));
    sshbuf_reset(child);assert(!sshbuf_len(child));
    sshbuf_free(b);sshbuf_free(child);
    const unsigned char constant[]={1,2,3};
    b=sshbuf_from(constant,sizeof(constant));assert(b);sshbuf_reset(b);
    assert(!sshbuf_len(b) && constant[0]==1 && constant[2]==3);sshbuf_free(b);
#ifdef SSH_RESET_ALLOC_FAULT
    unsigned char bytes[300];memset(bytes,0x7a,sizeof(bytes));
    b=sshbuf_new();assert(b && !sshbuf_set_max_size(b,512) && !sshbuf_put(b,bytes,sizeof(bytes)));
    const unsigned char *prior=sshbuf_ptr(b);size_t prior_alloc=sshbuf_alloc(b);
    fail_next=1;sshbuf_reset(b);
    assert(failures==1 && !fail_next && !sshbuf_len(b) && sshbuf_ptr(b)==prior);
    assert(sshbuf_alloc(b)==prior_alloc && prior_alloc<=512 && sshbuf_max_size(b)==512);
    for(size_t i=0;i<prior_alloc;i++)assert(prior[i]==0);
    assert(!sshbuf_put_u32(b,0x12345678));uint32_t value;
    assert(!sshbuf_get_u32(b,&value) && value==0x12345678);
    sshbuf_reset(b);assert(sshbuf_alloc(b)==256);sshbuf_free(b);
    printf("APPLE_SSH_RESET_HOST_PASS CAPACITIES=%u ZEROIZATION=1 READONLY_PARENT=1 ALLOC_FAILURE=1\n",cases);
#else
    printf("APPLE_SSH_RESET_HOST_PASS CAPACITIES=%u ZEROIZATION=1 READONLY_PARENT=1 ALLOC_FAILURE=0\n",cases);
#endif
    return 0;
}
