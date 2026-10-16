/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include "../../../loader/rpi5/ramroot_confirmation.h"
static uint64_t state;
static unsigned done;
static void *writer(void *unused)
{
    (void)unused;
    for (unsigned i=0;i<200000;i++) {
        assert(rpi5_root_confirmation_publish(&state,4,32768,true));
        assert(rpi5_root_confirmation_publish(&state,96,67108864,true));
        rpi5_root_confirmation_clear(&state);
    }
    __atomic_store_n(&done,1,__ATOMIC_RELEASE);
    return 0;
}
int main(void)
{
    uint32_t n=777;uint64_t b=999;
    assert(!rpi5_root_confirmation_snapshot(&state,&n,&b) && n==777 && b==999);
    for (unsigned count=0;count<128;count++) {
        bool valid=count>=4 && count<=96;
        assert(rpi5_root_confirmation_publish(&state,count,32768,true)==valid);
        assert(rpi5_root_confirmation_snapshot(&state,&n,&b)==valid);
        if (valid) assert(n==count && b==32768);
    }
    const uint64_t invalid[]={0,16384,32769,67125248,UINT64_MAX};
    for (unsigned i=0;i<sizeof invalid/sizeof invalid[0];i++) {
        assert(!rpi5_root_confirmation_publish(&state,42,invalid[i],true));
        n=777;b=999;
        assert(!rpi5_root_confirmation_snapshot(&state,&n,&b) && n==777 && b==999);
    }
    assert(!rpi5_root_confirmation_publish(&state,42,2506752,false));
    assert(rpi5_root_confirmation_publish(&state,42,2506752,true));
    assert(rpi5_root_confirmation_snapshot(&state,&n,&b) && n==42 && b==2506752);
    for (unsigned bit=8;bit<16;bit++) {
        uint64_t invalid_word=(UINT64_C(32768)<<16)|(42<<1)|1|(UINT64_C(1)<<bit);
        __atomic_store_n(&state,invalid_word,__ATOMIC_RELEASE);
        assert(!rpi5_root_confirmation_snapshot(&state,&n,&b));
    }
    rpi5_root_confirmation_clear(&state);
    assert(!rpi5_root_confirmation_snapshot(&state,&n,&b));
    pthread_t thread;assert(!pthread_create(&thread,0,writer,0));
    while (!__atomic_load_n(&done,__ATOMIC_ACQUIRE)) {
        if (rpi5_root_confirmation_snapshot(&state,&n,&b))
            assert((n==4 && b==32768)||(n==96 && b==67108864));
    }
    assert(!pthread_join(thread,0));
    puts("ROOT_CONFIRMATION_NATIVE PASS COUNTS=128 INVALID_BYTES=5 RESERVED_BITS=8 PUBLICATIONS=400000");
    return 0;
}
