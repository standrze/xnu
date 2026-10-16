# SPDX-License-Identifier: BSD-2-Clause
"""Actual C++ adapter with explicit host doubles; not IOKit runtime evidence."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]


class SDMemoryTests(unittest.TestCase):
    def test_descriptor_lifetime_heap_snapshot_and_error_pairing(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory); objects=[]
            flags=['-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',
                   '-I',str(ROOT/'iokit/Kernel'),'-I',str(ROOT/'tools/rpi5/tests/sd_memory_doubles')]
            for name in ('rpi5_sd_transfer.c','rpi5_sd_contract.c','rpi5_sd_write_policy.c'):
                obj=work/(name+'.o'); objects.append(str(obj))
                subprocess.run(['xcrun','clang','-std=c11',*flags,'-c',str(ROOT/'iokit/Kernel'/name),'-o',str(obj)],check=True)
            binary=work/'sd-memory'
            subprocess.run(['xcrun','clang++','-std=c++17',*flags,
                            str(ROOT/'iokit/Kernel/rpi5_sd_memory.cpp'),
                            str(ROOT/'tools/rpi5/tests/sd_memory_host.cpp'),*objects,'-o',str(binary)],check=True)
            result=subprocess.run([str(binary)],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(result.stdout,b'SD_MEMORY_ADAPTER_PASS\n')


if __name__=='__main__':
    unittest.main()
