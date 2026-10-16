# SPDX-License-Identifier: BSD-2-Clause
"""Real generated PTE audit/readiness bodies with explicit host PTE/MAIR doubles."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from .. import display_xnu_overlays as overlays
from ..console_mirror_overlay import original_body
ROOT=overlays.ROOT
class DisplayXNUMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name)
        pmap=overlays.pmap((ROOT/'osfmk/arm/pmap/pmap.c').read_text())
        body=original_body(pmap,'int\nrpi5_display_xnu_mapping_verify(')
        body=overlays.once(body,'__asm__ volatile("mrs %0, mair_el1" : "=r"(mair));','mair = host_mair; /* Explicit host register double. */')
        video=overlays.video((ROOT/'osfmk/console/video_console.c').read_text())
        start=video.index('    /* initialize_screen has completed:')
        ready=video[start:video.index('\n}\n\nvoid vcattach',start)]
        guard_start=video.index('    if (boot_vinfo) {\n        /* A revoke')
        remap_guard=video[guard_start:video.index('\t\tstruct vc_info new_vinfo = vinfo;',guard_start)]
        serial=overlays.serial((ROOT/'osfmk/console/serial_console.c').read_text())
        publish=original_body(serial,'bool\nrpi5_console_mirror_publish(')
        revoke=original_body(serial,'void\nrpi5_console_mirror_revoke(')
        started=original_body(serial,'int\nrpi5_display_xnu_mirror_started(')
        constants=(ROOT/'osfmk/arm64/proc_reg.h').read_text()
        names=('ARM_PTE_TYPE_VALID','ARM_PTE_APMASK','ARM_TTE_ATTRINDXBITS','ARM_TTE_ATTRINDXMASK','ARM_PTE_NX','ARM_PTE_PNX','AP_RWNA','CACHE_ATTRINDX_WRITECOMB')
        defines=[]
        for name in names:
            match=re.search(r'^#define '+name+r'\s+([^\n]+)',constants,re.M)
            if not match:raise AssertionError('Original PTE constant absent '+name)
            defines.append('#define '+name+' '+match[1])
        harness='''#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <assert.h>
#include <stdio.h>
#include <setjmp.h>
#define kprintf printf /* Host output double; no actual serial/renderer. */
#define PAGE_MASK 16383
#define PAGE_SIZE 16384
#define PT_ENTRY_NULL NULL
#define ARM_PTE_ATTRINDX(v) ((v)<<2)
#define ARM_TTE_ATTRINDX(v) ((v)<<2)
#define ARM_PTE_AP(v) ((v)<<6)
#define ARM_PTE_ATTRINDXMASK ARM_TTE_ATTRINDXMASK /* Cortex-A76: no FEAT_AIE. */
#define pte_to_pa(p) ((p)&UINT64_C(0x0000ffffffffc000))
typedef uint64_t pt_entry_t;
static int kernel_pmap;
static uint64_t host_mair;
static pt_entry_t pages[507];
static int missing=-1;
static unsigned pte_reads;
static pt_entry_t *pmap_pte(int pmap,uint64_t va) {
    assert(pmap==kernel_pmap && va>=UINT64_C(0xfffffe8000000000));
    unsigned index=(unsigned)((va-UINT64_C(0xfffffe8000000000))/16384);
    assert(index<507);pte_reads++;return (int)index==missing?NULL:&pages[index];
}
static int rpi5_display_xnu_map_admit(uint64_t s,uint64_t e,unsigned w,unsigned nx,unsigned early) {
    return s==0x3f400000&&e==0x3fbec000&&w&&nx&&early?1:-1;
}
'''+ '\n'.join(defines)+'\n'+body+'''
static unsigned rpi5_console_mirror_state;
'''+publish+revoke+started+'''
static int vm_initialized,gc_initialized,gc_enabled,gc_acquired,gc_graphics_boot;
static struct {uint64_t v_baseaddr,v_physaddr,v_width,v_height,v_rowbytes,v_depth,v_rotate;} vinfo;
static uint64_t lastVideoMapSize=0x7ec000,lastVideoVirt=UINT64_C(0xfffffe8000000000);
static int geometry_bad;
static int rpi5_display_xnu_geometry(uint64_t b,uint64_t w,uint64_t h,uint64_t s,uint64_t d,uint64_t n) {
    return geometry_bad||b!=0x3f400000||w!=1920||h!=1080||s!=7680||d!=32||n!=0x7ec000;
}
static jmp_buf panic_return;
static unsigned mutations,panics;
static _Noreturn void panic(const char *message) {assert(message);panics++;longjmp(panic_return,1);}
typedef struct {uint64_t v_baseAddr,v_width,v_height,v_rowBytes,v_depth,v_offset,v_length,v_rotate,v_scale;} PE_Video;
static int rpi5_display_xnu_video_admit(uint64_t b,uint64_t w,uint64_t h,uint64_t s,uint64_t d,
    uint64_t offset,uint64_t length,uint64_t rotate,uint64_t scale) {
    return b!=0x3f400001||w!=1920||h!=1080||s!=7680||d!=32||offset||length||rotate||scale!=1;
}
static void guarded_descriptor(PE_Video *boot_vinfo) {
'''+remap_guard+'''
        mutations++; /* First original descriptor mutation is below the guard. */
    }
}
static void completed_initialize_screen(void) {
'''+ready+'''
}
int main(void) {
    host_mair=UINT64_C(0x44)<<8;
    for(unsigned i=0;i<507;i++)pages[i]=(0x3f400000+16384*i)|ARM_PTE_TYPE_VALID|
        ARM_PTE_ATTRINDX(CACHE_ATTRINDX_WRITECOMB)|ARM_PTE_NX|ARM_PTE_PNX|ARM_PTE_AP(AP_RWNA);
    assert(!rpi5_display_xnu_mapping_verify(lastVideoVirt,0x3f400000,lastVideoMapSize));assert(pte_reads==507);
    const uint64_t faults[]={ARM_PTE_TYPE_VALID,ARM_PTE_NX,ARM_PTE_PNX,ARM_PTE_ATTRINDXMASK,ARM_PTE_APMASK,16384};
    for(unsigned i=0;i<507;i++)for(unsigned j=0;j<6;j++) {
        uint64_t original=pages[i];pages[i]^=faults[j];
        assert(rpi5_display_xnu_mapping_verify(lastVideoVirt,0x3f400000,lastVideoMapSize));pages[i]=original;
    }
    missing=506;assert(rpi5_display_xnu_mapping_verify(lastVideoVirt,0x3f400000,lastVideoMapSize));missing=-1;
    host_mair^=UINT64_C(1)<<8;assert(rpi5_display_xnu_mapping_verify(lastVideoVirt,0x3f400000,lastVideoMapSize));host_mair^=UINT64_C(1)<<8;
    assert(rpi5_display_xnu_mapping_verify(lastVideoVirt+1,0x3f400000,lastVideoMapSize));
    assert(rpi5_display_xnu_mapping_verify(lastVideoVirt,0x3f400000,lastVideoMapSize-16384));
    vinfo=(__typeof__(vinfo)){lastVideoVirt,0x3f400000,1920,1080,7680,32,0};
    for(unsigned state=0;state<32;state++) {
        vm_initialized=!!(state&1);gc_initialized=!!(state&2);gc_enabled=!!(state&4);gc_acquired=!!(state&8);gc_graphics_boot=!!(state&16);
        rpi5_console_mirror_state=0;completed_initialize_screen();assert(rpi5_console_mirror_state==(state==15?1:0));
    }
    vm_initialized=gc_initialized=gc_enabled=gc_acquired=1;gc_graphics_boot=0;
    rpi5_console_mirror_state=0;rpi5_console_mirror_revoke();assert(!rpi5_console_mirror_state);assert(!rpi5_display_xnu_mirror_started());
    geometry_bad=1;completed_initialize_screen();assert(!rpi5_console_mirror_state);geometry_bad=0;
    completed_initialize_screen();assert(rpi5_console_mirror_state==1);assert(rpi5_display_xnu_mirror_started());
    rpi5_console_mirror_revoke();assert(rpi5_console_mirror_state==2);assert(rpi5_display_xnu_mirror_started());
    completed_initialize_screen();assert(rpi5_console_mirror_state==2);
    PE_Video descriptor={0x3f400001,1920,1080,7680,32,0,0,0,1};
    rpi5_console_mirror_state=0;guarded_descriptor(&descriptor);assert(mutations==1&&!panics&&!rpi5_display_xnu_mirror_started());
    rpi5_console_mirror_state=1;if(!setjmp(panic_return)){guarded_descriptor(&descriptor);assert(0);}
    assert(mutations==1&&panics==1&&rpi5_console_mirror_state==2);
    if(!setjmp(panic_return)){guarded_descriptor(&descriptor);assert(0);}
    assert(mutations==1&&panics==2&&rpi5_console_mirror_state==2);
    rpi5_console_mirror_state=0;descriptor.v_offset=4;
    if(!setjmp(panic_return)){guarded_descriptor(&descriptor);assert(0);}
    assert(mutations==1&&panics==3&&!rpi5_display_xnu_mirror_started());
    puts("ACTUAL_PTE_AUDIT 507_PAGES 3042_CORRUPTIONS READINESS32 PERMANENT_REVOKE HOST_DOUBLES_ONLY");return 0;
}
'''
        source=cls.work/'host.c';source.write_text(harness)
        result=subprocess.run(['xcrun','clang','-std=gnu11','-O1','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',source,'-o',cls.work/'native'],capture_output=True,text=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_actual_pte_audit_and_initialize_screen_readiness(self):
        result=subprocess.run([self.work/'native'],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,'');self.assertIn('3042_CORRUPTIONS',result.stdout)
    def test_exact_overlay_boundaries_and_source_preservation(self):
        for source,transform in ((overlays.ARM,overlays.arm),(overlays.LOADER,overlays.loader),(overlays.SEED,overlays.seed),
                (ROOT/'osfmk/arm/pmap/pmap.c',overlays.pmap),(ROOT/'osfmk/console/video_console.c',overlays.video),(ROOT/'osfmk/console/serial_console.c',overlays.serial)):
            original=source.read_bytes();result=transform(original.decode());self.assertNotEqual(result,original.decode());self.assertEqual(original,source.read_bytes())
            with self.assertRaises(ValueError):transform('')
        generated=overlays.video((ROOT/'osfmk/console/video_console.c').read_text())
        self.assertIn('#if defined(ARM64_BOARD_CONFIG_BCM2712)',generated)
        self.assertNotIn('#define HAS_UCNORMAL_MEM',generated)
        self.assertLess(generated.index('if (rpi5_display_xnu_mirror_started())'),generated.index('struct vc_info new_vinfo = vinfo;'))
if __name__=='__main__':unittest.main()
