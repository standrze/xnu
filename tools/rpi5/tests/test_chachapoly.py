# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]
class ChachapolyTests(unittest.TestCase):
    def test_streaming_aead(self):
        upstream=(ROOT/'build/rpi5/bearssl-candidate/test/test_crypto.c').read_text()
        kat=upstream.split('} KAT_POLY1305[] = {',1)[1].split('\n};',1)[0]
        values=[bytes.fromhex(v) for v in re.findall(r'"([0-9a-f]+)"',kat)]
        self.assertEqual(len(values),6)
        source=r'''
#include "rpi5_chachapoly.h"
#include "rpi5_chachapoly_binding.h"
#include <libkern/crypto/chacha20poly1305.h>
#include <corecrypto/cc_error.h>
#include <bearssl_block.h>
#include <assert.h>
#include <string.h>
static struct crypto_functions crypto={.ccchacha20poly1305_fns=&rpi5_chachapoly_functions};
crypto_functions_t g_crypto_funcs=&crypto;
int main(void) {
    /* Fixed known-answer fixture, not an oracle invocation of our primitive. */
    const unsigned char kp[]={KPLAIN},ka[]={KAAD},kk[]={KKEY},kn[]={KNONCE},kc[]={KCIPHER},kt[]={KTAG};
    unsigned char ko[sizeof kp],got[16];
    const struct ccchacha20poly1305_fns *f=&rpi5_chachapoly_functions;
    ccchacha20poly1305_ctx ctx;
    assert(!f->init(f->info(),&ctx,kk));
    ccchacha20poly1305_ctx unchanged=ctx;
    unsigned char increment_nonce[12]; memcpy(increment_nonce,kn,12);
    assert(f->incnonce(f->info(),&ctx,increment_nonce)==1);
    assert(!memcmp(&ctx,&unchanged,sizeof ctx) && !memcmp(increment_nonce,kn,12));
    assert(f->incnonce(NULL,NULL,NULL)==1);
    assert(f->encrypt(f->info(),&ctx,1,kp,ko)==CCERR_PARAMETER);
    for(unsigned run=0;run<2;run++) {
        assert(!f->reset(f->info(),&ctx));
        assert(!f->setnonce(f->info(),&ctx,kn));
        assert(!f->aad(f->info(),&ctx,sizeof ka,ka));
        assert(!f->encrypt(f->info(),&ctx,sizeof kp,kp,ko));
        assert(!f->finalize(f->info(),&ctx,got));
        assert(!memcmp(ko,kc,sizeof kc) && !memcmp(got,kt,16));
        assert(!f->reset(f->info(),&ctx));
        assert(!f->setnonce(f->info(),&ctx,kn));
        assert(!f->aad(f->info(),&ctx,sizeof ka,ka));
        assert(!f->decrypt(f->info(),&ctx,sizeof kc,kc,ko));
        if(run) got[0]^=1;
        assert(f->verify(f->info(),&ctx,got)==(run?CCERR_INTEGRITY:0));
        assert(f->verify(f->info(),&ctx,got)==CCERR_PARAMETER);
        assert(!memcmp(ko,kp,sizeof kp));
    }
    /* Run unchanged XNU wrappers over every plaintext split. */
    assert(!chacha20poly1305_init(&ctx,kk));
    for(size_t split=0;split<=sizeof kp;split++) {
        assert(!chacha20poly1305_reset(&ctx));
        assert(!chacha20poly1305_setnonce(&ctx,kn));
        assert(!chacha20poly1305_aad(&ctx,sizeof ka,ka));
        assert(!chacha20poly1305_encrypt(&ctx,split,kp,ko));
        assert(!chacha20poly1305_encrypt(&ctx,sizeof kp-split,kp+split,ko+split));
        assert(!chacha20poly1305_finalize(&ctx,got));
        assert(!memcmp(ko,kc,sizeof kc) && !memcmp(got,kt,16));
        assert(!chacha20poly1305_reset(&ctx));
        assert(!chacha20poly1305_setnonce(&ctx,kn));
        assert(!chacha20poly1305_aad(&ctx,sizeof ka,ka));
        assert(!chacha20poly1305_decrypt(&ctx,split,ko,ko));
        assert(!chacha20poly1305_decrypt(&ctx,sizeof kp-split,ko+split,ko+split));
        if(split%2) got[0]^=1;
        unsigned char saved_tag[16]; memcpy(saved_tag,got,16);
        assert(chacha20poly1305_verify(&ctx,got)==(split%2?CCERR_INTEGRITY:0));
        assert(!memcmp(got,saved_tag,16) && !memcmp(ko,kp,sizeof kp));
        unchanged=ctx;
        assert(chacha20poly1305_incnonce(&ctx,increment_nonce)==1);
        assert(chacha20poly1305_verify(&ctx,got)==CCERR_PARAMETER);
        assert(!memcmp(&ctx,&unchanged,sizeof ctx));
    }
    assert(!chacha20poly1305_reset(&ctx)); unchanged=ctx;
    memset(ko,0xa5,sizeof ko);
    assert(f->setnonce(NULL,&ctx,kn)==CCERR_PARAMETER);
    assert(f->setnonce(f->info(),NULL,kn)==CCERR_PARAMETER);
    assert(chacha20poly1305_setnonce(&ctx,(const uint8_t *)&ctx)==CCERR_PARAMETER);
    assert(chacha20poly1305_setnonce(&ctx,NULL)==CCERR_PARAMETER);
    assert(!memcmp(&ctx,&unchanged,sizeof ctx));
    assert(!chacha20poly1305_setnonce(&ctx,kn)); unchanged=ctx;
    assert(chacha20poly1305_setnonce(&ctx,kn)==CCERR_PARAMETER);
    assert(chacha20poly1305_encrypt(&ctx,1,kp,&ctx)==CCERR_PARAMETER);
    assert(chacha20poly1305_encrypt(&ctx,1,&ctx,ko)==CCERR_PARAMETER);
    assert(chacha20poly1305_aad(&ctx,1,&ctx)==CCERR_PARAMETER);
    assert(chacha20poly1305_finalize(&ctx,(uint8_t *)&ctx)==CCERR_PARAMETER);
    assert(chacha20poly1305_verify(&ctx,(uint8_t *)&ctx)==CCERR_PARAMETER);
    assert(!memcmp(&ctx,&unchanged,sizeof ctx));
    for(size_t i=0;i<sizeof ko;i++) assert(ko[i]==0xa5);
    for(size_t as=0;as<=sizeof ka;as++) for(size_t ps=0;ps<=sizeof kp;ps++) {
        struct rpi5_chachapoly s;
        assert(!rpi5_chachapoly_init(&s,kk,kn));
        assert(!rpi5_chachapoly_aad(&s,ka,as));
        assert(!rpi5_chachapoly_aad(&s,ka+as,sizeof ka-as));
        assert(!rpi5_chachapoly_crypt(&s,kp,ko,ps,1));
        assert(!rpi5_chachapoly_crypt(&s,kp+ps,ko+ps,sizeof kp-ps,1));
        assert(!rpi5_chachapoly_finish(&s,got,1));
        assert(!memcmp(ko,kc,sizeof kc) && !memcmp(got,kt,16));
    }
    unsigned char key[32],nonce[12],aad[65],input[65],expected[65],out[67],tag[18],want[16];
    for(unsigned i=0;i<32;i++) key[i]=(unsigned char)i;
    for(unsigned i=0;i<12;i++) nonce[i]=(unsigned char)(i+3);
    for(unsigned i=0;i<65;i++) { aad[i]=(unsigned char)i; input[i]=(unsigned char)(i+9); }
    const size_t lengths[]={0,1,15,16,17,63,64,65};
    struct rpi5_chachapoly invalid,saved_invalid;
    assert(!rpi5_chachapoly_init(&invalid,key,nonce));
    saved_invalid=invalid; memset(out,0xa5,sizeof out);
    assert(rpi5_chachapoly_crypt(&invalid,input,out,1,2)==-1);
    assert(rpi5_chachapoly_crypt(&invalid,input,NULL,1,1)==-1);
    assert(rpi5_chachapoly_crypt(&invalid,out,out+1,8,1)==-1);
    assert(rpi5_chachapoly_crypt(&invalid,input,out,SIZE_MAX,1)==-1);
    assert(rpi5_chachapoly_aad(&invalid,NULL,1)==-1);
    assert(rpi5_chachapoly_finish(&invalid,NULL,1)==-1);
    assert(!memcmp(&invalid,&saved_invalid,sizeof invalid));
    for(unsigned i=0;i<sizeof out;i++) assert(out[i]==0xa5);
    invalid.aad_length=UINT64_MAX; saved_invalid=invalid;
    assert(rpi5_chachapoly_aad(&invalid,aad,1)==-1);
    assert(!memcmp(&invalid,&saved_invalid,sizeof invalid));
    invalid.stream.position=RPI5_CHACHA_TEXT_LIMIT; saved_invalid=invalid;
    assert(rpi5_chachapoly_crypt(&invalid,input,out,1,1)==-1);
    assert(!memcmp(&invalid,&saved_invalid,sizeof invalid));
    for(unsigned ai=0;ai<8;ai++) for(unsigned ni=0;ni<8;ni++) {
        size_t an=lengths[ai],n=lengths[ni];
        memcpy(expected,input,n);
        br_poly1305_ctmul_run(key,nonce,expected,n,aad,an,want,br_chacha20_ct_run,1);
        for(size_t split=0;split<=n;split++) {
            struct rpi5_chachapoly s,saved;
            assert(!rpi5_chachapoly_init(&s,key,nonce));
            for(size_t i=0;i<an;i++) assert(!rpi5_chachapoly_aad(&s,aad+i,1));
            memset(out,0xa5,sizeof out); memset(tag,0xa5,sizeof tag);
            assert(!rpi5_chachapoly_crypt(&s,input,out+1,split,1));
            assert(!rpi5_chachapoly_crypt(&s,input+split,out+1+split,n-split,1));
            saved=s;
            assert(rpi5_chachapoly_aad(&s,aad,1)==-1);
            assert(rpi5_chachapoly_crypt(&s,input,out+1,1,0)==-1);
            assert(!memcmp(&s,&saved,sizeof s));
            assert(!rpi5_chachapoly_finish(&s,tag+1,1));
            assert(!memcmp(out+1,expected,n) && !memcmp(tag+1,want,16));
            assert(out[0]==0xa5 && out[n+1]==0xa5 && tag[0]==0xa5 && tag[17]==0xa5);
            saved=s; assert(rpi5_chachapoly_finish(&s,tag+1,1)==-1);
            assert(!memcmp(&s,&saved,sizeof s));
            assert(!rpi5_chachapoly_init(&s,key,nonce));
            assert(!rpi5_chachapoly_aad(&s,aad,an));
            assert(!rpi5_chachapoly_crypt(&s,out+1,out+1,split,0));
            assert(!rpi5_chachapoly_crypt(&s,out+1+split,out+1+split,n-split,0));
            assert(!rpi5_chachapoly_finish(&s,tag+1,0));
            assert(!memcmp(out+1,input,n) && !memcmp(tag+1,want,16));
        }
        for(unsigned changed=0;changed<16;changed++) {
            struct rpi5_chachapoly s;
            assert(!rpi5_chachapoly_init(&s,key,nonce));
            assert(!rpi5_chachapoly_aad(&s,aad,an));
            assert(!rpi5_chachapoly_crypt(&s,expected,out,n,0));
            memcpy(tag,want,16); tag[changed]^=1;
            assert(rpi5_chachapoly_finish(&s,tag,0)==-1);
        }
    }
}
'''
        for name,value in zip(('KPLAIN','KAAD','KKEY','KNONCE','KCIPHER','KTAG'),values):
            source=source.replace('{'+name+'}','{'+','.join(map(str,value))+'}')
        lib=ROOT/'build/rpi5/bearssl-candidate'
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory); (p/'test.c').write_text(source)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'EXTERNAL_HEADERS'),'-I'+str(ROOT/'osfmk/prng'),'-I'+str(ROOT/'libkern'),
                '-I'+str(lib/'inc'),'-I'+str(lib/'src'),str(p/'test.c'),
                str(ROOT/'libkern/crypto/corecrypto_chacha20poly1305.c'),
                *[str(ROOT/'osfmk/prng'/u) for u in ('rpi5_chachapoly.c','rpi5_chacha_stream.c','rpi5_poly1305.c','rpi5_chachapoly_binding.c')],
                *[str(lib/'src'/u) for u in ('symcipher/chacha20_ct.c','symcipher/poly1305_ctmul.c',
                    'codec/dec32le.c','codec/enc32le.c','codec/enc64le.c')],
                '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=30)
