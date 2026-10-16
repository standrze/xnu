# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]

class RsaImportTests(unittest.TestCase):
    def test_native_layout(self):
        source=r'''
#include "rpi5_rsa.h"
#include <libkern/crypto/register_crypto.h>
#include <libkern/crypto/rsa.h>
#include <assert.h>
#include <string.h>
static const struct crypto_functions f={.ccrsa_make_pub_fn=rpi5_rsa_make_pub};
int main(void) {
    struct { rsa_pub_ctx pub; unsigned char guard[16]; } storage;
    unsigned char saved[sizeof storage],mod[512],exponent[]={0,1,0,1};
    memset(mod,0x95,sizeof mod);
    for(size_t bytes=8;bytes<=512;bytes+=8) for(unsigned fixed=0;fixed<2;fixed++) {
        memset(&storage,0xa5,sizeof storage);
        ccrsa_pub_ctx_t key=(void *)storage.pub.key;
        key->pb_n=(fixed?512:bytes)/sizeof(cc_unit);
        size_t capacity=key->pb_n;
        assert(!f.ccrsa_make_pub_fn(key,4,exponent,bytes,mod));
        assert(key->pb_n==capacity && key->pb_bitlen==bytes*8 && !key->pb_funcs);
        for(size_t i=0;i<capacity*sizeof(cc_unit);i++) {
            cc_unit word=key->pb_ccn[i/sizeof(cc_unit)];
            unsigned byte=(unsigned)((word>>(8*(i%sizeof(cc_unit))))&255);
            assert(byte==(i<bytes?0x95:0));
        }
        for(size_t i=0;i<=capacity;i++) assert(!key->pb_ccn[capacity+i]);
        assert(key->pb_ccn[2*capacity+1]==65537);
        for(size_t i=1;i<capacity;i++) assert(!key->pb_ccn[2*capacity+1+i]);
        for(size_t i=ccrsa_pub_ctx_size(capacity*sizeof(cc_unit));i<sizeof storage;i++)
            assert(((unsigned char *)&storage)[i]==0xa5);
        memcpy(saved,&storage,sizeof storage);
        unsigned char bad[]={0,1,2};
        for(unsigned j=0;j<3;j++) {
            assert(f.ccrsa_make_pub_fn(key,1,bad+j,bytes,mod));
            assert(!memcmp(saved,&storage,sizeof storage));
        }
        assert(f.ccrsa_make_pub_fn(key,4,exponent,0,mod));
        assert(f.ccrsa_make_pub_fn(key,4,exponent,513,mod));
        assert(!memcmp(saved,&storage,sizeof storage));
    }
}
'''
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory); (p/'test.c').write_text(source)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'EXTERNAL_HEADERS'),'-I'+str(ROOT/'libkern'),
                '-I'+str(ROOT/'osfmk/prng'),str(p/'test.c'),
                str(ROOT/'osfmk/prng/rpi5_rsa.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=15)
