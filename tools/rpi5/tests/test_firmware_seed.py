from pathlib import Path
import hashlib
import hmac
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]

class FirmwareSeedTests(unittest.TestCase):
    def test_derivation_and_rejection(self):
        seed=bytes(range(64))
        prk=hmac.new(bytes(32),seed,hashlib.sha256).digest()
        result=b''; block=b''
        for i in range(1,9):
            block=hmac.new(prk,block+b'rpi5-xnu/boot-seed/v1'+bytes([i]),hashlib.sha256).digest()
            result+=block
        expected=','.join(str(v) for v in result)
        code=r'''
#include "firmware_seed.h"
#include "bearssl.h"
#include <assert.h>
#include <string.h>
int main(void) {
    unsigned char seed[64], out[258], saved[258];
    for(unsigned i=0;i<64;i++) seed[i]=i;
    memset(out,0xa5,sizeof out); memcpy(saved,out,sizeof out);
    const unsigned char expected[256]={EXPECTED};
    assert(!rpi5_firmware_seed_derive(seed,64,out+1,256));
    assert(out[0]==0xa5 && out[257]==0xa5 && !memcmp(out+1,expected,256));
    for(unsigned i=0;i<64;i++) assert(seed[i]==i);
    memcpy(out,saved,sizeof out);
    assert(rpi5_firmware_seed_derive(seed,63,out+1,256)==-1);
    assert(rpi5_firmware_seed_derive(seed,64,out+1,255)==-1);
    assert(rpi5_firmware_seed_derive(0,64,out+1,256)==-1);
    assert(rpi5_firmware_seed_derive(out,64,out+1,256)==-1);
    memset(seed,0,sizeof seed);
    assert(rpi5_firmware_seed_derive(seed,64,out+1,256)==-1);
    assert(!memcmp(out,saved,sizeof out));
    uint8_t consumed=0;
    for(unsigned i=0;i<64;i++) seed[i]=i;
    assert(rpi5_firmware_seed_consume(seed,63,out+1,256,&consumed)==-1);
    assert(!consumed && seed[1]==1 && !memcmp(out,saved,sizeof out));
    assert(rpi5_firmware_seed_consume(seed,64,out+1,256,seed)==-1);
    assert(rpi5_firmware_seed_consume(seed,64,out+1,256,out+1)==-1);
    assert(!consumed && seed[1]==1 && !memcmp(out,saved,sizeof out));
    assert(!rpi5_firmware_seed_consume(seed,64,out+1,256,&consumed));
    assert(consumed==1 && !memcmp(out+1,expected,256));
    for(unsigned i=0;i<64;i++) assert(seed[i]==0);
    for(unsigned i=0;i<64;i++) seed[i]=i;
    assert(rpi5_firmware_seed_consume(seed,64,out+1,256,&consumed)==-1);
    assert(seed[1]==1 && !memcmp(out+1,expected,256));
    /* Fresh all-zero source fails derivation but is still consumed. */
    consumed=0; memset(seed,0,sizeof seed); memcpy(out,saved,sizeof out);
    assert(rpi5_firmware_seed_consume(seed,64,out+1,256,&consumed)==-1);
    assert(consumed==1 && !memcmp(out,saved,sizeof out));
    /* RFC 5869 test case 1, independently published HKDF-SHA256 output. */
    unsigned char ikm[22],salt[13],info[10],okm[42];
    memset(ikm,0x0b,sizeof ikm);
    for(unsigned i=0;i<13;i++) salt[i]=i;
    for(unsigned i=0;i<10;i++) info[i]=0xf0+i;
    const unsigned char vector[]={
        0x3c,0xb2,0x5f,0x25,0xfa,0xac,0xd5,0x7a,0x90,0x43,0x4f,0x64,0xd0,0x36,
        0x2f,0x2a,0x2d,0x2d,0x0a,0x90,0xcf,0x1a,0x5a,0x4c,0x5d,0xb0,0x2d,0x56,
        0xec,0xc4,0xc5,0xbf,0x34,0x00,0x72,0x08,0xd5,0xb8,0x87,0x18,0x58,0x65};
    br_hkdf_context c;
    br_hkdf_init(&c,&br_sha256_vtable,salt,sizeof salt);
    br_hkdf_inject(&c,ikm,sizeof ikm); br_hkdf_flip(&c);
    assert(br_hkdf_produce(&c,info,sizeof info,okm,sizeof okm)==42);
    assert(!memcmp(okm,vector,42));
}
'''.replace('EXPECTED',expected)
        lib=ROOT/'build/rpi5/bearssl-candidate'
        units=['hash/sha2small.c','codec/dec32be.c','codec/enc32be.c','mac/hmac.c','kdf/hkdf.c']
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I'+str(ROOT/'loader/rpi5'),
                '-I'+str(lib/'inc'),'-I'+str(lib/'src'),str(p/'test.c'),
                str(ROOT/'loader/rpi5/firmware_seed.c'),
                *[str(lib/'src'/u) for u in units],'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
