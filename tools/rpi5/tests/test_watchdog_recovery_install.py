# SPDX-License-Identifier: BSD-2-Clause
"""Real file-copy/publication with explicit mount/block/identity doubles."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

from tools.rpi5 import recovery_trial_install_core as core
from tools.rpi5 import probe_install_core as helper
from tools.rpi5 import pcie_recovery_reference_core as reference
from tools.rpi5 import stage_watchdog_recovery_trial as stage

BOOT = '8512e93e-ec70-4715-bb02-d118afe393ed'
def digest(data): return hashlib.sha256(data).hexdigest()


class RecoveryInstallTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        with tempfile.TemporaryDirectory(prefix='recovery-install-test-') as name:
            parent = Path(name).resolve(); boot = parent/'boot'; boot.mkdir(); work = parent/'work'; work.mkdir()
            old, new = b'working zsh image'*17, b'standalone watchdog-only image'*7
            config = b'[all]\nkernel=probe.bin\narmstub=bl31.bin\nset_reboot_order=0xf6\nkernel_watchdog_timeout=60\n'
            (boot/'probe.bin').write_bytes(old); (boot/'config.txt').write_bytes(config); (work/'candidate.bin').write_bytes(new)
            plan = dict(profile='watchdog-only-trial', old_image_sha256=digest(old), new_image_sha256=digest(new),
                run=str(work), linux_boot_id=BOOT, identity_binding=dict(expected=dict(root='SSD ext4 uuid')),
                nvme_backups=[dict(path='preserved-'+str(i)) for i in range(44)],
                protected_files={'config.txt':digest(config)}, protected_sha256={k:digest(k.encode()) for k,*_ in core.EXTENTS})
            state = dict(mounted=False, mode=None, id=42, lookups=0, replace=False, fail_rw=False, commands=[], verifies=0)
            identity = dict(identity=plan['identity_binding']['expected'], boot_id=BOOT, hostname='kamidana')
            def verify(p):
                self.assertEqual(p['nvme_backups'], plan['nvme_backups']); state['verifies'] += 1
            capture = types.SimpleNamespace(identity=lambda p:copy.deepcopy(identity), verify_backups=verify,
                command=lambda *args:'SSD ext4 uuid', full_hash=lambda p,size:digest(Path(p).read_bytes()))
            def block(node, capacity, length, directory=None, filename=None):
                key = next(k for k,n,*_ in core.EXTENTS if n == node)
                if directory is not None: (work/filename).write_bytes(key.encode())
                return dict(device=node, bytes=length, sha256=digest(key.encode()), saved_as=filename)
            snapshots = types.SimpleNamespace(block_snapshot=block)
            def run(args):
                state['commands'].append(args)
                if args[0] == 'findmnt':
                    if not state['mounted']: return subprocess.CompletedProcess(args, 1, '', '')
                    state['lookups'] += 1
                    row = dict(id=42+(state['replace'] and state['lookups'] > 1), source=core.NODE, fstype='vfat',
                        target=str(boot), options=state['mode']+',nosuid,nodev,noexec,relatime')
                    return subprocess.CompletedProcess(args, 0, json.dumps({'filesystems':[row]}), '')
                if args[0] == 'mount':
                    if 'remount,rw,nosuid,nodev,noexec' in args and state['fail_rw']:
                        return subprocess.CompletedProcess(args, 1, '', 'denied')
                    state['mounted'] = True; state['mode'] = 'rw' if any('remount,rw' in a for a in args) else 'ro'
                elif args[0] == 'umount': state['mounted'] = False
                else: raise AssertionError(args)
                return subprocess.CompletedProcess(args, 0, '', '')
            real_stat, real_iterdir, real_read_text = Path.stat, Path.iterdir, Path.read_text
            real_open, real_close = os.open, os.close
            opened = set()
            def tracked_open(path, *args, **kwargs):
                fd = real_open(path, *args, **kwargs)
                if Path(path) == boot: opened.add(fd)
                return fd
            def tracked_close(fd):
                opened.discard(fd); return real_close(fd)
            original_run = run
            def checked_run(args):
                if args[0] == 'umount': self.assertFalse(opened, 'Live directory FD would keep Linux mount busy')
                return original_run(args)
            def stat(path, *args, **kwargs):
                return real_stat(work if path == Path('/') else path, *args, **kwargs)
            def iterdir(path): return iter(()) if path == boot else real_iterdir(path)
            def read_text(path, *args, **kwargs):
                return BOOT if path == Path('/proc/sys/kernel/random/boot_id') else real_read_text(path, *args, **kwargs)
            with patch.object(core, 'MOUNTPOINT', str(boot)), patch.object(core.os, 'geteuid', return_value=0), \
                    patch.object(core.os, 'open', tracked_open), patch.object(core.os, 'close', tracked_close), \
                    patch.object(Path, 'stat', stat), patch.object(Path, 'iterdir', iterdir), patch.object(Path, 'read_text', read_text):
                yield plan, capture, snapshots, checked_run, state, boot, work, old, new

    def test_full_snapshot_owned_mount_actual_copy_publish_and_cleanup(self):
        with self.fixture() as (plan, capture, snapshots, run, state, boot, work, old, new):
            result = core.execute(plan, capture, helper, snapshots, reference, run)
            stage.validate_result(result, plan)
            self.assertEqual((boot/'probe.bin').read_bytes(), new)
            self.assertEqual((boot/core.NAMES[plan['profile']][0]).read_bytes(), old)
            self.assertEqual((work/core.NAMES[plan['profile']][2]).read_bytes(), old)
            self.assertFalse(state['mounted']); self.assertEqual(state['verifies'], 2)
            self.assertEqual([c[0] for c in state['commands']].count('umount'), 1)
            self.assertFalse(result['power_loss_atomicity_claimed'])
            for key in ('boot_unmounted','no_config_change','no_hfs_mount','no_reboot'):
                bad = copy.deepcopy(result); bad[key] = 1
                with self.assertRaises(ValueError): stage.validate_result(bad, plan)

    def test_wrong_raw_baseline_never_mounts_or_writes_sd(self):
        with self.fixture() as (plan, capture, snapshots, run, state, boot, work, old, new):
            plan['protected_sha256']['hfs'] = '0'*64
            with self.assertRaisesRegex(ValueError, 'baseline differs'): core.execute(plan, capture, helper, snapshots, reference, run)
            self.assertFalse(state['commands']); self.assertEqual((boot/'probe.bin').read_bytes(), old)

    def test_replaced_mount_is_never_remounted_or_unmounted(self):
        with self.fixture() as (plan, capture, snapshots, run, state, boot, work, old, new):
            state['replace'] = True
            with self.assertRaisesRegex(ValueError, 'Mount replaced'): core.execute(plan, capture, helper, snapshots, reference, run)
            self.assertTrue(state['mounted']); self.assertEqual((boot/'probe.bin').read_bytes(), old)
            self.assertEqual([c[0] for c in state['commands']].count('mount'), 1)
            self.assertNotIn('umount', [c[0] for c in state['commands']])

    def test_failed_rw_remount_cleans_only_owned_mount_no_publication(self):
        with self.fixture() as (plan, capture, snapshots, run, state, boot, work, old, new):
            state['fail_rw'] = True
            with self.assertRaisesRegex(ValueError, 'Mount operation'): core.execute(plan, capture, helper, snapshots, reference, run)
            self.assertFalse(state['mounted']); self.assertEqual((boot/'probe.bin').read_bytes(), old)
            self.assertEqual((work/core.NAMES[plan['profile']][2]).read_bytes(), old)

    def test_failed_temporary_readback_retains_old_backup_and_partial(self):
        original = helper.copy_image
        def fault(source, directory, name, expected):
            original(source, directory, name, expected)
            if name.endswith('.tmp'): raise ValueError('injected temporary failure')
        with self.fixture() as (plan, capture, snapshots, run, state, boot, work, old, new), \
                patch.object(helper, 'copy_image', side_effect=fault):
            with self.assertRaisesRegex(ValueError, 'temporary failure'): core.execute(plan, capture, helper, snapshots, reference, run)
            self.assertFalse(state['mounted']); self.assertEqual((boot/'probe.bin').read_bytes(), old)
            self.assertEqual((boot/core.NAMES[plan['profile']][0]).read_bytes(), old)
            self.assertTrue((boot/core.NAMES[plan['profile']][1]).exists())

    def test_after_rename_failure_does_not_automatically_restore_or_retry(self):
        original = os.rename
        def fault(*args, **kwargs): original(*args, **kwargs); raise ValueError('injected post-publication failure')
        with self.fixture() as (plan, capture, snapshots, run, state, boot, work, old, new), \
                patch.object(core.os, 'rename', side_effect=fault) as rename:
            with self.assertRaisesRegex(ValueError, 'post-publication'): core.execute(plan, capture, helper, snapshots, reference, run)
            self.assertEqual(rename.call_count, 1); self.assertFalse(state['mounted'])
            self.assertEqual((boot/'probe.bin').read_bytes(), new)
            self.assertEqual((boot/core.NAMES[plan['profile']][0]).read_bytes(), old)
            self.assertFalse((work/'result.json').exists())

    def test_wrong_mount_options_source_id_and_ambiguity_refused(self):
        row = dict(id=42, source=core.NODE, fstype='vfat', target=core.MOUNTPOINT, options='ro,nosuid,nodev,noexec')
        def run(rows): return lambda args:subprocess.CompletedProcess(args, 0, json.dumps({'filesystems':rows}), '')
        self.assertEqual(core.mount_record(run([row]), 'ro')['id'], 42)
        for key,value in (('id',True),('id',0),('source','/dev/nvme0n1p1'),('options','rw,nosuid,nodev,noexec'),('target','/')):
            with self.subTest(key=key), self.assertRaises(ValueError): core.mount_record(run([dict(row, **{key:value})]), 'ro')
        with self.assertRaises(ValueError): core.mount_record(run([row,row]))

    def test_actual_pinned_44_artifact_plan_and_generated_remote_compile_no_network(self):
        original = stage.subprocess.run
        def no_network(args, *rest, **kwargs):
            if args[0] in ('ssh', 'scp'): raise AssertionError('No network in planning')
            return original(args, *rest, **kwargs)
        with patch.object(stage.subprocess, 'run', side_effect=no_network):
            plan = stage.load_plan(BOOT)
            self.assertEqual(len(plan['nvme_backups']), 44)
            self.assertEqual(plan['old_image_sha256'], stage.prior.NEW_SHA)
            self.assertEqual(plan['new_image_sha256'], stage.IMAGE_SHA)
            plan['run'] = '/home/sandrzej/xnu-gate5-watchdog-12345678'
            compile(stage.remote_source(plan), '<guarded-remote>', 'exec')
        for bad in ('invalid', 'A'*36):
            with self.assertRaises(ValueError): stage.load_plan(bad)

    def test_guarded_publisher_existing_backup_refuses_retry(self):
        with self.fixture() as (plan, capture, snapshots, run, state, boot, work, old, new):
            (boot/core.NAMES[plan['profile']][0]).write_bytes(b'previous partial artifact')
            with self.assertRaisesRegex(ValueError, 'Partial/existing'): core.execute(plan, capture, helper, snapshots, reference, run)
            self.assertEqual((boot/'probe.bin').read_bytes(), old); self.assertFalse(state['mounted'])

    def test_explicit_restore_profile_uses_distinct_names_and_preserves_trial(self):
        with self.fixture() as (plan, capture, snapshots, run, state, boot, work, old, new):
            plan['profile'] = 'watchdog-only-restore'
            result = core.execute(plan, capture, helper, snapshots, reference, run)
            stage.validate_result(result, plan)
            self.assertEqual(result['sd_backup'], 'probe.watchdog-only-trial-20261012.bin')
            self.assertEqual((boot/result['sd_backup']).read_bytes(), old)
            self.assertEqual((work/'watchdog-only-trial.bin').read_bytes(), old)
            self.assertEqual((boot/'probe.bin').read_bytes(), new)

    def test_restore_plan_inherits_48_artifacts_and_requires_new_linux_boot(self):
        plan = stage.load_plan(BOOT); plan['run'] = '/home/sandrzej/xnu-gate5-watchdog-12345678'
        backup = core.NAMES[plan['profile']][0]
        result = dict(status='installed', run=plan['run'], image_sha256=plan['new_image_sha256'],
            preserved_sd_image_sha256=plan['old_image_sha256'], nvme_previous_image_sha256=plan['old_image_sha256'],
            boot_unmounted=True, no_hfs_mount=True, no_config_change=True, no_reboot=True,
            power_loss_atomicity_claimed=False, temporary_published=True, sd_backup=backup,
            nvme_backups_verified=plan['nvme_backups'],
            identity=dict(identity=plan['identity_binding']['expected'],boot_id=BOOT,hostname='kamidana'),
            protected_files_sha256=dict(plan['protected_files'], **{'probe.bin':stage.IMAGE_SHA,backup:stage.prior.NEW_SHA}),
            backups=[dict(device=node,bytes=length,sha256=plan['protected_sha256'][key],saved_as=name)
                     for key,node,_,length,name in core.EXTENTS],
            protected_after={key:dict(device=node,bytes=length,sha256=plan['protected_sha256'][key])
                             for key,node,_,length,_ in core.EXTENTS})
        with tempfile.TemporaryDirectory(prefix='recovery-receipt-test-',dir=stage.ROOT/'build/rpi5') as name:
            directory = Path(name)
            (directory/'plan.json').write_text(json.dumps(plan)); (directory/'result.json').write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError,'Distinct Linux return'): stage.load_plan(BOOT,directory)
            restored = stage.load_plan('9512e93e-ec70-4715-bb02-d118afe393ed',directory)
            self.assertEqual(len(restored['nvme_backups']),48)
            self.assertEqual(restored['profile'],'watchdog-only-restore')
            self.assertEqual(restored['old_image_sha256'],stage.IMAGE_SHA)
            self.assertEqual(restored['new_image_sha256'],stage.prior.NEW_SHA)


if __name__ == '__main__': unittest.main()
