# SPDX-License-Identifier: BSD-2-Clause
"""Link setup models/target code only, not physical PCIe admission."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT/'loader/rpi5/pcie_link.c'


class PCIeLinkTests(unittest.TestCase):
    def test_sanitized_poll_paths_and_callback_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary)/'link'
            subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-I',str(CORE.parent),
                            str(Path(__file__).with_name('pcie_link_host.c')),str(CORE),'-o',str(program)],
                           check=True,timeout=60)
            result = subprocess.run([str(program)],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(result.stdout,b'PCIE_LINK_HOST_PASS FAILURE_POSITIONS=1701\n')

    def test_freestanding_a76_has_no_undefined_symbols(self):
        with tempfile.TemporaryDirectory() as temporary:
            obj = Path(temporary)/'link.o'
            subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                            '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin',
                            '-fno-stack-protector','-O2','-Wall','-Wextra','-Werror',
                            '-c',str(CORE),'-o',str(obj)],check=True,timeout=60)
            symbols = subprocess.check_output(['xcrun','llvm-nm','--undefined-only',str(obj)],text=True,timeout=30)
            self.assertEqual(symbols.strip(),'')


if __name__ == '__main__':
    unittest.main()
