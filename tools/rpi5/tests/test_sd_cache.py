# SPDX-License-Identifier: BSD-2-Clause
"""SD cache observation byte/register models, not live cache/flush proof."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]


class SDCacheTests(unittest.TestCase):
    def test_sanitized_scr_extension_pages_and_protocol_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            binary=Path(directory)/'sd-cache'
            subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                            '-I',str(ROOT/'iokit/Kernel'),
                            str(ROOT/'tools/rpi5/tests/sd_cache_host.c'),
                            str(ROOT/'iokit/Kernel/rpi5_sd_cache.c'),'-o',str(binary)],check=True)
            result=subprocess.run([str(binary)],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(result.stdout,b'SD_CACHE_OBSERVATION_PASS\n')

    def test_freestanding_cortex_a76_has_no_external_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            obj=Path(directory)/'sd-cache.o'
            subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                            '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin',
                            '-fno-stack-protector','-O2','-Wall','-Wextra','-Werror','-c',
                            str(ROOT/'iokit/Kernel/rpi5_sd_cache.c'),'-o',str(obj)],check=True)
            undefined=subprocess.check_output(['xcrun','llvm-nm','--undefined-only',str(obj)],text=True)
            self.assertEqual(undefined.strip(),'')


if __name__=='__main__': unittest.main()
