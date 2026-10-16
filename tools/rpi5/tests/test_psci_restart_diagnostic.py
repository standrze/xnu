# SPDX-License-Identifier: BSD-2-Clause
"""New diagnostic hook executes the original policy under explicit host doubles."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import psci_restart_diagnostic_profile as profile
from tools.rpi5.tests.test_psci_restart_candidate import fixture
from tools.rpi5.tests.test_pcie_fdt import _encode_fdt

class PSCIRestartDiagnosticTests(unittest.TestCase):
    def test_actual_policy_gate_and_formatter_snapshot_and_return_failures(self):
        with tempfile.TemporaryDirectory(prefix='restart-diagnostic-') as name:
            out=Path(name);tree=out/'tree.dtb';tree.write_bytes(_encode_fdt(fixture()));exe=out/'host'
            root=profile.ROOT
            args=['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                  '-fsanitize=address,undefined','-fno-sanitize-recover=undefined','-I',str(root),
                  '-I',str(root/'loader/rpi5'),str(root/'loader/rpi5/psci_restart_diagnostic.c'),
                  str(root/'tools/rpi5/tests/psci_restart_diagnostic_host.c'),
                  str(root/'loader/rpi5/fdt.c'),str(root/'loader/rpi5/ranges.c'),'-o',str(exe)]
            subprocess.run(args,check=True,capture_output=True)
            result=subprocess.run([str(exe),str(tree)],check=True,capture_output=True,text=True)
            self.assertIn('DIAGNOSTIC_POLICY PASS',result.stdout);self.assertEqual(result.stderr,'')
    def test_only_exact_new_platform_include_and_loader_tag(self):
        original=profile.original.derive(profile.original.ORIGINAL.read_text())
        derived=profile.platform(profile.original.ORIGINAL.read_text())
        self.assertEqual(derived.replace('rpi5_psci_restart_diagnostic.inc','rpi5_psci_restart_candidate.inc'),original)
        with self.assertRaises(ValueError):profile.platform('changed')
        with self.assertRaises(ValueError):profile.main('changed')
        source=(profile.ROOT/'loader/rpi5/psci_restart_diagnostic.c').read_text()
        self.assertIn('#include "psci_restart_candidate.c"',source)
        self.assertNotIn('kprintf(',source);self.assertNotIn('printf(',source)
