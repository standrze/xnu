# SPDX-License-Identifier: BSD-2-Clause
"""Write-profile metadata rejection fixtures; not linked bytes or board proof."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_hfs_write_package as checker


class HFSWritePackageTests(unittest.TestCase):
    def fixture(self):
        return (
            dict(gate4_hfs_write_trial=True, gate4_storage_binding_snapshot=True,
                 gate4_sd_readonly=False, gate4_hfs_readonly=False,
                 commands=[['clang', 'probe_main.c', '-DRPI5_GATE4_STORAGE=1',
                            '-DRPI5_GATE4_HFS_WRITE_TRIAL=1', '-DRPI5_GATE4_SD_READONLY=0',
                            '-DRPI5_GATE4_HFS_READONLY=0']]),
            dict(hfs_write_trial=True, hfs_read_trial=False, sd_read_trial=False),
            dict(exit_code=0, fresh_kernel_outputs=True, source_unchanged_during_build=True,
                 storage_provider=dict(write_trial=True), command=['RPI5_STORAGE_WRITE_TRIAL=1']),
            dict(write_trial=True, adapted=True, all_core_units=True, all_screened_units_compiled=True,
                 partial_link=dict(returncode=0, missing_required_definitions=[],
                                   not_defined_in_reference_kernel=[], forbidden_profile_definitions=[])))

    def test_complete_fixture_only_proves_metadata_shape(self):
        self.assertTrue(all(checker.profile_checks(*self.fixture()).values()))

    def test_missing_or_ambiguous_each_profile_flag_fails(self):
        original = self.fixture()
        for index, keys in ((0, ('gate4_hfs_write_trial', 'gate4_storage_binding_snapshot',
                                'gate4_sd_readonly', 'gate4_hfs_readonly')),
                            (1, ('hfs_write_trial', 'hfs_read_trial', 'sd_read_trial')),
                            (2, ('fresh_kernel_outputs', 'source_unchanged_during_build')),
                            (3, ('write_trial', 'adapted', 'all_core_units', 'all_screened_units_compiled'))):
            for key in keys:
                for value in (None, int(original[index][key]), not original[index][key]):
                    with self.subTest(index=index, key=key, value=value):
                        fixture = copy.deepcopy(original)
                        fixture[index][key] = value
                        self.assertFalse(all(checker.profile_checks(*fixture).values()))

    def test_each_compile_switch_and_exclusivity_proof_is_required(self):
        original = self.fixture()
        for item in original[0]['commands'][0][2:]:
            fixture = copy.deepcopy(original)
            fixture[0]['commands'][0].remove(item)
            self.assertFalse(all(checker.profile_checks(*fixture).values()))
        for key in ('missing_required_definitions', 'not_defined_in_reference_kernel', 'forbidden_profile_definitions'):
            for value in (None, ['opposite-class-or-missing-symbol']):
                fixture = copy.deepcopy(original)
                fixture[3]['partial_link'][key] = value
                self.assertFalse(all(checker.profile_checks(*fixture).values()))
        fixture = copy.deepcopy(original)
        fixture[2]['command'] = []
        self.assertFalse(all(checker.profile_checks(*fixture).values()))
        fixture = copy.deepcopy(original)
        fixture[2]['storage_provider']['write_trial'] = False
        self.assertFalse(all(checker.profile_checks(*fixture).values()))


if __name__ == '__main__':
    unittest.main()
