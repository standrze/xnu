# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]


class MemoryTypeTests(unittest.TestCase):
    def test_wire_encoding(self):
        code=r'''
#include "memory_type.h"
#include "../../osfmk/arm64/rpi5_memory_map.h"
#include <assert.h>
#include <string.h>
static uint64_t le(const unsigned char *p,unsigned n) {
    uint64_t v=0; for(unsigned i=0;i<n;i++) v|=(uint64_t)p[i]<<(8*i); return v;
}
int main(void) {
    struct rpi5_memory_types t={0};
    t.normal.count=2;
    t.normal.extent[0]=(struct rpi5_range){0,0x3fc00000};
    t.normal.extent[1]=(struct rpi5_range){0x40000000,0x200000000};
    t.device.count=1;
    t.device.extent[0]=(struct rpi5_range){0x107d000000,0x107d004000};
    unsigned char storage[RPI5_MEMORY_MAP_MAX_BYTES+2];
    memset(storage,0xa5,sizeof(storage));
    unsigned char *b=storage+1; /* Encoding must not require aligned output. */
    size_t n=999;
    assert(!rpi5_memory_types_encode(&t,b,sizeof(storage)-2,&n));
    assert(n==80 && le(b,4)==1 && le(b+4,4)==3);
    assert(le(b+8,8)==1 && le(b+16,8)==0 && le(b+24,8)==0x3fc00000);
    assert(le(b+32,8)==1 && le(b+40,8)==0x40000000 && le(b+48,8)==0x200000000);
    assert(le(b+56,8)==2 && le(b+64,8)==0x107d000000 && le(b+72,8)==0x107d004000);
    assert(storage[0]==0xa5);
    for(size_t i=n+1;i<sizeof(storage);i++) assert(storage[i]==0xa5);
    unsigned char saved[sizeof(storage)]; memcpy(saved,storage,sizeof(storage));
    assert(rpi5_memory_types_encode(&t,b,n-1,&n)==-1);
    assert(n==80 && !memcmp(saved,storage,sizeof(storage)));
    t.device.extent[0].start=0;
    assert(rpi5_memory_types_encode(&t,b,sizeof(storage)-2,&n)==-1);
    assert(n==80 && !memcmp(saved,storage,sizeof(storage)));
    assert(rpi5_memory_types_encode(0,b,sizeof(storage)-2,&n)==-1);
    t.device.count=0;
    assert(rpi5_memory_types_encode(&t,0,100,&n)==-1);
    assert(rpi5_memory_types_encode(&t,b,100,0)==-1);
    t.device.count=3;
    t.device.extent[0]=(struct rpi5_range){0x107d000000,0x107d004000};
    t.device.extent[1]=(struct rpi5_range){0x107d200000,0x107d204000};
    t.device.extent[2]=(struct rpi5_range){0x107fff8000,0x107fffc000};
    assert(!rpi5_memory_types_validate(&t));
    struct rpi5_range swap=t.device.extent[1];
    t.device.extent[1]=t.device.extent[2]; t.device.extent[2]=swap;
    assert(rpi5_memory_types_validate(&t)==-1);
    t.normal.count=32; t.device.count=32;
    for(unsigned i=0;i<32;i++) {
        t.normal.extent[i]=(struct rpi5_range){i*0x4000ull,(i+1)*0x4000ull};
        t.device.extent[i]=(struct rpi5_range){0x100000ull+i*0x4000ull,0x100000ull+(i+1)*0x4000ull};
    }
    assert(!rpi5_memory_types_encode(&t,b,RPI5_MEMORY_MAP_MAX_BYTES,&n));
    assert(n==RPI5_MEMORY_MAP_MAX_BYTES && le(b+4,4)==64);
    struct rpi5_kernel_memory_map decoded={0};
    assert(!rpi5_map_decode(b,n,&decoded));
    assert(decoded.count==64);
    struct rpi5_kernel_memory_map previous=decoded;
    b[0]=2; assert(rpi5_map_decode(b,n,&decoded)==-1); b[0]=1;
    assert(!memcmp(&previous,&decoded,sizeof decoded));
    assert(rpi5_map_decode(b,n-1,&decoded)==-1);
    b[8]=3; assert(rpi5_map_decode(b,n,&decoded)==-1); b[8]=1;
    b[16]=1; assert(rpi5_map_decode(b,n,&decoded)==-1); b[16]=0;
    assert(!memcmp(&previous,&decoded,sizeof decoded));
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            unit=ROOT/'loader/rpi5/memory_type.c'
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-I'+str(unit.parent),
                            str(p/'test.c'),str(unit),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)

    def test_exhaustive_small_maps(self):
        # Independent page-label oracle: every six-page assignment of unknown,
        # normal and device memory, including adjacent unmerged extents.
        code=r'''
#include "memory_type.h"
#include "../../osfmk/arm64/rpi5_memory_map.h"
#include <assert.h>
int main(void) {
    const uint64_t page=0x4000;
    for (unsigned map=0; map<729; ++map) {
        unsigned labels[6], digits=map, normal=0;
        struct rpi5_memory_types t={0};
        for (unsigned i=0; i<6; ++i) {
            labels[i]=digits%3; digits/=3;
            struct rpi5_ranges *r=0;
            if (labels[i]==1) { r=&t.normal; ++normal; }
            if (labels[i]==2) r=&t.device;
            if (r) r->extent[r->count++]=(struct rpi5_range){i*page,(i+1)*page};
        }
        assert((rpi5_memory_types_validate(&t)==0)==(normal!=0));
        struct rpi5_kernel_memory_map kernel={0};
        unsigned char wire[RPI5_MEMORY_MAP_MAX_BYTES]; size_t bytes=0;
        if(normal) {
            assert(!rpi5_memory_types_encode(&t,wire,sizeof wire,&bytes));
            assert(!rpi5_map_decode(wire,bytes,&kernel));
        }
        /* Half-page endpoints exercise aligned and unaligned queries, plus
         * the page beyond the supplied map. Oracle uses labels, not ranges. */
        for (unsigned start=0; start<14; ++start)
            for (unsigned end=start+1; end<=14; ++end) {
                unsigned expected=normal && start/2<6 ? labels[start/2] : 0;
                for (unsigned i=start/2; i<=(end-1)/2; ++i)
                    if (i>=6 || labels[i]!=expected) expected=0;
                assert((unsigned)rpi5_memory_type_for(&t,
                    (struct rpi5_range){start*(page/2),end*(page/2)})==expected);
                assert(rpi5_map_type(&kernel,start*(page/2),end*(page/2))==expected);
            }
    }
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            unit=ROOT/'loader/rpi5/memory_type.c'
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-I'+str(unit.parent),
                            str(p/'test.c'),str(unit),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)

    def test_holes_boundaries_and_overlap(self):
        code=r'''
#include "memory_type.h"
#include <assert.h>
int main(void) {
    struct rpi5_memory_types t={0};
    t.normal.count=3;
    t.normal.extent[0]=(struct rpi5_range){0,0x8000};
    t.normal.extent[1]=(struct rpi5_range){0x8000,0x10000};
    t.normal.extent[2]=(struct rpi5_range){0x20000,0x24000};
    t.device.count=1;
    t.device.extent[0]=(struct rpi5_range){0x30000,0x34000};
    assert(!rpi5_memory_types_validate(&t));
    assert(rpi5_memory_type_for(&t,(struct rpi5_range){0,0x10000})==RPI5_MEMORY_NORMAL);
    assert(rpi5_memory_type_for(&t,(struct rpi5_range){0x30001,0x30002})==RPI5_MEMORY_DEVICE);
    assert(rpi5_memory_type_for(&t,(struct rpi5_range){0x10000,0x10001})==RPI5_MEMORY_UNKNOWN);
    assert(rpi5_memory_type_for(&t,(struct rpi5_range){0xffff,0x10001})==RPI5_MEMORY_UNKNOWN);
    assert(rpi5_memory_type_for(&t,(struct rpi5_range){0,0x24000})==RPI5_MEMORY_UNKNOWN);
    assert(rpi5_memory_type_for(&t,(struct rpi5_range){0x20000,0x34000})==RPI5_MEMORY_UNKNOWN);
    assert(rpi5_memory_type_for(&t,(struct rpi5_range){0,0})==RPI5_MEMORY_UNKNOWN);
    assert(rpi5_memory_type_for(&t,(struct rpi5_range){1ull<<40,UINT64_MAX})==RPI5_MEMORY_UNKNOWN);
    t.device.extent[0]=(struct rpi5_range){0xc000,0x14000};
    assert(rpi5_memory_types_validate(&t)==-1);
    assert(rpi5_memory_type_for(&t,(struct rpi5_range){0,1})==RPI5_MEMORY_UNKNOWN);
    t.device.count=0;
    t.normal.extent[1].start=0x4000; assert(rpi5_memory_types_validate(&t)==-1);
    t.normal.extent[1].start=0x8001; assert(rpi5_memory_types_validate(&t)==-1);
    t.normal.extent[1].start=0x8000;
    t.normal.extent[2]=(struct rpi5_range){(1ull<<40)-0x4000,1ull<<40};
    assert(!rpi5_memory_types_validate(&t));
    assert(rpi5_memory_type_for(&t,(struct rpi5_range){(1ull<<40)-1,1ull<<40})==RPI5_MEMORY_NORMAL);
    t.normal.count=33; assert(rpi5_memory_types_validate(&t)==-1);
    t.normal.count=0; assert(rpi5_memory_types_validate(&t)==-1);
    assert(rpi5_memory_types_validate(0)==-1);
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            unit=ROOT/'loader/rpi5/memory_type.c'
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-I'+str(unit.parent),
                            str(p/'test.c'),str(unit),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
