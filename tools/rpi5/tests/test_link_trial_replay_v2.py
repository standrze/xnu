# SPDX-License-Identifier: BSD-2-Clause
"""Offline reporting wrapper guards, not a physical restoration proof."""
import ast
import json
import subprocess
import unittest
from unittest.mock import patch
from tools.rpi5 import replay_link_trial_v2 as replay


class ReplayTests(unittest.TestCase):
    def test_exact_program_isolated_and_no_hardware_api(self):
        tree=ast.parse(replay.PROGRAM)
        calls=[ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)]
        self.assertNotIn('subprocess.run',calls);self.assertNotIn('os.open',calls)
        self.assertNotIn('stage.dispatch',calls);self.assertNotIn('stage.launch',calls)
        self.assertIn('stage.prepare_restore',calls);self.assertIn('stage.engine.validate_result',calls)
        self.assertIn('stage.subprocess.run=forbidden',replay.PROGRAM)
        self.assertIn('stage.prior.validate_result=forbidden',replay.PROGRAM)
        self.assertIn("context['descriptor']['checker'].inspect=forbidden",replay.PROGRAM)

    def test_child_failure_is_not_reported_as_success(self):
        with patch.object(replay.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'{"fake":true}','expected failure')):
            with self.assertRaisesRegex(ValueError,'expected failure'):replay.run({'fixture':True})

    def test_wrapper_records_own_source_outside_admission_seal(self):
        with patch.object(replay.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'{"offline_fixture":true}','')) as run:
            report=replay.run({'fixture':True})
        command=run.call_args.args[0]
        self.assertEqual(command[1:3],['-c',replay.PROGRAM]);self.assertEqual(json.loads(command[3]),{'fixture':True})
        self.assertFalse(report['wrapper_part_of_original_admission_seal'])
        self.assertEqual(len(report['replay_wrapper_sha256']),64);self.assertEqual(len(report['isolated_program_sha256']),64)


if __name__=='__main__':unittest.main()
