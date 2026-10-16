# SPDX-License-Identifier: BSD-2-Clause
"""Actual Apple encoder bodies: reproduce old assert, validate bounded records."""
from pathlib import Path
import json
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import pcie_bounded_log_profile as p


def c_string(value):
    return json.dumps(value.replace('\\n','\n'))


def values(fmt):
    types=re.findall(r'%(?:0[248])?(llu|[udx])',fmt)
    return ','.join('UINT64_C(42795364)' if t=='llu' else '1' for t in types)


def encoder_source():
    """Only external host bindings differ; all encoder function bodies are exact."""
    types=(p.ROOT/'libkern/os/log_encode_types.h').read_text()
    types=types[types.index('OS_ENUM(os_log_fmt_hdr_flags'):types.rindex('#endif')]
    types=re.sub(r'OS_ENUM\((\w+),\s*(\w+),(.*?)\);',
        lambda m:'typedef '+m[2]+' '+m[1]+'_t;\nenum {'+m[3]+'};',types,flags=re.S)
    code=(p.ROOT/'libkern/os/log_encode.c').read_text()
    code=code[code.index('#define LOG_FMT_MAX_PRECISION'):]
    return r'''
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <stdarg.h>
#include <errno.h>
typedef int boolean_t;
typedef int logmem_t;
#define assert(x) do {if(!(x)){fprintf(stderr,"ENCODER_ASSERT:%s:%s\n",__func__,#x);exit(77);}}while(0)
#define MIN(a,b) ((a)<(b)?(a):(b))
#define VM_KERNEL_ADDRESS(a) ((uint64_t)(a)>=UINT64_C(0xffff000000000000))
#define SCALABLE_COUNTER_DEFINE(name) static unsigned name
#define counter_inc(p) (++*(p))
#define slowpath(x) (x)
#define OS_ALWAYS_INLINE __attribute__((always_inline))
#define panic(...) do {fprintf(stderr,__VA_ARGS__);exit(78);}while(0)
boolean_t doprnt_hide_pointers=0;
static bool oslog_is_safe(void){return false;}
static void *logmem_alloc_locked(logmem_t *m,size_t *n){(void)m;(void)n;return NULL;}
static void logmem_free_locked(logmem_t *m,void *b,size_t n){(void)m;(void)b;(void)n;abort();}
static bool logmem_ready(logmem_t *m){(void)m;return false;}
static size_t logmem_max_size(logmem_t *m){(void)m;return 256;}
static bool os_log_subsystem_id_valid(uint16_t sid){return sid!=0;}
'''+types+code+r'''
static size_t location_size=4;static uint16_t subsystem=0;
static unsigned encoded_calls=0;static size_t max_bytes=0;
static int encode(const char *fmt,...) {
    uint8_t guarded[288];memset(guarded,0xa5,sizeof guarded);
    logmem_t mem=0;struct os_log_context_s ctx;
    os_log_context_init(&ctx,&mem,guarded+16,256);
    va_list args;va_start(args,fmt);
    bool ok=os_log_context_encode(&ctx,fmt,args,0x1234,location_size,subsystem);
    va_end(args);
    for(unsigned i=0;i<16;i++)assert(guarded[i]==0xa5&&guarded[272+i]==0xa5);
    if(ok) {
        assert(ctx.ctx_hdr->hdr_cmd_cnt<=15&&!ctx.ctx_allocated&&!ctx.ctx_truncated);
        assert(!ctx.ctx_pubdata_cnt&&ctx.ctx_content_sz<=128);
        if(ctx.ctx_content_sz>max_bytes)max_bytes=ctx.ctx_content_sz;
        encoded_calls++;
    }
    os_log_context_free(&ctx);return ok;
}
'''


class BoundedLogTests(unittest.TestCase):
    def test_actual_encoder_old_assert_and_all_new_records(self):
        original=(p.FROZEN/'BCM2712PCIeIDTrialProgress.inc').read_text()
        match,fields,_=p.original_call(original)
        config_fmt='RPI5XNU:PCIEID:END '+' '.join(fields[:43])+'\\n'
        lines=['int main(int argc,char **argv){',
            '_Static_assert(sizeof(struct os_log_fmt_hdr_s)==2,"header ABI");',
            '_Static_assert(sizeof(struct os_log_fmt_cmd_s)==2,"command ABI");',
            '_Static_assert(sizeof(void*)==8&&sizeof(int)==4,"arm64 scalar sizes");',
            'if(argc==2){if(!strcmp(argv[1],"old53"))return !encode('+c_string(match[1])+','+values(match[1])+');',
            'if(!strcmp(argv[1],"old43"))return !encode('+c_string(config_fmt)+','+values(config_fmt)+');return 90;}',
            'for(unsigned hide=0;hide<2;hide++)for(unsigned loc=4;loc<=8;loc+=4)for(unsigned sid=0;sid<2;sid++){',
            'doprnt_hide_pointers=hide;location_size=loc;subsystem=sid;']
        for _,fmt,_ in p.records(original):lines.append('assert(encode('+c_string(fmt)+','+values(fmt)+'));')
        lines+=['}', 'assert(encoded_calls==40);printf("BOUNDED_LOG_PASS CALLS=%u MAX_BYTES=%zu\\n",encoded_calls,max_bytes);return 0;}']
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);source=folder/'actual_encoder.c';source.write_text(encoder_source()+'\n'.join(lines))
            exe=folder/'actual_encoder'
            build=subprocess.run(['xcrun','clang','-std=gnu11','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined',str(source),'-o',str(exe)],text=True,capture_output=True,timeout=60)
            self.assertEqual(build.returncode,0,build.stderr)
            for old in ('old43','old53'):
                result=subprocess.run([exe,old],text=True,capture_output=True,timeout=10)
                self.assertEqual(result.returncode,77,result.stderr)
                self.assertIn('ENCODER_ASSERT:log_add_cmd:log_fits_cmd(ctx, cmd_sz)',result.stderr)
            result=subprocess.run([exe],text=True,capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,'BOUNDED_LOG_PASS CALLS=40 MAX_BYTES=100\n')

    def test_exact_field_expression_conservation_and_only_logging_changed(self):
        original=(p.FROZEN/'BCM2712PCIeIDTrialProgress.inc').read_text()
        match,fields,args=p.original_call(original);rows=p.records(original)
        rebuilt=[]
        for name,start,end in p.GROUPS:
            row=next(r for r in rows if r[0]==name)
            self.assertEqual(row[1],'RPI5XNU:PCIEID:'+name+' '+' '.join(fields[start:end])+'\\n')
            self.assertEqual(row[2],args[start:end]);rebuilt+=list(range(start,end))
        self.assertEqual(sorted(rebuilt),list(range(53)))
        changed=p.trial(original)
        self.assertEqual(changed[:match.start()],original[:match.start()])
        self.assertTrue(changed.endswith(original[match.end():]))
        self.assertEqual(changed.count('kprintf('),7)
        self.assertLess(changed.index('PCIEID:ROOT '),changed.index('PCIEID:END '))
        with tempfile.TemporaryDirectory() as d:
            overlay=Path(d)/'overlay';p.emit(overlay)
            for source in p.FROZEN.iterdir():
                if source.is_file() and source.name!='BCM2712PCIeIDTrialProgress.inc':
                    self.assertEqual((overlay/source.name).read_bytes(),source.read_bytes())

    def test_actual_kprintf_serial_precedes_encoder_and_frozen_fault_is_after_end(self):
        source=(p.ROOT/'pexpert/arm/pe_kprintf.c').read_text()
        self.assertLess(source.index('_doprnt_log(fmt, &listp, PE_kputc, 16);'),
            source.index('os_log_with_args(OS_LOG_DEFAULT, OS_LOG_TYPE_DEFAULT, fmt, listp2, caller);'))
        for relative in ('rp1-config-v3-serial-20261013','root-route-serial-20261013'):
            raw=(p.ROOT/'build/rpi5'/relative/'serial.bin').read_bytes()
            end=raw.index(b'RPI5XNU:PCIEID:END ')
            panic=raw.index(b'panic(cpu 0 caller ',end)
            self.assertLess(raw.index(b'\n',end),panic)
            self.assertIn(b'log_encode.c:120 Assertion failed: log_fits_cmd(ctx, cmd_sz)',raw[panic:])


if __name__=='__main__':unittest.main()
