# SPDX-License-Identifier: BSD-2-Clause
"""Explicit latest late-PID1 restoration fixture, byte-only and never staging.

Caller supplies the separately retained actual receipt pins. Missing pins fail
rather than silently selecting an old operational baseline or skipping proof.
"""
import copy
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from tools.rpi5 import stage_gem_cpu_batch_trial_v1 as stage
class LatestCPUBatchIntakeTests(unittest.TestCase):
    def test_actual_completed_late_pid1_restoration_byte_only(self):
        keys=('RPI5_CPU_BATCH_BASELINE','RPI5_CPU_BATCH_BASELINE_SEAL',
              'RPI5_CPU_BATCH_BASELINE_PLAN','RPI5_CPU_BATCH_BASELINE_RESULT')
        values=[os.environ.get(key) for key in keys]
        if not all(values):self.fail('Supply the exact main-retained late-PID1 restoration path/seal/plan/result pins')
        directory=Path(values[0]).resolve();seal,plan,result=values[1:]
        self.assertEqual(stage.sha(directory/'result.json'),result)
        with patch.object(subprocess,'run',side_effect=AssertionError('No compiler/history/SSH/hardware')),\
            patch.object(stage.preceding.checker,'inspect',side_effect=AssertionError('No predecessor semantic replay')):
            value=stage.baseline(directory,seal,plan)
            self.assertEqual(value['plan']['media']['controller'],stage.preceding.CONTROLLER)
            self.assertEqual(value['plan']['media']['profile'],stage.preceding.engine.RESTORE)
            self.assertEqual(len(value['result']['next_catalog']),454)
            self.assertEqual(value['result']['publication']['protected_files_sha256']['config.txt'],stage.engine.ORIGINAL_CONFIG_SHA)
            for bad_seal,bad_plan in (('0'*64,plan),(seal,'0'*64)):
                with self.assertRaises(ValueError):stage.baseline(directory,bad_seal,bad_plan)
            for name in stage.GOOD:
                bad=copy.deepcopy(value);bad['result']['publication']['protected_files_sha256'][name]='0'*64
                with patch.object(stage.preceding,'restoration',return_value=bad),self.assertRaises(ValueError):stage.baseline(directory,seal,plan)
if __name__=='__main__':unittest.main()
