# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]
class CryptoStartupTests(unittest.TestCase):
    def test_coordinator_order(self):
        body=(ROOT/'osfmk/prng/rpi5_crypto_startup.c').read_text()
        body=re.sub(r'^#include.*\n','',body,flags=re.M)
        source=r'''
#include <assert.h>
#include <setjmp.h>
#include <stdbool.h>
enum { STARTUP_SUB_SYSCTL=20,STARTUP_SUB_EARLY_BOOT=21 };
static unsigned current_cpu,boot_cpu_id,startup_phase,registrations,prng_starts;
static bool crypto_init,reject;
static int table;
#define rpi5_crypto_functions table
static void *g_crypto_funcs;
static unsigned cpu_number(void) { return current_cpu; }
static jmp_buf escape;
static void panic(const char *message) __attribute__((noreturn));
static void panic(const char *message) { assert(message); longjmp(escape,1); }
static int register_crypto_functions(void *p) {
    assert(p==&table && !prng_starts); registrations++;
    if(reject) return -1;
    g_crypto_funcs=p; crypto_init=true; return 0;
}
void rpi5_prng_platform_start(void) {
    assert(registrations==1 && crypto_init && g_crypto_funcs==&table); prng_starts++;
}
#define PANICS(call) do { if(!setjmp(escape)) { call; assert(!"expected panic"); } } while(0)
'''+body+r'''
int main(void) {
    for(unsigned mode=0;mode<5;mode++) {
        current_cpu=0; startup_phase=STARTUP_SUB_SYSCTL; crypto_init=false; g_crypto_funcs=0;
        if(mode==0) current_cpu=1;
        if(mode==1) startup_phase--;
        if(mode==2) startup_phase++;
        if(mode==3) crypto_init=true;
        if(mode==4) g_crypto_funcs=&table;
        PANICS(rpi5_crypto_platform_start()); assert(!registrations && !prng_starts);
    }
    g_crypto_funcs=0; crypto_init=false; reject=true;
    PANICS(rpi5_crypto_platform_start());
    assert(registrations==1 && !prng_starts && !crypto_init);
    registrations=0; reject=false;
    rpi5_crypto_platform_start(); assert(prng_starts==1);
    PANICS(rpi5_crypto_platform_start()); assert(prng_starts==1 && registrations==1);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory); (p/'test.c').write_text(source)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',str(p/'test.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
