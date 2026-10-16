/* SPDX-License-Identifier: BSD-2-Clause
 * Candidate digest dispatch; not a complete registered crypto provider.
 */
#include <corecrypto/ccdigest.h>
#include "rpi5_digest_abi.h"
extern const struct ccdigest_info rpi5_sha256_di;
void rpi5_sha256_digest_init(const struct ccdigest_info *,ccdigest_ctx_t);
void rpi5_sha256_digest_update(const struct ccdigest_info *,ccdigest_ctx_t,size_t,const void *);
void rpi5_sha256_digest_final(const struct ccdigest_info *,ccdigest_ctx_t,void *);
void rpi5_sha256_digest(const struct ccdigest_info *,unsigned long,const void *,void *);
void rpi5_sha512_digest_init(const struct ccdigest_info *,ccdigest_ctx_t);
void rpi5_sha512_digest_update(const struct ccdigest_info *,ccdigest_ctx_t,size_t,const void *);
void rpi5_sha512_digest_final(const struct ccdigest_info *,ccdigest_ctx_t,void *);
void rpi5_sha512_digest(const struct ccdigest_info *,unsigned long,const void *,void *);
/* The 512-family adapter validates SHA-384/SHA-512 identity, rejecting NULL
 * and every unsupported descriptor before accessing caller context. */
void rpi5_digest_init(const struct ccdigest_info *di,ccdigest_ctx_t ctx)
{
    if(di==&rpi5_md5_di || di==&rpi5_sha1_di) rpi5_legacy_digest_init(di,ctx);
    else if(di==&rpi5_sha256_di) rpi5_sha256_digest_init(di,ctx);
    else rpi5_sha512_digest_init(di,ctx);
}
void rpi5_digest_update(const struct ccdigest_info *di,ccdigest_ctx_t ctx,size_t n,const void *p)
{
    if(di==&rpi5_md5_di || di==&rpi5_sha1_di) rpi5_legacy_digest_update(di,ctx,n,p);
    else if(di==&rpi5_sha256_di) rpi5_sha256_digest_update(di,ctx,n,p);
    else rpi5_sha512_digest_update(di,ctx,n,p);
}
void rpi5_digest_final(const struct ccdigest_info *di,ccdigest_ctx_t ctx,void *out)
{
    if(di==&rpi5_md5_di || di==&rpi5_sha1_di) rpi5_legacy_digest_final(di,ctx,out);
    else if(di==&rpi5_sha256_di) rpi5_sha256_digest_final(di,ctx,out);
    else rpi5_sha512_digest_final(di,ctx,out);
}
void rpi5_digest(const struct ccdigest_info *di,unsigned long n,const void *p,void *out)
{
    if(di==&rpi5_md5_di || di==&rpi5_sha1_di) rpi5_legacy_digest(di,n,p,out);
    else if(di==&rpi5_sha256_di) rpi5_sha256_digest(di,n,p,out);
    else rpi5_sha512_digest(di,n,p,out);
}
