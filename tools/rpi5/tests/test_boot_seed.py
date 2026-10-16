# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class BootSeedTests(unittest.TestCase):
    def test_bounded_atomic_collection(self):
        code = r'''
#include "boot_seed.h"
#include <assert.h>
#include <string.h>
struct state { uint64_t clock; unsigned calls, words, mode; };
static uint64_t clock_read(void *p) {
    struct state *s=p;
    return s->mode==3 ? s->clock : s->clock++;
}
static enum rpi5_seed_step read_word(void *p,uint32_t *word) {
    struct state *s=p; ++s->calls;
    if (s->mode==1 || s->mode==3) return RPI5_SEED_WAIT;
    if (s->mode==2 && s->words==63) return RPI5_SEED_FAULT;
    if (s->mode==4 && s->calls%2) return RPI5_SEED_WAIT;
    if (s->mode==5) return (enum rpi5_seed_step)99;
    *word=s->mode==6 ? 0 : 0x12340000+s->words;
    ++s->words;
    return RPI5_SEED_WORD;
}
int main(void) {
    struct state s={0};
    struct rpi5_seed_source source={&s,read_word,clock_read};
    unsigned char guarded[258], before[258];
    memset(guarded,0xa5,sizeof guarded); memcpy(before,guarded,sizeof before);
    assert(!rpi5_boot_seed_collect(&source,1000,64,guarded+1));
    assert(s.words==64 && guarded[0]==0xa5 && guarded[257]==0xa5);
    for (unsigned i=0;i<64;i++) {
        assert(guarded[1+4*i]==i && guarded[2+4*i]==0);
        assert(guarded[3+4*i]==0x34 && guarded[4+4*i]==0x12);
    }
    for (unsigned mode=0;mode<=6;mode++) {
        s=(struct state){.mode=mode}; memcpy(guarded,before,sizeof before);
        /* Fewer than 64 polls, stalls, partial fault, invalid provider status. */
        size_t budget=mode==0 ? 63 : 100;
        assert(rpi5_boot_seed_collect(&source,1000,budget,guarded+1)==-1);
        assert(!memcmp(guarded,before,sizeof before) && s.calls<=budget);
    }
    s=(struct state){.mode=4};
    assert(!rpi5_boot_seed_collect(&source,1000,128,guarded+1));
    assert(s.calls==128);
    s=(struct state){.clock=UINT64_MAX-20};
    assert(!rpi5_boot_seed_collect(&source,1000,64,guarded+1));
    for (uint64_t ticks=127;ticks<=129;ticks++) {
        s=(struct state){0}; memcpy(guarded,before,sizeof before);
        int status=rpi5_boot_seed_collect(&source,ticks,1000,guarded+1);
        assert(status==(ticks==129 ? 0 : -1));
        if (status) assert(!memcmp(guarded,before,sizeof before));
    }
    s=(struct state){0};
    assert(rpi5_boot_seed_collect(&source,0,64,guarded+1)==-1);
    assert(rpi5_boot_seed_collect(&source,1ull<<63,64,guarded+1)==-1);
    assert(rpi5_boot_seed_collect(&source,1000,0,guarded+1)==-1);
    assert(rpi5_boot_seed_collect(0,1000,64,guarded+1)==-1);
    assert(rpi5_boot_seed_collect(&source,1000,64,0)==-1);
    source.read=0;
    assert(rpi5_boot_seed_collect(&source,1000,64,guarded+1)==-1);
    source.read=read_word; source.counter=0;
    assert(rpi5_boot_seed_collect(&source,1000,64,guarded+1)==-1);
    assert(s.calls==0);
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            unit=ROOT/'loader/rpi5/boot_seed.c'
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-I'+str(unit.parent),
                            str(p/'test.c'),str(unit),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
            subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                            '-ffreestanding','-fno-stack-protector','-O2',
                            '-Wall','-Wextra','-Werror','-c',str(unit),'-o',str(p/'seed.o')],check=True)
