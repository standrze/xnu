# SPDX-License-Identifier: BSD-2-Clause
"""PCIe2 window encoder/programmer models, not hardware admission."""
from pathlib import Path
import hashlib
import subprocess
import tempfile
import unittest

from tools.rpi5.tests.test_pcie_fdt import PINNED, PINNED_SHA256, _encode_fdt, _synthetic_tree

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT/'loader/rpi5/pcie_windows.c'


class PCIeWindowTests(unittest.TestCase):
    def test_decoder_composition_and_optional_pinned_firmware(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            dtb, program = work/'synthetic.dtb', work/'windows-fdt'
            dtb.write_bytes(_encode_fdt(_synthetic_tree()))
            subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-I',str(CORE.parent),
                            str(Path(__file__).with_name('pcie_windows_fdt_host.c')),
                            *(str(CORE.parent/name) for name in ('fdt.c','fdt_reg.c','pcie_fdt.c','pcie_windows.c')),
                            '-o',str(program)],check=True,timeout=60)
            inputs = [dtb]
            if PINNED.exists():
                self.assertEqual(hashlib.sha256(PINNED.read_bytes()).hexdigest(),PINNED_SHA256)
                inputs.append(PINNED)
            for source in inputs:
                with self.subTest(source=source):
                    result = subprocess.run([str(program),str(source)],capture_output=True,timeout=30)
                    self.assertEqual(result.returncode,0,result.stderr.decode())
                    self.assertEqual(result.stdout,b'PCIE_WINDOWS_FDT_HOST_PASS\n')

    def test_sanitized_encodings_quiescence_and_every_callback_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary)/'windows'
            subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-I',str(CORE.parent),
                            str(Path(__file__).with_name('pcie_windows_host.c')),str(CORE),'-o',str(program)],
                           check=True,timeout=60)
            result = subprocess.run([str(program)],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(result.stdout,b'PCIE_WINDOWS_HOST_PASS\n')

    def test_freestanding_a76_has_no_undefined_symbols(self):
        with tempfile.TemporaryDirectory() as temporary:
            obj = Path(temporary)/'windows.o'
            subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                            '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin',
                            '-fno-stack-protector','-O2','-Wall','-Wextra','-Werror',
                            '-c',str(CORE),'-o',str(obj)],check=True,timeout=60)
            symbols = subprocess.check_output(['xcrun','llvm-nm','--undefined-only',str(obj)],text=True,timeout=30)
            self.assertEqual(symbols.strip(),'')


if __name__ == '__main__':
    unittest.main()
