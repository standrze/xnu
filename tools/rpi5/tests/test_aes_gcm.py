# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]

class AesGcmTests(unittest.TestCase):
    def test_pinned_known_answers_and_lifecycle(self):
        lib=ROOT/'build/rpi5/bearssl-candidate'
        text=(lib/'test/test_crypto.c').read_text()
        array=text.split('static const char *const KAT_GCM[] = {',1)[1].split('};',1)[0]
        values=[bytes.fromhex(s) for s in re.findall(r'"([0-9a-f]*)"',array)]
        self.assertEqual(len(values),108)  # 18 published GCM cases, six fields each.
        cases=[]
        for start in range(0,len(values),6):
            key,plain,aad,iv,cipher,tag=values[start:start+6]
            self.assertEqual(len(plain),len(cipher)); self.assertEqual(len(tag),16)
            fields=','.join('{'+','.join(map(str,v))+'}' for v in (key,plain,aad,iv,cipher,tag))
            cases.append('{'+','.join(map(str,(len(key),len(plain),len(aad),len(iv))))+','+fields+'}')
        code=r'''
#include "rpi5_aes_gcm.h"
#include <corecrypto/ccmode.h>
#include <corecrypto/cc_error.h>
#include <assert.h>
#include <string.h>
#include <libkern/crypto/register_crypto.h>
static const struct crypto_functions helper_fixture={
    .ccgcm_init_with_iv_fn=rpi5_gcm_init_with_iv,.ccgcm_inc_iv_fn=rpi5_gcm_inc_iv};
int main(void) {
    const struct {size_t k,n,a,v; unsigned char key[32],plain[64],aad[20],iv[60],cipher[64],tag[16];}
        cases[]={CASES};
    const size_t chunks[]={1,2,7,16,31,65};
    const struct ccmode_gcm *enc=&rpi5_aes_gcm_encrypt,*dec=&rpi5_aes_gcm_decrypt;
    ccgcm_ctx_decl(enc->size,e); ccgcm_ctx_decl(dec->size,d);
    unsigned char out[66],tag[18],snapshot[enc->size];
    for(size_t c=0;c<sizeof cases/sizeof cases[0];c++) for(unsigned ch=0;ch<6;ch++) {
        assert(!enc->init(enc,e,cases[c].k,cases[c].key));
        assert(enc->gcm(e,0,NULL,NULL)==CCERR_CALL_SEQUENCE);
        assert(!enc->set_iv(e,cases[c].v,cases[c].iv));
        assert(enc->set_iv(e,cases[c].v,cases[c].iv)==CCERR_CALL_SEQUENCE);
        for(size_t i=0;i<cases[c].a;) {
            size_t n=cases[c].a-i; if(n>chunks[ch]) n=chunks[ch];
            assert(!enc->gmac(e,n,cases[c].aad+i)); i+=n;
        }
        memset(out,0xa5,sizeof out); memset(tag,0xa5,sizeof tag);
        assert(!enc->gcm(e,0,NULL,NULL));
        assert(enc->gmac(e,0,NULL)==CCERR_CALL_SEQUENCE);
        for(size_t i=0;i<cases[c].n;) {
            size_t n=cases[c].n-i; if(n>chunks[ch]) n=chunks[ch];
            assert(!enc->gcm(e,n,cases[c].plain+i,out+1+i)); i+=n;
        }
        assert(!enc->finalize(e,16,tag+1));
        assert(!memcmp(out+1,cases[c].cipher,cases[c].n));
        assert(!memcmp(tag+1,cases[c].tag,16));
        assert(out[0]==0xa5 && out[cases[c].n+1]==0xa5 && tag[0]==0xa5 && tag[17]==0xa5);
        memcpy(snapshot,e,enc->size);
        assert(enc->gcm(e,0,NULL,NULL)==CCERR_CALL_SEQUENCE);
        assert(enc->finalize(e,16,tag+1)==CCERR_CALL_SEQUENCE);
        assert(!memcmp(snapshot,e,enc->size));
        assert(!enc->reset(e));
        for(unsigned bad=0;bad<2;bad++) {
            assert(!dec->init(dec,d,cases[c].k,cases[c].key));
            assert(!dec->set_iv(d,cases[c].v,cases[c].iv));
            assert(!dec->gmac(d,cases[c].a,cases[c].aad));
            memcpy(out+1,cases[c].cipher,cases[c].n);
            for(size_t i=0;i<cases[c].n;) {
                size_t n=cases[c].n-i; if(n>chunks[ch]) n=chunks[ch];
                assert(!dec->gcm(d,n,out+1+i,out+1+i)); i+=n;
            }
            memcpy(tag+1,cases[c].tag,16); tag[1]^=bad;
            assert(dec->finalize(d,16,tag+1)==(bad?CCERR_INTEGRITY:0));
            assert(!memcmp(tag+1,cases[c].tag,16));
            assert(!memcmp(out+1,cases[c].plain,cases[c].n));
            assert(!dec->reset(d));
        }
    }
    unsigned char key[32]={0},iv[12]={1,2,3,4},next[14],manual_tag[16];
    for(unsigned k=16;k<=32;k+=8) {
        assert(!helper_fixture.ccgcm_init_with_iv_fn(enc,e,k,key,iv));
        assert(enc->set_iv(e,12,iv)==CCERR_CALL_SEQUENCE);
        assert(helper_fixture.ccgcm_inc_iv_fn(enc,e,next+1)==CCERR_CALL_SEQUENCE);
        assert(!enc->finalize(e,16,tag+1));
        assert(!enc->init(enc,d,k,key)); assert(!enc->set_iv(d,12,iv));
        assert(!enc->finalize(d,16,manual_tag));
        assert(!memcmp(tag+1,manual_tag,16));
        for(unsigned message=1;message<=3;message++) {
            assert(!enc->reset(e)); memset(next,0xa5,sizeof next);
            assert(enc->set_iv(e,12,iv)==CCERR_CALL_SEQUENCE);
            assert(helper_fixture.ccgcm_inc_iv_fn(dec,e,next+1)==CCERR_CALL_SEQUENCE);
            assert(!helper_fixture.ccgcm_inc_iv_fn(enc,e,next+1));
            assert(!memcmp(next+1,iv,11) && next[12]==message && next[0]==0xa5 && next[13]==0xa5);
            assert(!enc->finalize(e,16,tag+1));
            assert(!enc->reset(d)); assert(!enc->set_iv(d,12,next+1));
            assert(!enc->finalize(d,16,manual_tag));
            assert(!memcmp(tag+1,manual_tag,16));
        }
        assert(!enc->reset(d));
        assert(helper_fixture.ccgcm_inc_iv_fn(enc,d,next+1)==CCERR_CALL_SEQUENCE);
    }
    memset(iv+4,255,8); iv[11]=254;
    assert(!helper_fixture.ccgcm_init_with_iv_fn(enc,e,16,key,iv));
    assert(!enc->reset(e)); assert(!helper_fixture.ccgcm_inc_iv_fn(enc,e,next+1));
    assert(next[12]==255 && !memcmp(next+1,iv,11));
    assert(!enc->reset(e)); memcpy(snapshot,e,enc->size); memset(next,0xa5,sizeof next);
    assert(helper_fixture.ccgcm_inc_iv_fn(enc,e,next+1)==CCERR_OVERFLOW);
    assert(!memcmp(snapshot,e,enc->size));
    for(unsigned i=0;i<sizeof next;i++) assert(next[i]==0xa5);
}
'''.replace('CASES',','.join(cases))
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory); (p/'test.c').write_text(code)
            units=['aead/gcm.c','hash/ghash_ctmul64.c','symcipher/aes_ct64.c',
                   'symcipher/aes_ct64_enc.c','symcipher/aes_ct64_ctr.c',
                   'codec/dec32le.c','codec/enc32le.c','codec/dec32be.c','codec/enc32be.c']
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'EXTERNAL_HEADERS'),'-I'+str(ROOT/'osfmk/prng'),'-I'+str(ROOT/'libkern'),
                '-I'+str(lib/'inc'),'-I'+str(lib/'src'),str(p/'test.c'),
                str(ROOT/'osfmk/prng/rpi5_aes_gcm.c'),*[str(lib/'src'/u) for u in units],
                '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=15)
