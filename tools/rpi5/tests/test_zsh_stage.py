# SPDX-License-Identifier: BSD-2-Clause
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_zsh_trial as stage


class ZshStageTests(unittest.TestCase):
    def test_history_expands_exactly_and_preserves_independent_w3_size(self):
        report = {'image': '/candidate', 'image_sha256': 'a' * 64}
        with patch.object(stage.package_check, 'inspect', return_value=report):
            plan = stage.load_plan(Path('/candidate'), '67033e75-2d50-40fa-a871-1a3eb05ff10a')
        self.assertEqual(len(plan['nvme_backups']), 24)
        self.assertEqual(plan['nvme_backups'][-1]['bytes'], 18163520)
        self.assertEqual(plan['nvme_backups'][-1]['sha256'], stage.previous.W3)
        self.assertEqual(plan['protected_sha256']['boot'], stage.FAT_SHA)
        self.assertEqual(plan['identity_binding']['linux_boot_id_after_write'], plan['linux_boot_id'])
        with patch.object(stage.package_check, 'inspect', return_value=report), self.assertRaises(ValueError):
            stage.load_plan(Path('/candidate'), '36ac234c-2a31-4b30-bb5d-de87fa5bd8e2')

    def test_remote_template_and_source_drift_fail_before_execution(self):
        files = [Path(stage.__file__), Path(stage.previous.__file__),
                 Path(stage.previous.capture.__file__), Path(stage.previous.install_core.__file__),
                 Path(stage.previous.snapshots.__file__)]
        plan = {'source_sha256': {str(path): stage.previous.terminal.sha256(path) for path in files}}
        compile(stage.remote_source(plan), '<zsh-remote>', 'exec')
        remote = stage.remote_template()
        self.assertEqual(remote.count(repr(stage.PREVIOUS_NAME)), 3)
        self.assertIn(",'zsh-trial')", remote)
        for word in ('vcmailbox', "['reboot'", 'CMD49', "['mount','/dev/mmcblk0p2'"):
            self.assertNotIn(word, remote)
        plan['source_sha256'][str(files[0])] = '0' * 64
        with self.assertRaises(ValueError): stage.remote_source(plan)
        with patch.object(stage.previous, 'REMOTE', 'different template'), self.assertRaises(ValueError):
            stage.remote_template()

    def test_distinct_profile_preserves_prior_images_and_refuses_repeat(self):
        core = stage.previous.install_core
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory); boot = work / 'boot'; boot.mkdir()
            old, new = b'passed topology', b'zsh diagnostic'
            (boot / 'probe.bin').write_bytes(old)
            (work / 'candidate.bin').write_bytes(new)
            earlier = boot / 'probe.hfs-cache-buffer-failed-20261012.bin'
            earlier.write_bytes(b'preserve W3')
            d = os.open(boot, os.O_RDONLY | os.O_DIRECTORY)
            c = os.open(work / 'candidate.bin', os.O_RDONLY)
            try:
                a, b = [hashlib.sha256(x).hexdigest() for x in (old, new)]
                result = core.install(d, c, a, b, 'zsh-trial')
                self.assertEqual((boot / result['sd_backup']).read_bytes(), old)
                self.assertEqual(earlier.read_bytes(), b'preserve W3')
                with self.assertRaises(ValueError): core.install(d, c, a, b, 'zsh-trial')
            finally:
                os.close(c); os.close(d)

    def test_outcome_requires_every_protection_record(self):
        plan = {'run': '/home/sandrzej/xnu-gate6-zsh-abcdefgh', 'new_image_sha256': 'a'*64,
                'linux_boot_id': 'boot', 'identity_binding': {'expected': {'card': 'fixed'}},
                'nvme_backups': ['24 pinned backups'], 'protected_files': {'config.txt': 'b'*64},
                'protected_sha256': {'mbr': 'c'*64, 'boot': 'd'*64, 'hfs': 'e'*64}}
        backup = stage.previous.install_core.INSTALL_NAMES['zsh-trial'][0]
        result = dict(status='installed', run=plan['run'], image_sha256='a'*64,
                      preserved_sd_image_sha256=stage.OLD_SHA, nvme_previous_image_sha256=stage.OLD_SHA,
                      boot_unmounted=True, no_hfs_mount=True, no_config_change=True, no_reboot=True,
                      power_loss_atomicity_claimed=False, temporary_published=True, sd_backup=backup,
                      nvme_backups_verified=plan['nvme_backups'],
                      identity={'identity': {'card': 'fixed'}, 'boot_id': 'boot', 'hostname': 'kamidana'},
                      protected_files_sha256={**plan['protected_files'], 'probe.bin': 'a'*64, backup: stage.OLD_SHA})
        rows = [('mbr','/dev/mmcblk0',512,'mbr.before-write.bin'),
                ('boot','/dev/mmcblk0p1',536870912,'boot-partition.before-write.img'),
                ('hfs','/dev/mmcblk0p2',134217728,'hfs-partition.before.img')]
        result['backups'] = [dict(device=node,bytes=size,sha256=plan['protected_sha256'][key],saved_as=name)
                             for key,node,size,name in rows]
        result['protected_after'] = {key:dict(device=node,bytes=size,
            sha256='f'*64 if key=='boot' else plan['protected_sha256'][key]) for key,node,size,_ in rows}
        stage.validate_result(result, plan)
        for name in result:
            bad = copy.deepcopy(result); del bad[name]
            with self.subTest(missing=name), self.assertRaises(ValueError): stage.validate_result(bad, plan)


if __name__ == '__main__': unittest.main()
