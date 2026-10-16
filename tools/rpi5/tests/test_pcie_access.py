# SPDX-License-Identifier: BSD-2-Clause
"""Actual candidate build plus modeled callback faults; no hardware access."""
from pathlib import Path
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT/'loader/rpi5/pcie_access.c'
sys.path.insert(0,str(ROOT/'tools/rpi5'))
import check_pcie_access_package as package_check


class PCIeAccessTests(unittest.TestCase):
    def test_sanitized_fixed_allowlist_and_every_callback_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory)/'access'
            subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-I',str(CORE.parent),
                            str(Path(__file__).with_name('pcie_access_host.c')),str(CORE),'-o',str(program)],
                           check=True,timeout=60)
            result = subprocess.run([str(program)],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(result.stdout,b'PCIE_ACCESS_HOST_PASS CALLBACKS=184 READS=30\n')

    def test_actual_distinct_a76_image_no_undefined_symbols_and_halfword_load(self):
        # The builder only writes a new local directory. It has no installer,
        # serial, SSH, reboot or media access path. Keep its output as evidence.
        result = subprocess.check_output(['python3',str(ROOT/'tools/rpi5/build_pcie_access_probe.py')],
                                         cwd=ROOT,text=True,timeout=60)
        summary = json.loads(result)
        package = Path(summary['image']).parent
        manifest = json.loads((package/'manifest.json').read_text())
        report = package_check.inspect(package)
        self.assertTrue(report['preflight_pass'])
        self.assertIs(report['installation_admitted'],False)
        self.assertEqual(manifest['profile'],'pcie2-readonly-access-v1')
        self.assertTrue(manifest['sources_stable'])
        self.assertTrue(manifest['pcie_mmio'])
        for field in ('installed','physical_execution','hardware_recovery_proven',
                      'watchdog_destination_proven','xnu_transfer','pcie_writes',
                      'config_access','dma','reset_calibration_writes'):
            self.assertIs(manifest[field],False,field)
        self.assertLess(manifest['stack_budget']['conservative_bytes']+512,0x4000)
        disassembly = subprocess.check_output(['xcrun','llvm-objdump','-d',
            '--disassemble-symbols=rpi5_access_load16,rpi5_access_load32',str(package/'probe.elf')],
            text=True,timeout=30)
        self.assertIn('ldrh\tw0, [x0]',disassembly)
        self.assertIn('ldr\tw0, [x0]',disassembly)
        self.assertEqual(disassembly.count('dsb\tsy'),4)
        symbols = subprocess.check_output(['xcrun','llvm-nm','--undefined-only',str(package/'probe.elf')],
                                          text=True,timeout=30)
        self.assertEqual(symbols.strip(),'')
        for change in ('dma','installed','watchdog_destination_proven','profile','hash','sources','stack','extent'):
            bad = copy.deepcopy(manifest)
            if change in ('dma','installed','watchdog_destination_proven'): bad[change] = True
            if change == 'profile': bad['profile'] = 'declarations-only'
            if change == 'hash': bad['sha256']['loader/rpi5/pcie_access.c'] = '0'*64
            if change == 'sources': bad['commands'][0].append('/tmp/extra.c')
            if change == 'stack': bad['stack_budget']['conservative_bytes'] = 0
            if change == 'extent': bad['image_bytes'] -= 1
            with self.subTest(change=change), patch.object(package_check,'read_manifest',return_value=bad), \
                    self.assertRaises(ValueError):
                package_check.inspect(package)


if __name__ == '__main__':
    unittest.main()
