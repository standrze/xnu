# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class NativeMachOTests(unittest.TestCase):
    def test_materialized_readback(self):
        harness = r'''
#include "macho.h"
#include <assert.h>
#include <string.h>
static void put(unsigned char *p,uint64_t v,unsigned n) {
    for(unsigned i=0;i<n;i++) p[i]=(unsigned char)(v>>(i*8));
}
int main(void) {
    unsigned char image[512]={0}, target[0x4000]={0};
    uint64_t link=0xfffffe0007004000ull, pa=0x7004000;
    put(image,0xfeedfacf,4); put(image+4,0x100000c,4); put(image+12,2,4);
    put(image+16,2,4); put(image+20,360,4);
    put(image+32,0x19,4); put(image+36,72,4); memcpy(image+40,"__TEXT",6);
    put(image+56,link,8); put(image+64,1024,8); put(image+80,512,8);
    put(image+88,5,4); put(image+92,5,4);
    put(image+104,5,4); put(image+108,288,4); put(image+112,6,4); put(image+116,68,4);
    put(image+376,link+400,8);
    memcpy(target,image,sizeof image);
    assert(!rpi5_macho_verify_materialized(image,sizeof image,target,sizeof target,pa));
    const unsigned corrupt[]={0,400,511,512,1023,1024,16383};
    for(unsigned i=0;i<sizeof corrupt/sizeof *corrupt;i++) {
        target[corrupt[i]]^=1;
        assert(rpi5_macho_verify_materialized(image,sizeof image,target,sizeof target,pa)==-1);
        target[corrupt[i]]^=1;
    }
    assert(rpi5_macho_verify_materialized(image,sizeof image,target,sizeof target-1,pa)==-1);
    assert(rpi5_macho_verify_materialized(image,sizeof image,image,sizeof image,pa)==-1);
    assert(rpi5_macho_verify_materialized(0,sizeof image,target,sizeof target,pa)==-1);
    assert(rpi5_macho_verify_materialized(image,sizeof image,target,sizeof target,UINT64_MAX)==-1);
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(harness)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I'+str(ROOT/'loader/rpi5'),
                str(p/'test.c'),str(ROOT/'loader/rpi5/macho.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)

    def test_command_framing(self):
        harness = r'''
#include "macho.h"
#include <assert.h>
#include <string.h>
static void put(unsigned char *p,unsigned v) {
    for(unsigned i=0;i<4;i++) p[i]=(unsigned char)(v>>(i*8));
}
int main(void) {
    unsigned char image[104]={0};
    put(image,0xfeedfacf); put(image+4,0x100000c); put(image+12,2);
    put(image+16,1); put(image+20,72); put(image+32,0x19); put(image+36,72);
    struct rpi5_macho_commands out, prior={99,98,97};
    assert(!rpi5_macho_commands(image,sizeof image,&out));
    assert(out.count==1 && out.bytes==72 && !out.flags);
    for(unsigned n=0;n<sizeof image;n++) {
        out=prior;
        assert(rpi5_macho_commands(image,n,&out)==-1 && !memcmp(&out,&prior,sizeof out));
    }
    put(image+96,1); assert(rpi5_macho_commands(image,sizeof image,&out)==-1); put(image+96,0);
    put(image+32,0x80000028); assert(rpi5_macho_commands(image,sizeof image,&out)==-1);
    put(image+32,0x19); put(image+36,0xfffffff8);
    assert(rpi5_macho_commands(image,sizeof image,&out)==-1);
    put(image+36,72); put(image+8,2);
    assert(rpi5_macho_commands(image,sizeof image,&out)==-1);
    put(image+8,0); put(image+16,2);
    assert(rpi5_macho_commands(image,sizeof image,&out)==-1);
    /* Two UUID commands are individually framed but duplicate singletons. */
    put(image+20,48); put(image+32,0x1b); put(image+36,24);
    put(image+56,0x1b); put(image+60,24);
    assert(rpi5_macho_commands(image,sizeof image,&out)==-1);
    unsigned char kernel[512]={0};
    put(kernel,0xfeedfacf); put(kernel+4,0x100000c); put(kernel+12,2);
    put(kernel+16,2); put(kernel+20,360);
    put(kernel+32,0x19); put(kernel+36,72); memcpy(kernel+40,"__TEXT",6);
    put(kernel+56,0x1000); put(kernel+64,512); put(kernel+80,512);
    put(kernel+88,5); put(kernel+92,5);
    put(kernel+104,5); put(kernel+108,288); put(kernel+112,6); put(kernel+116,68);
    put(kernel+376,0x1190);
    struct rpi5_macho_segments segments, saved;
    assert(!rpi5_macho_segments(kernel,sizeof kernel,&segments));
    assert(segments.count==1 && segments.entry==0x1190 && segments.segment[0].filesize==512);
    memset(&saved,0xa5,sizeof saved); segments=saved;
    put(kernel+376,0x11fc); /* Last complete instruction is valid. */
    assert(!rpi5_macho_segments(kernel,sizeof kernel,&segments));
    for (unsigned tail=1;tail<4;tail++) {
        put(kernel+80,508+tail); segments=saved;
        assert(rpi5_macho_segments(kernel,sizeof kernel,&segments)==-1 && !memcmp(&segments,&saved,sizeof saved));
    }
    put(kernel+80,512); segments=saved;
    put(kernel+376,0x1200); /* Entry cannot point into zero-fill/outside file bytes. */
    assert(rpi5_macho_segments(kernel,sizeof kernel,&segments)==-1 && !memcmp(&segments,&saved,sizeof saved));
    put(kernel+376,0x1191); assert(rpi5_macho_segments(kernel,sizeof kernel,&segments)==-1);
    put(kernel+376,0x1190); put(kernel+92,1);
    assert(rpi5_macho_segments(kernel,sizeof kernel,&segments)==-1);
    put(kernel+92,5); put(kernel+80,513);
    assert(rpi5_macho_segments(kernel,sizeof kernel,&segments)==-1);
    put(kernel+80,512); put(kernel+60,0xffffffff); put(kernel+56,0xffffff00);
    assert(rpi5_macho_segments(kernel,sizeof kernel,&segments)==-1);
    unsigned char symbols[160]={0};
    put(symbols,0xfeedfacf); put(symbols+4,0x100000c); put(symbols+12,2);
    put(symbols+16,2); put(symbols+20,104);
    put(symbols+32,2); put(symbols+36,24);
    put(symbols+40,136); put(symbols+44,1); put(symbols+48,152); put(symbols+52,8);
    put(symbols+56,0xb); put(symbols+60,80); put(symbols+68,1);
    symbols[140]=0x0e; memcpy(symbols+152,"name",5);
    assert(!rpi5_macho_symbols(symbols,sizeof symbols));
    symbols[140]=1; assert(rpi5_macho_symbols(symbols,sizeof symbols)==-1); symbols[140]=0x0e;
    put(symbols+136,8); assert(rpi5_macho_symbols(symbols,sizeof symbols)==-1); put(symbols+136,0);
    memset(symbols+152,'x',8); assert(rpi5_macho_symbols(symbols,sizeof symbols)==-1); symbols[159]=0;
    assert(!rpi5_macho_symbols(symbols,sizeof symbols));
    put(symbols+84,1); assert(rpi5_macho_symbols(symbols,sizeof symbols)==-1); put(symbols+84,0);
    put(symbols+124,1); assert(rpi5_macho_symbols(symbols,sizeof symbols)==-1); put(symbols+124,0);
    put(symbols+44,0xffffffff); assert(rpi5_macho_symbols(symbols,sizeof symbols)==-1);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.c").write_text(harness)
            subprocess.run(["xcrun", "clang", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", "-I"+str(ROOT/"loader/rpi5"),
                            str(path/"test.c"), str(ROOT/"loader/rpi5/macho.c"),
                            "-o", str(path/"test")], check=True)
            subprocess.run([str(path/"test")], check=True)
