/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "boot_video.h"
#include "boot_abi_original.inc"
_Static_assert(sizeof(boot_args) == RPI5_BOOT_ARGS_SIZE, "actual ARM64 boot ABI");
_Static_assert(offsetof(boot_args, Video) == 40 && sizeof(Boot_Video) == 48, "video ABI");
_Static_assert(offsetof(Boot_Video, v_baseAddr) == 0 && offsetof(Boot_Video, v_display) == 8 &&
    offsetof(Boot_Video, v_rowBytes) == 16 && offsetof(Boot_Video, v_width) == 24 &&
    offsetof(Boot_Video, v_height) == 32 && offsetof(Boot_Video, v_depth) == 40, "LP64 fields");
int main(void)
{
    const struct rpi5_boot_args_input args = { .virt_base=0xfffffe0006000000,
        .phys_base=0, .mem_size=1ull<<30, .top=0x3000000, .tree_pa=0x2800000,
        .kernel_end=0x2000000, .mem_actual=8ull<<30, .tree_length=4096 };
    const struct rpi5_fb_descriptor fb = { {0x20000004,0x20800000}, 1920ull*4*1080,
        1920,1080,7680,RPI5_FB_XRGB8888 };
    const struct rpi5_range ram = {0,1ull<<30};
    uint8_t headless[RPI5_BOOT_ARGS_SIZE], actual[RPI5_BOOT_ARGS_SIZE+16], before[sizeof(actual)];
    memset(actual,0xa5,sizeof(actual));
    assert(!rpi5_boot_args_encode(&args,"-v serial=3",11,headless,sizeof(headless)));
    assert(!rpi5_boot_video_encode(&args,"-v serial=3",11,&fb,&ram,1,NULL,0,actual,sizeof(actual)));
    boot_args decoded; memcpy(&decoded,actual,sizeof(decoded));
    assert(decoded.Video.v_baseAddr == (fb.allocation.start|1));
    assert((decoded.Video.v_baseAddr & ~3ull) == fb.allocation.start);
    assert(decoded.Video.v_display == 0 && decoded.Video.v_rowBytes == 7680);
    assert(decoded.Video.v_width == 1920 && decoded.Video.v_height == 1080);
    assert(decoded.Video.v_depth == 32);
    assert(((decoded.Video.v_depth >> kBootVideoDepthScaleShift) & kBootVideoDepthMask)+1 == 1);
    for (size_t i=0;i<sizeof(actual);i++) {
        if (i>=40 && i<88) continue;
        assert(actual[i] == (i<sizeof(headless)?headless[i]:0xa5));
    }
    memcpy(before,actual,sizeof(actual));
    for (unsigned mode=0;mode<13;mode++) {
        struct rpi5_fb_descriptor d=fb;
        struct rpi5_boot_args_input a=args;
        struct rpi5_range conflict={0x1ffffff0,0x20000004};
        const struct rpi5_range *live=NULL;size_t count=0,capacity=sizeof(actual);
        const char *command="-v serial=3";size_t length=11;
        switch(mode) {
        case 0:d.format=RPI5_FB_ARGB8888;break;
        case 1:d.format=RPI5_FB_XBGR8888;break;
        case 2:d.format=RPI5_FB_ABGR8888;break;
        case 3:d.width=7;break;
        case 4:d.height=15;d.visible_bytes=(uint64_t)d.stride*d.height;break;
        case 5:live=&conflict;count=1;break; /* rounded page prefix conflict */
        case 6:d.allocation.start=0x2000000;d.allocation.end=0x2800000;break;
        case 7:a.top=0x3000001;break;
        case 8:a.tree_pa=a.kernel_end-1;break;
        case 9:capacity=RPI5_BOOT_ARGS_SIZE-1;break;
        case 10:command="bad\0bytes";length=9;break;
        case 11:d.visible_bytes++;break;
        case 12:d.allocation.end=(1ull<<40)+1;break;
        }
        assert(rpi5_boot_video_encode(&a,command,length,&d,&ram,1,live,count,actual,capacity));
        assert(!memcmp(actual,before,sizeof(actual)));
    }
    assert(rpi5_boot_video_encode(NULL,"",0,&fb,&ram,1,NULL,0,actual,sizeof(actual)));
    assert(rpi5_boot_video_encode(&args,"",0,NULL,&ram,1,NULL,0,actual,sizeof(actual)));
    assert(!memcmp(actual,before,sizeof(actual)));
    puts("BOOT_VIDEO PASS ACTUAL_ABI=1 SIX_FIELDS_ONLY=1 ATOMIC=1 NO_MAPPING=1");
}
