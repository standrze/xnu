# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]

def ecb(key,data):
    return subprocess.run(['openssl','enc',f'-aes-{len(key)*8}-ecb','-K',key.hex(),'-nopad'],
                          input=data,capture_output=True,check=True).stdout

class AesXtsTests(unittest.TestCase):
    def test_reference_splits_and_failures(self):
        vectors=[]
        for n in (16,32):
            key=bytes(range(n)); tweak_key=bytes(range(32,32+n))
            value=int.from_bytes(ecb(tweak_key,bytes(range(16))),'little')
            masks=[]
            for _ in range(16):
                masks.append(value.to_bytes(16,'little'))
                value=(value<<1)^((value>>127)*((1<<128)|0x87))
            mask=b''.join(masks)
            intermediate=ecb(key,bytes(a^b for a,b in zip(bytes(range(256)),mask)))
            vectors.append('{'+','.join(map(str,bytes(a^b for a,b in zip(intermediate,mask))))+'}')
        code=r'''
#include "rpi5_aes_ecb.h"
#include <corecrypto/ccmode.h>
#include <corecrypto/cc_error.h>
#include <libkern/crypto/aes.h>
#include <libkern/crypto/aesxts.h>
#include <assert.h>
#include <string.h>
#include "rpi5_aes_ecb.c"
int main(void) {
    const unsigned char expected[2][256]={VECTORS};
    const struct ccmode_xts *enc=&rpi5_aes_xts_encrypt,*dec=&rpi5_aes_xts_decrypt;
    assert(enc->size<=sizeof(((symmetric_xts *)0)->enc));
    assert(dec->size<=sizeof(((symmetric_xts *)0)->dec));
    assert(rpi5_aes_cbc_encrypt.size<=sizeof(aes_encrypt_ctx));
    assert(rpi5_aes_cbc_decrypt.size<=sizeof(aes_decrypt_ctx));
    ccxts_ctx_decl(enc->size,e); ccxts_ctx_decl(dec->size,d);
    ccxts_tweak_decl(enc->tweak_size,t);
    unsigned char key[32],key2[32],iv[16],data[256],out[258];
    unsigned char saved_key[enc->size],saved_tweak[enc->tweak_size];
    for(unsigned i=0;i<32;i++) { key[i]=i; key2[i]=i+32; }
    for(unsigned i=0;i<16;i++) iv[i]=i;
    for(unsigned i=0;i<256;i++) data[i]=i;
    for(unsigned k=0;k<2;k++) {
        assert(!enc->init(enc,e,16+16*k,key,key2));
        dec->key_sched(dec,d,16+16*k,key,key2);
        memcpy(saved_key,e,enc->size);
        for(size_t split=0;split<=16;split++) {
            assert(!enc->set_tweak(e,t,iv)); memset(out,0xa5,sizeof out);
            assert(enc->xts(e,t,split,data,out+1)==t);
            assert(enc->xts(e,t,16-split,data+split*16,out+1+split*16)==t);
            assert(!memcmp(out+1,expected[k],256));
            assert(!dec->set_tweak(d,t,iv));
            assert(dec->xts(d,t,split,out+1,out+1)==t);
            assert(dec->xts(d,t,16-split,out+1+split*16,out+1+split*16)==t);
            assert(!memcmp(out+1,data,256));
            assert(!enc->set_tweak(e,t,iv));
            assert(enc->xts(e,t,16,out+1,out+1)==t);
            assert(!memcmp(out+1,expected[k],256));
            assert(out[0]==0xa5 && out[257]==0xa5);
        }
        assert(!enc->set_tweak(e,t,iv)); memcpy(saved_tweak,t,enc->tweak_size);
        memset(out,0xa5,sizeof out);
        assert(enc->xts(e,t,(1u<<20)+1,data,out)==NULL);
        assert(enc->xts(e,t,1,NULL,out)==NULL);
        assert(enc->xts(e,t,1,out,out+1)==NULL);
        assert(dec->xts(e,t,1,data,out)==NULL);
        assert(!memcmp(t,saved_tweak,enc->tweak_size));
        for(size_t i=0;i<sizeof out;i++) assert(out[i]==0xa5);
        assert(enc->init(enc,e,16+16*k,key,key)==CCERR_PARAMETER);
        assert(enc->init(enc,e,24,key,key2)==CCERR_PARAMETER);
        assert(!memcmp(e,saved_key,enc->size));
        /* Inject a near-limit count without doing a million AES operations. */
        struct xts_tweak near_limit;
        memcpy(&near_limit,t,sizeof near_limit); near_limit.blocks=(1u<<20)-1;
        memcpy(t,&near_limit,sizeof near_limit); memcpy(saved_tweak,t,enc->tweak_size);
        assert(enc->xts(e,t,2,data,out+1)==NULL);
        assert(!memcmp(t,saved_tweak,enc->tweak_size));
        assert(enc->xts(e,t,1,data,out+1)==t);
        memcpy(&near_limit,t,sizeof near_limit); assert(near_limit.blocks==(1u<<20));
        memcpy(saved_tweak,t,enc->tweak_size);
        assert(enc->xts(e,t,1,data,out+1)==NULL);
        assert(enc->xts(e,t,0,NULL,NULL)==t);
        assert(!memcmp(t,saved_tweak,enc->tweak_size));
    }
}
'''.replace('VECTORS',','.join(vectors))
        lib=ROOT/'build/rpi5/bearssl-candidate'
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory); (p/'test.c').write_text(code)
            units=['symcipher/aes_ct64.c','symcipher/aes_ct64_enc.c','symcipher/aes_ct64_dec.c',
                   'symcipher/aes_ct64_cbcenc.c','symcipher/aes_ct64_cbcdec.c',
                   'codec/dec32le.c','codec/enc32le.c']
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'EXTERNAL_HEADERS'),'-I'+str(ROOT/'osfmk/prng'),'-I'+str(ROOT/'libkern'),
                '-I'+str(lib/'inc'),'-I'+str(lib/'src'),str(p/'test.c'),
                *[str(lib/'src'/u) for u in units],
                '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=15)
