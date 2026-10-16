# SPDX-License-Identifier: BSD-2-Clause
import copy
import os
from pathlib import Path
import subprocess
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import build_display_restart_copy as b
from tools.rpi5 import check_display_restart_copy as c

class DisplayRestartCopyTests(unittest.TestCase):
    def test_exact_loader_only_link_and_limits(self):
        p=b.ROOT/'build/rpi5/copy-plan-only';rows=b.command_plan(p,'a'*32)
        old=next(r['command'] for r in b.document(b.BASE/'manifest.json')['commands'] if r['label']=='loader-link')
        new=next(r['command'] for r in rows if r['label']=='loader-link')
        self.assertEqual([(a,d) for a,d in zip(old,new) if a!=d],
            [(str(b.BASE/'loader-main.o'),str(p/'loader-main.o')),(str(b.BASE/'display_restart.elf'),str(p/'display_restart.elf'))])
        self.assertEqual(b.CONTRACT['copy_renewal_max'],2);self.assertEqual(b.CONTRACT['loader_outer_seconds'],60)
        self.assertEqual(len(rows),5)

    @unittest.skipUnless(os.environ.get('RPI5_RESTART_COPY_PACKAGE'),'Actual package required')
    def test_actual_package_and_mutations_byte_only(self):
        p=Path(os.environ['RPI5_RESTART_COPY_PACKAGE']).resolve();m=b.document(p/'manifest.json')
        with patch.object(subprocess,'run',side_effect=AssertionError('no compiler')):
            report=c.inspect(p,b.sha(p/'manifest.json'));self.assertTrue(all(report['copy_phase_checks'].values()))
            for fault in ('omit','commands','deadline','third','bool','root','header'):
                bad=copy.deepcopy(m)
                if fault=='omit':bad['inputs_sha256'].pop(str(b.phase.BODY))
                if fault=='commands':bad['commands'][1]['command'].remove('-mcpu=cortex-a76')
                if fault=='deadline':bad['copy_phase_contract']['loader_outer_seconds']=61
                if fault=='third':bad['copy_phase_contract']['copy_renewal_max']=3
                if fault=='bool':bad['copy_phase_contract']['post_readback_renewal']=0
                if fault=='root':bad['root_nodes']=32
                if fault=='header':bad['headers_sha256'].pop(str(b.phase.BODY))
                read=b.document
                with patch.object(b,'document',side_effect=lambda name:bad if Path(name)==p/'manifest.json' else read(name)):
                    with self.assertRaises((ValueError,KeyError)):c.inspect(p)

    @unittest.skipUnless(os.environ.get('RPI5_RESTART_COPY_PACKAGE'),'Actual package required')
    def test_actual_native_materialization(self):
        from tools.rpi5 import display_restart_native as native
        view=types.SimpleNamespace(inspect=c.inspect,b=b.prior.original)
        fn=types.FunctionType(native.inspect.__code__,dict(vars(native),check=view),argdefs=native.inspect.__defaults__)
        result=fn(Path(os.environ['RPI5_RESTART_COPY_PACKAGE']))
        self.assertTrue(result['exact_same_image_bytes']);self.assertFalse(result['target_executed'])

if __name__=='__main__':unittest.main()
