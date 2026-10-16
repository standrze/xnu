/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_rsa.h"
#include "rpi5_rsa_digest.h"
#include <corecrypto/cc_error.h>
/* Pinned upstream header has stale Doxygen parameter names. Keep the
 * suppression scoped to that unmodified header, not our translation unit. */
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdocumentation"
#include <bearssl_rsa.h>
#pragma clang diagnostic pop
#include <string.h>

static size_t export_words(const cc_unit *words, size_t n, unsigned char out[512])
{
    size_t len=n*sizeof(cc_unit);
    for(size_t i=0;i<len;i++)
        out[len-1-i]=(unsigned char)(words[i/sizeof(cc_unit)]>>(8*(i%sizeof(cc_unit))));
    size_t skip=0;
    while(skip<len && !out[skip]) ++skip;
    memmove(out,out+skip,len-skip);
    return len-skip;
}

int rpi5_rsa_verify_pkcs1v15(ccrsa_pub_ctx_t key, const uint8_t *oid,
    size_t digest_len, const uint8_t *digest, size_t sig_len,
    const uint8_t *sig, bool *valid)
{
    if(!valid) return CCERR_PARAMETER;
    *valid=false;
    if(!key || (uintptr_t)key % _Alignof(struct ccrsa_pub_ctx) ||
        !digest || !sig || !key->pb_n || key->pb_n>512/sizeof(cc_unit) ||
        key->pb_funcs) return CCERR_PARAMETER;
    const unsigned char *hash_oid;
    if(rpi5_rsa_digest_oid(oid,digest_len,&hash_oid)) return CCERR_PARAMETER;
    unsigned char modulus[512],exponent[512],recovered[64];
    size_t n=key->pb_n;
    size_t mn=export_words(key->pb_ccn,n,modulus);
    size_t en=export_words(key->pb_ccn+2*n+1,n,exponent);
    if(!mn || !en || !(modulus[mn-1]&1) || !(exponent[en-1]&1) ||
        (en==1 && exponent[0]<3) || en>mn ||
        (en==mn && memcmp(exponent,modulus,en)>=0)) return CCERR_PARAMETER;
    size_t bits=(mn-1)*8;
    for(unsigned v=modulus[0];v;v>>=1) ++bits;
    if(key->pb_bitlen!=bits) return CCERR_PARAMETER;
    if(sig_len!=mn) return 0;
    br_rsa_public_key pub={modulus,mn,exponent,en};
    if(!br_rsa_i31_pkcs1_vrfy(sig,sig_len,hash_oid,digest_len,&pub,recovered)) return 0;
    volatile unsigned difference=0;
    for(size_t i=0;i<digest_len;i++) difference|=recovered[i]^digest[i];
    *valid=difference==0;
    return 0;
}
