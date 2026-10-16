# SPDX-License-Identifier: BSD-2-Clause
"""BCM2712 UBUS callback models and target link; no actual MMIO."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT/'loader/rpi5/pcie_ubus.c'


class PCIeUBUSTests(unittest.TestCase):
    def test_sanitized_normal_reserved_zero_and_all_callback_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary)/'ubus'
            subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-I',str(CORE.parent),
                            str(Path(__file__).with_name('pcie_ubus_host.c')),str(CORE),'-o',str(program)],
                           check=True,timeout=60)
            result = subprocess.run([str(program)],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(result.stdout,b'PCIE_UBUS_HOST_PASS\n')

    def test_freestanding_a76_has_no_undefined_symbols(self):
        with tempfile.TemporaryDirectory() as temporary:
            obj = Path(temporary)/'ubus.o'
            subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                            '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin',
                            '-fno-stack-protector','-O2','-Wall','-Wextra','-Werror',
                            '-c',str(CORE),'-o',str(obj)],check=True,timeout=60)
            symbols = subprocess.check_output(['xcrun','llvm-nm','--undefined-only',str(obj)],text=True,timeout=30)
            self.assertEqual(symbols.strip(),'')


if __name__ == '__main__':
    unittest.main()
