# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]
class ChachaStreamTests(unittest.TestCase):
    def test_splits_and_counter_limit(self):
        source=r'''
#include "rpi5_chacha_stream.h"
#include <bearssl_block.h>
#include <assert.h>
#include <string.h>
int main(void) {
    unsigned char key[32],nonce[12],input[257],expected[257],out[259];
    for(unsigned i=0;i<32;i++) key[i]=(unsigned char)i;
    for(unsigned i=0;i<12;i++) nonce[i]=(unsigned char)(i+32);
    for(unsigned i=0;i<257;i++) input[i]=(unsigned char)i;
    memcpy(expected,input,257); br_chacha20_ct_run(key,nonce,1,expected,257);
    struct rpi5_chacha_stream s,saved;
    for(size_t split=0;split<=257;split++) {
        assert(!rpi5_chacha_stream_init(&s,key,nonce)); memset(out,0xa5,sizeof out);
        assert(!rpi5_chacha_stream_crypt(&s,split,input,out+1));
        assert(!rpi5_chacha_stream_crypt(&s,257-split,input+split,out+1+split));
        assert(!memcmp(out+1,expected,257) && out[0]==0xa5 && out[258]==0xa5);
        assert(!rpi5_chacha_stream_init(&s,key,nonce));
        for(size_t i=0;i<257;i++) assert(!rpi5_chacha_stream_crypt(&s,1,out+1+i,out+1+i));
        assert(!memcmp(out+1,input,257));
    }
    s.position=RPI5_CHACHA_TEXT_LIMIT-64;
    unsigned char last[64]={0}; br_chacha20_ct_run(key,nonce,UINT32_MAX,last,64);
    memset(out,0,64);
    assert(!rpi5_chacha_stream_crypt(&s,63,out,out));
    assert(!rpi5_chacha_stream_crypt(&s,1,out+63,out+63));
    assert(!memcmp(out,last,64)); saved=s;
    assert(rpi5_chacha_stream_crypt(&s,1,out,out)==-1);
    assert(!memcmp(&s,&saved,sizeof s) && !memcmp(out,last,64));
    assert(!rpi5_chacha_stream_crypt(&s,0,NULL,NULL));
    assert(!rpi5_chacha_stream_init(&s,key,nonce)); saved=s;
    assert(rpi5_chacha_stream_crypt(&s,8,out,out+1)==-1);
    assert(rpi5_chacha_stream_crypt(&s,SIZE_MAX,out,out)==-1);
    assert(!memcmp(&s,&saved,sizeof s));
}
'''
        lib=ROOT/'build/rpi5/bearssl-candidate'
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory); (p/'test.c').write_text(source)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'osfmk/prng'),'-I'+str(lib/'inc'),'-I'+str(lib/'src'),
                str(p/'test.c'),str(ROOT/'osfmk/prng/rpi5_chacha_stream.c'),
                *[str(lib/'src'/u) for u in ('symcipher/chacha20_ct.c','codec/dec32le.c','codec/enc32le.c')],
                '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=15)
