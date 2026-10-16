/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#define ISO_CHAR_HEIGHT 16
#define ISO_CHAR_WIDTH 8
#define ATTR_BOLD 1
#define ATTR_UNDER 2
#define ATTR_REVERSE 4
#include "video_layout_original.inc"
static struct vc_info vinfo;
static uint32_t vc_color_fore,vc_color_back;
static unsigned char *vc_rendered_font;
static int vc_rendered_char_size=16*8*4;
static _Alignas(4) unsigned char vc_rendered_char[16*8*4];
static void gc_clear_line(unsigned x,unsigned y,int which) {(void)x;(void)y;(void)which;abort();}
#include "video_glyph_original.inc"
static uint32_t color(unsigned ch,unsigned x,unsigned y,unsigned attrs) {
    unsigned row=iso_font[ch*16+y];
    unsigned bit=(row>>x)&1u;
    if((attrs&ATTR_BOLD) && x && ((row>>(x-1))&1u))bit=1;
    if(attrs&ATTR_REVERSE)bit^=1;
    if((attrs&ATTR_UNDER) && y==15)bit^=1;
    return bit?vc_color_fore:vc_color_back;
}
int main(int argc,char **argv) {
    size_t page=(size_t)sysconf(_SC_PAGESIZE),span=page*2,total=span+page*2;
    uint8_t *mapping=mmap(NULL,total,PROT_NONE,MAP_PRIVATE|MAP_ANON,-1,0);assert(mapping!=MAP_FAILED);
    uint8_t *area=mapping+page;assert(!mprotect(area,span,PROT_READ|PROT_WRITE));
    uint8_t *pixels=area+64;
    vinfo.v_baseaddr=(unsigned long)pixels;vinfo.v_width=32;vinfo.v_height=32;
    vinfo.v_depth=32;vinfo.v_rowbytes=144;vinfo.v_rowscanbytes=128;vinfo.v_rows=2;vinfo.v_columns=4;
    const uint32_t pairs[3][2]={{0x00ffffff,0},{0x00ff0000,0x000000ff},{0x0000ff00,0x00ff00ff}};
    uint32_t font[256*16*8];
    for(unsigned ch=0;ch<256;ch++)vc_render_char((unsigned char)ch,(unsigned char*)&font[ch*16*8],32);
    unsigned cases=0;
    for(unsigned cache=0;cache<2;cache++) {
        vc_rendered_font=cache?(unsigned char*)font:NULL;
        for(unsigned ch=0;ch<256;ch++)for(unsigned attr=0;attr<8;attr++)for(unsigned pair=0;pair<3;pair++) {
            unsigned xx=(ch&1u)?3:0,yy=(ch&2u)?1:0;
            vc_color_fore=pairs[pair][0];vc_color_back=pairs[pair][1];
            memset(area,0xa5,span);vc_paint_char_32(xx,yy,(unsigned char)ch,(int)attr,0,0);
            for(unsigned y=0;y<32;y++)for(unsigned x=0;x<36;x++) {
                uint32_t actual;memcpy(&actual,pixels+y*144+x*4,4);
                uint32_t expected=0xa5a5a5a5;
                if(x>=xx*8 && x<(xx+1)*8 && y>=yy*16 && y<(yy+1)*16)
                    expected=color(ch,x-xx*8,y-yy*16,attr);
                if(argc==2 && !strcmp(argv[1],"bad-expectation") && cases==0 && x==0 && y==0)expected^=1;
                if(actual!=expected)return 74;
            }
            for(size_t i=0;i<64;i++)assert(area[i]==0xa5);
            for(size_t i=64+32*144;i<span;i++)assert(area[i]==0xa5);
            /* The real cached equal-previous-glyph fast path must preserve pixels. */
            if(cache && ch && !attr) {
                uint8_t saved[32*144];memcpy(saved,pixels,sizeof(saved));
                vc_paint_char_32(xx,yy,(unsigned char)ch,0,(unsigned char)ch,0);
                assert(!memcmp(saved,pixels,sizeof(saved)));
                unsigned other=(ch+1)&255;vc_paint_char_32(xx,yy,(unsigned char)other,0,(unsigned char)ch,0);
                for(unsigned y=0;y<16;y++)for(unsigned x=0;x<8;x++) {
                    uint32_t actual;memcpy(&actual,pixels+(yy*16+y)*144+(xx*8+x)*4,4);
                    assert(actual==color(other,x,y,0));
                }
            }
            cases++;
        }
    }
    memset(area,0xa5,span);vc_color_back=0x00ff0000;vc_clear_screen(0,0,0,2,2);
    for(unsigned y=0;y<32;y++)for(unsigned x=0;x<36;x++) {
        uint32_t actual;memcpy(&actual,pixels+y*144+x*4,4);
        assert(actual==(x<32?vc_color_back:0xa5a5a5a5));
    }
    for(size_t i=0;i<64;i++)assert(area[i]==0xa5);
    for(size_t i=64+32*144;i<span;i++)assert(area[i]==0xa5);
    assert(!munmap(mapping,total));
    printf("APPLE_GLYPHS PASS CASES=%u ORIGINAL_FONT=1 ATTRS=8 GUARDED_ROWS=1 ORIGINAL_CLEAR=1 NO_SCANOUT=1\n",cases);
}
