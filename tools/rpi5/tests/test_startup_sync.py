from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class StartupSyncTests(unittest.TestCase):
    def test_emitted_pi_fp_enable_is_synchronized(self):
        source = (ROOT / 'osfmk/arm64/start.s').read_text()
        block = source.split('// Enable NEON\n', 1)[1].split('// Clear thread pointer', 1)[0]
        block = block.rsplit('#endif', 1)[0]  # outer kernel-integrity guard
        with tempfile.TemporaryDirectory() as directory:
            assembly = Path(directory) / 'enable.S'
            obj = Path(directory) / 'enable.o'
            assembly.write_text('#define CPACR_FPEN_ENABLE 0x300000\n.text\n' + block)
            for pi in (False, True):
                command = ['xcrun', 'clang', '--target=aarch64-none-elf', '-c',
                           str(assembly), '-o', str(obj)]
                if pi:
                    command.append('-DARM64_BOARD_CONFIG_BCM2712=1')
                subprocess.run(command, check=True)
                dump = subprocess.check_output(['xcrun', 'llvm-objdump', '-d', str(obj)], text=True)
                instructions = []
                for line in dump.splitlines():
                    match = re.match(r'\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+(.+)', line)
                    if match:
                        instructions.append(' '.join(match[1].split()).lower())
                self.assertEqual(instructions[1], 'msr cpacr_el1, x0')
                self.assertEqual(len(instructions), 3 if pi else 2)
                if pi:
                    self.assertEqual(instructions[2], 'isb')

    def test_warning_policy_is_board_scoped_and_pin_independent(self):
        source = (ROOT / 'makedefs/MakeInc.def').read_text()
        end = source.index('\nCWARNFLAGS_STD =')
        start = source.rfind('ifeq ($(CURRENT_MACHINE_CONFIG),BCM2712)', 0, end)
        block = source[start:end]
        for board in ('BCM2712', 'T8103'):
            for exploratory in (0, 1):
                makefile = (f'CURRENT_MACHINE_CONFIG := {board}\n'
                            f'RPI5_EXPLORATORY_TOOLCHAIN := {exploratory}\n'
                            'WARNFLAGS_STD := -Werror\n' + block +
                            '\nprobe:\n\t@echo $(WARNFLAGS_STD)\n')
                result = subprocess.run(['make', '-f', '-', 'probe'], input=makefile,
                                        capture_output=True, text=True, check=True)
                flags = result.stdout.split()
                self.assertIn('-Werror', flags)
                for diagnostic in ('unused-but-set-variable', 'gnu-folding-constant'):
                    self.assertEqual('-Wno-error=' + diagnostic in flags, board == 'BCM2712')
