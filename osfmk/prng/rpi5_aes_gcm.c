/* SPDX-License-Identifier: BSD-2-Clause
 * Candidate GCM descriptor; not registered. Caller serializes a context and
 * keeps context, IV, AAD and tag disjoint from payload buffers. Payload may be
 * exactly in place. Decryption output is unauthenticated until finalize succeeds.
 */
#include "rpi5_aes_gcm.h"
#include <corecrypto/cc_error.h>
#include "bearssl_aead.h"
#include <stdint.h>
#include <string.h>
enum phase { KEY=1,AAD,DATA,FINAL };
struct gcm_state {
    _Alignas(16) br_aes_ct64_ctr_keys key;
    br_gcm_context gcm;
    uint32_t ready,encrypting,phase,managed_iv;
    unsigned char nonce[12];
};
#define GCM_READY UINT32_C(0x5247434d)
#define GCM_DATA_LIMIT ((UINT64_C(1)<<36)-32)
static void wipe(void *p,size_t n) { volatile unsigned char *v=p; while(n--) *v++=0; }
static int load(const ccgcm_ctx *ctx,struct gcm_state *s)
{
    if(!ctx) return CCERR_PARAMETER;
    memcpy(s,ctx,sizeof *s);
    if(s->ready!=GCM_READY || s->encrypting>1 || s->managed_iv>1 || s->phase<KEY || s->phase>FINAL) {
        wipe(s,sizeof *s); return CCERR_PARAMETER;
    }
    /* The persisted context must never retain a pointer into a temporary copy. */
    s->gcm.bctx=&s->key.vtable; return 0;
}
static void save(ccgcm_ctx *ctx,struct gcm_state *s)
{
    s->gcm.bctx=NULL; memcpy(ctx,s,sizeof *s); wipe(s,sizeof *s);
}
static int init(const struct ccmode_gcm *mode,ccgcm_ctx *ctx,size_t n,const void *key)
{
    if(!ctx || !key || (n!=16 && n!=24 && n!=32) ||
        (mode!=&rpi5_aes_gcm_encrypt && mode!=&rpi5_aes_gcm_decrypt)) return CCERR_PARAMETER;
    struct gcm_state s={0}; br_aes_ct64_ctr_init(&s.key,key,n);
    br_gcm_init(&s.gcm,&s.key.vtable,br_ghash_ctmul64);
    s.ready=GCM_READY; s.encrypting=mode==&rpi5_aes_gcm_encrypt; s.phase=KEY;
    save(ctx,&s); return 0;
}
static int set_iv(ccgcm_ctx *ctx,size_t n,const void *iv)
{
    if(!n || !iv || n>UINT64_MAX/8) return CCERR_PARAMETER;
    struct gcm_state s; int rc=load(ctx,&s); if(rc) return rc;
    if(s.phase!=KEY || s.managed_iv) { wipe(&s,sizeof s); return CCERR_CALL_SEQUENCE; }
    br_gcm_reset(&s.gcm,iv,n); s.phase=AAD; save(ctx,&s); return 0;
}
static int aad(ccgcm_ctx *ctx,size_t n,const void *in)
{
    if(n && !in) return CCERR_PARAMETER;
    struct gcm_state s; int rc=load(ctx,&s); if(rc) return rc;
    if(s.phase!=AAD) { wipe(&s,sizeof s); return CCERR_CALL_SEQUENCE; }
    if(s.gcm.count_aad>UINT64_MAX/8 || n>UINT64_MAX/8-s.gcm.count_aad) {
        wipe(&s,sizeof s); return CCERR_OVERFLOW;
    }
    if(n) br_gcm_aad_inject(&s.gcm,in,n);
    save(ctx,&s); return 0;
}
static int crypt(ccgcm_ctx *ctx,size_t n,const void *in,void *out)
{
    uintptr_t src=(uintptr_t)in,dst=(uintptr_t)out;
    if(n && (!in || !out || n>UINTPTR_MAX-src || n>UINTPTR_MAX-dst ||
        (src!=dst && src<dst+n && dst<src+n))) return CCERR_PARAMETER;
    struct gcm_state s; int rc=load(ctx,&s); if(rc) return rc;
    if(s.phase!=AAD && s.phase!=DATA) { wipe(&s,sizeof s); return CCERR_CALL_SEQUENCE; }
    if(s.gcm.count_ctr>GCM_DATA_LIMIT || n>GCM_DATA_LIMIT-s.gcm.count_ctr) {
        wipe(&s,sizeof s); return CCERR_OVERFLOW;
    }
    if(s.phase==AAD) { br_gcm_flip(&s.gcm); s.phase=DATA; }
    if(n) {
        if(in!=out) memcpy(out,in,n);
        br_gcm_run(&s.gcm,(int)s.encrypting,out,n);
    }
    save(ctx,&s); return 0;
}
static int finalize(ccgcm_ctx *ctx,size_t n,void *tag)
{
    if(!tag || !n || n>16) return CCERR_PARAMETER;
    struct gcm_state s; int rc=load(ctx,&s); if(rc) return rc;
    if(s.phase!=AAD && s.phase!=DATA) { wipe(&s,sizeof s); return CCERR_CALL_SEQUENCE; }
    if(s.phase==AAD) br_gcm_flip(&s.gcm);
    unsigned char actual[16]; br_gcm_get_tag(&s.gcm,actual);
    volatile unsigned difference=0;
    if(!s.encrypting) for(size_t i=0;i<n;i++) difference|=(unsigned)(actual[i]^((unsigned char *)tag)[i]);
    /* XNU specifies overwriting the supplied tag even on verification failure. */
    memcpy(tag,actual,n); wipe(actual,sizeof actual); s.phase=FINAL; save(ctx,&s);
    return difference ? CCERR_INTEGRITY : 0;
}
static int reset(ccgcm_ctx *ctx)
{
    struct gcm_state s; int rc=load(ctx,&s); if(rc) return rc;
    wipe(&s.gcm,sizeof s.gcm); br_gcm_init(&s.gcm,&s.key.vtable,br_ghash_ctmul64);
    s.phase=KEY; save(ctx,&s); return 0;
}
const struct ccmode_gcm rpi5_aes_gcm_encrypt={.size=sizeof(struct gcm_state),.encdec=CCMODE_GCM_ENCRYPTOR,
    .block_size=1,.init=init,.set_iv=set_iv,.gmac=aad,.gcm=crypt,.finalize=finalize,.reset=reset};
const struct ccmode_gcm rpi5_aes_gcm_decrypt={.size=sizeof(struct gcm_state),.encdec=CCMODE_GCM_DECRYPTOR,
    .block_size=1,.init=init,.set_iv=set_iv,.gmac=aad,.gcm=crypt,.finalize=finalize,.reset=reset};

int rpi5_gcm_init_with_iv(const struct ccmode_gcm *mode,ccgcm_ctx *ctx,size_t n,const void *key,const void *iv)
{
    if(!iv) return CCERR_PARAMETER;
    int rc=init(mode,ctx,n,key); if(rc) return rc;
    struct gcm_state s; rc=load(ctx,&s); if(rc) return rc;
    memcpy(s.nonce,iv,12); s.managed_iv=1;
    br_gcm_reset(&s.gcm,s.nonce,12); s.phase=AAD; save(ctx,&s); return 0;
}
int rpi5_gcm_inc_iv(const struct ccmode_gcm *mode,ccgcm_ctx *ctx,void *iv)
{
    if(!iv || (mode!=&rpi5_aes_gcm_encrypt && mode!=&rpi5_aes_gcm_decrypt)) return CCERR_PARAMETER;
    struct gcm_state s; int rc=load(ctx,&s); if(rc) return rc;
    if(!s.managed_iv || s.phase!=KEY || s.encrypting!=(unsigned)(mode==&rpi5_aes_gcm_encrypt)) {
        wipe(&s,sizeof s); return CCERR_CALL_SEQUENCE;
    }
    uint64_t counter=0;
    for(unsigned i=4;i<12;i++) counter=(counter<<8)|s.nonce[i];
    /* Unlike raw CTR's counter, this is the GCM message nonce. Reject wrap
     * rather than repeat a key/IV pair. Reinitialization is caller-controlled. */
    if(counter==UINT64_MAX) { wipe(&s,sizeof s); return CCERR_OVERFLOW; }
    counter++;
    for(unsigned i=0;i<8;i++) s.nonce[11-i]=(unsigned char)(counter>>(i*8));
    br_gcm_reset(&s.gcm,s.nonce,12); s.phase=AAD;
    memcpy(iv,s.nonce,12); save(ctx,&s); return 0;
}
