# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]

class RsaDigestTests(unittest.TestCase):
    def test_oid_translation(self):
        source=r'''
#include "rpi5_rsa_digest.h"
#include <corecrypto/ccdigest.h>
#include <assert.h>
#include <string.h>
int main(void) {
    const unsigned char *oids[]={CC_DIGEST_OID_MD5,CC_DIGEST_OID_SHA1,
        CC_DIGEST_OID_SHA256,CC_DIGEST_OID_SHA384,CC_DIGEST_OID_SHA512};
    const size_t sizes[]={16,20,32,48,64};
    const unsigned char *out;
    for(unsigned i=0;i<5;i++) {
        unsigned char copy[11]; size_t n=oids[i][1]+2;
        memcpy(copy,oids[i],n);
        assert(!rpi5_rsa_digest_oid(copy,sizes[i],&out));
        assert(out!=copy+1 && !memcmp(out,copy+1,n-1));
        for(size_t j=0;j<n;j++) {
            copy[j]^=0x80; out=oids[i];
            assert(rpi5_rsa_digest_oid(copy,sizes[i],&out) && !out);
            copy[j]^=0x80;
        }
        for(size_t size=0;size<66;size++) if(size!=sizes[i]) {
            out=oids[i]; assert(rpi5_rsa_digest_oid(copy,size,&out) && !out);
        }
    }
    assert(!rpi5_rsa_digest_oid(NULL,36,&out) && !out);
    assert(rpi5_rsa_digest_oid(NULL,32,&out) && !out);
    assert(rpi5_rsa_digest_oid(oids[0],16,NULL));
}
'''
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory); (p/'test.c').write_text(source)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'EXTERNAL_HEADERS'),'-I'+str(ROOT/'osfmk/prng'),
                str(p/'test.c'),str(ROOT/'osfmk/prng/rpi5_rsa_digest.c'),
                '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=15)
