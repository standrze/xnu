# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class CcrngTests(unittest.TestCase):
    def test_bridge(self):
        source = r'''
#include "rpi5_ccrng.h"
#include <corecrypto/cc_error.h>
#include <libkern/crypto/register_crypto.h>
#include <assert.h>
#include <stdint.h>
#include <string.h>
static unsigned calls;
static size_t total;
void read_random(void *out, unsigned int n) {
    assert(n && n <= 256); ++calls;
    for(unsigned i=0;i<n;i++) ((unsigned char *)out)[i]=(unsigned char)(total++);
}
static const struct crypto_functions functions = { .ccrng_fn = rpi5_ccrng };
int main(void) {
    int error=123;
    struct ccrng_state *rng=functions.ccrng_fn(&error);
    assert(rng && !error && functions.ccrng_fn(NULL)==rng);
    unsigned char out[1027];
    for(size_t n=0;n<=1025;n++) {
        memset(out,0xa5,sizeof out); total=0; calls=0;
        assert(!ccrng_generate(rng,n,out+1));
        assert(total==n && calls==(n+255)/256);
        assert(out[0]==0xa5 && out[n+1]==0xa5);
        for(size_t i=0;i<n;i++) assert(out[i+1]==(unsigned char)i);
    }
    calls=0;
    assert(!ccrng_generate(rng,0,NULL));
    assert(ccrng_generate(rng,1,NULL)==CCERR_PARAMETER);
    assert(rng->generate(NULL,0,NULL)==CCERR_PARAMETER);
    assert(ccrng_generate(rng,SIZE_MAX,out)==CCERR_PARAMETER);
    assert(ccrng_generate(rng,sizeof *rng,rng)==CCERR_PARAMETER);
    assert(!calls && functions.ccrng_fn(NULL)==rng);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.c').write_text(source)
            subprocess.run(['xcrun', 'clang', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                '-I' + str(ROOT / 'EXTERNAL_HEADERS'),
                '-I' + str(ROOT / 'libkern'), '-I' + str(ROOT / 'osfmk/prng'),
                str(path / 'test.c'), str(ROOT / 'osfmk/prng/rpi5_ccrng.c'),
                '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True, timeout=15)
