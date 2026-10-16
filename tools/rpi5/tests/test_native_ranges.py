# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class NativeRangesTests(unittest.TestCase):
    def test_subtraction_against_byte_oracle(self):
        harness = r'''
#include "ranges.h"
#include <assert.h>
#include <string.h>
static unsigned seed=17;
static unsigned next(void) { seed=seed*1664525u+1013904223u; return seed; }
int main(void) {
    struct rpi5_range ram[2]={{0,96},{128,256}}, excluded[64];
    struct rpi5_ranges out, prior; memset(&prior,0xa5,sizeof prior);
    for (unsigned trial=0;trial<1000;trial++) {
        unsigned n=next()%20;
        for (unsigned i=0;i<n;i++) {
            excluded[i].start=next()%300; excluded[i].end=excluded[i].start+1+next()%80;
        }
        assert(!rpi5_ranges_subtract(ram,2,excluded,n,&out));
        for (unsigned byte=0;byte<300;byte++) {
            int expected=byte<96 || (byte>=128 && byte<256), actual=0;
            for (unsigned i=0;i<n;i++) if (excluded[i].start<=byte && byte<excluded[i].end) expected=0;
            for (size_t i=0;i<out.count;i++) {
                assert(out.extent[i].start<out.extent[i].end);
                if (i) assert(out.extent[i-1].end<=out.extent[i].start);
                if (out.extent[i].start<=byte && byte<out.extent[i].end) actual++;
            }
            assert(actual==expected);
        }
    }
    struct rpi5_range whole={0,100};
    for (unsigned i=0;i<32;i++) excluded[i]=(struct rpi5_range){2*i+1,2*i+2};
    out=prior; assert(rpi5_ranges_subtract(&whole,1,excluded,32,&out)==-1);
    assert(!memcmp(&out,&prior,sizeof out));
    excluded[32]=(struct rpi5_range){0,100};
    assert(!rpi5_ranges_subtract(&whole,1,excluded,33,&out) && !out.count);
    excluded[0]=(struct rpi5_range){4,4}; out=prior;
    assert(rpi5_ranges_subtract(&whole,1,excluded,1,&out)==-1 && !memcmp(&out,&prior,sizeof out));
    struct rpi5_range high={(1ull<<40)-4,1ull<<40};
    assert(!rpi5_ranges_subtract(&high,1,0,0,&out)); assert(out.extent[0].end==1ull<<40);
    high.end++; assert(rpi5_ranges_subtract(&high,1,0,0,&out)==-1);
    ram[1].start=95; assert(rpi5_ranges_subtract(ram,2,0,0,&out)==-1);
    assert(rpi5_ranges_subtract(&whole,1,0,1,&out)==-1);
    out=(struct rpi5_ranges){{{3,50},{64,128}},2};
    struct rpi5_range windows[2]={{70,100},{4,40}}, fit, sentinel={123,456};
    assert(!rpi5_ranges_find(&out,windows,2,16,16,&fit)); assert(fit.start==16 && fit.end==32);
    assert(!rpi5_ranges_find(&out,windows,2,24,8,&fit)); assert(fit.start==8 && fit.end==32);
    fit=sentinel; assert(rpi5_ranges_find(&out,windows,2,33,8,&fit)==-1);
    assert(fit.start==sentinel.start && fit.end==sentinel.end);
    assert(rpi5_ranges_find(&out,windows,2,16,3,&fit)==-1);
    assert(rpi5_ranges_find(&out,windows,2,0,16,&fit)==-1);
    assert(rpi5_ranges_find(&out,windows,0,16,16,&fit)==-1);
    out=(struct rpi5_ranges){{{0,(1ull<<40)}},1}; windows[0]=(struct rpi5_range){0,1ull<<40};
    assert(!rpi5_ranges_find(&out,windows,1,1ull<<40,1,&fit) && fit.start==0 && fit.end==(1ull<<40));
    for (unsigned trial=0;trial<1000;trial++) {
        out=(struct rpi5_ranges){{{0,96},{128,256}},2};
        uint64_t low=next()%256, span=1+next()%100, size=1+next()%50, alignment=1ull<<(next()%6);
        windows[0]=(struct rpi5_range){low,low+span};
        uint64_t expected=UINT64_MAX;
        for (uint64_t address=0;address<256;address++) {
            if (!(address&(alignment-1)) && address>=low && address+size<=low+span &&
                ((address<96 && address+size<=96) || (address>=128 && address+size<=256))) { expected=address; break; }
        }
        int result=rpi5_ranges_find(&out,windows,1,size,alignment,&fit);
        if (expected==UINT64_MAX) assert(result==-1);
        else assert(!result && fit.start==expected && fit.end==expected+size);
    }
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.c").write_text(harness)
            subprocess.run(["xcrun", "clang", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-I" + str(ROOT / "loader/rpi5"), str(path / "test.c"), str(ROOT / "loader/rpi5/ranges.c"), "-o", str(path / "test")], check=True)
            subprocess.run([str(path / "test")], check=True)
