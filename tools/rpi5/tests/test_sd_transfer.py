# SPDX-License-Identifier: BSD-2-Clause
"""Offline buffer execution model, not IOMemoryDescriptor runtime evidence."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class SDTransferTests(unittest.TestCase):
    def test_sanitized_snapshot_prepare_cleanup_partial_and_cancel_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory)/'sd-transfer'
            subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                            '-I',str(ROOT/'iokit/Kernel'),
                            str(ROOT/'tools/rpi5/tests/sd_transfer_host.c'),
                            str(ROOT/'iokit/Kernel/rpi5_sd_transfer.c'),
                            str(ROOT/'iokit/Kernel/rpi5_sd_contract.c'),
                            str(ROOT/'iokit/Kernel/rpi5_sd_write_policy.c'),'-o',str(binary)],check=True)
            result = subprocess.run([str(binary)],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(result.stdout,b'SD_TRANSFER_PASS\n')

    def test_freestanding_a76_no_allocation_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            obj = Path(directory)/'sd-transfer.o'
            subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                            '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin',
                            '-fno-stack-protector','-O2','-Wall','-Wextra','-Werror','-c',
                            str(ROOT/'iokit/Kernel/rpi5_sd_transfer.c'),'-o',str(obj)],check=True)
            undefined = subprocess.check_output(['xcrun','llvm-nm','--undefined-only',str(obj)],text=True)
            self.assertEqual({line.split()[-1] for line in undefined.splitlines()},
                             {'rpi5_sd_read_request_valid','rpi5_sd_write_request_valid',
                              'rpi5_sd_write_quarantine','rpi5_sd_read_sector','rpi5_sd_write_sector'})


if __name__ == '__main__':
    unittest.main()
