# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_handoff import image
ROOT=Path(__file__).resolve().parents[3]


class TreeHandoffTests(unittest.TestCase):
    def test_derived_length_and_atomic_rejection(self):
        source=(ROOT/'loader/rpi5/probe_main.c').read_text()
        command_setup=source[source.index('    const char *command_line='):source.index('    if (rpi5_resolved_tree_handoff(')]
        code=r'''
#include "tree_handoff.h"
#include "board_tree.h"
#include <assert.h>
#include <string.h>
'''+ 'static const unsigned char image[]={'+','.join(map(str,image()))+'};\n'+r'''
int main(void) {
    struct rpi5_board_tree tree;
    const uint64_t ids[]={0};
    struct rpi5_range uart={0x107d001000ull,0x107d001200ull};
    assert(!rpi5_board_tree_init(ids,1,0,54000000,uart,0,0x200000000ull,&tree));
    struct rpi5_handoff_input input={0x3004000,0x2000000,0xe000000,0x200000000ull,
        0x3008000,0x300c000,{0x2000000,0x10000000},0};
    struct rpi5_range live={0x6000000,0x7000000};
    struct rpi5_handoff_plan plan;
    size_t length;
    assert(!rpi5_seed_tree_measure(&tree.root,4096,&length));
    assert(!rpi5_tree_handoff_plan(image,sizeof image,&input,&tree.root,4096,
        &live,1,"-v",2,&plan));
    uint32_t encoded=0;
    for(unsigned i=0;i<4;i++) encoded|=(uint32_t)plan.args[104+i]<<(8*i);
    assert(encoded==length && input.tree_length==0);
    unsigned char prior[sizeof plan]; memcpy(prior,&plan,sizeof plan);
    assert(rpi5_tree_handoff_plan(image,sizeof image,&input,&tree.root,length-1,
        &live,1,"-v",2,&plan)==-1);
    input.tree_length=1;
    assert(rpi5_tree_handoff_plan(image,sizeof image,&input,&tree.root,4096,
        &live,1,"-v",2,&plan)==-1);
    input.tree_length=0; input.tree_pa=live.start;
    assert(rpi5_tree_handoff_plan(image,sizeof image,&input,&tree.root,4096,
        &live,1,"-v",2,&plan)==-1);
    assert(!memcmp(prior,&plan,sizeof plan));
    input.tree_pa=0x300c000; input.usable=(struct rpi5_range){0,0};
    struct rpi5_fdt_memory memory={0};
    memory.count=1; memory.start[0]=0; memory.end[0]=0x40000000;
    struct rpi5_reservation_plan reservations={0};
    reservations.fixed.count=1;
    reservations.fixed.extent[0]=(struct rpi5_range){0,0x80000};
    struct rpi5_resolved_reservations resolved;
    struct rpi5_memory_types types={0};
    types.normal.count=1;
    types.normal.extent[0]=(struct rpi5_range){0x2000000,0x10000000};
    assert(!rpi5_resolve_reservations(&memory,&reservations,&live,1,&resolved));
    assert(!rpi5_resolved_tree_handoff(image,sizeof image,&input,&resolved,&types,
        &tree.root,4096,&live,1,"-v",2,&plan));
    assert(!memcmp(prior,&plan,sizeof plan));
    /* Exercise the production command selection/length, not just its spelling. */
    for (int transfer=0;transfer<2;transfer++) {
    for (int with_init=0;with_init<2;with_init++) {
        const void *validated_init=with_init ? image : 0;
#define RPI5_XNU_TRANSFER transfer
'''+command_setup+r'''
#undef RPI5_XNU_TRANSFER
        struct rpi5_handoff_plan console_plan;
        assert(!rpi5_resolved_tree_handoff(image,sizeof image,&input,&resolved,&types,
            &tree.root,4096,&live,1,command_line,command_length,&console_plan));
        assert(!strcmp((const char *)console_plan.args+108,
            transfer ? (with_init ?
                "serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release" :
                "serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress") : ""));
    }
    }
    /* Reservation-free space must still have a proven normal-memory type.
     * A hole beyond live allocations also invalidates the managed extent. */
    types.normal.extent[0].end=0xf000000;
    assert(rpi5_resolved_tree_handoff(image,sizeof image,&input,&resolved,&types,
        &tree.root,4096,&live,1,"-v",2,&plan)==-1);
    types.device.count=1;
    types.device.extent[0]=(struct rpi5_range){0xf000000,0x10000000};
    assert(rpi5_resolved_tree_handoff(image,sizeof image,&input,&resolved,&types,
        &tree.root,4096,&live,1,"-v",2,&plan)==-1);
    assert(rpi5_resolved_tree_handoff(image,sizeof image,&input,&resolved,0,
        &tree.root,4096,&live,1,"-v",2,&plan)==-1);
    assert(!memcmp(prior,&plan,sizeof plan));
    types.device.count=0; types.normal.extent[0].end=0x10000000;
    /* Managed RAM is normal, but block rounding reaches below it. Check
     * rejection after the inner planner succeeds, without publishing output. */
    input.phys_base+=0x4000; input.mem_size-=0x4000;
    types.normal.extent[0].start=input.phys_base;
    struct rpi5_handoff_input rounded=input;
    rounded.usable=resolved.reservation_free.extent[0];
    struct rpi5_handoff_plan inner;
    assert(!rpi5_tree_handoff_plan(image,sizeof image,&rounded,&tree.root,4096,
        &live,1,"-v",2,&inner));
    assert(inner.mapping.physical_start<types.normal.extent[0].start);
    assert(rpi5_resolved_tree_handoff(image,sizeof image,&input,&resolved,&types,
        &tree.root,4096,&live,1,"-v",2,&plan)==-1);
    assert(!memcmp(prior,&plan,sizeof plan));
    input.phys_base-=0x4000; input.mem_size+=0x4000;
    types.normal.extent[0].start=input.phys_base;
    /* A foreign reservation splits the mapping extent; never bridge it. */
    reservations.fixed.extent[1]=(struct rpi5_range){0x4000000,0x4400000};
    reservations.fixed.count=2;
    assert(!rpi5_resolve_reservations(&memory,&reservations,&live,1,&resolved));
    assert(rpi5_resolved_tree_handoff(image,sizeof image,&input,&resolved,&types,
        &tree.root,4096,&live,1,"-v",2,&plan)==-1);
    assert(!memcmp(prior,&plan,sizeof plan));
    resolved.reservation_free.count=33;
    assert(rpi5_resolved_tree_handoff(image,sizeof image,&input,&resolved,&types,
        &tree.root,4096,&live,1,"-v",2,&plan)==-1);
    input.usable=(struct rpi5_range){0x2000000,0x10000000};
    assert(rpi5_resolved_tree_handoff(image,sizeof image,&input,&resolved,&types,
        &tree.root,4096,&live,1,"-v",2,&plan)==-1);
    assert(!memcmp(prior,&plan,sizeof plan));
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            units=('tree_handoff.c','board_tree.c','cpu_tree.c','serial_tree.c',
                   'seed_tree.c','boot_seed.c','apple_dt.c','handoff.c','macho.c',
                   'ranges.c','reservations.c','bootstrap.c','boot_args.c','memory_type.c')
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-I'+str(ROOT/'loader/rpi5'),
                            str(p/'test.c'),*[str(ROOT/'loader/rpi5'/x) for x in units],
                            '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
