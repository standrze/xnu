from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]

class BootDataTests(unittest.TestCase):
    def test_copy_and_preflight(self):
        code=r'''
#include "boot_data.h"
#include <assert.h>
#include <string.h>
int main(void) {
    uint8_t a[1152],t[1684],ad[1154],td[1686];
    for(unsigned i=0;i<1152;i++) a[i]=i;
    for(unsigned i=0;i<1684;i++) t[i]=i*3;
    memset(ad,0xa5,sizeof ad); memset(td,0xa5,sizeof td);
    assert(!rpi5_boot_data_publish(a,t,sizeof t,ad+1,td+1));
    assert(!memcmp(a,ad+1,sizeof a) && !memcmp(t,td+1,sizeof t));
    assert(ad[0]==0xa5 && ad[1153]==0xa5 && td[0]==0xa5 && td[1685]==0xa5);
    memset(ad,0xa5,sizeof ad); memset(td,0xa5,sizeof td);
    assert(rpi5_boot_data_publish(a,t,0,ad+1,td+1)==-1);
    assert(rpi5_boot_data_publish(a,t,(1u<<24)+1,ad+1,td+1)==-1);
    assert(rpi5_boot_data_publish(a,t,sizeof t,a,td+1)==-1);
    assert(rpi5_boot_data_publish(a,t,sizeof t,ad+1,t)==-1);
    assert(rpi5_boot_data_publish(a,t,sizeof t,td,td+1)==-1);
    assert(rpi5_boot_data_publish(a,a,sizeof a,ad+1,td+1)==-1);
    assert(rpi5_boot_data_publish(0,t,sizeof t,ad+1,td+1)==-1);
    assert(rpi5_boot_data_publish(a,t,sizeof t,(void *)(UINTPTR_MAX-10),td+1)==-1);
    for(unsigned i=0;i<sizeof ad;i++) assert(ad[i]==0xa5);
    for(unsigned i=0;i<sizeof td;i++) assert(td[i]==0xa5);
    uint8_t scratch[2048],saved[2048];
    memset(scratch,0x73,sizeof scratch); memcpy(scratch,t,sizeof t);
    memcpy(saved,scratch,sizeof scratch);
    assert(rpi5_boot_data_commit(a,scratch,sizeof t,sizeof t-1,ad+1,td+1)==-1);
    assert(!memcmp(scratch,saved,sizeof scratch));
    /* Encoded data itself is disjoint, but the full wipe capacity overlaps. */
    assert(rpi5_boot_data_commit(a,scratch,16,sizeof scratch,ad+1,scratch+1024)==-1);
    assert(!memcmp(scratch,saved,sizeof scratch));
    for(unsigned i=0;i<sizeof ad;i++) assert(ad[i]==0xa5);
    for(unsigned i=0;i<sizeof td;i++) assert(td[i]==0xa5);
    assert(!rpi5_boot_data_commit(a,scratch,sizeof t,sizeof scratch,ad+1,td+1));
    assert(!memcmp(a,ad+1,sizeof a) && !memcmp(t,td+1,sizeof t));
    for(unsigned i=0;i<sizeof scratch;i++) assert(!scratch[i]);
    assert(ad[0]==0xa5 && ad[1153]==0xa5 && td[0]==0xa5 && td[1685]==0xa5);
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I'+str(ROOT/'loader/rpi5'),str(p/'test.c'),
                str(ROOT/'loader/rpi5/boot_data.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
