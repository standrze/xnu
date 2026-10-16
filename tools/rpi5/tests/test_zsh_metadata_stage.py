# SPDX-License-Identifier: BSD-2-Clause
"""Offline current-baseline preservation tests; no device/network access."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import stage_zsh_metadata_trial as stage

BOOT = 'deadbeef-0000-0000-0000-000000000001'


class MetadataStageTests(unittest.TestCase):
    def plan(self):
        with patch.object(stage.package_check, 'inspect', return_value=dict(image='/candidate', image_sha256='a'*64)):
            return stage.load_plan(Path('/candidate'), BOOT)

    def result(self, plan):
        result = json.loads((stage.HISTORY/'result.json').read_text())
        backup = stage.base.install_core.INSTALL_NAMES[stage.PROFILE][0]
        result.update(run=plan['run'], image_sha256='a'*64, preserved_sd_image_sha256=stage.OLD_SHA,
                      nvme_previous_image_sha256=stage.OLD_SHA, sd_backup=backup,
                      nvme_backups_verified=plan['nvme_backups'],
                      identity=dict(identity=plan['identity_binding']['expected'], boot_id=BOOT, hostname='kamidana'),
                      protected_files_sha256=dict(plan['protected_files'], **{'probe.bin':'a'*64, backup:stage.OLD_SHA}))
        result['backups'][1]['sha256'] = stage.FAT_SHA
        result['protected_after']['boot']['sha256'] = 'b'*64
        return result

    def test_full_current_baseline_chain_and_only_fixed_substitutions(self):
        plan = self.plan()
        self.assertEqual(len(plan['nvme_backups']), 32)
        self.assertEqual(plan['nvme_backups'][-1]['sha256'], stage.previous.OLD_SHA)
        self.assertEqual(plan['nvme_backups'][-1]['bytes'], 18008768)
        self.assertEqual(plan['protected_sha256']['boot'], stage.FAT_SHA)
        self.assertIn('probe.zsh-interactive-passed-20261012.bin', plan['protected_files'])
        self.assertEqual(plan['old_image_sha256'], stage.OLD_SHA)
        source = stage.remote_source(plan)
        compile(source, '<metadata-remote>', 'exec')
        self.assertEqual(stage.remote_template().count(repr(stage.PREVIOUS_NAME)), 3)
        self.assertIn(",'zsh-metadata-trial')", stage.remote_template())
        self.assertNotIn(",'statprobe-trial')", stage.remote_template())

    def test_same_boot_bad_uuid_history_or_source_drift_rejected(self):
        old_boot = json.loads((stage.HISTORY/'result.json').read_text())['identity']['boot_id']
        for boot in (old_boot, '', '../bad', 'DEADBEEF-0000-0000-0000-000000000001'):
            with self.subTest(boot=boot), self.assertRaises(ValueError):
                stage.load_plan(Path('/candidate'), boot)
        with patch.object(stage, 'HISTORY_SHA', {'result.json':'0'*64}), self.assertRaises(ValueError):
            stage.load_plan(Path('/candidate'), BOOT)
        plan = self.plan()
        plan['source_sha256'][str(Path(stage.__file__))] = '0'*64
        with self.assertRaises(ValueError): stage.remote_source(plan)
        with patch.object(stage.previous, 'remote_template', return_value='changed'), self.assertRaises(ValueError):
            stage.remote_template()

    def test_receipt_requires_every_identity_backup_and_protection_field(self):
        plan = self.plan(); plan['run'] = '/home/sandrzej/xnu-gate6-metadata-abcdefgh'
        result = self.result(plan)
        stage.validate_result(result, plan)
        for name in result:
            bad = copy.deepcopy(result); del bad[name]
            with self.subTest(missing=name), self.assertRaises(ValueError): stage.validate_result(bad, plan)
        for field in ('mbr', 'hfs'):
            bad = copy.deepcopy(result); bad['protected_after'][field]['sha256'] = '0'*64
            with self.assertRaises(ValueError): stage.validate_result(bad, plan)
        for field in ('nvme_backups_verified', 'backups'):
            bad = copy.deepcopy(result); bad[field] = bad[field][:-1]
            with self.assertRaises(ValueError): stage.validate_result(bad, plan)

    def test_fixed_new_profile_preserves_current_and_prior_images_no_retry(self):
        core = stage.base.install_core
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); boot = root/'boot'; boot.mkdir()
            old, new = b'physically diagnosed image', b'corrective metadata kernel'
            (boot/'probe.bin').write_bytes(old); (root/'candidate').write_bytes(new)
            preserved = 'probe.zsh-interactive-passed-20261012.bin'
            (boot/preserved).write_bytes(b'working zsh')
            d, c = os.open(boot, os.O_RDONLY|os.O_DIRECTORY), os.open(root/'candidate', os.O_RDONLY)
            try:
                old_sha, new_sha = [hashlib.sha256(v).hexdigest() for v in (old,new)]
                result = core.install(d,c,old_sha,new_sha,stage.PROFILE)
                self.assertEqual((boot/result['sd_backup']).read_bytes(), old)
                self.assertEqual((boot/'probe.bin').read_bytes(), new)
                self.assertEqual((boot/preserved).read_bytes(), b'working zsh')
                self.assertFalse(result['power_loss_atomicity_claimed'])
                with self.assertRaises(ValueError): core.install(d,c,old_sha,new_sha,stage.PROFILE)
            finally:
                os.close(c); os.close(d)


if __name__ == '__main__':
    unittest.main()
