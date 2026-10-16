# SPDX-License-Identifier: BSD-2-Clause
"""Compile the candidate platform adapter with the real BCM2712 kernel flags.

This is a translation-unit check, not linkage or startup execution evidence.
Requires the existing exploratory kernel build and pinned BearSSL checkout.
"""
import json
import re
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class PlatformTests(unittest.TestCase):
    def test_startup_order_and_mutex_callbacks(self):
        # Execute the unchanged adapter body with observable kernel-service
        # stand-ins. The separate translation-unit test checks real headers.
        source = (ROOT / 'osfmk/prng/rpi5_prng_platform.c').read_text()
        source = re.sub(r'^#include .*\n', '', source, flags=re.MULTILINE)
        prefix = r'''
#include "rpi5_prng_binding.h"
#include <assert.h>
#include <stdarg.h>
#include <setjmp.h>
#include <stdint.h>
#define MAX_CPUS 4
#define STARTUP_SUB_PERCPU 10
#define LCK_GRP_ATTR_NULL 0
#define LCK_ATTR_NULL 0
typedef struct { unsigned initialized; } lck_grp_t;
typedef struct { unsigned initialized, held; } lck_mtx_t;
static unsigned step, crypto_init, startup_phase, current_cpu, boot_cpu_id;
static unsigned expecting_panic;
static jmp_buf panic_return;
static struct rpi5_prng_lock saved_lock;
static struct cckprng_ctx token;
const struct cckprng_funcs rpi5_prng_binding_functions = {0};
static void panic(const char *format, ...) __attribute__((noreturn));
static void panic(const char *format, ...) {
    assert(format && expecting_panic); longjmp(panic_return, 1);
}
#define PANICS(call) do { expecting_panic=1; if (!setjmp(panic_return)) { \
    call; assert(!"expected panic"); } expecting_panic=0; } while(0)
static unsigned cpu_number(void) { return current_cpu; }
static void lck_grp_init(lck_grp_t *g, const char *name, int attr) {
    assert(step++ == 0 && name && !attr && !g->initialized); g->initialized=1;
}
static void lck_mtx_init(lck_mtx_t *m, lck_grp_t *g, int attr) {
    assert(step++ == 1 && g->initialized && !attr && !m->initialized); m->initialized=1;
}
static void lck_mtx_lock(lck_mtx_t *m) {
    assert(m->initialized && !m->held); m->held=1;
}
static int lck_mtx_try_lock(lck_mtx_t *m) {
    assert(m->initialized); if(m->held) return 0; m->held=1; return 1;
}
static void lck_mtx_unlock(lck_mtx_t *m) { assert(m->held); m->held=0; }
int rpi5_prng_binding_prepare(const struct rpi5_prng_lock *lock) {
    assert(step++ == 2); saved_lock=*lock; return 0;
}
struct cckprng_ctx *rpi5_prng_binding_context(void) { return &token; }
static uint64_t early_random(void) { assert(step++ == 3); return 42; }
static void register_and_init_prng(struct cckprng_ctx *ctx, const struct cckprng_funcs *f) {
    assert(step++ == 4 && ctx == &token && f == &rpi5_prng_binding_functions);
    saved_lock.lock(saved_lock.context);
    assert(!saved_lock.try_lock(saved_lock.context));
    saved_lock.unlock(saved_lock.context);
    assert(saved_lock.try_lock(saved_lock.context));
    saved_lock.unlock(saved_lock.context);
}
'''
        main = r'''
int main(void) {
    PANICS(rpi5_prng_platform_start()); assert(step==0);
    crypto_init=1;
    PANICS(rpi5_prng_platform_start()); assert(step==0);
    startup_phase=STARTUP_SUB_PERCPU; current_cpu=1;
    PANICS(rpi5_prng_platform_start()); assert(step==0);
    current_cpu=0;
    rpi5_prng_platform_start(); assert(step==5);
    PANICS(rpi5_prng_platform_start()); assert(step==5);
    PANICS(rpi5_prng_binding_panic("test")); assert(step==5);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.c').write_text(prefix + source + main)
            command = ['xcrun', 'clang', '-Wall', '-Wextra', '-Werror',
                       '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                       '-idirafter', str(ROOT / 'EXTERNAL_HEADERS'),
                       '-I' + str(ROOT / 'osfmk/prng'),
                       '-I' + str(ROOT / 'build/rpi5/bearssl-candidate/inc'),
                       str(path / 'test.c'), '-o', str(path / 'test')]
            subprocess.run(command, check=True)
            subprocess.run([str(path / 'test')], check=True, timeout=15)

    def test_kernel_translation_unit(self):
        record = ROOT / 'build/rpi5/obj/DEVELOPMENT_ARM64_BCM2712/osfmk/DEVELOPMENT/prng_random.o.json'
        if not record.exists():
            self.skipTest('requires a BCM2712 kernel build compilation record')
        entry = json.loads(record.read_text().strip().rstrip(','))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'rpi5_prng_platform.o'
            args = []
            iterator = iter(entry['arguments'])
            for arg in iterator:
                if arg in ('-o', '-MF', '-MT', '-MQ', '-MJ'):
                    next(iterator)
                elif arg not in ('-MD', '-MMD', entry['file']):
                    args.append(arg)
            args += ['-I' + str(ROOT / 'build/rpi5/bearssl-candidate/inc')]
            for unit in ('prng_platform', 'prng_binding', 'prng_provider',
                         'prng_refresh', 'prng_generator', 'sha256_digest',
                         'sha512_compress', 'sha512_digest', 'digest_dispatch', 'hmac', 'legacy_digest',
                         'crypto_digest', 'crypto_hmac', 'aes_ecb', 'aes_gcm', 'des', 'cts', 'ccrng', 'crypto_random', 'rsa_digest', 'rsa', 'rsa_verify', 'chacha_stream', 'poly1305', 'chachapoly', 'chachapoly_binding', 'crypto_table', 'crypto_startup'):
                with self.subTest(unit=unit):
                    output = Path(directory) / ('rpi5_' + unit + '.o')
                    command = args + [str(ROOT / ('osfmk/prng/rpi5_' + unit + '.c')),
                                      '-o', str(output)]
                    result = subprocess.run(command, cwd=entry['directory'], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertTrue(output.is_file())
            for flags_record, source in (
                    ('libkern/DEVELOPMENT/corecrypto_aesxts.o.json', 'libkern/crypto/corecrypto_aesxts.c'),
                    ('libkern/DEVELOPMENT/corecrypto_aesxts.o.json', 'libkern/crypto/corecrypto_chacha20poly1305.c'),
                    ('libkern/DEVELOPMENT/corecrypto_aesxts.o.json', 'libkern/crypto/register_crypto.c'),
                    ('bsd/DEVELOPMENT/kern_descrip.o.json', 'bsd/nfs/gss/gss_krb5_mech.c')):
                with self.subTest(source=source):
                    wrapper_record = record.parents[2] / flags_record
                    wrapper_entry = json.loads(wrapper_record.read_text().strip().rstrip(','))
                    wrapper_args = []
                    iterator = iter(wrapper_entry['arguments'])
                    for arg in iterator:
                        if arg in ('-o', '-MF', '-MT', '-MQ', '-MJ'):
                            next(iterator)
                        elif arg not in ('-MD', '-MMD', wrapper_entry['file']):
                            wrapper_args.append(arg)
                    command = wrapper_args + [str(ROOT / source),
                                      '-o', str(Path(directory) / (Path(source).stem + '.o'))]
                    result = subprocess.run(command, cwd=wrapper_entry['directory'], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
