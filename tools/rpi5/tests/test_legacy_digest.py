# SPDX-License-Identifier: BSD-2-Clause
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]

class LegacyDigestTests(unittest.TestCase):
    def test_md5_sha1_vectors(self):
        lengths=[0,1,55,56,63,64,65,127,128,129,255,256,257]
        expected=[]
        for name in ('md5','sha1'):
            expected.append('{'+','.join('{'+','.join(map(str,hashlib.new(name,
                bytes(i%256 for i in range(n))).digest()))+'}' for n in lengths)+'}')
        source=r'''
#include "rpi5_digest_abi.h"
#include <assert.h>
int main(void) {
    const unsigned char expected[2][13][20]={EXPECTED};
    const size_t lengths[]={LENGTHS};
    const struct ccdigest_info *algorithms[]={&rpi5_md5_di,&rpi5_sha1_di};
    unsigned char data[257],out[22];
    for(size_t i=0;i<sizeof data;i++) data[i]=(unsigned char)i;
    for(unsigned a=0;a<2;a++) {
        const struct ccdigest_info *di=algorithms[a];
        for(unsigned k=0;k<13;k++) {
            memset(out,0xa5,sizeof out);
            rpi5_legacy_digest(di,lengths[k],lengths[k]?data:NULL,out+1);
            assert(!memcmp(out+1,expected[a][k],di->output_size));
            for(size_t chunk=1;chunk<=129;chunk++) {
                ccdigest_ctx_decl(20,64,ctx);
                memset(ctx,0xa5,ccdigest_ctx_size(20,64));
                rpi5_legacy_digest_init(di,ctx);
                rpi5_legacy_digest_update(di,ctx,0,NULL);
                for(size_t offset=0;offset<lengths[k];) {
                    size_t take=lengths[k]-offset; if(take>chunk) take=chunk;
                    rpi5_legacy_digest_update(di,ctx,take,data+offset); offset+=take;
                }
                rpi5_legacy_digest_final(di,ctx,out+1);
                assert(!memcmp(out+1,expected[a][k],di->output_size));
                di->final(di,ctx,out+1);
                assert(!memcmp(out+1,expected[a][k],di->output_size));
                assert(out[0]==0xa5);
                for(size_t i=di->output_size+1;i<sizeof out;i++) assert(out[i]==0xa5);
                for(size_t i=ccdigest_di_size(di);i<ccdigest_ctx_size(20,64);i++)
                    assert(((unsigned char *)ctx)[i]==0xa5);
            }
        }
    }
}
'''.replace('EXPECTED',','.join(expected)).replace('LENGTHS',','.join(map(str,lengths)))
        lib=ROOT/'build/rpi5/bearssl-candidate'
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory); (p/'test.c').write_text(source)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'EXTERNAL_HEADERS'),'-I'+str(ROOT/'osfmk/prng'),
                '-I'+str(lib/'inc'),'-I'+str(lib/'src'),str(p/'test.c'),
                str(ROOT/'osfmk/prng/rpi5_legacy_digest.c'),
                *[str(lib/'src'/u) for u in ('hash/md5.c','hash/sha1.c',
                   'codec/dec32be.c','codec/enc32be.c','codec/dec32le.c','codec/enc32le.c')],
                '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=15)
