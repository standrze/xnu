# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]
class Poly1305Tests(unittest.TestCase):
    def test_padded_segments(self):
        key=bytes(range(32))
        r=int.from_bytes(key[:16],'little') & 0x0ffffffc0ffffffc0ffffffc0fffffff
        expected=[]
        for n in range(66):
            data=bytes(range(n)); data+=bytes((-len(data))%16)
            acc=0
            for offset in range(0,len(data),16):
                acc=((acc+int.from_bytes(data[offset:offset+16]+b'\x01','little'))*r)%((1<<130)-5)
            tag=((acc+int.from_bytes(key[16:],'little'))% (1<<128)).to_bytes(16,'little')
            expected.append('{'+','.join(map(str,tag))+'}')
        source=r'''
#include "rpi5_poly1305.h"
#include <assert.h>
#include <string.h>
int main(void) {
    const unsigned char expected[66][16]={EXPECTED};
    unsigned char key[32],data[65],tag[18];
    for(unsigned i=0;i<32;i++) key[i]=(unsigned char)i;
    for(unsigned i=0;i<65;i++) data[i]=(unsigned char)i;
    for(size_t n=0;n<=65;n++) for(size_t split=0;split<=n;split++) {
        struct rpi5_poly1305 s;
        rpi5_poly1305_init(&s,key);
        rpi5_poly1305_update(&s,data,split);
        rpi5_poly1305_update(&s,data+split,n-split);
        rpi5_poly1305_pad(&s); rpi5_poly1305_pad(&s);
        memset(tag,0xa5,sizeof tag); rpi5_poly1305_final(&s,tag+1);
        assert(!memcmp(tag+1,expected[n],16) && tag[0]==0xa5 && tag[17]==0xa5);
        for(size_t i=0;i<sizeof s;i++) assert(!((unsigned char *)&s)[i]);
    }
}
'''.replace('EXPECTED',','.join(expected))
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory); (p/'test.c').write_text(source)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                '-I'+str(ROOT/'osfmk/prng'),str(p/'test.c'),
                str(ROOT/'osfmk/prng/rpi5_poly1305.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True,timeout=15)
