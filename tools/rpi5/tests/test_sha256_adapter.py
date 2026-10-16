# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import hashlib
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]

class Sha256AdapterTests(unittest.TestCase):
    def test_independent_vectors_and_chunks(self):
        lengths=[0,1,55,56,63,64,65,127,128,129,255,256,257]
        vectors=','.join('{'+','.join(str(x) for x in hashlib.sha256(
            bytes(i%256 for i in range(n))).digest())+'}' for n in lengths)
        source=r'''
#include <assert.h>
#include <string.h>
#include <corecrypto/ccdigest.h>
extern const struct ccdigest_info rpi5_sha256_di;
void rpi5_sha256_digest_init(const struct ccdigest_info *,ccdigest_ctx_t);
void rpi5_sha256_digest_update(const struct ccdigest_info *,ccdigest_ctx_t,size_t,const void *);
void rpi5_sha256_digest_final(const struct ccdigest_info *,ccdigest_ctx_t,void *);
void rpi5_sha256_digest(const struct ccdigest_info *,unsigned long,const void *,void *);
int main(void) {
    const size_t lengths[]={LENGTHS};
    const unsigned char expected[][32]={VECTORS};
    unsigned char data[257],out[34];
    for(size_t i=0;i<sizeof data;i++) data[i]=(unsigned char)i;
    const struct ccdigest_info *di=&rpi5_sha256_di;
    for(size_t n=0;n<sizeof lengths/sizeof lengths[0];n++) {
        memset(out,0xa5,sizeof out);
        rpi5_sha256_digest(di,lengths[n],lengths[n]?data:NULL,out+1);
        assert(!memcmp(out+1,expected[n],32) && out[0]==0xa5 && out[33]==0xa5);
        for(size_t chunk=1;chunk<=65;chunk++) {
            ccdigest_ctx_decl(32,64,ctx);
            rpi5_sha256_digest_init(di,ctx);
            rpi5_sha256_digest_update(di,ctx,0,NULL);
            for(size_t offset=0;offset<lengths[n];) {
                size_t take=lengths[n]-offset; if(take>chunk) take=chunk;
                rpi5_sha256_digest_update(di,ctx,take,data+offset); offset+=take;
            }
            rpi5_sha256_digest_final(di,ctx,out+1);
            assert(!memcmp(out+1,expected[n],32) && out[0]==0xa5 && out[33]==0xa5);
            di->final(di,ctx,out+1);
            assert(!memcmp(out+1,expected[n],32));
        }
    }
}
'''.replace('LENGTHS',','.join(map(str,lengths))).replace('VECTORS',vectors)
        lib=ROOT/'build/rpi5/bearssl-candidate'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(source)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'EXTERNAL_HEADERS'),'-I'+str(lib/'inc'),'-I'+str(lib/'src'),
                str(p/'test.c'),str(ROOT/'osfmk/prng/rpi5_sha256_digest.c'),
                *[str(lib/'src'/u) for u in ('hash/sha2small.c','codec/dec32be.c','codec/enc32be.c')],
                '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
