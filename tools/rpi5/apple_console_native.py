# SPDX-License-Identifier: BSD-2-Clause
"""Test-only extraction of original Apple ABI/dispatch/renderer functions.

Neither original kernel source nor renderer is replaced in a target build.
Native scaffolds explicitly substitute locks/console transport and ordinary
guarded host RAM, not VM mapping, GPIO/UART, or scanout.
"""
from pathlib import Path
from . import console_mirror_overlay as overlay

ROOT = overlay.ROOT
VIDEO = ROOT / 'osfmk/console/video_console.c'
BOOT = ROOT / 'pexpert/pexpert/arm64/boot.h'
LAYOUT = ROOT / 'osfmk/console/video_console.h'
FONT = ROOT / 'osfmk/console/iso_font.c'
HARNESS = ROOT / 'tools/rpi5/tests'


def prepare(directory):
    directory = Path(directory)
    boot = BOOT.read_text()
    declarations = boot[boot.index('struct Boot_Video {'):boot.index('#define SOC_DEVICE_TYPE_BUFFER_SIZE')]
    (directory/'boot_abi_original.inc').write_text(
        boot[:boot.index('*/')+2]+'\n#define BOOT_LINE_LENGTH 1024\n'+declarations)
    header = LAYOUT.read_text()
    layout = header[header.index('struct vc_info {'):header.index('struct vc_progress_element {')]
    (directory/'video_layout_original.inc').write_text(header[:header.index('*/')+2]+'\n'+layout)
    serial = overlay.SOURCE.read_text()
    text = overlay.overlay(serial)
    video = VIDEO.read_text()
    video_body = overlay.original_body(video, 'void\nvcputc_options(char c, __unused bool poll)')
    cons_start = text.index(overlay.ANCHOR)
    cons_end = text.index('LCK_GRP_DECLARE(console_lck_grp', cons_start)
    dispatch = serial[:serial.index('#ifdef __x86_64__')] + '\n'
    dispatch += video[:video.index('#include')] + video_body
    dispatch += overlay.WRAPPER + text[cons_start:cons_end]
    for signature in ('static inline uint32_t\nget_cons_ops_index(void)',
                      'static inline void\n_cnputc(char c, bool poll)',
                      'static inline void\n_cnputs(char *c, int size, bool poll)'):
        dispatch += overlay.original_body(text,signature)
    (directory/'console_dispatch_original.inc').write_text(dispatch)
    glyph = video[:video.index('#include')] + '\n#include "'+str(FONT)+'"\n'
    for signature in ('static void\nvc_render_char(unsigned char ch, unsigned char *renderptr, short newdepth)',
                      'static void\nvc_paint_char_32(unsigned int xx, unsigned int yy, unsigned char ch, int attrs,',
                      'static void\nvc_clear_screen(unsigned int xx, unsigned int yy, unsigned int scrreg_top,'):
        glyph += overlay.original_body(video,signature)
    (directory/'video_glyph_original.inc').write_text(glyph)


def commands(directory):
    directory = Path(directory)
    common = ['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
              '-fsanitize=address,undefined','-I',str(directory),'-I',str(ROOT/'loader/rpi5')]
    return {
        'boot-video': common+[str(HARNESS/'boot_video_host.c'),
            *[str(ROOT/'loader/rpi5'/p) for p in ('boot_video.c','boot_args.c','framebuffer_descriptor.c','fdt.c','ranges.c')],
            '-o',str(directory/'boot-video')],
        'console-mirror':common+[str(HARNESS/'console_mirror_host.c'),'-o',str(directory/'console-mirror')],
        'apple-glyph':common+[str(HARNESS/'apple_video_glyph_host.c'),'-o',str(directory/'apple-glyph')],
    }
