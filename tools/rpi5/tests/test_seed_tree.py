# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]


class SeedTreeTests(unittest.TestCase):
    def test_collection_preflight_encoding_and_failure(self):
        source=r'''
#include "seed_tree.h"
#include "board_tree.h"
#include <assert.h>
#include <string.h>
static unsigned calls;
static int fail;
static enum rpi5_seed_step read_word(void *p,uint32_t *word) {
    (void)p; ++calls; if (fail && calls==32) return RPI5_SEED_FAULT;
    *word=0x04030201; return RPI5_SEED_WORD;
}
static uint64_t counter(void *p) { (void)p; return 0; }
int main(void) {
    struct rpi5_seed_source provider={0,read_word,counter};
    struct rpi5_adt_property property={"sample","abc",3};
    struct rpi5_adt_node chosen={"chosen",&property,0,1,0};
    const struct rpi5_adt_node *children[]={&chosen};
    struct rpi5_adt_node root={"device-tree",0,children,0,1};
    unsigned char out[4096], expected[4096], seed[256]; size_t n=999,e=0;
    memset(out,0xa5,sizeof out);
    assert(rpi5_seed_tree_encode(&root,&provider,1000,64,out,1,&n)==-1);
    assert(calls==0 && n==999);
    /* Bare tree fits, but adding the seed exceeds this capacity. */
    assert(!rpi5_adt_measure(&root,sizeof out,&e));
    assert(rpi5_seed_tree_encode(&root,&provider,1000,64,out,e,&n)==-1);
    assert(calls==0 && n==999);
    property.name="random-seed";
    assert(rpi5_seed_tree_encode(&root,&provider,1000,64,out,sizeof out,&n)==-1);
    assert(calls==0); property.name="sample";
    chosen.name="other";
    assert(rpi5_seed_tree_encode(&root,&provider,1000,64,out,sizeof out,&n)==-1);
    assert(calls==0); chosen.name="chosen";
    fail=1;
    assert(rpi5_seed_tree_encode(&root,&provider,1000,64,out,sizeof out,&n)==-1);
    assert(calls==32 && n==999);
    for(unsigned i=0;i<sizeof out;i++) assert(out[i]==0xa5);
    calls=0; fail=0;
    assert(!rpi5_seed_tree_encode(&root,&provider,1000,64,out,sizeof out,&n));
    assert(calls==64 && chosen.property_count==1 && chosen.properties==&property);
    for(unsigned i=0;i<256;i++) seed[i]=1+i%4;
    struct rpi5_adt_property props[]={property,{"random-seed",seed,256}};
    chosen.properties=props; chosen.property_count=2;
    assert(!rpi5_adt_encode(&root,expected,sizeof expected,&e));
    assert(e==n && !memcmp(out,expected,n));
    for(size_t i=n;i<sizeof out;i++) assert(out[i]==0xa5);
    struct rpi5_board_tree board;
    const uint64_t ids[]={0,0x100,0x200,0x300};
    struct rpi5_range uart={0x107d001000ull,0x107d001200ull};
    assert(!rpi5_board_tree_init(ids,4,0x200,54000000,uart,0,0x200000000ull,&board));
    assert(board.root.property_count==1 && !strcmp(board.root_props[0].name,"compatible"));
    assert(board.root_props[0].length==35);
    assert(!memcmp(board.root_props[0].data,"raspberrypi,5-model-b\0brcm,bcm2712\0",35));
    assert(board.chosen.child_count==1);
    assert(board.chosen.children[0]==&board.image_memory_map);
    assert(!strcmp(board.image_memory_map.name,"memory-map"));
    assert(board.image_memory_map.property_count==0 && board.image_memory_map.child_count==0);
    unsigned char saved[sizeof board]; memcpy(saved,&board,sizeof board);
    assert(rpi5_board_tree_init(ids,4,0x400,54000000,uart,0,0x200000000ull,&board)==-1);
    assert(rpi5_board_tree_init(ids,4,0,54000000,uart,0,0,&board)==-1);
    assert(rpi5_board_tree_init(ids,4,0,54000000,uart,1ull<<40,1,&board)==-1);
    assert(rpi5_board_tree_init(ids,4,0,54000000,uart,(1ull<<40)-1,2,&board)==-1);
    assert(!memcmp(saved,&board,sizeof board));
    struct rpi5_memory_types types={0};
    memcpy(saved,&board,sizeof board);
    assert(rpi5_board_tree_memory_map(&board,&types)==-1);
    assert(!memcmp(saved,&board,sizeof board));
    types.normal.count=2;
    types.normal.extent[0]=(struct rpi5_range){0,0x3fc00000};
    types.normal.extent[1]=(struct rpi5_range){0x40000000,0x200000000};
    types.device.count=1;
    types.device.extent[0]=(struct rpi5_range){0x107d000000,0x107d004000};
    assert(!rpi5_board_tree_memory_map(&board,&types));
    assert(board.chosen.property_count==3);
    assert(!strcmp(board.chosen_props[2].name,"rpi5-memory-map"));
    assert(board.chosen_props[2].data==board.memory_map && board.chosen_props[2].length==80);
    memcpy(saved,&board,sizeof board);
    calls=0;
    size_t measured=0;
    assert(!rpi5_seed_tree_measure(&board.root,sizeof out,&measured));
    assert(calls==0);
    size_t sentinel=999;
    assert(rpi5_seed_tree_measure(&board.root,measured-1,&sentinel)==-1);
    assert(sentinel==999 && calls==0);
    assert(!rpi5_seed_tree_encode(&board.root,&provider,1000,64,out,sizeof out,&n));
    assert(n==measured);
    assert(calls==64 && !memcmp(saved,&board,sizeof board));
    struct rpi5_adt_property chosen_props[]={board.chosen_props[0],board.chosen_props[1],board.chosen_props[2],
        {"random-seed",seed,256}};
    board.chosen.properties=chosen_props; board.chosen.property_count=4;
    assert(!rpi5_adt_encode(&board.root,expected,sizeof expected,&e));
    assert(e==n && !memcmp(out,expected,n));
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(source)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-I'+str(ROOT/'loader/rpi5'),
                            str(p/'test.c'),*[str(ROOT/'loader/rpi5'/f) for f in
                            ('seed_tree.c','boot_seed.c','apple_dt.c','board_tree.c',
                             'cpu_tree.c','serial_tree.c','memory_type.c')],'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
