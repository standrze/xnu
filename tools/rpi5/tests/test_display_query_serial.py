# SPDX-License-Identifier: BSD-2-Clause
"""Actual C terminal formatter, with explicit query/UART outcome doubles."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import display_query_serial as protocol
ROOT=Path(__file__).resolve().parents[3]
TAG='0123456789abcdef0123456789abcdef'
TEMPLATE=r'''
#include "display_query_adapter.h"
#include "uart.h"
#include <stdio.h>
#include <stdlib.h>
#include <setjmp.h>
#include <string.h>
#define RPI5_DISPLAY_QUERY_TAG "0123456789abcdef0123456789abcdef"
#define UART 0x107d001000ull
#define UART_BUDGET 1000000u
static unsigned stage;static unsigned char *__probe_start=(void *)0x9000000,*__probe_end,*rpi5_display_query_pages;
static size_t original_size=0x13a32;static uint64_t primary_affinity;static int failure;
static struct rpi5_display_mailbox_result query_result;
static struct rpi5_display_query_report query_report;
static jmp_buf stopped;
static _Noreturn void park(void){longjmp(stopped,1);}
static int within(void){return 1;}
static int text(const char *s){fputs(s,stdout);return 1;}
static int hex(uint64_t n){printf("0x%016llX",(unsigned long long)n);return 1;}
enum rpi5_uart_result rpi5_uart_drain(uintptr_t p,size_t n){(void)p;(void)n;return RPI5_UART_OK;}
int rpi5_display_query_run(const void *f,size_t n,struct rpi5_range image,void *storage,uint64_t affinity,
    struct rpi5_display_mailbox_result *out,struct rpi5_display_query_report *r){
    (void)f;(void)n;(void)image;(void)affinity;
    memset(r,0,sizeof *r);r->admission=1;r->cache_operations=9;r->mmio_reads=23;r->mmio_writes=3;
    r->session=(struct rpi5_display_mailbox_session){.state=RPI5_DISPLAY_MBOX_COMPLETE,.stage=12,.slot=2,
        .polls=6,.callbacks=107,.tx_attempted=7,.pop_attempted=7,.completed=7,.start_us=100,.last_us=9000,.deadline_us=1000100};
    r->session.expected_word=r->session.peek_word=r->session.popped_word=(uint32_t)(uintptr_t)storage+8192+8;
    r->binding.mmio=(struct rpi5_range){0x107c013880ull,0x107c0138c0ull};r->binding.firmware_phandle=26;r->binding.mailbox_phandle=25;
    if(failure){r->session.state=RPI5_DISPLAY_MBOX_QUARANTINED;r->session.quarantined_buffers=7;return -6;}
    memset(out,0,sizeof *out);out->count=2;for(unsigned d=0;d<2;d++)for(unsigned i=0;i<16;i++)out->settings[d].words[i]=i?0xa0000000+d*16+i:d;
    return 0;
}
static _Noreturn void actual_formatter(uintptr_t fdt_pa){uint64_t sctlr=0x30d00800,daif=0x3c0;
/* ACTUAL_BODY */
int main(int argc,char **argv){if(argc!=4)return 2;__probe_end=(void *)(uintptr_t)strtoull(argv[1],0,0);rpi5_display_query_pages=(void *)(uintptr_t)strtoull(argv[2],0,0);failure=atoi(argv[3]);
    if(!setjmp(stopped))actual_formatter(0x20000000);return stage==22?0:1;}
'''
class DisplayQuerySerialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name)
        s=(ROOT/'loader/rpi5/probe_display_query_main.c').read_text();body=s[s.index('    stage=20;'):s.index('\nvoid probe_exception(')]
        (cls.work/'main.c').write_text(TEMPLATE.replace('/* ACTUAL_BODY */',body))
        r=subprocess.run(['xcrun','clang','-std=c11','-O1','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),str(cls.work/'main.c'),'-o',str(cls.work/'native')],capture_output=True,text=True,timeout=30)
        if r.returncode:raise AssertionError(r.stderr)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def fixture(self,report=None,failure=False):
        report=report or dict(profile=protocol.PROFILE,tag=TAG,loader_live=dict(start=0x9000000,end=0x9160000),query_storage=dict(start=0x9020000,bytes=12288))
        prefix=protocol.PREFIX
        head=f'{prefix}ENTRY TAG={report["tag"]} EL2 PRECHECK NO_XNU NO_CPU_ON ZERO_SERIAL_INPUT\r\n'+prefix+'UART CR=0x0000000000000301 FR=0x0000000000000090 IBRD=0x0000000000000018 FBRD=0x0000000000000000 LCRH=0x0000000000000070 FIRMWARE_PRESERVED_CLOCK_UNVERIFIED\r\n'
        head+=''.join(prefix+f'CHECK STAGE=0x{n:016X}\r\n' for n in range(1,20))+prefix+'ARMED WATCHDOG=15 SOFTWARE=8 NO_RELOAD\r\n'
        r=subprocess.run([self.work/'native',hex(report['loader_live']['end']),hex(report['query_storage']['start']),str(int(failure))],capture_output=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,b'')
        return head.encode()+r.stdout.replace(TAG.encode(),report['tag'].encode()),report
    def test_actual_c_records_success_and_complete_failure(self):
        raw,report=self.fixture();r=protocol.inspect(raw,report);self.assertTrue(r['query_pass']);self.assertEqual(r['count'],2);self.assertFalse(r['framebuffer_authority'])
        raw,report=self.fixture(failure=True);r=protocol.inspect(raw,report);self.assertFalse(r['query_pass']);self.assertEqual(r['result_rc'],-6)
    def test_whole_capture_faults_and_strict_records(self):
        raw,report=self.fixture()
        for bad in (raw+b'panic: after STOP\r\n',b'RPI5XNU:FAULT before\r\n'+raw,raw+raw,raw[:-8],raw.replace(b'GET_ONLY=1',b'GET_ONLY=0'),
            raw.replace(b'STORAGE_BYTES=0x0000000000003000',b'STORAGE_BYTES=0x0000000000004000'),
            raw.replace(b'STATE=0x0000000000000002',b'STATE=0x0000000000000001'),
            raw.replace(b'RAW DISPLAY=0x0000000000000000 INDEX=0x0000000000000001',b'RAW DISPLAY=0x0000000000000000 INDEX=0x0000000000000002')):
            with self.assertRaises(ValueError):protocol.inspect(bad,report)
        for i in range(1,len(raw.splitlines())-1):
            with self.assertRaises(ValueError):protocol.inspect(b'\r\n'.join(raw.splitlines()[:i])+b'\r\n',report)
    def test_prechecks_preserved_from_frozen_observer(self):
        old=(ROOT/'loader/rpi5/probe_framebuffer_diagnostic_main.c').read_text();new=(ROOT/'loader/rpi5/probe_display_query_main.c').read_text()
        old=old[old.index('void probe_main('):old.index('void probe_el1_main(')].replace('RPI5XNU:FBOBS:','RPI5XNU:DISPLAYGET:').replace('RPI5_FB_OBSERVE_TAG','RPI5_DISPLAY_QUERY_TAG').replace('original_size=size;admitted=1;','original_size=size;primary_affinity=cpus.affinity[0];admitted=1;')
        self.assertEqual(old,new[new.index('void probe_main('):new.index('void probe_el1_main(')])
if __name__=='__main__':unittest.main()
