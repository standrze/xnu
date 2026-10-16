# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]


class ResolverTests(unittest.TestCase):
    def test_observed_8gb_linux_reservation_geometry(self):
        # Decoded observations, not a firmware DTB or approved boot placement.
        # Source: docs/rpi5/BOARD-BASELINE-2026-09-06.md.
        harness=r'''
#include "fdt.h"
#include <assert.h>
int main(void) {
    struct rpi5_fdt_memory ram={
        {0,0x40000000,0x100000000ull},
        {0x3fc00000,0x100000000ull,0x200000000ull},3};
    struct rpi5_reservation_plan plan={0};
    plan.fixed.extent[0]=(struct rpi5_range){0,0x80000};
    /* Enabled firmware config lies in the hole between advertised banks. */
    plan.fixed.extent[1]=(struct rpi5_range){0x3fd235c0,0x3fd235f8};
    plan.fixed.count=2;
    plan.count=1;
    plan.request[0].size=0x4000000;
    plan.request[0].alignment=1; /* No alignment property observed. */
    plan.request[0].window[0]=(struct rpi5_range){0,0x40000000};
    plan.request[0].window_count=1;
    struct rpi5_resolved_reservations out;
    assert(!rpi5_resolve_reservations(&ram,&plan,0,0,&out));
    assert(out.count==1 && out.allocation[0].start>=0x80000);
    assert(out.allocation[0].end-out.allocation[0].start==0x4000000);
    assert(out.allocation[0].end<=0x3fc00000);
    int high=0;
    for (unsigned i=0;i<out.available.count;i++) {
        struct rpi5_range r=out.available.extent[i];
        assert(r.start>=0x80000 && r.end<=0x200000000ull);
        assert(r.end<=0x3fc00000 || r.start>=0x40000000);
        assert(r.end<=out.allocation[0].start || r.start>=out.allocation[0].end);
        if(r.end==0x200000000ull) high=1;
    }
    assert(high); /* Do not truncate the 8 GB SKU to a 32-bit address space. */
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory); (path/"test.c").write_text(harness)
            subprocess.run(["xcrun","clang","-Wall","-Wextra","-Werror","-fsanitize=address,undefined","-I"+str(ROOT/"loader/rpi5"),str(path/"test.c"),str(ROOT/"loader/rpi5/ranges.c"),str(ROOT/"loader/rpi5/reservations.c"),"-o",str(path/"test")],check=True)
            subprocess.run([str(path/"test")],check=True)

    def test_sequential_exclusion_and_atomic_failure(self):
        harness=r'''
#include "fdt.h"
#include <assert.h>
#include <string.h>
int main(void) {
    struct rpi5_range banks[]={{0x80000,0x88000},{0x88000,0x100000}};
    struct rpi5_range images[]={{0x84000,0x8c000},{0x90000,0x91000}};
    assert(!rpi5_ranges_validate_live(banks,2,images,2));
    banks[1].start++; /* A one-byte RAM hole must not be bridged. */
    assert(rpi5_ranges_validate_live(banks,2,images,2)==-1);
    banks[1].start=0x88000;
    images[1].start=0x8bfff;
    assert(rpi5_ranges_validate_live(banks,2,images,2)==-1);
    images[1].start=0x8c000; /* Touching endpoints do not overlap. */
    assert(!rpi5_ranges_validate_live(banks,2,images,2));
    images[1].end=0x100001;
    assert(rpi5_ranges_validate_live(banks,2,images,2)==-1);
    images[1].end=images[1].start;
    assert(rpi5_ranges_validate_live(banks,2,images,2)==-1);
    assert(rpi5_ranges_validate_live(banks,2,0,1)==-1);
    /* Probe, FDT, foreign initrd: no overlap or uncovered RAM is acceptable. */
    struct rpi5_range inputs[]={{0x80000,0x84000},{0x84000,0x85000},{0x88000,0x90000}};
    assert(!rpi5_ranges_validate_live(banks,2,inputs,3));
    inputs[2].start=0x83fff;
    assert(rpi5_ranges_validate_live(banks,2,inputs,3)==-1);
    inputs[2].start=0x84fff;
    assert(rpi5_ranges_validate_live(banks,2,inputs,3)==-1);
    inputs[2]=(struct rpi5_range){0xfffff,0x100001};
    assert(rpi5_ranges_validate_live(banks,2,inputs,3)==-1);
    struct rpi5_fdt_memory ram={{0},{0x100000},1};
    struct rpi5_reservation_plan plan={0};
    plan.fixed.extent[0]=(struct rpi5_range){0,0x80000}; plan.fixed.count=1;
    struct rpi5_range live={0x80000,0x84000};
    plan.count=2;
    for(unsigned i=0;i<2;i++) {
        plan.request[i].size=0x4000; plan.request[i].alignment=0x4000;
        plan.request[i].window[0]=(struct rpi5_range){0,0x100000}; plan.request[i].window_count=1;
    }
    struct rpi5_resolved_reservations out,prior; memset(&prior,0xa5,sizeof prior);
    assert(!rpi5_resolve_reservations(&ram,&plan,&live,1,&out));
    assert(out.count==2 && out.allocation[0].start==0x84000 && out.allocation[1].start==0x88000);
    assert(out.available.count==1 && out.available.extent[0].start==0x8c000);
    assert(out.reservation_free.count==2 &&
        out.reservation_free.extent[0].start==0x80000 &&
        out.reservation_free.extent[0].end==0x84000 &&
        out.reservation_free.extent[1].start==0x8c000 &&
        out.reservation_free.extent[1].end==0x100000);
    /* Firmware belongs in fixed; probe image/stacks and FDT remain live. */
    struct rpi5_range runtime_live[]={{0x80000,0x84000},{0x84000,0x85000}};
    assert(!rpi5_resolve_reservations(&ram,&plan,runtime_live,2,&out));
    assert(out.allocation[0].start==0x88000 && out.allocation[1].start==0x8c000);
    assert(out.available.count==2 && out.available.extent[0].start==0x85000 &&
        out.available.extent[0].end==0x88000 && out.available.extent[1].start==0x90000);
    assert(out.reservation_free.count==2 && out.reservation_free.extent[0].start==0x80000 &&
        out.reservation_free.extent[0].end==0x88000 && out.reservation_free.extent[1].start==0x90000);
    /* Overlapping firmware/FDT fixed exclusions are legal, never resurrected. */
    plan.fixed.extent[1]=(struct rpi5_range){0,0x40000}; plan.fixed.count=2;
    assert(!rpi5_resolve_reservations(&ram,&plan,runtime_live,2,&out));
    assert(out.reservation_free.extent[0].start==0x80000);
    assert(!rpi5_ranges_validate_live(out.reservation_free.extent,
        out.reservation_free.count,runtime_live,2));
    /* Arithmetic subtraction itself need not reject this map. The runtime
     * must separately reject a live probe overlapping a foreign exclusion. */
    plan.fixed.extent[1]=(struct rpi5_range){0x81000,0x82000};
    assert(!rpi5_resolve_reservations(&ram,&plan,runtime_live,2,&out));
    assert(rpi5_ranges_validate_live(out.reservation_free.extent,
        out.reservation_free.count,runtime_live,2)==-1);
    plan.fixed.count=1;
    plan.request[1].size=0x100000; out=prior;
    assert(rpi5_resolve_reservations(&ram,&plan,&live,1,&out)==-1 && !memcmp(&out,&prior,sizeof out));
    plan.request[1].size=0x4000; plan.request[0].window[0].end=0x80000;
    assert(rpi5_resolve_reservations(&ram,&plan,&live,1,&out)==-1);
    plan.count=0; assert(!rpi5_resolve_reservations(&ram,&plan,&live,1,&out));
    assert(!out.count && out.available.extent[0].start==0x84000);
    assert(out.reservation_free.count==1 && out.reservation_free.extent[0].start==0x80000);
    live.end=live.start; out=prior;
    assert(rpi5_resolve_reservations(&ram,&plan,&live,1,&out)==-1 && !memcmp(&out,&prior,sizeof out));
    plan.count=9; assert(rpi5_resolve_reservations(&ram,&plan,0,0,&out)==-1);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory); (path/"test.c").write_text(harness)
            subprocess.run(["xcrun","clang","-Wall","-Wextra","-Werror","-fsanitize=address,undefined","-I"+str(ROOT/"loader/rpi5"),str(path/"test.c"),str(ROOT/"loader/rpi5/ranges.c"),str(ROOT/"loader/rpi5/reservations.c"),"-o",str(path/"test")],check=True)
            subprocess.run([str(path/"test")],check=True)
