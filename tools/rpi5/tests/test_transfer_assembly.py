# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class TransferAssemblyTests(unittest.TestCase):
    def test_xnu_entry_checkpoint_is_bounded_and_preserves_boot_args(self):
        source = (ROOT / 'osfmk/arm64/start.s').read_text()
        entry = source.split('LEXT(start_first_cpu)', 1)[1]
        marker = entry.split('#if defined(ARM64_BOARD_CONFIG_BCM2712)', 1)[1].split('#endif', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            assembly = Path(directory) / 'checkpoint.S'
            obj = Path(directory) / 'checkpoint.o'
            # Expand repeatedly to check local branch-label isolation too.
            assembly.write_text('.text\n' + marker + '\nrpi5_pre_mmu_mark 68\n')
            subprocess.run(['xcrun', 'clang', '--target=aarch64-none-elf',
                            '-c', str(assembly), '-o', str(obj)], check=True)
            dump = subprocess.check_output(['xcrun', 'llvm-objdump', '-d', str(obj)], text=True)
        instructions = []
        for line in dump.splitlines():
            match = re.match(r'\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+(.+)', line)
            if match:
                instructions.append(' '.join(match[1].split()).lower())
        self.assertFalse(any(re.search(r'\b(?:[wx]0|sp|[wx]30)\b', i) for i in instructions))
        self.assertFalse(any(i.startswith(('bl ', 'blr ', 'ret')) for i in instructions))
        self.assertEqual(sum(i.startswith('subs x10, x10, #0x1') for i in instructions), 4)
        self.assertTrue(any(i.startswith('str w11, [x9]') for i in instructions))

    def test_checkpoint_order_and_pre_mmu_scope(self):
        source = (ROOT / 'osfmk/arm64/start.s').read_text()
        entry = source.split('LEXT(start_first_cpu)', 1)[1]
        checkpoints = ['rpi5_pre_mmu_mark 88', 'msr\t\tOSLAR_EL1, xzr',
                       'rpi5_pre_mmu_mark 68', 'BA_BOOT_FLAGS',
                       'rpi5_pre_mmu_mark 65', 'Linvalidate_bootstrap:',
                       'rpi5_pre_mmu_mark 90', 'Lkernelcache_base_found:',
                       'rpi5_pre_mmu_mark 80', 'common_start:',
                       'rpi5_pre_mmu_mark 77', 'MSR_SCTLR_EL1_X0']
        positions = [entry.index(item) for item in checkpoints]
        self.assertEqual(positions, sorted(positions))
        tail = entry[positions[-1]:]
        self.assertIn('cbz\tx21, 95f', tail)
        self.assertIn('rpi5_pre_mmu_mark 118', tail)
        self.assertIn('rpi5_pre_mmu_mark 86', tail)
        self.assertIn('rpi5_pre_mmu_mark 116', tail)
        self.assertIn('rpi5_pre_mmu_mark 107', tail)
        self.assertIn('rpi5_pre_mmu_mark 67', tail)

    def test_uart_page_descriptor_and_owned_storage(self):
        source = (ROOT / 'osfmk/arm64/start.s').read_text()
        block = source.split('/* Identity-map only', 1)[1].split('/* Ensure TTEs are visible */', 1)[0]
        self.assertIn('cbnz\tx9, .', block)
        self.assertIn('EXT(rpi5_boot_uart_tables)', block)
        self.assertIn('str\t\tx11, [x9, #496]', block)
        self.assertIn('str\t\tx11, [x10, #8192]', block)
        self.assertLess(block.index('dsb\t\tishst'), block.index('str\t\tx11, [x25, #8]'))
        # Independently decode the intended leaf and indices, including both
        # adjacent invalid pages; this is not execution of the assembly.
        address = int(re.search(r'MOV64\s+x11, (0x[0-9a-f]+)', block)[1], 16)
        flags = int(re.search(r'MOV64\s+x12, (0x[0-9a-f]+)', block)[1], 16)
        self.assertEqual(address, 0x107d000000)
        self.assertEqual(((address >> 36) & 2047, (address >> 25) & 2047,
                          (address >> 14) & 2047), (1, 62, 1024))
        self.assertEqual(flags & 3, 3)
        self.assertEqual((flags >> 2) & 7, 3)  # MAIR Device-nGnRnE
        self.assertEqual((flags >> 6) & 3, 0)  # EL1 RW, no EL0 access
        self.assertEqual((flags >> 8) & 3, 2)  # Outer shareable
        self.assertEqual((flags >> 10) & 1, 1) # Access flag
        self.assertEqual((flags >> 53) & 3, 3) # PXN and UXN
        leaves = [0] * 2048
        leaves[1024] = address | flags
        self.assertEqual(sum(bool(pte) for pte in leaves), 1)
        self.assertEqual(leaves[1023], 0)
        self.assertEqual(leaves[1025], 0)
        storage = (ROOT / 'osfmk/arm64/arm_vm_init.c').read_text()
        self.assertIn('rpi5_boot_uart_tables[2 * ARM_PGBYTES]', storage)

    def test_primary_placement_guard_precedes_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            obj = Path(directory) / "entry.o"
            subprocess.run(["xcrun", "clang", "--target=aarch64-none-elf",
                            "-mcpu=cortex-a76", "-c", str(ROOT/"loader/rpi5/probe_entry.S"),
                            "-o", str(obj)], check=True)
            dump = subprocess.check_output(["xcrun", "llvm-objdump", "-dr", str(obj)], text=True)
        instructions=[]
        for line in dump.splitlines():
            match=re.match(r"\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+(.+)",line)
            if match:
                instructions.append(" ".join(match[1].split()).lower())
        self.assertEqual(instructions[0], "msr daifset, #0xf")
        self.assertTrue(instructions[1].startswith("adr x9,"))
        self.assertTrue(instructions[2].startswith("ldr x10,"))
        self.assertEqual(instructions[3], "cmp x9, x10")
        self.assertRegex(instructions[4], r"^b\.ne .*<probe_stop>")
        self.assertRegex(dump, r"R_AARCH64_ADR_PREL_LO21\s+_start")
        self.assertRegex(dump, r"R_AARCH64_ABS64\s+__probe_start")

    def test_emitted_terminal_sequence(self):
        # Structural assembly evidence only: this does not execute system ops.
        with tempfile.TemporaryDirectory() as directory:
            obj = Path(directory) / "transfer.o"
            subprocess.run(["xcrun", "clang", "--target=aarch64-none-elf",
                            "-mcpu=cortex-a76", "-c", str(ROOT/"loader/rpi5/transfer.S"),
                            "-o", str(obj)], check=True)
            dump = subprocess.check_output(["xcrun", "llvm-objdump", "-d", str(obj)], text=True)
        instructions = []
        for line in dump.splitlines():
            match = re.match(r"\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+(.+)", line)
            if match:
                instructions.append(" ".join(match[1].split()).split(" //")[0].lower())
        self.assertTrue(instructions)
        self.assertEqual(instructions[0], "msr daifset, #0xf")
        branch = instructions.index("br x16")
        body = instructions[:branch+1]
        self.assertFalse(any(i.split()[0] in {"ldr", "str", "ldp", "stp", "bl", "blr", "ret"} for i in body))
        self.assertFalse(any(re.match(r"\w+ x0,", i) for i in body if not i.startswith(("tst ", "cmp "))))
        sequence = ["mrs x9, currentel", "mrs x9, sctlr_el1", "mov x16, x1",
                    "msr vbar_el1, x9", "msr tpidr_el1, xzr", "dsb sy",
                    "tlbi vmalle1", "ic ialluis", "dsb sy", "isb", "br x16"]
        cursor = 0
        for instruction in sequence:
            cursor = body.index(instruction, cursor) + 1
        self.assertEqual(instructions[branch+1], "wfe")
