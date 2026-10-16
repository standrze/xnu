# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]

class AesEcbTests(unittest.TestCase):
    def test_vectors_inplace_and_rejections(self):
        data=bytes(range(256))
        vectors=[]; cbc_vectors=[]; ctr_vectors=[]
        counter=bytes(range(160,168))+bytes.fromhex('fffffffffffffffe')
        for n in (16,24,32):
            result=subprocess.run(['openssl','enc',f'-aes-{n*8}-ecb',
                '-K',bytes(range(n)).hex(),'-nopad'],input=data,capture_output=True,check=True)
            self.assertEqual(len(result.stdout),256)
            vectors.append('{'+','.join(map(str,result.stdout))+'}')
            result=subprocess.run(['openssl','enc',f'-aes-{n*8}-cbc',
                '-K',bytes(range(n)).hex(),'-iv',bytes(range(160,176)).hex(),
                '-nopad'],input=data,capture_output=True,check=True)
            self.assertEqual(len(result.stdout),256)
            cbc_vectors.append('{'+','.join(map(str,result.stdout))+'}')
            counters=b''.join(counter[:8]+((int.from_bytes(counter[8:],'big')+i)%(1<<64)).to_bytes(8,'big')
                              for i in range(17))
            stream=subprocess.run(['openssl','enc',f'-aes-{n*8}-ecb',
                '-K',bytes(range(n)).hex(),'-nopad'],input=counters,capture_output=True,check=True).stdout
            expected=bytes((i%256)^stream[i] for i in range(257))
            ctr_vectors.append('{'+','.join(map(str,expected))+'}')
        source=r'''
#include "rpi5_aes_ecb.h"
#include <corecrypto/ccmode.h>
#include <corecrypto/cc_error.h>
#include <assert.h>
#include <stdint.h>
#include <string.h>
int main(void) {
    const unsigned char vectors[3][256]={VECTORS};
    const unsigned char cbc_vectors[3][256]={CBC_VECTORS};
    const unsigned char ctr_vectors[3][257]={CTR_VECTORS};
    const struct ccmode_ecb *enc=&rpi5_aes_ecb_encrypt,*dec=&rpi5_aes_ecb_decrypt;
    const struct ccmode_cbc *ce=&rpi5_aes_cbc_encrypt,*cd=&rpi5_aes_cbc_decrypt;
    unsigned char key[32],data[256],out[258];
    for(unsigned i=0;i<32;i++) key[i]=i;
    for(unsigned i=0;i<256;i++) data[i]=i;
    ccecb_ctx_decl(enc->size,e); ccecb_ctx_decl(dec->size,d);
    unsigned char saved[enc->size];
    for(unsigned k=0;k<3;k++) {
        assert(!enc->init(enc,e,16+8*k,key)); assert(!dec->init(dec,d,16+8*k,key));
        memcpy(saved,e,enc->size);
        for(size_t blocks=0;blocks<=16;blocks++) {
            memset(out,0xa5,sizeof out);
            assert(!enc->ecb(e,blocks,blocks?data:NULL,blocks?out+1:NULL));
            assert(!memcmp(out+1,vectors[k],blocks*16));
            assert(out[0]==0xa5 && out[blocks*16+1]==0xa5);
            assert(!dec->ecb(d,blocks,out+1,out+1));
            assert(!memcmp(out+1,data,blocks*16));
            assert(!enc->ecb(e,blocks,out+1,out+1));
            assert(!memcmp(out+1,vectors[k],blocks*16));
        }
        memset(out,0xa5,sizeof out);
        assert(enc->ecb(e,1,out,out+1)==CCERR_PARAMETER);
        assert(enc->ecb(e,1,out+1,out)==CCERR_PARAMETER);
        assert(enc->ecb(e,SIZE_MAX,NULL,out)==CCERR_PARAMETER);
        assert(enc->ecb(e,1,NULL,out)==CCERR_PARAMETER);
        assert(dec->ecb(e,1,data,out)==CCERR_PARAMETER);
        for(size_t i=0;i<sizeof out;i++) assert(out[i]==0xa5);
        for(size_t n=0;n<34;n++) if(n!=16 && n!=24 && n!=32) {
            assert(enc->init(enc,e,n,key)==CCERR_PARAMETER);
            assert(!memcmp(e,saved,enc->size));
        }
        assert(!memcmp(e,saved,enc->size));
        cccbc_ctx_decl(ce->size,ec); cccbc_ctx_decl(cd->size,dc);
        cccbc_iv_decl(16,iv);
        unsigned char initial_iv[16];
        for(unsigned i=0;i<16;i++) initial_iv[i]=160+i;
        assert(!ce->init(ce,ec,16+8*k,key)); assert(!cd->init(cd,dc,16+8*k,key));
        for(size_t split=0;split<=16;split++) {
            memset(out,0xa5,sizeof out); memcpy(iv,initial_iv,16);
            assert(!ce->cbc(ec,iv,split,split?data:NULL,split?out+1:NULL));
            assert(!memcmp(iv,split?cbc_vectors[k]+(split-1)*16:initial_iv,16));
            assert(!ce->cbc(ec,iv,16-split,data+split*16,out+1+split*16));
            assert(!memcmp(out+1,cbc_vectors[k],256));
            assert(!memcmp(iv,cbc_vectors[k]+240,16));
            memcpy(iv,initial_iv,16);
            assert(!cd->cbc(dc,iv,split,out+1,out+1));
            assert(!memcmp(iv,split?cbc_vectors[k]+(split-1)*16:initial_iv,16));
            assert(!cd->cbc(dc,iv,16-split,out+1+split*16,out+1+split*16));
            assert(!memcmp(out+1,data,256) && out[0]==0xa5 && out[257]==0xa5);
            assert(!memcmp(iv,cbc_vectors[k]+240,16));
            memcpy(iv,initial_iv,16);
            assert(!ce->cbc(ec,iv,16,out+1,out+1));
            assert(!memcmp(out+1,cbc_vectors[k],256));
        }
        memcpy(iv,initial_iv,16); memset(out,0xa5,sizeof out);
        assert(ce->cbc(ec,iv,1,out,out+1)==CCERR_PARAMETER);
        assert(cd->cbc(ec,iv,1,data,out)==CCERR_PARAMETER);
        assert(ce->cbc(ec,iv,SIZE_MAX,data,out)==CCERR_PARAMETER);
        assert(ce->cbc(ec,iv,1,NULL,out)==CCERR_PARAMETER);
        assert(!memcmp(iv,initial_iv,16));
        for(size_t i=0;i<sizeof out;i++) assert(out[i]==0xa5);
        const struct ccmode_ctr *ct=&rpi5_aes_ctr;
        ccctr_ctx_decl(ct->size,ctr);
        unsigned char ctr_iv[16]={160,161,162,163,164,165,166,167,255,255,255,255,255,255,255,254};
        unsigned char message[257],cipher[259],snapshot[ct->size];
        for(unsigned i=0;i<257;i++) message[i]=(unsigned char)i;
        assert(ct->block_size==1 && ct->ecb_block_size==16);
        for(size_t split=0;split<=257;split++) {
            assert(!ct->init(ct,ctr,16+8*k,key,ctr_iv));
            memset(cipher,0xa5,sizeof cipher);
            assert(!ct->ctr(ctr,split,message,cipher+1));
            assert(!ct->ctr(ctr,257-split,message+split,cipher+1+split));
            assert(!memcmp(cipher+1,ctr_vectors[k],257));
            assert(cipher[0]==0xa5 && cipher[258]==0xa5);
            assert(!ct->setctr(ct,ctr,ctr_iv));
            assert(!ct->ctr(ctr,257,cipher+1,cipher+1));
            assert(!memcmp(cipher+1,message,257));
        }
        assert(!ct->setctr(ct,ctr,ctr_iv));
        assert(!ct->ctr(ctr,1,message,cipher+1));
        assert(!ct->setctr(ct,ctr,ctr_iv));
        assert(!ct->ctr(ctr,257,message,cipher+1));
        assert(!memcmp(cipher+1,ctr_vectors[k],257));
        memcpy(snapshot,ctr,ct->size); memset(cipher,0xa5,sizeof cipher);
        assert(ct->ctr(ctr,16,cipher,cipher+1)==CCERR_PARAMETER);
        assert(ct->ctr(ctr,1,NULL,cipher)==CCERR_PARAMETER);
        assert(!ct->ctr(ctr,0,NULL,NULL));
        assert(!memcmp(snapshot,ctr,ct->size));
        for(size_t i=0;i<sizeof cipher;i++) assert(cipher[i]==0xa5);
    }
}
'''.replace('CTR_VECTORS',','.join(ctr_vectors)).replace('CBC_VECTORS',','.join(cbc_vectors)).replace('VECTORS',','.join(vectors))
        lib=ROOT/'build/rpi5/bearssl-candidate'
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory); (p/'test.c').write_text(source)
            units=['symcipher/aes_ct64.c','symcipher/aes_ct64_enc.c','symcipher/aes_ct64_dec.c',
                   'symcipher/aes_ct64_cbcenc.c','symcipher/aes_ct64_cbcdec.c',
                   'codec/dec32le.c','codec/enc32le.c']
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'EXTERNAL_HEADERS'),'-I'+str(ROOT/'osfmk/prng'),
                '-I'+str(lib/'inc'),'-I'+str(lib/'src'),str(p/'test.c'),
                str(ROOT/'osfmk/prng/rpi5_aes_ecb.c'),*[str(lib/'src'/u) for u in units],
                '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=15)
