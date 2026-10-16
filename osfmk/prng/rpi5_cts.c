/* SPDX-License-Identifier: BSD-2-Clause
 * Candidate CBC-CS3, for the checked Pi AES/DES CBC descriptors only.
 * Key/IV must be disjoint from buffers. Exact in-place data is supported.
 * Returns nbytes on success, zero on rejected input or cipher failure.
 */
#include "rpi5_cts.h"
#include "rpi5_aes_ecb.h"
#include "rpi5_des.h"
#include <corecrypto/ccmode.h>
#include <stdint.h>
#include <string.h>
static void wipe(void *p,size_t n) { volatile unsigned char *v=p; while(n--) *v++=0; }
static size_t process(const struct ccmode_cbc *mode,cccbc_ctx *key,cccbc_iv *iv,
    size_t n,const void *in,void *out,unsigned decrypting)
{
    if(decrypting) {
        if(mode!=&rpi5_aes_cbc_decrypt && mode!=&rpi5_des_cbc_decrypt && mode!=&rpi5_tdes_cbc_decrypt) return 0;
    } else {
        if(mode!=&rpi5_aes_cbc_encrypt && mode!=&rpi5_des_cbc_encrypt && mode!=&rpi5_tdes_cbc_encrypt) return 0;
    }
    size_t b=mode->block_size;
    uintptr_t src=(uintptr_t)in,dst=(uintptr_t)out;
    if(!key || !iv || !in || !out || n<=b || n>UINTPTR_MAX-src || n>UINTPTR_MAX-dst ||
        (src!=dst && src<dst+n && dst<src+n)) return 0;
    size_t tail=(n-1)%b+1,prefix=n-b-tail,result=0;
    cccbc_iv_decl(16,chain); cccbc_iv_decl(16,zero);
    unsigned char first[16]={0},last[16]={0},work[16]={0},final_iv[16]={0};
    memcpy(chain,iv,b); memset(zero,0,16);
    /* Capture both final pieces before processing any in-place prefix. */
    memcpy(first,(const unsigned char *)in+prefix,b);
    memcpy(last,(const unsigned char *)in+prefix+b,tail);
    if(mode->cbc(key,chain,0,NULL,NULL)) goto done;
    if(prefix && mode->cbc(key,chain,prefix/b,in,out)) goto done;
    if(!decrypting) {
        if(mode->cbc(key,chain,1,first,first)) goto done;
        if(mode->cbc(key,chain,1,last,work)) goto done;
        memcpy((unsigned char *)out+prefix,work,b);
        memcpy((unsigned char *)out+prefix+b,first,tail);
        memcpy(final_iv,work,b);
    } else {
        /* D(final ciphertext) yields padded final plaintext XOR the preceding
         * ciphertext. Its suffix reconstructs the bytes that were stolen. */
        memcpy(final_iv,first,b);
        if(mode->cbc(key,zero,1,first,work)) goto done;
        for(size_t i=0;i<tail;i++) first[i]=work[i]^last[i];
        memcpy(last+tail,work+tail,b-tail);
        if(mode->cbc(key,chain,1,last,work)) goto done;
        memcpy((unsigned char *)out+prefix,work,b);
        memcpy((unsigned char *)out+prefix+b,first,tail);
    }
    memcpy(iv,final_iv,b); result=n;
done:
    wipe(chain,16); wipe(zero,16); wipe(first,16); wipe(last,16); wipe(work,16); wipe(final_iv,16);
    return result;
}
size_t rpi5_cts3_encrypt(const struct ccmode_cbc *m,cccbc_ctx *k,cccbc_iv *v,size_t n,const void *i,void *o)
{
    return process(m,k,v,n,i,o,0);
}
size_t rpi5_cts3_decrypt(const struct ccmode_cbc *m,cccbc_ctx *k,cccbc_iv *v,size_t n,const void *i,void *o)
{
    return process(m,k,v,n,i,o,1);
}
