# SPDX-License-Identifier: BSD-2-Clause
"""Actual allocation C formatter with explicit firmware/outcome doubles."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import display_compact_serial as protocol
ROOT=Path(__file__).resolve().parents[3]
TAG='0123456789abcdef0123456789abcdef'
TEMPLATE=r'''
#include "display_compact_adapter.h"
#include "uart.h"
#include <stdio.h>
#include <stdlib.h>
#include <setjmp.h>
#include <string.h>
#define RPI5_DISPLAY_COMPACT_TAG "0123456789abcdef0123456789abcdef"
#define UART 0x107d001000ull
#define UART_BUDGET 1000000u
static unsigned stage;static unsigned char *__probe_start=(void *)0x9000000,*__probe_end,*rpi5_display_allocate_pages;
static size_t original_size=0x13a32;static uint64_t primary_affinity;static int failure;
static struct rpi5_display_allocate_result query_result;
static struct rpi5_display_allocate_report query_report;
static struct rpi5_display_compact_report draw_report;
static uint64_t deadline=UINT64_MAX;
static jmp_buf stopped;
static _Noreturn void park(void){longjmp(stopped,1);}
static int within(void){return 1;}
static int text(const char *s){fputs(s,stdout);return 1;}
static int hex(uint64_t n){printf("0x%016llX",(unsigned long long)n);return 1;}
enum rpi5_uart_result rpi5_uart_drain(uintptr_t p,size_t n){(void)p;(void)n;return RPI5_UART_OK;}
int rpi5_display_compact_run(const void *f,size_t n,struct rpi5_range image,void *storage,uint64_t affinity,uint64_t absolute,
    struct rpi5_display_allocate_result *out,struct rpi5_display_allocate_report *r,struct rpi5_display_compact_report *draw){
    (void)f;(void)n;(void)image;(void)affinity;(void)absolute;
    *draw=(struct rpi5_display_compact_report){.result=-2};memset(out,0,sizeof *out);memset(r,0,sizeof *r);
    r->admission=1;r->cache_operations=12;r->mmio_reads=30;r->mmio_writes=4;
    r->session=(struct rpi5_display_mailbox_session){.state=RPI5_DISPLAY_MBOX_COMPLETE,.stage=12,.slot=3,
        .polls=8,.callbacks=150,.tx_attempted=15,.pop_attempted=15,.completed=15,.start_us=100,.last_us=9000,.deadline_us=1000100};
    r->session.expected_word=r->session.peek_word=r->session.popped_word=(uint32_t)(uintptr_t)storage+12288+8;
    r->binding.mmio=(struct rpi5_range){0x107c013880ull,0x107c0138c0ull};r->binding.firmware_phandle=26;r->binding.mailbox_phandle=25;
    r->decoded_replies=15;
    const uint32_t pre[17]={1,0,1920,1080,32,7680,1920,1080,0,0};
    const uint32_t set[16]={1920,1080,1920,1080,32,0,2,0,0,0,0,0,0,0x3f800000,8294400,7680};
    const uint32_t get[30]={1920,1080,1920,1080,32,0,2,0,0,0,0,0,0,7680,0,1920,1080,32,7680,1920,1080,0,0};
    r->replies[0].count=17;memcpy(r->replies[0].words,pre,sizeof pre);r->replies[1].count=1;
    r->replies[2].count=16;memcpy(r->replies[2].words,set,sizeof set);
    r->replies[3].count=30;memcpy(r->replies[3].words,get,sizeof get);
    if(failure==1||failure==2){
        r->session.state=RPI5_DISPLAY_MBOX_QUARANTINED;r->session.quarantined_buffers=15;
        if(failure==1){r->decoded_replies=1;r->session.slot=0;r->session.completed=r->session.pop_attempted=r->session.tx_attempted=1;
            r->mmio_writes=1;r->cache_operations=6;r->replies[0].words[4]=16;r->replies[0].words[5]=3840;}
        return -6;
    }
    r->candidate_valid=1;r->candidate=(struct rpi5_display_allocate_candidate){.bus_address=0x3f800000,
        .cpu_address=0x3f800000,.allocation_bytes=8294400,.reservation_start=0x3f800000,.reservation_end=0x3ffec000,
        .width=1920,.height=1080,.stride=7680,.depth=32,.pixel_order=0,.alpha_mode=2};
    *draw=(struct rpi5_display_compact_report){.first_address=0x3f81e040,.last_address=0x3f82b3bc,
        .start_us=100,.last_us=21000,.deadline_us=500100,.attempted=768,.completed=768,.rows=8,
        .guard_calls=17,.time_calls=785,.barriers=8,.used=1,.result=0};
    if(failure==3){draw->attempted=100;draw->completed=99;draw->rows=0;draw->guard_calls=2;draw->time_calls=103;draw->barriers=0;draw->result=-1;}
    return 0;
}
static _Noreturn void actual_formatter(uintptr_t fdt_pa){uint64_t sctlr=0x30d00800,daif=0x3c0;
/* ACTUAL_BODY */
int main(int argc,char **argv){if(argc!=4)return 2;__probe_end=(void *)(uintptr_t)strtoull(argv[1],0,0);rpi5_display_allocate_pages=(void *)(uintptr_t)strtoull(argv[2],0,0);failure=atoi(argv[3]);
    if(!setjmp(stopped))actual_formatter(0x20000000);return stage==22?0:1;}
'''
class DisplayCompactSerialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name)
        s=(ROOT/'loader/rpi5/probe_display_compact_main.c').read_text();body=s[s.index('    stage=20;'):s.index('\nvoid probe_exception(')]
        (cls.work/'main.c').write_text(TEMPLATE.replace('/* ACTUAL_BODY */',body))
        r=subprocess.run(['xcrun','clang','-std=c11','-O1','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),str(cls.work/'main.c'),'-o',str(cls.work/'native')],capture_output=True,text=True,timeout=30)
        if r.returncode:raise AssertionError(r.stderr)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def fixture(self,report=None,failure=False):
        report=report or dict(profile=protocol.PROFILE,tag=TAG,loader_live=dict(start=0x9000000,end=0x9260000),allocation_storage=dict(start=0x9020000,bytes=16384),visible_contract=protocol.CONTRACT)
        prefix=protocol.PREFIX
        head=f'{prefix}ENTRY TAG={report["tag"]} EL2 PRECHECK NO_XNU NO_CPU_ON ZERO_SERIAL_INPUT\r\n'+prefix+'UART CR=0x0000000000000301 FR=0x0000000000000090 IBRD=0x0000000000000018 FBRD=0x0000000000000000 LCRH=0x0000000000000070 FIRMWARE_PRESERVED_CLOCK_UNVERIFIED\r\n'
        head+=''.join(prefix+f'CHECK STAGE=0x{n:016X}\r\n' for n in range(1,20))+prefix+'ARMED WATCHDOG=15 SOFTWARE=8 NO_RELOAD\r\n'
        r=subprocess.run([self.work/'native',hex(report['loader_live']['end']),hex(report['allocation_storage']['start']),str(int(failure))],capture_output=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,b'')
        return head.encode()+r.stdout.replace(TAG.encode(),report['tag'].encode()),report
    def test_actual_c_success_and_failures_preserve_completed_raw(self):
        raw,report=self.fixture();r=protocol.inspect(raw,report);self.assertTrue(r['allocation_trial_pass']);self.assertTrue(r['visible_store_pass']);self.assertFalse(r['physical_visibility_proven']);self.assertEqual(r['mailbox_requests'],4);self.assertFalse(r['framebuffer_authority'])
        for failure in (1,2):
            raw,report=self.fixture(failure=failure);r=protocol.inspect(raw,report);self.assertFalse(r['allocation_trial_pass']);self.assertEqual(r['result_rc'],-6)
            self.assertEqual(len(r['raw_replies']),1 if failure==1 else 4)
        self.assertEqual(protocol.inspect(self.fixture(failure=1)[0],report)['raw_replies']['0'][4],16)
    def test_whole_capture_faults_strict_records_and_geometry(self):
        raw,report=self.fixture()
        for bad in (raw+b'panic: after STOP\r\n',b'RPI5XNU:FAULT before\r\n'+raw,raw+raw,raw[:-8],raw.replace(b'ALLOCATE_MAX=1',b'ALLOCATE_MAX=2'),
            raw.replace(b'STORAGE_BYTES=0x0000000000004000',b'STORAGE_BYTES=0x0000000000003000'),
            raw.replace(b'STATE=0x0000000000000002',b'STATE=0x0000000000000001'),
            raw.replace(b'RAW SLOT=0x0000000000000000 INDEX=0x0000000000000001',b'RAW SLOT=0x0000000000000000 INDEX=0x0000000000000002'),
            raw.replace(b'BUS=0x000000003F800000',b'BUS=0x00000000FF800000'),raw.replace(b'RESERVE_END=0x000000003FFEC000',b'RESERVE_END=0x000000003FFEB000')):
            with self.assertRaises(ValueError):protocol.inspect(bad,report)
        for i in range(1,len(raw.splitlines())-1):
            with self.assertRaises(ValueError):protocol.inspect(b'\r\n'.join(raw.splitlines()[:i])+b'\r\n',report)
    def test_prechecks_identical_to_frozen_get(self):
        old=(ROOT/'loader/rpi5/probe_display_query_main.c').read_text();new=(ROOT/'loader/rpi5/probe_display_compact_main.c').read_text()
        old=old[old.index('void probe_main('):old.index('void probe_el1_main(')].replace('RPI5XNU:DISPLAYGET:','RPI5XNU:DISPLAYCOMPACT:').replace('RPI5_DISPLAY_QUERY_TAG','RPI5_DISPLAY_COMPACT_TAG')
        self.assertEqual(old,new[new.index('void probe_main('):new.index('void probe_el1_main(')])
    def test_other_reply_prefix_classes_and_predecessor_profile_rejected(self):
        raw,report=self.fixture()
        for address in (0x7f800000,0xbf800000,0xff800000):
            replacement=f'0x{address:016X}'.encode()
            bad=raw.replace(b'INDEX=0x000000000000000D VALUE=0x000000003F800000',
                b'INDEX=0x000000000000000D VALUE='+replacement).replace(b'BUS=0x000000003F800000',b'BUS='+replacement)
            with self.subTest(address=hex(address)),self.assertRaises(ValueError):protocol.inspect(bad,report)
        with self.assertRaises(ValueError):protocol.inspect(raw,report|{'profile':'pi5-display-allocate-standalone-v1'})
        with self.assertRaises(ValueError):protocol.inspect(raw.replace(b'DISPLAYCOMPACT:',b'DISPLAYALLOC:'),report)

    def test_successful_allocation_with_partial_draw_never_passes(self):
        raw,report=self.fixture(failure=3);r=protocol.inspect(raw,report)
        self.assertTrue(r['allocation_trial_pass']);self.assertFalse(r['diagnostic_pass']);self.assertFalse(r['visible_store_pass'])
        self.assertEqual(r['result_rc'],0);self.assertEqual(r['draw_result_rc'],-1)
        self.assertEqual(r['framebuffer_writes_attempted'],100);self.assertFalse(r['physical_visibility_proven'])
        self.assertTrue(r['drawing']);self.assertTrue(r['framebuffer_memory_access']);self.assertFalse(r['allocation_component_drawing'])
    def test_draw_counts_deadlines_phase_order_and_contract_cannot_be_forged(self):
        raw,report=self.fixture()
        for a,b in ((b'COMPLETED=0x0000000000000300',b'COMPLETED=0x00000000000002FF'),
            (b'DEADLINE_US=0x000000000007A184',b'DEADLINE_US=0x000000000007A183'),
            (b'DRAW=1 VISUAL_CONFIRMATION_REQUIRED',b'DRAW=0'),
            (b'NO_FB_READ',b'FB_READS_ALLOWED'),
            (b'BOUNDED_FRAMEBUFFER_STORES',b'NO_FRAMEBUFFER_ACCESS')):
            changed=raw.replace(a,b);self.assertNotEqual(changed,raw)
            with self.assertRaises(ValueError):protocol.inspect(changed,report)
        with self.assertRaises(ValueError):protocol.inspect(raw,report|{'visible_contract':protocol.CONTRACT|{'stores':768.0}})
        with self.assertRaises(ValueError):protocol.inspect(raw+raw,report)

if __name__=='__main__':unittest.main()



