# SPDX-License-Identifier: BSD-2-Clause
"""Installer guard/profile tests; not SD/FAT or board validation."""
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
import stage_pcie_topology as stage


class TopologyStageTests(unittest.TestCase):
    def test_local_plan_rejects_wrong_boot_and_changed_history(self):
        with self.assertRaises(ValueError): stage.load_plan(Path('/not-a-package'), 'not-a-uuid')
        with tempfile.TemporaryDirectory() as directory:
            control = Path(directory); (control / 'plan.json').write_text('{}')
            with patch.object(stage, 'CONTROL', control), self.assertRaisesRegex(ValueError, 'control plan changed'):
                stage.load_plan(Path('/not-a-package'), '36ac234c-2a31-4b30-bb5d-de87fa5bd8e2')

    def test_remote_program_compiles_and_refuses_changed_source(self):
        sources = [Path(stage.capture.__file__), Path(stage.install_core.__file__), Path(stage.snapshots.__file__)]
        plan = {'source_sha256': {str(path): stage.terminal.sha256(path) for path in sources}}
        compile(stage.remote_source(plan), '<guarded-remote-stage>', 'exec')
        plan['source_sha256'][str(sources[0])] = '0' * 64
        with self.assertRaises(ValueError): stage.remote_source(plan)
        # The stager cannot itself launch a boot, issue card commands or mount HFS.
        for forbidden in ('vcmailbox', "['reboot'", 'ioctl(', "['mount','/dev/mmcblk0p2'"):
            self.assertNotIn(forbidden, stage.REMOTE)

    def test_gate5_profile_keeps_all_old_files_and_refuses_repeat(self):
        core = stage.install_core
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory); boot = work / 'boot'; boot.mkdir()
            old, new = b'old held W3', b'new declarations only'
            (boot / 'probe.bin').write_bytes(old); (work / 'candidate').write_bytes(new)
            previous = boot / 'probe.hfs-write-cache-probe-failed-20261012.bin'
            previous.write_bytes(b'earlier W2')
            dirfd = os.open(boot, os.O_RDONLY | os.O_DIRECTORY)
            candidate = os.open(work / 'candidate', os.O_RDONLY)
            try:
                a, b = (hashlib.sha256(value).hexdigest() for value in (old, new))
                result = core.install(dirfd, candidate, a, b, 'pcie-topology')
                self.assertEqual((boot / result['sd_backup']).read_bytes(), old)
                self.assertEqual(previous.read_bytes(), b'earlier W2')
                self.assertEqual((boot / 'probe.bin').read_bytes(), new)
                with self.assertRaises(ValueError): core.install(dirfd, candidate, a, b, 'pcie-topology')
            finally: os.close(candidate); os.close(dirfd)

    def test_result_requires_complete_protected_bytes_backups_and_identity(self):
        plan = {'run': '/home/sandrzej/xnu-gate5-topology-abcdefgh', 'new_image_sha256': 'a'*64,
            'linux_boot_id': 'boot', 'identity_binding': {'expected': {'fixed': 'identity'}},
            'nvme_backups': ['twenty separately pinned records'],
            'protected_sha256': {'mbr': 'b'*64, 'boot': 'c'*64, 'hfs': 'd'*64}}
        result = dict(status='installed', run=plan['run'], image_sha256='a'*64,
            preserved_sd_image_sha256=stage.W3, nvme_previous_image_sha256=stage.W3,
            boot_unmounted=True, no_hfs_mount=True, no_config_change=True, no_reboot=True,
            power_loss_atomicity_claimed=False, temporary_published=True,
            sd_backup=stage.install_core.INSTALL_NAMES['pcie-topology'][0],
            nvme_backups_verified=plan['nvme_backups'],
            identity={'identity': {'fixed': 'identity'}, 'boot_id': 'boot', 'hostname': 'kamidana'})
        result['protected_files_sha256'] = dict(stage.PROTECTED,
            **{'probe.bin': 'a'*64, result['sd_backup']: stage.W3})
        rows = [('mbr', '/dev/mmcblk0', 512, 'mbr.before-write.bin'),
                ('boot', '/dev/mmcblk0p1', 536870912, 'boot-partition.before-write.img'),
                ('hfs', '/dev/mmcblk0p2', 134217728, 'hfs-partition.before.img')]
        result['protected_after'] = {key: dict(device=node, bytes=size,
            sha256='e'*64 if key == 'boot' else plan['protected_sha256'][key]) for key,node,size,_ in rows}
        result['backups'] = [dict(device=node, bytes=size, sha256=plan['protected_sha256'][key], saved_as=name)
            for key,node,size,name in rows]
        stage.validate_result(result, plan)
        for key in list(result):
            bad = copy.deepcopy(result); del bad[key]
            with self.subTest(missing=key), self.assertRaises(ValueError): stage.validate_result(bad, plan)
        for key in ('mbr','hfs'):
            bad = copy.deepcopy(result); bad['protected_after'][key]['sha256'] = 'f'*64
            with self.assertRaises(ValueError): stage.validate_result(bad, plan)


if __name__ == '__main__': unittest.main()
