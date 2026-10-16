/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_rsa.h"
#include <corecrypto/cc_error.h>
#include <string.h>
#define MAX_BYTES 512

static void import_words(cc_unit *words, size_t n, const uint8_t *bytes, size_t len)
{
    memset(words,0,n*sizeof *words);
    for(size_t i=0;i<len;i++) {
        words[i/sizeof *words] |= (cc_unit)bytes[len-1-i] << (8*(i%sizeof *words));
    }
}

int rpi5_rsa_make_pub(ccrsa_pub_ctx_t key, size_t en, const uint8_t *e,
    size_t mn, const uint8_t *m)
{
    if(!key || (uintptr_t)key % _Alignof(struct ccrsa_pub_ctx) ||
        !e || !m || !en || !mn || en>MAX_BYTES || mn>MAX_BYTES)
        return CCERR_PARAMETER;
    cc_size n=key->pb_n;
    if(!n || n>MAX_BYTES/sizeof(cc_unit)) return CCERR_PARAMETER;
    while(en && !*e) { ++e; --en; }
    while(mn && !*m) { ++m; --mn; }
    if(!en || !mn || en>n*sizeof(cc_unit) || mn>n*sizeof(cc_unit) ||
        !(e[en-1]&1) || !(m[mn-1]&1) || (en==1 && e[0]<3) ||
        en>mn || (en==mn && memcmp(e,m,en)>=0)) return CCERR_PARAMETER;
    /* Stage both inputs before modifying the context, permitting input that
     * aliases it. Failure above leaves the old context unchanged. */
    cc_unit modulus[MAX_BYTES/sizeof(cc_unit)],exponent[MAX_BYTES/sizeof(cc_unit)];
    import_words(modulus,n,m,mn); import_words(exponent,n,e,en);
    cc_unit bits=(cc_unit)((mn-1)*8);
    for(unsigned v=m[0];v;v>>=1) ++bits;
    key->pb_bitlen=bits;
    key->pb_funcs=NULL;
    memcpy(key->pb_ccn,modulus,n*sizeof(cc_unit));
    memset(key->pb_ccn+n,0,(n+1)*sizeof(cc_unit));
    memcpy(key->pb_ccn+2*n+1,exponent,n*sizeof(cc_unit));
    /* No Montgomery methods/precomputation: only the paired BearSSL-backed
     * verifier may consume this representation. Not registered yet. */
    return 0;
}
