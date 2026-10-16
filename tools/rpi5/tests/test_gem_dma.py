# SPDX-License-Identifier: BSD-2-Clause
"""Host ownership/fault models and target compile; not physical Ethernet proof."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "iokit/Kernel/rpi5_gem_dma.c"


class GEMDMATests(unittest.TestCase):
    def test_sanitized_descriptor_ownership_and_faults(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "gem-dma"
            subprocess.run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", "-I", str(CORE.parent),
                            str(Path(__file__).with_name("gem_dma_host.c")), str(CORE),
                            "-o", str(binary)], check=True, timeout=60)
            result = subprocess.run([str(binary)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b"GEM_DMA_HOST_PASS\n")

    def test_freestanding_cortex_a76_no_external_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            obj = Path(directory) / "gem-dma.o"
            subprocess.run(["xcrun", "clang", "--target=aarch64-none-elf", "-mcpu=cortex-a76",
                            "-mstrict-align", "-mgeneral-regs-only", "-ffreestanding", "-fno-builtin",
                            "-fno-stack-protector", "-O2", "-Wall", "-Wextra", "-Werror",
                            "-c", str(CORE), "-o", str(obj)], check=True, timeout=60)
            symbols = subprocess.check_output(["xcrun", "llvm-nm", "--undefined-only", str(obj)], text=True)
            self.assertEqual(symbols.strip(), "")
            assembly = subprocess.check_output(["xcrun", "llvm-objdump", "-d", str(obj)], text=True)
            for name in ("slot_init", "tx_reserve", "tx_submit", "tx_complete", "rx_post",
                         "rx_complete", "rx_recycle"):
                self.assertIn("<rpi5_gem_" + name + ">:", assembly)


if __name__ == "__main__":
    unittest.main()
