/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_rsa_digest.h"
#include <corecrypto/ccdigest.h>
#include <corecrypto/cc_error.h>
#include <string.h>

int
rpi5_rsa_digest_oid(const uint8_t *oid, size_t digest_size,
    const unsigned char **translated)
{
    if (!translated) return CCERR_PARAMETER;
    *translated=NULL;
    /* The declared NULL-OID interoperability case is MD5 || SHA-1. */
    if (!oid) return digest_size == 36 ? 0 : CCERR_PARAMETER;
    if (oid[0] != 0x06) return CCERR_PARAMETER;
    struct digest_oid { const unsigned char *der; size_t size; };
    const struct digest_oid supported[] = {
        {CC_DIGEST_OID_MD5,16}, {CC_DIGEST_OID_SHA1,20},
        {CC_DIGEST_OID_SHA256,32}, {CC_DIGEST_OID_SHA384,48},
        {CC_DIGEST_OID_SHA512,64}
    };
    for (size_t i=0;i<sizeof supported/sizeof supported[0];i++) {
        const unsigned char *der=supported[i].der;
        if (digest_size==supported[i].size && oid[1]==der[1] &&
            !memcmp(oid,der,(size_t)der[1]+2)) {
            /* Return our trusted constant, never arbitrary caller encoding. */
            *translated=der+1;
            return 0;
        }
    }
    return CCERR_PARAMETER;
}
