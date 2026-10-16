# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]

class CtsTests(unittest.TestCase):
    def test_all_tail_lengths_and_modes(self):
        cases=[]
        for name,k,b in [('aes',16,16),('aes',24,16),('aes',32,16),('des',8,8),('tdes',24,8)]:
            key=bytes(range(k)); oracle_key=key*3 if name=='des' else key
            algorithm=f'aes-{k*8}-cbc' if name=='aes' else 'des-ede3-cbc'
            iv=bytes(range(160,160+b))
            for n in range(b+1,4*b+1):
                plain=bytes(range(n)); tail=(n-1)%b+1
                padded=plain+bytes((-n)%b)
                ciphertext=subprocess.run(['openssl','enc','-'+algorithm,'-K',oracle_key.hex(),
                    '-iv',iv.hex(),'-nopad'],input=padded,capture_output=True,check=True).stdout
                self.assertEqual(len(ciphertext),len(padded))
                expected=ciphertext[:-2*b]+ciphertext[-b:]+ciphertext[-2*b:-b][:tail]
                fields=','.join('{'+','.join(map(str,v))+'}' for v in (expected,ciphertext[-b:]))
                cases.append('{&rpi5_'+name+'_cbc_encrypt,&rpi5_'+name+'_cbc_decrypt,'+
                             f'{k},{n},'+fields+'}')
        code=r'''
#include "rpi5_cts.h"
#include "rpi5_aes_ecb.h"
#include "rpi5_des.h"
#include <corecrypto/ccmode.h>
#include <libkern/crypto/register_crypto.h>
#include <assert.h>
#include <string.h>
static const struct crypto_functions table={.ccpad_cts3_encrypt_fn=rpi5_cts3_encrypt,.ccpad_cts3_decrypt_fn=rpi5_cts3_decrypt};
int main(void) {
    const struct {const struct ccmode_cbc *enc,*dec; size_t keylen,n; unsigned char cipher[64],final_iv[16];} cases[]={CASES};
    unsigned char key[32],data[64],initial_iv[16],out[66],plain[66];
    for(unsigned i=0;i<32;i++) key[i]=i;
    for(unsigned i=0;i<64;i++) data[i]=i;
    for(unsigned i=0;i<16;i++) initial_iv[i]=160+i;
    for(size_t c=0;c<sizeof cases/sizeof cases[0];c++) {
        const struct ccmode_cbc *enc=cases[c].enc,*dec=cases[c].dec;
        size_t b=enc->block_size,n=cases[c].n;
        cccbc_ctx_decl(enc->size,e); cccbc_ctx_decl(dec->size,d); cccbc_iv_decl(16,iv);
        assert(!enc->init(enc,e,cases[c].keylen,key)); assert(!dec->init(dec,d,cases[c].keylen,key));
        memset(out,0xa5,sizeof out); memcpy(iv,initial_iv,b);
        assert(table.ccpad_cts3_encrypt_fn(enc,e,iv,n,data,out+1)==n);
        assert(!memcmp(out+1,cases[c].cipher,n) && !memcmp(iv,cases[c].final_iv,b));
        memset(plain,0xa5,sizeof plain); memcpy(iv,initial_iv,b);
        assert(table.ccpad_cts3_decrypt_fn(dec,d,iv,n,out+1,plain+1)==n);
        assert(!memcmp(plain+1,data,n) && !memcmp(iv,cases[c].final_iv,b));
        assert(plain[0]==0xa5 && plain[n+1]==0xa5);
        memcpy(iv,initial_iv,b);
        assert(table.ccpad_cts3_decrypt_fn(dec,d,iv,n,out+1,out+1)==n);
        assert(!memcmp(out+1,data,n)); memcpy(iv,initial_iv,b);
        assert(table.ccpad_cts3_encrypt_fn(enc,e,iv,n,out+1,out+1)==n);
        assert(!memcmp(out+1,cases[c].cipher,n) && out[0]==0xa5 && out[n+1]==0xa5);
        memset(out,0xa5,sizeof out); memcpy(iv,initial_iv,b);
        assert(!table.ccpad_cts3_encrypt_fn(enc,e,iv,b,data,out));
        assert(!table.ccpad_cts3_encrypt_fn(dec,d,iv,n,data,out));
        assert(!table.ccpad_cts3_decrypt_fn(dec,e,iv,n,data,out));
        assert(!table.ccpad_cts3_encrypt_fn(enc,e,iv,n,out,out+1));
        assert(!memcmp(iv,initial_iv,b));
        for(unsigned i=0;i<sizeof out;i++) assert(out[i]==0xa5);
    }
}
'''.replace('CASES',','.join(cases))
        lib=ROOT/'build/rpi5/bearssl-candidate'
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory); (p/'test.c').write_text(code)
            units=['symcipher/aes_ct64.c','symcipher/aes_ct64_enc.c','symcipher/aes_ct64_dec.c',
                   'symcipher/aes_ct64_cbcenc.c','symcipher/aes_ct64_cbcdec.c',
                   'symcipher/des_ct.c','symcipher/des_ct_cbcenc.c','symcipher/des_ct_cbcdec.c',
                   'symcipher/des_support.c','codec/dec32be.c','codec/enc32be.c',
                   'codec/dec32le.c','codec/enc32le.c']
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'EXTERNAL_HEADERS'),'-I'+str(ROOT/'osfmk/prng'),'-I'+str(ROOT/'libkern'),
                '-I'+str(lib/'inc'),'-I'+str(lib/'src'),str(p/'test.c'),
                *[str(ROOT/'osfmk/prng'/u) for u in ('rpi5_cts.c','rpi5_aes_ecb.c','rpi5_des.c')],
                *[str(lib/'src'/u) for u in units],'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=15)
