# SPDX-License-Identifier: BSD-2-Clause
import unittest
from unittest.mock import patch
from tools.rpi5 import check_pcie_access_evidence as checker


class AccessEvidenceTests(unittest.TestCase):
    def test_actual_saved_board_trial_and_restore_replay(self):
        r=checker.inspect()
        self.assertTrue(r['read_only_access_trial_pass']);self.assertTrue(r['autonomous_recovery_observed'])
        self.assertTrue(r['working_zsh_image_restored']);self.assertEqual(r['diagnostic']['reads'],30)
        self.assertEqual(r['diagnostic']['elapsed_us'],578620);self.assertEqual(r['next_inherited_artifact_count'],60)
        self.assertTrue(r['project_rc_down_predicate_observed']);self.assertFalse(r['project_link_up_predicate_observed'])
        self.assertFalse(r['nic_ready']);self.assertFalse(r['controller_initialization_admitted'])

    def test_changed_receipt_refused_without_network_or_media_actions(self):
        with patch.dict(checker.RECEIPTS,{checker.INSTALL/'plan.json':'0'*64}),self.assertRaises(ValueError):checker.inspect()


if __name__=='__main__':unittest.main()
