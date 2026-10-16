# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import hmac
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]

class GeneratorTests(unittest.TestCase):
    def test_vectors_limits_and_terminal_failure(self):
        def vector(identifier):
            seed=hmac.digest(bytes(range(64)),b'rpi5-xnu/generator/v1'+identifier.to_bytes(4,'little'),'sha256')
            key=bytes(32); value=bytes([1])*32
            def update(data):
                nonlocal key,value
                for separator in ((b'\0',b'\1') if data else (b'\0',)):
                    key=hmac.digest(key,value+separator+data,'sha256')
                    value=hmac.digest(key,value,'sha256')
            def generate(n):
                nonlocal value
                result=b''
                while len(result)<n:
                    value=hmac.digest(key,value,'sha256')
                    result+=value
                update(b'')
                return result[:n]
            update(seed)
            result=generate(32)+generate(17)
            update(bytes(range(31)))
            result+=generate(64)
            update(bytes(range(64)))  # user mix at request limit
            update(bytes(range(64)))  # qualified reseed
            return result+generate(256)
        expected=','.join('{'+','.join(map(str,vector(i)))+'}' for i in (0,1,0xffffffff))
        code=r'''
#include "rpi5_prng_generator.h"
#include <assert.h>
#include <string.h>
int main(void) {
    const unsigned char expected[][369]={EXPECTED};
    const uint32_t ids[]={0,1,UINT32_MAX};
    unsigned char seed[64],out[258];
    for(unsigned i=0;i<64;i++)seed[i]=i;
    for(unsigned i=0;i<3;i++) {
        struct rpi5_prng_generator g={0};
        assert(!rpi5_prng_generator_init(&g,seed,ids[i]));
        struct rpi5_prng_generator saved=g;
        assert(rpi5_prng_generator_init(&g,seed,ids[i])==-1);
        assert(!memcmp(&g,&saved,sizeof g));
        memset(out,0xa5,sizeof out);
        assert(!rpi5_prng_generator_generate(&g,out+1,32));
        assert(!memcmp(out+1,expected[i],32) && out[0]==0xa5 && out[33]==0xa5);
        assert(g.requests==1);
        assert(!rpi5_prng_generator_generate(&g,out+1,17));
        assert(!memcmp(out+1,expected[i]+32,17) && g.requests==2);
        assert(!rpi5_prng_generator_mix(&g,seed,31) && g.requests==2);
        assert(!rpi5_prng_generator_generate(&g,out+1,64));
        assert(!memcmp(out+1,expected[i]+49,64) && g.requests==3);
        saved=g;
        assert(rpi5_prng_generator_generate(&g,out,257)==-1);
        assert(rpi5_prng_generator_generate(&g,out,0)==-1);
        assert(rpi5_prng_generator_generate(&g,0,1)==-1);
        assert(!memcmp(&g,&saved,sizeof g));
        g.requests=RPI5_PRNG_REQUEST_LIMIT;
        memset(out,0xa5,sizeof out);
        assert(rpi5_prng_generator_generate(&g,out,1)==-1);
        assert(!rpi5_prng_generator_mix(&g,seed,64));
        assert(g.requests==RPI5_PRNG_REQUEST_LIMIT);
        assert(rpi5_prng_generator_generate(&g,out,1)==-1 && out[0]==0xa5);
        assert(!rpi5_prng_generator_reseed(&g,seed));
        assert(!g.requests && !rpi5_prng_generator_generate(&g,out+1,256));
        assert(!memcmp(out+1,expected[i]+113,256) && g.requests==1);
        assert(out[0]==0xa5 && out[257]==0xa5);
        rpi5_prng_generator_fail(&g);
        for(size_t j=0;j<sizeof g.drbg;j++) assert(((unsigned char *)&g.drbg)[j]==0);
        memset(out,0xa5,sizeof out);
        assert(rpi5_prng_generator_generate(&g,out,1)==-1 && out[0]==0xa5);
        assert(rpi5_prng_generator_reseed(&g,seed)==-1);
        assert(rpi5_prng_generator_init(&g,seed,ids[i])==-1);
    }
}
'''.replace('EXPECTED',expected)
        lib=ROOT/'build/rpi5/bearssl-candidate'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'osfmk/prng'),'-I'+str(lib/'inc'),'-I'+str(lib/'src'),
                str(p/'test.c'),str(ROOT/'osfmk/prng/rpi5_prng_generator.c'),
                *[str(lib/'src'/u) for u in ('rand/hmac_drbg.c','mac/hmac.c',
                'hash/sha2small.c','codec/dec32be.c','codec/enc32be.c')],
                '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
