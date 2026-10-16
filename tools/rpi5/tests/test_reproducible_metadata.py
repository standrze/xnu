from pathlib import Path
import runpy
import unittest
import subprocess
from types import SimpleNamespace

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'rpi5.py'))


class ReproducibleMetadataTests(unittest.TestCase):
    def test_linker_mode_is_opt_in_and_board_scoped(self):
        root = Path(__file__).resolve().parents[3]
        source = (root / 'makedefs/MakeInc.def').read_text()
        line = source.index('LDFLAGS_KERNEL_ONLY += -Wl,-reproducible')
        start = source.rfind('ifeq ($(CURRENT_MACHINE_CONFIG),BCM2712)', 0, line)
        end = source.index('endif\nendif', line) + len('endif\nendif')
        fragment = source[start:end]
        for board, enabled, expected in (
                ('BCM2712', 1, '-Wl,-reproducible'), ('BCM2712', 0, ''),
                ('T8103', 1, '')):
            makefile = (f'CURRENT_MACHINE_CONFIG := {board}\nRPI5_REPRODUCIBLE := {enabled}\n'
                        + fragment + '\nprobe:\n\t@echo $(LDFLAGS_KERNEL_ONLY)\n')
            result = subprocess.run(['make', '-f', '-', 'probe'], input=makefile,
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), expected)

    def test_fixed_utc_and_logical_root(self):
        values = MODULE['reproducible_metadata'](0)
        self.assertEqual(values, {
            'KERNEL_BUILD_DATE': '1970-01-01 00:00:00 UTC',
            'KERNEL_BUILD_OBJROOT': 'xnu/DEVELOPMENT_ARM64_BCM2712'})
        self.assertEqual(values, MODULE['reproducible_metadata'](0))

    def test_invalid_epoch(self):
        for value in (-1, '0', 0.5, True, None):
            with self.assertRaises(ValueError):
                MODULE['reproducible_metadata'](value)

    def test_requires_new_outputs_before_any_build_action(self):
        with self.assertRaisesRegex(RuntimeError, 'requires --fresh'):
            MODULE['build']({}, SimpleNamespace(reproducible=True, fresh=False))
