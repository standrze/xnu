/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define SECURITY_READ_ONLY_EARLY(type) type
#define SECURITY_READ_ONLY_LATE(type) type
#define VC_CONS_OPS 1
#ifndef __unused
#define __unused __attribute__((unused))
#endif
#define SCHED_HYGIENE_DEBUG 0
struct console_ops { void (*putc)(char,bool); int (*getc)(bool); };
static unsigned kernel_debugger_entry_count, disableConsoleOutput;
static bool gc_initialized, gc_enabled;
static unsigned gc_x,gc_y, lock_depth,locks,unlock_disable;
static unsigned uart_count,video_count;
static char uart[8192],video[8192];
static bool uart_poll[8192];
static void lock_video(void) { assert(!lock_depth);lock_depth++;locks++;if(unlock_disable)gc_enabled=false; }
static void unlock_video(void) { assert(lock_depth==1);lock_depth--; }
#define VCPUTC_LOCK_LOCK() lock_video()
#define VCPUTC_LOCK_UNLOCK() unlock_video()
static void gc_hide_cursor(unsigned x,unsigned y) {(void)x;(void)y;assert(lock_depth==1);}
static void gc_show_cursor(unsigned x,unsigned y) {(void)x;(void)y;assert(lock_depth==1);}
static void gc_putchar(char c) {
    assert(lock_depth==1 && uart_count>video_count);
    assert(uart[uart_count-1]==c); /* UART first, never recursive console output */
    assert(video_count<sizeof(video));video[video_count++]=c;
}
static void serial_putc_options(char c,bool poll) {
    assert(!lock_depth);assert(uart_count<sizeof(uart));
    uart_poll[uart_count]=poll;uart[uart_count++]=c;
}
static int _serial_getc(bool wait) {return wait?17:18;}
static int _vcgetc(bool wait) {return wait?19:20;}
__attribute__((noreturn)) static void panic(const char *fmt,...) {(void)fmt;exit(91);}
#include "console_dispatch_original.inc"
static void reset_output(void) {uart_count=video_count=locks=0;memset(uart,0,sizeof(uart));memset(video,0,sizeof(video));}
int main(int argc,char **argv)
{
    cons_ops_index=0;
    if(argc==2 && !strcmp(argv[1],"invalid-index")){cons_ops_index=2;_cnputc('x',false);return 99;}
    assert(cons_ops[0].getc==_serial_getc && cons_ops[1].getc==_vcgetc);
    assert(cons_ops[0].getc(false)==18 && cons_ops[0].getc(true)==17);
    gc_initialized=gc_enabled=true;
    char payload[]="xnu> /bin/zsh -c 'printf nonce'\nB45:nonce:END:0\n";
    _cnputs(payload,(int)strlen(payload),false);
    char expected[]="xnu> /bin/zsh -c 'printf nonce'\r\nB45:nonce:END:0\r\n";
    assert(uart_count==strlen(expected) && !memcmp(uart,expected,uart_count) && !video_count);
    assert(rpi5_console_mirror_publish());assert(!rpi5_console_mirror_publish());
    reset_output();_cnputs(payload,(int)strlen(payload),false);
    assert(uart_count==strlen(expected) && !memcmp(uart,expected,uart_count));
    assert(video_count==uart_count && !memcmp(video,uart,uart_count));
    assert(locks==video_count && !lock_depth);
    for(unsigned i=0;i<uart_count;i++)assert(!uart_poll[i]);
    reset_output();_cnputs(payload,(int)strlen(payload),true);
    assert(uart_count==strlen(expected) && !video_count && !locks);
    for(unsigned i=0;i<uart_count;i++)assert(uart_poll[i]);
    reset_output();kernel_debugger_entry_count=1;_cnputs(payload,(int)strlen(payload),false);
    assert(uart_count==strlen(expected) && !video_count && !locks);
    for(unsigned i=0;i<uart_count;i++)assert(uart_poll[i]);
    kernel_debugger_entry_count=0;
    reset_output();gc_initialized=false;_cnputs(payload,(int)strlen(payload),false);
    assert(uart_count==strlen(expected) && !video_count && !locks);
    gc_initialized=true;gc_enabled=false;reset_output();_cnputc('a',false);
    assert(uart_count==1 && !video_count && !locks);
    gc_enabled=true;unlock_disable=1;reset_output();_cnputc('a',false);
    assert(uart_count==1 && !video_count && locks==1 && !lock_depth);
    unlock_disable=0;gc_enabled=true;
    reset_output();disableConsoleOutput=1;_cnputs(payload,(int)strlen(payload),false);
    assert(!uart_count && !video_count);disableConsoleOutput=0;
    rpi5_console_mirror_revoke();assert(!rpi5_console_mirror_publish());
    reset_output();_cnputs(payload,(int)strlen(payload),false);
    assert(uart_count==strlen(expected) && !video_count && !locks);
    puts("CONSOLE_MIRROR PASS UART_EXACT=1 ORIGINAL_DISPATCH=1 ORIGINAL_VIDEO_GATE=1 POLL_UART_ONLY=1 NO_MAPPING=1");
}
