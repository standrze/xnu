from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]

class FirmwareSeedTreeTests(unittest.TestCase):
    def test_transaction_order_and_cleanup(self):
        code=r'''
#include "firmware_seed_tree.h"
#include "seed_tree.h"
#include <assert.h>
#include <string.h>
static unsigned mode,calls,base_count;
static struct rpi5_board_tree tree;
int rpi5_seed_tree_measure(const struct rpi5_adt_node *r,size_t n,size_t *out) {
    assert(r==&tree.root); if(mode==1 || n<100) return -1; *out=100; return 0;
}
static int consume(uint8_t *s,size_t n,uint8_t *o,size_t l,uint8_t *used) {
    assert(n==64 && l==256); calls++; *used=1; memset(s,0,n);
    memset(o,0x5a,l); return mode==2?-1:0;
}
int rpi5_adt_encode(const struct rpi5_adt_node *r,void *o,size_t n,size_t *written) {
    assert(r==&tree.root && n>=100 && tree.chosen.property_count==base_count+1);
    if(base_count==3) assert(!strcmp(tree.chosen.properties[2].name,"rpi5-memory-map"));
    const struct rpi5_adt_property *p=&tree.chosen.properties[base_count];
    assert(!strcmp(p->name,"random-seed") && p->length==256);
    for(unsigned i=0;i<256;i++) assert(((const uint8_t *)p->data)[i]==0x5a);
    memset(o,0x5a,100); *written=mode==4?99:100; return mode==3?-1:0;
}
int main(void) {
    for(base_count=2;base_count<=3;base_count++) for(mode=0;mode<5;mode++) {
        tree.chosen.properties=tree.chosen_props; tree.chosen.property_count=base_count;
        tree.chosen_props[2]=(struct rpi5_adt_property){"rpi5-memory-map",0,0};
        uint8_t seed[64],used=0,output[102]; size_t written=999;
        memset(seed,1,64); memset(output,0xa5,102); calls=0;
        int r=rpi5_firmware_seed_tree(&tree,seed,&used,output+1,100,&written,consume);
        assert((r==0)==(mode==0)); assert(calls==(mode!=1));
        assert(tree.chosen.properties==tree.chosen_props && tree.chosen.property_count==base_count);
        assert(output[0]==0xa5 && output[101]==0xa5);
        assert(written==(mode==0?100:999));
        for(unsigned i=1;i<=100;i++) assert(output[i]==(mode==0?0x5a:mode>=3?0:0xa5));
    }
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I'+str(ROOT/'loader/rpi5'),
                str(p/'test.c'),str(ROOT/'loader/rpi5/firmware_seed_tree.c'),
                '-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
