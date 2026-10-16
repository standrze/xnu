# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]

class DesTests(unittest.TestCase):
    def test_compact_contexts_and_vectors(self):
        vectors=[]; cbc_vectors=[]
        for triple in (False,True):
            key=bytes(range(24)) if triple else bytes(range(8))*3
            result=subprocess.run(['openssl','enc','-des-ede3','-K',key.hex(),'-nopad'],
                                  input=bytes(range(128)),capture_output=True,check=True)
            self.assertEqual(len(result.stdout),128)
            vectors.append('{'+','.join(map(str,result.stdout))+'}')
            result=subprocess.run(['openssl','enc','-des-ede3-cbc','-K',key.hex(),
                '-iv','a0a1a2a3a4a5a6a7','-nopad'],input=bytes(range(128)),capture_output=True,check=True)
            self.assertEqual(len(result.stdout),128)
            cbc_vectors.append('{'+','.join(map(str,result.stdout))+'}')
        source=r'''
#include "rpi5_des.h"
#include <libkern/crypto/des.h>
#include <corecrypto/cc_error.h>
#include <assert.h>
#include <string.h>
#include <libkern/crypto/register_crypto.h>
static const struct crypto_functions helpers={
    .ccdes_key_is_weak_fn=rpi5_des_key_is_weak,
    .ccdes_key_set_odd_parity_fn=rpi5_des_key_set_odd_parity};
int main(void) {
    unsigned char parity[256],saved_parity[256];
    for(unsigned i=0;i<256;i++) parity[i]=(unsigned char)i;
    helpers.ccdes_key_set_odd_parity_fn(NULL,0);
    helpers.ccdes_key_set_odd_parity_fn(parity,256);
    for(unsigned i=0;i<256;i++) {
        unsigned count=0;
        for(unsigned j=0;j<8;j++) count+=(parity[i]>>j)&1u;
        assert(count%2==1 && (parity[i]&0xfeu)==(i&0xfeu));
    }
    memcpy(saved_parity,parity,256); helpers.ccdes_key_set_odd_parity_fn(parity,256);
    assert(!memcmp(saved_parity,parity,256));
    const uint64_t weak[]={
        UINT64_C(0x0101010101010101),UINT64_C(0xfefefefefefefefe),
        UINT64_C(0x1f1f1f1f0e0e0e0e),UINT64_C(0xe0e0e0e0f1f1f1f1),
        UINT64_C(0x01fe01fe01fe01fe),UINT64_C(0xfe01fe01fe01fe01),
        UINT64_C(0x1fe01fe00ef10ef1),UINT64_C(0xe01fe01ff10ef10e),
        UINT64_C(0x01e001e001f101f1),UINT64_C(0xe001e001f101f101),
        UINT64_C(0x1ffe1ffe0efe0efe),UINT64_C(0xfe1ffe1ffe0efe0e),
        UINT64_C(0x011f011f010e010e),UINT64_C(0x1f011f010e010e01),
        UINT64_C(0xe0fee0fef1fef1fe),UINT64_C(0xfee0fee0fef1fef1)};
    for(unsigned k=0;k<16;k++) for(unsigned mask=0;mask<256;mask++) {
        unsigned char bytes[8],original[8];
        for(unsigned i=0;i<8;i++) bytes[i]=(unsigned char)(weak[k]>>(56-8*i))^((mask>>i)&1u);
        memcpy(original,bytes,8);
        assert(helpers.ccdes_key_is_weak_fn(bytes,8)==1);
        assert(!memcmp(bytes,original,8));
        if(mask==0) for(unsigned i=0;i<8;i++) for(unsigned bit=1;bit<8;bit++) {
            bytes[i]^=1u<<bit; assert(helpers.ccdes_key_is_weak_fn(bytes,8)==0); bytes[i]^=1u<<bit;
        }
    }
    assert(helpers.ccdes_key_is_weak_fn(NULL,8)==CCERR_PARAMETER);
    assert(helpers.ccdes_key_is_weak_fn(parity,7)==CCERR_PARAMETER);
    assert(helpers.ccdes_key_is_weak_fn(parity,9)==CCERR_PARAMETER);
    const unsigned char expected[2][128]={VECTORS};
    const unsigned char expected_cbc[2][128]={CBC_VECTORS};
    const struct ccmode_ecb *encs[]={&rpi5_des_ecb_encrypt,&rpi5_tdes_ecb_encrypt};
    const struct ccmode_ecb *decs[]={&rpi5_des_ecb_decrypt,&rpi5_tdes_ecb_decrypt};
    const struct ccmode_cbc *cbc_encs[]={&rpi5_des_cbc_encrypt,&rpi5_tdes_cbc_encrypt};
    const struct ccmode_cbc *cbc_decs[]={&rpi5_des_cbc_decrypt,&rpi5_tdes_cbc_decrypt};
    assert(encs[0]->size<=sizeof(((des_ecb_key_schedule *)0)->enc));
    assert(encs[1]->size<=sizeof(((des3_ecb_key_schedule *)0)->enc));
    unsigned char key[24],data[128],out[130];
    for(unsigned i=0;i<24;i++) key[i]=i;
    for(unsigned i=0;i<128;i++) data[i]=i;
    for(unsigned t=0;t<2;t++) {
        const struct ccmode_ecb *enc=encs[t],*dec=decs[t];
        ccecb_ctx_decl(enc->size,e); ccecb_ctx_decl(dec->size,d);
        unsigned char saved[enc->size];
        assert(!enc->init(enc,e,t?24:8,key)); assert(!dec->init(dec,d,t?24:8,key));
        memcpy(saved,e,enc->size);
        for(size_t n=0;n<=16;n++) {
            memset(out,0xa5,sizeof out);
            assert(!enc->ecb(e,n,n?data:NULL,n?out+1:NULL));
            assert(!memcmp(out+1,expected[t],n*8));
            assert(out[0]==0xa5 && out[n*8+1]==0xa5);
            assert(!dec->ecb(d,n,out+1,out+1)); assert(!memcmp(out+1,data,n*8));
            assert(!enc->ecb(e,n,out+1,out+1)); assert(!memcmp(out+1,expected[t],n*8));
        }
        memset(out,0xa5,sizeof out);
        assert(encs[!t]->ecb(e,1,data,out)==CCERR_PARAMETER);
        assert(dec->ecb(e,1,data,out)==CCERR_PARAMETER);
        assert(enc->ecb(e,1,out,out+1)==CCERR_PARAMETER);
        assert(enc->ecb(e,SIZE_MAX,data,out)==CCERR_PARAMETER);
        assert(enc->ecb(e,1,NULL,out)==CCERR_PARAMETER);
        for(unsigned i=0;i<sizeof out;i++) assert(out[i]==0xa5);
        for(unsigned n=0;n<26;n++) if(n!=(t?24u:8u)) {
            assert(enc->init(enc,e,n,key)==CCERR_PARAMETER);
            assert(!memcmp(e,saved,enc->size));
        }
        const struct ccmode_cbc *ce=cbc_encs[t],*cd=cbc_decs[t];
        cccbc_ctx_decl(ce->size,ec); cccbc_ctx_decl(cd->size,dc); cccbc_iv_decl(8,iv);
        const unsigned char initial_iv[8]={160,161,162,163,164,165,166,167};
        assert(!ce->init(ce,ec,t?24:8,key)); assert(!cd->init(cd,dc,t?24:8,key));
        memcpy(saved,ec,ce->size);
        for(size_t split=0;split<=16;split++) {
            memset(out,0xa5,sizeof out); memcpy(iv,initial_iv,8);
            assert(!ce->cbc(ec,iv,split,split?data:NULL,split?out+1:NULL));
            assert(!memcmp(iv,split?expected_cbc[t]+(split-1)*8:initial_iv,8));
            assert(!ce->cbc(ec,iv,16-split,data+split*8,out+1+split*8));
            assert(!memcmp(out+1,expected_cbc[t],128));
            assert(!memcmp(iv,expected_cbc[t]+120,8));
            memcpy(iv,initial_iv,8);
            assert(!cd->cbc(dc,iv,split,out+1,out+1));
            assert(!memcmp(iv,split?expected_cbc[t]+(split-1)*8:initial_iv,8));
            assert(!cd->cbc(dc,iv,16-split,out+1+split*8,out+1+split*8));
            assert(!memcmp(out+1,data,128) && out[0]==0xa5 && out[129]==0xa5);
            assert(!memcmp(iv,expected_cbc[t]+120,8));
            memcpy(iv,initial_iv,8);
            assert(!ce->cbc(ec,iv,16,out+1,out+1));
            assert(!memcmp(out+1,expected_cbc[t],128));
        }
        memcpy(iv,initial_iv,8); memset(out,0xa5,sizeof out);
        assert(cd->cbc(ec,iv,1,data,out)==CCERR_PARAMETER);
        assert(cbc_encs[!t]->cbc(ec,iv,1,data,out)==CCERR_PARAMETER);
        assert(ce->cbc(ec,iv,1,out,out+1)==CCERR_PARAMETER);
        assert(ce->cbc(ec,iv,SIZE_MAX,data,out)==CCERR_PARAMETER);
        assert(ce->cbc(ec,NULL,0,NULL,NULL)==CCERR_PARAMETER);
        assert(!memcmp(iv,initial_iv,8));
        assert(!memcmp(ec,saved,ce->size));
        for(unsigned i=0;i<sizeof out;i++) assert(out[i]==0xa5);
    }
}
'''.replace('CBC_VECTORS',','.join(cbc_vectors)).replace('VECTORS',','.join(vectors))
        lib=ROOT/'build/rpi5/bearssl-candidate'
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory); (p/'test.c').write_text(source)
            units=['symcipher/des_ct.c','symcipher/des_ct_cbcenc.c','symcipher/des_ct_cbcdec.c',
                   'symcipher/des_support.c','codec/dec32be.c','codec/enc32be.c']
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'EXTERNAL_HEADERS'),'-I'+str(ROOT/'osfmk/prng'),'-I'+str(ROOT/'libkern'),
                '-I'+str(lib/'inc'),'-I'+str(lib/'src'),str(p/'test.c'),
                str(ROOT/'osfmk/prng/rpi5_des.c'),*[str(lib/'src'/u) for u in units],
                '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=15)
