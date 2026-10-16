# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import hashlib
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]

class RsaVerifyTests(unittest.TestCase):
    def test_openssl_signature(self):
        for bits, algorithm in [(1024,'sha256'),(4096,'sha256'),
                *[(2048,a) for a in ('md5','sha1','sha256','sha384','sha512')]]:
            with self.subTest(bits=bits,algorithm=algorithm):
                self.check_signature(bits,algorithm)

    def check_signature(self, bits, algorithm):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            subprocess.run(['openssl','genrsa','-out',str(p/'key.pem'),str(bits)],
                check=True,capture_output=True)
            modulus=subprocess.run(['openssl','rsa','-in',str(p/'key.pem'),
                '-noout','-modulus'],check=True,capture_output=True).stdout.strip().split(b'=')[1]
            message=b'XNU Pi candidate RSA verification test'
            signature=subprocess.run(['openssl','dgst','-'+algorithm,'-sign',str(p/'key.pem')],
                input=message,check=True,capture_output=True).stdout
            source=r'''
#include "rpi5_rsa.h"
#include <libkern/crypto/register_crypto.h>
#include <libkern/crypto/rsa.h>
#include <assert.h>
#include <string.h>
static struct crypto_functions f={.ccrsa_make_pub_fn=rpi5_rsa_make_pub,
    .ccrsa_verify_pkcs1v15_fn=rpi5_rsa_verify_pkcs1v15};
crypto_functions_t g_crypto_funcs=&f;
int main(void) {
    unsigned char modulus[]={MODULUS},sig[]={SIGNATURE},digest[]={DIGEST};
    const unsigned char exponent[]={1,0,1};
    rsa_pub_ctx pub; memset(&pub,0,sizeof pub);
    ccrsa_pub_ctx_t key=(void *)pub.key;
    key->pb_n=ccn_nof(4096);
    assert(!f.ccrsa_make_pub_fn(key,3,exponent,sizeof modulus,modulus));
    unsigned char saved[sizeof pub]; memcpy(saved,&pub,sizeof pub);
    bool valid=false;
    /* Exercise the unmodified libkern wrappers and their fixed capacity. */
    rsa_pub_ctx wrapper_pub;
    memset(&wrapper_pub,0,sizeof wrapper_pub);
    assert(!rsa_make_pub(&wrapper_pub,3,exponent,sizeof modulus,modulus));
    assert(!rsa_verify_pkcs1v15(&wrapper_pub,CC_DIGEST_OID_SHA256,32,digest,sizeof sig,sig,&valid) && valid);
    assert(!f.ccrsa_verify_pkcs1v15_fn(key,CC_DIGEST_OID_SHA256,32,digest,sizeof sig,sig,&valid) && valid);
    for(unsigned i=0;i<32;i++) {
        digest[i]^=1; valid=true;
        assert(!f.ccrsa_verify_pkcs1v15_fn(key,CC_DIGEST_OID_SHA256,32,digest,sizeof sig,sig,&valid) && !valid);
        digest[i]^=1;
    }
    sig[0]^=1; valid=true;
    assert(!f.ccrsa_verify_pkcs1v15_fn(key,CC_DIGEST_OID_SHA256,32,digest,sizeof sig,sig,&valid) && !valid);
    sig[0]^=1; valid=true;
    assert(!f.ccrsa_verify_pkcs1v15_fn(key,CC_DIGEST_OID_SHA256,32,digest,sizeof sig-1,sig,&valid) && !valid);
    valid=true;
    assert(f.ccrsa_verify_pkcs1v15_fn(key,CC_DIGEST_OID_SHA256,31,digest,sizeof sig,sig,&valid) && !valid);
    assert(!memcmp(saved,&pub,sizeof pub));
    /* Invalid contexts must clear a previously true result. */
    valid=true;
    key->pb_bitlen--;
    assert(f.ccrsa_verify_pkcs1v15_fn(key,CC_DIGEST_OID_SHA256,32,digest,sizeof sig,sig,&valid) && !valid);
    memcpy(&pub,saved,sizeof pub);
    key->pb_n=0; valid=true;
    assert(f.ccrsa_verify_pkcs1v15_fn(key,CC_DIGEST_OID_SHA256,32,digest,sizeof sig,sig,&valid) && !valid);
    memcpy(&pub,saved,sizeof pub);
    key->pb_n=ccn_nof(4096)+1; valid=true;
    assert(f.ccrsa_verify_pkcs1v15_fn(key,CC_DIGEST_OID_SHA256,32,digest,sizeof sig,sig,&valid) && !valid);
    memcpy(&pub,saved,sizeof pub);
    valid=true;
    assert(f.ccrsa_verify_pkcs1v15_fn(NULL,CC_DIGEST_OID_SHA256,32,digest,sizeof sig,sig,&valid) && !valid);
    assert(f.ccrsa_verify_pkcs1v15_fn(key,CC_DIGEST_OID_SHA256,32,digest,sizeof sig,sig,NULL));
}
'''
            source=source.replace('CC_DIGEST_OID_SHA256','CC_DIGEST_OID_'+algorithm.upper())
            source=source.replace(',32,digest',',sizeof digest,digest')
            source=source.replace(',31,digest',',sizeof digest-1,digest')
            source=source.replace('i<32','i<sizeof digest')
            for name,data in [('MODULUS',bytes.fromhex(modulus.decode())),
                              ('SIGNATURE',signature),('DIGEST',hashlib.new(algorithm,message).digest())]:
                source=source.replace('{'+name+'}','{'+','.join(map(str,data))+'}')
            (p/'test.c').write_text(source)
            lib=ROOT/'build/rpi5/bearssl-candidate'
            units=list((lib/'src/int').glob('i31_*.c'))
            units += [lib/'src'/u for u in ('rsa/rsa_i31_pub.c','rsa/rsa_i31_pkcs1_vrfy.c',
                'rsa/rsa_pkcs1_sig_unpad.c','codec/dec32be.c','codec/enc32be.c','int/i32_div32.c','codec/ccopy.c')]
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'EXTERNAL_HEADERS'),'-I'+str(ROOT/'libkern'),
                '-I'+str(ROOT/'osfmk/prng'),'-I'+str(lib/'inc'),'-I'+str(lib/'src'),
                str(p/'test.c'),str(ROOT/'libkern/crypto/corecrypto_rsa.c'),
                *[str(ROOT/'osfmk/prng'/u) for u in
                    ('rpi5_rsa.c','rpi5_rsa_digest.c','rpi5_rsa_verify.c')],
                *map(str,units),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=30)
