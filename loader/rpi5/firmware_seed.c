/* SPDX-License-Identifier: BSD-2-Clause */
#include "firmware_seed.h"
#include "bearssl.h"
static void wipe(void *p,size_t n)
{
    volatile uint8_t *v=p;
    while(n--) *v++=0;
}
int rpi5_firmware_seed_consume(uint8_t *seed,size_t seed_length,
    uint8_t *output,size_t output_length,uint8_t *consumed)
{
    if (!seed || !output || !consumed || seed_length!=64 || output_length!=256)
        return -1;
    uintptr_t starts[3]={(uintptr_t)seed,(uintptr_t)output,(uintptr_t)consumed};
    size_t sizes[3]={64,256,1};
    for(size_t i=0;i<3;i++) {
        if (sizes[i]>UINTPTR_MAX-starts[i]) return -1;
        for(size_t j=0;j<i;j++)
            if (starts[i]<starts[j]+sizes[j] && starts[j]<starts[i]+sizes[i]) return -1;
    }
    if (*consumed) return -1;
    *(volatile uint8_t *)consumed=1;
    int result=rpi5_firmware_seed_derive(seed,seed_length,output,output_length);
    wipe(seed,seed_length);
    return result;
}
int rpi5_firmware_seed_derive(const uint8_t *seed,size_t seed_length,
    uint8_t *output,size_t output_length)
{
    uintptr_t s=(uintptr_t)seed,o=(uintptr_t)output;
    if (!seed || !output || seed_length!=64 || output_length!=256 ||
        s>UINTPTR_MAX-64 || o>UINTPTR_MAX-256 || (s<o+256 && o<s+64)) return -1;
    uint8_t nonzero=0;
    for(size_t i=0;i<64;i++) nonzero|=seed[i];
    if (!nonzero) return -1;
    static const char info[]="rpi5-xnu/boot-seed/v1";
    br_hkdf_context context;
    uint8_t derived[256];
    br_hkdf_init(&context,&br_sha256_vtable,BR_HKDF_NO_SALT,0);
    br_hkdf_inject(&context,seed,64);
    br_hkdf_flip(&context);
    size_t written=br_hkdf_produce(&context,info,sizeof info-1,derived,sizeof derived);
    if (written==sizeof derived)
        for(size_t i=0;i<sizeof derived;i++) output[i]=derived[i];
    wipe(derived,sizeof derived);
    wipe(&context,sizeof context);
    return written==sizeof derived ? 0 : -1;
}
