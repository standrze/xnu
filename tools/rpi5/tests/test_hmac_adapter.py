# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import hmac
import hashlib
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]

class HmacAdapterTests(unittest.TestCase):
    def test_independent_vectors(self):
        cases=[]
        for algorithm in ('md5','sha1','sha256','sha384','sha512'):
            for keylen in (0,1,63,64,65,127,128,129,200):
                for length in (0,1,55,56,63,64,65,111,112,127,128,129,257):
                    mac=hmac.digest(bytes(i%256 for i in range(keylen)),
                                    bytes((i*3)%256 for i in range(length)),algorithm)
                    digest=hashlib.new(algorithm,bytes((i*3)%256 for i in range(length))).digest()
                    cases.append('{&rpi5_'+algorithm+'_di,CRYPTO_DIGEST_ALG_'+algorithm.upper()+','+
                                 str(keylen)+','+str(length)+',{' +
                                 ','.join(map(str,mac))+'},{'+','.join(map(str,digest))+'}}')
        code=r'''
#include <corecrypto/cchmac.h>
#include <libkern/crypto/register_crypto.h>
#include <assert.h>
#include <string.h>
#include "rpi5_crypto_digest.h"
#include "rpi5_crypto_hmac.h"
extern const struct ccdigest_info rpi5_sha256_di,rpi5_sha384_di,rpi5_sha512_di;
extern const struct ccdigest_info rpi5_md5_di,rpi5_sha1_di;
void rpi5_hmac_init(const struct ccdigest_info *,cchmac_ctx_t,unsigned long,const void *);
void rpi5_hmac_update(const struct ccdigest_info *,cchmac_ctx_t,unsigned long,const void *);
void rpi5_hmac_final(const struct ccdigest_info *,cchmac_ctx_t,unsigned char *);
void rpi5_hmac(const struct ccdigest_info *,unsigned long,const void *,unsigned long,const void *,unsigned char *);
/* ABI-checked partial fixture only; never registered in a kernel. */
static struct crypto_functions fixture={
    .cchmac_init_fn=rpi5_hmac_init,.cchmac_update_fn=rpi5_hmac_update,
    .cchmac_final_fn=rpi5_hmac_final,.cchmac_fn=rpi5_hmac,
    .digest_ctx_size_fn=rpi5_crypto_digest_ctx_size,.digest_init_fn=rpi5_crypto_digest_init,
    .digest_update_fn=rpi5_crypto_digest_update,.digest_final_fn=rpi5_crypto_digest_final,
    .digest_fn=rpi5_crypto_digest,
    .hmac_ctx_size_fn=rpi5_crypto_hmac_ctx_size,.hmac_init_fn=rpi5_crypto_hmac_init,
    .hmac_update_fn=rpi5_crypto_hmac_update,
    .hmac_final_generate_fn=rpi5_crypto_hmac_final_generate,
    .hmac_final_verify_fn=rpi5_crypto_hmac_final_verify,
    .hmac_generate_fn=rpi5_crypto_hmac_generate,.hmac_verify_fn=rpi5_crypto_hmac_verify};
int main(void) {
    static const struct {const struct ccdigest_info *di; crypto_digest_alg_t alg;
        size_t k,n; unsigned char mac[64],digest[64];} cases[]={CASES};
    unsigned char key[200],data[257],out[66];
    for(size_t i=0;i<sizeof key;i++) key[i]=(unsigned char)i;
    for(size_t i=0;i<sizeof data;i++) data[i]=(unsigned char)(i*3);
    for(size_t t=0;t<sizeof cases/sizeof cases[0];t++) {
        const struct ccdigest_info *di=cases[t].di;
        memset(out,0xa5,sizeof out);
        fixture.digest_fn(cases[t].alg,cases[t].n?data:NULL,cases[t].n,out+1,di->output_size);
        assert(!memcmp(out+1,cases[t].digest,di->output_size));
        fixture.cchmac_fn(di,cases[t].k,cases[t].k?key:NULL,cases[t].n,cases[t].n?data:NULL,out+1);
        assert(!memcmp(out+1,cases[t].mac,di->output_size));
        fixture.hmac_generate_fn(cases[t].alg,key,cases[t].k,data,cases[t].n,out+1,di->output_size);
        assert(!memcmp(out+1,cases[t].mac,di->output_size));
        assert(fixture.hmac_verify_fn(cases[t].alg,key,cases[t].k,data,cases[t].n,out+1,di->output_size));
        for(size_t i=0;i<di->output_size;i++) {
            out[i+1]^=1;
            assert(!fixture.hmac_verify_fn(cases[t].alg,key,cases[t].k,data,cases[t].n,out+1,di->output_size));
            out[i+1]^=1;
        }
        for(size_t chunk=1;chunk<=129;chunk*=2) {
            cchmac_ctx_decl(64,128,new_ctx);
            size_t hmac_size=fixture.hmac_ctx_size_fn(cases[t].alg);
            assert(hmac_size==cchmac_di_size(di));
            memset(new_ctx,0xa5,cchmac_ctx_size(64,128));
            fixture.hmac_init_fn(cases[t].alg,new_ctx,hmac_size,key,cases[t].k);
            fixture.hmac_update_fn(cases[t].alg,new_ctx,hmac_size,NULL,0);
            ccdigest_ctx_decl(64,128,digest_ctx);
            size_t size=fixture.digest_ctx_size_fn(cases[t].alg);
            assert(size==ccdigest_di_size(di));
            memset(digest_ctx,0xa5,ccdigest_ctx_size(64,128));
            fixture.digest_init_fn(cases[t].alg,digest_ctx,size);
            fixture.digest_update_fn(cases[t].alg,digest_ctx,size,NULL,0);
            cchmac_di_decl(di,ctx);
            fixture.cchmac_init_fn(di,ctx,cases[t].k,cases[t].k?key:NULL);
            fixture.cchmac_update_fn(di,ctx,0,NULL);
            for(size_t offset=0;offset<cases[t].n;) {
                size_t take=cases[t].n-offset; if(take>chunk) take=chunk;
                fixture.cchmac_update_fn(di,ctx,take,data+offset); offset+=take;
                fixture.digest_update_fn(cases[t].alg,digest_ctx,size,data+offset-take,take);
                fixture.hmac_update_fn(cases[t].alg,new_ctx,hmac_size,data+offset-take,take);
            }
            fixture.digest_final_fn(cases[t].alg,digest_ctx,size,out+1,di->output_size);
            assert(!memcmp(out+1,cases[t].digest,di->output_size));
            for(size_t i=size;i<ccdigest_ctx_size(64,128);i++)
                assert(((unsigned char *)digest_ctx)[i]==0xa5);
            fixture.cchmac_final_fn(di,ctx,out+1);
            assert(!memcmp(out+1,cases[t].mac,di->output_size));
            fixture.hmac_final_generate_fn(cases[t].alg,new_ctx,hmac_size,out+1,di->output_size);
            assert(!memcmp(out+1,cases[t].mac,di->output_size));
            assert(fixture.hmac_final_verify_fn(cases[t].alg,new_ctx,hmac_size,out+1,di->output_size));
            out[di->output_size]^=1;
            assert(!fixture.hmac_final_verify_fn(cases[t].alg,new_ctx,hmac_size,out+1,di->output_size));
            out[di->output_size]^=1;
            for(size_t i=hmac_size;i<cchmac_ctx_size(64,128);i++)
                assert(((unsigned char *)new_ctx)[i]==0xa5);
        }
        assert(out[0]==0xa5);
        for(size_t i=di->output_size+1;i<sizeof out;i++) assert(out[i]==0xa5);
    }
}
'''.replace('CASES',','.join(cases))
        lib=ROOT/'build/rpi5/bearssl-candidate'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'EXTERNAL_HEADERS'),'-I'+str(lib/'inc'),'-I'+str(lib/'src'),
                '-I'+str(ROOT/'libkern'),'-I'+str(ROOT/'osfmk/prng'),
                str(p/'test.c'),*[str(ROOT/'osfmk/prng'/u) for u in
                ('rpi5_hmac.c','rpi5_digest_dispatch.c','rpi5_sha256_digest.c',
                 'rpi5_sha512_digest.c','rpi5_sha512_compress.c','rpi5_legacy_digest.c',
                 'rpi5_crypto_digest.c','rpi5_crypto_hmac.c')],
                *[str(lib/'src'/u) for u in ('hash/sha2small.c','hash/sha2big.c',
                  'codec/dec32be.c','codec/enc32be.c','codec/dec64be.c','codec/enc64be.c',
                  'hash/md5.c','hash/sha1.c','codec/dec32le.c','codec/enc32le.c')],
                '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
