# SPDX-License-Identifier: BSD-2-Clause
import copy
import unittest
from tools.rpi5 import check_watchdog_recovery_evidence as checker


class RecoveryEvidenceTests(unittest.TestCase):
    def test_actual_saved_physical_capture_install_and_restore_replay(self):
        report=checker.inspect()
        self.assertTrue(report['recovery_trial_pass']); self.assertTrue(report['working_zsh_image_restored'])
        self.assertTrue(report['autonomous_reset_and_nvme_return_observed'])
        self.assertEqual(report['next_inherited_artifact_count'],52)
        self.assertFalse(report['ethernet_ready']); self.assertFalse(report['pcie_access_admitted'])

    def test_journal_gaps_nonfinite_regression_and_incomplete_coverage_rejected(self):
        rows=[dict(offset=0,bytes=2,monotonic=1.,utc='2026-10-13T03:00:00+00:00'),
              dict(offset=2,bytes=2,monotonic=2.,utc='2026-10-13T03:00:01+00:00')]
        checker.journal(b'abcd',rows)
        for key,value in (('offset',3),('bytes',0),('monotonic',float('nan')),('monotonic',.5)):
            bad=copy.deepcopy(rows);bad[1][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):checker.journal(b'abcd',bad)
        with self.assertRaises(ValueError):checker.journal(b'abcde',rows)


if __name__=='__main__':unittest.main()
