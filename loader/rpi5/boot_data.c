/* SPDX-License-Identifier: BSD-2-Clause */
#include "boot_data.h"
static int disjoint(const uintptr_t starts[4],const size_t sizes[4])
{
    for(size_t i=0;i<4;i++) {
        if(!starts[i] || sizes[i]>UINTPTR_MAX-starts[i]) return 0;
        for(size_t j=0;j<i;j++)
            if(starts[i]<starts[j]+sizes[j] && starts[j]<starts[i]+sizes[i]) return 0;
    }
    return 1;
}
int rpi5_boot_data_publish(const uint8_t args[RPI5_BOOT_ARGS_SIZE],
    const uint8_t *tree,size_t tree_length,volatile uint8_t *ad,volatile uint8_t *td)
{
    if(!args || !tree || !ad || !td || !tree_length || tree_length>(1u<<24)) return -1;
    uintptr_t starts[4]={(uintptr_t)args,(uintptr_t)tree,(uintptr_t)ad,(uintptr_t)td};
    size_t sizes[4]={RPI5_BOOT_ARGS_SIZE,tree_length,RPI5_BOOT_ARGS_SIZE,tree_length};
    if(!disjoint(starts,sizes)) return -1;
    for(size_t i=0;i<tree_length;i++) td[i]=tree[i];
    for(size_t i=0;i<RPI5_BOOT_ARGS_SIZE;i++) ad[i]=args[i];
#if defined(__aarch64__)
    __asm__ volatile("dsb sy" ::: "memory");
#endif
    unsigned mismatch=0;
    for(size_t i=0;i<tree_length;i++) mismatch|=td[i]!=tree[i];
    for(size_t i=0;i<RPI5_BOOT_ARGS_SIZE;i++) mismatch|=ad[i]!=args[i];
    if(mismatch) {
        for(size_t i=0;i<tree_length;i++) td[i]=0;
        for(size_t i=0;i<RPI5_BOOT_ARGS_SIZE;i++) ad[i]=0;
        return -1;
    }
    return 0;
}

int rpi5_boot_data_commit(const uint8_t args[RPI5_BOOT_ARGS_SIZE],
    uint8_t *tree,size_t tree_length,size_t capacity,volatile uint8_t *ad,volatile uint8_t *td)
{
    if(!tree_length || tree_length>capacity || capacity>(1u<<24)) return -1;
    uintptr_t starts[4]={(uintptr_t)args,(uintptr_t)tree,(uintptr_t)ad,(uintptr_t)td};
    size_t sizes[4]={RPI5_BOOT_ARGS_SIZE,capacity,RPI5_BOOT_ARGS_SIZE,tree_length};
    /* The wipe range can exceed the encoded length; validate that full range
     * before publishing, so cleanup cannot erase either retained destination. */
    if(!disjoint(starts,sizes)) return -1;
    int status=rpi5_boot_data_publish(args,tree,tree_length,ad,td);
    volatile uint8_t *scratch=tree;
    for(size_t i=0;i<capacity;i++) scratch[i]=0;
#if defined(__aarch64__)
    __asm__ volatile("dsb sy" ::: "memory");
#endif
    for(size_t i=0;i<capacity;i++) if(scratch[i]) status=-1;
    if(status) {
        for(size_t i=0;i<tree_length;i++) td[i]=0;
        for(size_t i=0;i<RPI5_BOOT_ARGS_SIZE;i++) ad[i]=0;
    }
    return status;
}
