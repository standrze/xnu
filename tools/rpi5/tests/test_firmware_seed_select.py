from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]

class FirmwareSeedSelectTests(unittest.TestCase):
    def test_metadata_selection(self):
        code=r'''
#include "firmware_seed.h"
#include "fdt.h"
#include <assert.h>
#include <string.h>
static unsigned mode;
static unsigned char metadata[4096];
int rpi5_fdt_layout(const void *b,size_t n,struct rpi5_fdt_layout *o) {
    assert((b==(void *)1 || b==metadata) && n==4096);
    *o=(struct rpi5_fdt_layout){.total=mode==1?4095:4096};
    return mode==2?-1:0;
}
int rpi5_fdt_property(const void *b,size_t n,const char *p,const char *k,
    struct rpi5_fdt_property *o) {
    if(b==metadata) {
        assert(!strcmp(p,"/chosen/bootloader") && n==4096);
        if(!strcmp(k,"version")) *o=(struct rpi5_fdt_property){0,41,0};
        else { assert(!strcmp(k,"build-timestamp")); *o=(struct rpi5_fdt_property){64,4,0}; }
        if(mode==7) o->length--;
        if(mode==8) o->offset=4095;
        return mode==9?-2:0;
    }
    assert(b==(void *)1 && n==4096 && !strcmp(p,"/chosen") && !strcmp(k,"rng-seed"));
    *o=(struct rpi5_fdt_property){mode==3?4090:128,mode==4?63:64,40};
    return mode==5?-2:mode==6?-1:0;
}
int main(void) {
    struct rpi5_fdt_property out, prior={99,98,97};
    for(mode=1;mode<=6;mode++) {
        out=prior; assert(rpi5_firmware_seed_select((void *)1,4096,&out)==-1);
        assert(!memcmp(&out,&prior,sizeof out));
    }
    mode=0;
    assert(!rpi5_firmware_seed_select((void *)1,4096,&out));
    assert(out.offset==128 && out.length==64 && out.node_offset==40);
    assert(rpi5_firmware_seed_select((void *)1,4096,(void *)128)==-1);
    assert(rpi5_firmware_seed_select(0,4096,&out)==-1);
    assert(rpi5_firmware_seed_select((void *)(UINTPTR_MAX-1),4096,&out)==-1);
    memcpy(metadata,"6219bf00832ac18711372008da5ed99cf1c62ecf",41);
    metadata[64]=0x6a; metadata[65]=0x31; metadata[66]=0xe5; metadata[67]=0x1d;
    assert(!rpi5_firmware_seed_version(metadata,sizeof metadata));
    for(unsigned i=0;i<68;i++) if(i<41 || i>=64) {
        metadata[i]^=1; assert(rpi5_firmware_seed_version(metadata,sizeof metadata)==-1);
        metadata[i]^=1;
    }
    for(mode=7;mode<=9;mode++) assert(rpi5_firmware_seed_version(metadata,sizeof metadata)==-1);
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(code)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I'+str(ROOT/'loader/rpi5'),str(p/'test.c'),
                str(ROOT/'loader/rpi5/firmware_seed_fdt.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
