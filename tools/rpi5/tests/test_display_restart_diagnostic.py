# SPDX-License-Identifier: BSD-2-Clause
import copy
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import build_display_restart_diagnostic as b
from tools.rpi5 import check_display_restart_diagnostic as c

class DisplayRestartDiagnosticTests(unittest.TestCase):
    def test_exact_four_kernel_boundaries_no_cli_or_smc_change(self):
        p=b.ROOT/'build/rpi5/offline-diagnostic-plan';changes=b.replacements(p)
        self.assertEqual(len(changes),4);self.assertNotIn(str(b.BASE/'smc.o'),changes)
        self.assertNotIn(str(b.BASE/'NOT_RUN_reboot'),changes)
        rows=b.command_plan(p,'a'*32);self.assertEqual(len(rows),19)
        self.assertEqual(len({r['label'] for r in rows}),len(rows))
        for text in b.generated_sources(p).values():self.assertNotIn('RPI5_TERMINAL_WDOG_SECONDS 3600',text)
    @unittest.skipUnless(os.environ.get('RPI5_RESTART_DIAGNOSTIC_PACKAGE'),'Distinct actual diagnostic package required')
    def test_actual_linked_package_no_compiler_and_mutation_negatives(self):
        p=Path(os.environ['RPI5_RESTART_DIAGNOSTIC_PACKAGE']).resolve();m=b.document(p/'manifest.json')
        with patch.object(subprocess,'run',side_effect=AssertionError('byte-only checker')):
            report=c.inspect(p,b.sha(p/'manifest.json'));self.assertTrue(all(report['diagnostic_checks'].values()))
            for changed in ('omit','flags','rate','timer','root'):
                bad=copy.deepcopy(m)
                if changed=='omit':bad['inputs_sha256'].pop(str(b.ROOT/'loader/rpi5/psci_restart_diagnostic.c'))
                if changed=='flags':bad['commands'][1]['command'].remove('-mcpu=cortex-a76')
                if changed=='rate':bad['watchdog_rate_bound_proven']=1
                if changed=='timer':bad['terminal_seconds']=180.0
                if changed=='root':bad['root_nodes']=32
                read=b.document
                with patch.object(b,'document',side_effect=lambda path:bad if Path(path)==p/'manifest.json' else read(path)):
                    with self.assertRaises(ValueError):c.inspect(p)
    @unittest.skipUnless(os.environ.get('RPI5_RESTART_DIAGNOSTIC_PACKAGE'),'Distinct actual diagnostic package required')
    def test_actual_native_loader_materialization(self):
        from tools.rpi5 import display_restart_native as native
        check=types.SimpleNamespace(inspect=c.inspect,b=b.original)
        fn=types.FunctionType(native.inspect.__code__,dict(vars(native),check=check),argdefs=native.inspect.__defaults__)
        result=fn(Path(os.environ['RPI5_RESTART_DIAGNOSTIC_PACKAGE']))
        self.assertTrue(result['exact_same_image_bytes']);self.assertFalse(result['target_executed'])
