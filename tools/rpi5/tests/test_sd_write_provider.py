# SPDX-License-Identifier: BSD-2-Clause
"""Actual worker source with explicit host API/transport doubles, not IOKit."""
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).parent


class SDWriteProviderTests(unittest.TestCase):
    def test_sanitized_worker_ordering_completion_stop_and_quarantine(self):
        if platform.machine()!='arm64':
            self.skipTest('Native ARM64 needed for harmless user-mode DMB/DSB on model arrays')
        with tempfile.TemporaryDirectory() as directory:
            objects=[]
            common=['xcrun','clang','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                    '-fno-sanitize-recover=all','-I',str(ROOT/'iokit/Kernel')]
            for name in ('rpi5_sd_contract','rpi5_sd_transfer','rpi5_sd_write_policy'):
                obj=Path(directory)/(name+'.o')
                subprocess.run([*common,'-std=c11','-c',str(ROOT/'iokit/Kernel'/(name+'.c')),
                                '-o',str(obj)],check=True)
                objects.append(str(obj))
            binary=Path(directory)/'provider'
            subprocess.run(['xcrun','clang++','-std=c++17',*common[2:],
                            '-I',str(HERE/'sd_write_provider_doubles'),
                            '-DARM64_BOARD_CONFIG_BCM2712','-DDEVELOPMENT=1',
                            '-DRPI5_STORAGE_WRITE_PROVIDER=1','-DRPI5_SD_WRITE_HOST_TEST=1',
                            str(HERE/'sd_write_provider_host.cpp'),
                            str(ROOT/'iokit/Kernel/rpi5_sd_memory.cpp'),*objects,
                            '-o',str(binary)],check=True)
            result=subprocess.run([str(binary)],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(result.stdout,b'SD_WRITE_PROVIDER_HOST_PASS\n')


if __name__=='__main__': unittest.main()
