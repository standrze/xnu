# SPDX-License-Identifier: BSD-2-Clause
"""Installer guards and exact remote wrapper with mocked mount/reference I/O.

File publication itself uses real temporary regular files. No SSH, mount,
device opening or firmware change occurs in these host tests.
"""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_hfs_boot as boot
from tools.rpi5.tests import test_hfs_staging as fixture_tests


class HFSBootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def bundle(self):
        staged, plan = fixture_tests.HFSStagingTests().result_bundle()
        hashes = {key: hashlib.sha256(key.encode()).hexdigest()
                  for key in ('fixture', 'baseline', 'reference', 'preflight', 'sd_trial')}
        paths = {}
        for key in hashes:
            paths[key] = self.base / (key + '.json'); paths[key].write_text(key)
        plan.update(sd_trial_image_sha256='c'*64, evidence_sha256=hashes)
        for key, value in (('staging_plan', plan), ('staging_result', staged)):
            paths[key] = self.base / (key+'.json'); paths[key].write_text(json.dumps(value))
        reports = dict(baseline=dict(identity=plan['identity']), fixture=dict(image_sha256=plan['image_sha256']),
                       reference=dict(identity=dict(layout=staged['after_layout'])),
                       sd_trial=dict(image_sha256='c'*64), preflight=dict(image_sha256='d'*64, image='candidate.bin'))
        return paths, reports, hashes

    def test_plan_requires_binding_to_successful_fixture_and_original_sd_proof(self):
        paths, reports, hashes = self.bundle()
        with patch.object(boot.trial, 'load_inputs', return_value=(reports, hashes.copy())):
            plan = boot.load_plan(paths)
        self.assertEqual(plan['backup_run'], json.loads(paths['staging_result'].read_text())['run'])
        self.assertTrue(plan['no_hfs_mount'] and plan['no_reboot'] and plan['no_config_change'])
        for edit in ('baseline', 'fixture', 'sd_image', 'run'):
            paths, reports, hashes = self.bundle()
            if edit == 'run':
                result = json.loads(paths['staging_result'].read_text()); result['run']='/wrong'
                paths['staging_result'].write_text(json.dumps(result))
            else:
                reports = copy.deepcopy(reports)
                if edit == 'baseline': reports['baseline']['identity']['root']='wrong'
                if edit == 'fixture': reports['fixture']['image_sha256']='f'*64
                if edit == 'sd_image': reports['sd_trial']['image_sha256']='f'*64
            with self.subTest(edit=edit), patch.object(boot.trial, 'load_inputs', return_value=(reports, hashes)), \
                    self.assertRaises(ValueError):
                boot.load_plan(paths)

    def argv(self, paths, output, execute=False):
        flags = dict(fixture='fixture',baseline='sd-baseline-reference',reference='reference',
                     preflight='preflight',sd_trial='sd-trial',staging_plan='staging-plan',staging_result='staging-result')
        args = ['stage_hfs_boot.py','--output',str(output)]
        for key, flag in flags.items(): args += ['--'+flag,str(paths[key])]
        return args + (['--execute'] if execute else [])

    def test_local_default_and_invalid_evidence_never_connect(self):
        paths, _, _ = self.bundle()
        output = self.base / 'plan-only'
        with patch.object(sys,'argv',self.argv(paths,output)), \
                patch.object(Path,'is_relative_to',return_value=True), \
                patch.object(boot,'load_plan',return_value={'no_reboot':True}), \
                patch.object(boot.subprocess,'run') as network, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(boot.main(),0)
        network.assert_not_called()
        output = self.base / 'rejected'
        with patch.object(sys,'argv',self.argv(paths,output,True)), \
                patch.object(Path,'is_relative_to',return_value=True), \
                patch.object(boot,'load_plan',side_effect=ValueError('no accepted reads')), \
                patch.object(boot.subprocess,'run') as network, self.assertRaises(ValueError):
            boot.main()
        network.assert_not_called(); self.assertFalse(output.exists())

    def test_remote_timeout_preserves_exact_run_and_partial_diagnostics(self):
        paths, _, _ = self.bundle(); output = self.base / 'unknown'
        plan = dict(candidate='candidate.bin',expected={},fixture_sha256='a'*64)
        responses = [SimpleNamespace(stdout=json.dumps(dict(run='/home/sandrzej/xnu-gate4-hfs-boot-abcdefgh'))),
                     SimpleNamespace(returncode=0), boot.subprocess.TimeoutExpired('ssh',300,output=b'partial',stderr=b'error')]
        with patch.object(sys,'argv',self.argv(paths,output,True)), \
                patch.object(Path,'is_relative_to',return_value=True), \
                patch.object(boot,'load_plan',side_effect=lambda _:copy.deepcopy(plan)), \
                patch.object(boot.subprocess,'run',side_effect=responses) as network, \
                self.assertRaises(boot.subprocess.TimeoutExpired):
            boot.main()
        self.assertEqual(network.call_count,3)
        self.assertEqual((output/'remote.stdout').read_bytes(),b'partial')
        self.assertTrue((output/'outcome-unknown.txt').exists())
        self.assertFalse((output/'result.json').exists())

    def test_reference_program_cannot_clobber_installer_globals(self):
        definitions = boot.REMOTE.split('if os.geteuid()!=0:')[0]
        namespace = dict(REFERENCE_SOURCE="before='wrong'; fd=999; print('{\"verified\":true}')",before='preserved',fd=123)
        exec(definitions, namespace)
        self.assertEqual(namespace['checked_reference'](),dict(verified=True))
        self.assertEqual(namespace['before'],'preserved'); self.assertEqual(namespace['fd'],123)

    def workflow(self, fault=None, profile='initial'):
        base = Path(tempfile.mkdtemp(dir=self.base))
        run = '/home/sandrzej/xnu-gate4-hfs-boot-abcdefgh'
        backup = '/home/sandrzej/xnu-gate4-hfs-stage-abcdefgh'
        mp = '/mnt/xnu-probe'
        roots = {run:base/'run',backup:base/'backup',mp:base/'boot','/':base}
        for directory in roots.values(): directory.mkdir(exist_ok=True)
        old,new=b'verified old SD image',b'distinct HFS boot image'
        (roots[run]/'candidate.bin').write_bytes(new)
        (roots[mp]/'probe.bin').write_bytes(old)
        plan = dict(run=run,backup_run=backup,new_image_sha256=hashlib.sha256(new).hexdigest(),
                    old_image_sha256=hashlib.sha256(old).hexdigest(),boot_backup_sha256='b'*64,original_mbr_sha256='m'*64)
        if profile=='statfs-correction':
            plan.update(prior_boot_run=backup,passed_sd_image_sha256='c'*64)
            (roots[mp]/'probe.sd-read-passed-20261012.bin').write_bytes(b'original passed SD-only backup')
        if profile in ('write-trial','write-diagnostic'):
            plan.update(prior_boot_run=backup,prior_correction_run=backup,
                        passed_sd_image_sha256='c'*64,failed_hfs_image_sha256='f'*64)
            (roots[mp]/'probe.sd-read-passed-20261012.bin').write_bytes(b'original passed SD-only backup')
            (roots[mp]/'probe.hfs-statfs-failed-20261012.bin').write_bytes(b'preserved failed HFS image')
        if profile=='write-diagnostic':
            plan.update(readonly_image_sha256='a'*64,prior_write_run=backup,expected_boot_before_sha256='e'*64,
                prior_write_backup_sha256={'mbr.before-write.bin':'1'*64,
                    'boot-partition.before-write.img':'2'*64,'hfs-partition.before.img':'3'*64})
            (roots[mp]/'probe.hfs-read-passed-20261012.bin').write_bytes(b'original passed RO image')
        events=[]; refs=[]
        class MappedPath:
            def __init__(self,value): self.value=str(value)
            def __str__(self): return self.value
            def __fspath__(self):
                for prefix in (run,backup,mp):
                    if self.value==prefix or self.value.startswith(prefix+'/'):
                        return str(roots[prefix]/self.value[len(prefix):].lstrip('/'))
                if self.value=='/': return str(base)
                raise AssertionError('Unexpected filesystem path: '+self.value)
            def __truediv__(self,name): return MappedPath(self.value.rstrip('/')+'/'+str(name))
            def __eq__(self,other): return isinstance(other,MappedPath) and self.value==other.value
            @property
            def name(self): return PurePosixPath(self.value).name
            def resolve(self): return self
            def stat(self): return base.stat()
            def is_dir(self): return True
            def iterdir(self): return iter([self/'candidate.bin'] if self.value==run else [])
            def open(self,*args,**kwargs): return Path(os.fspath(self)).open(*args,**kwargs)
        def reference():
            refs.append('reference')
            if fault=='reference': raise RuntimeError('wrong root/card/reference')
            return dict(verified=True,changed=(fault=='post-reference' and len(refs)>1))
        def hash_file(path,size=None):
            name=PurePosixPath(str(path)).name
            if name=='boot-partition.before.img': return 'wrong' if fault=='backup' else 'b'*64
            if name=='mbr.before.bin': return 'm'*64
            if name in ('probe.sd-read-passed-20261012.bin','sd-read-passed.bin'): return 'c'*64
            if name in ('probe.hfs-statfs-failed-20261012.bin','hfs-statfs-failed.bin'): return 'f'*64
            if name in ('probe.hfs-read-passed-20261012.bin','hfs-read-passed.bin'): return 'a'*64
            if name in ('mbr.before-write.bin','boot-partition.before-write.img','hfs-partition.before.img'):
                return plan['prior_write_backup_sha256'][name]
            if name=='candidate.bin': return hashlib.sha256(old).hexdigest()
            if name=='probe.bin': return hashlib.sha256(Path(os.fspath(path)).read_bytes()).hexdigest()
            return {'config.txt':'aaccab184135aca272db4123fcba34e20874ae0959a90aed1ef6fd4d5e18ed28',
                 'bl31.bin':'413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46',
                 'bcm2712-rpi-5-b.dtb':'e67017e5d45b97af478ebc93d651a086f2adcb6a650fe453eb9f1cf47e66473f',
                 'probe.gate3-20260927.bin':'454906aa802f013549ef936a9d15bcc42b10638ed73d6759a276797737b1d06c'}.get(name,
                 'bf01b0eedcce48249a7358772f74613d0b0453217f35576369945de25d50374f')
        def subprocess_run(args,**kwargs):
            events.append(args)
            if args[0]=='findmnt': return SimpleNamespace(returncode=1,stdout='')
            if args[0]=='systemctl': return SimpleNamespace(returncode=3)
            if fault=='remount-rw' and 'remount,rw,nosuid,nodev,noexec' in args:
                raise RuntimeError('remount failed')
            return SimpleNamespace(returncode=0)
        definitions,body=boot.REMOTE.split('if os.geteuid()!=0:',1)
        namespace=dict(PLAN=plan,INSTALL_PROFILE=profile)
        exec(Path(boot.core.__file__).read_text()+'\n'+definitions,namespace)
        namespace.update(Path=MappedPath,checked_reference=reference,hash_file=hash_file)
        def prepare_write_backups(plan):
            events.append(['write-backups'])
            self.assertFalse(any(event[0]=='mount' for event in events))
            if fault=='write-backups': raise RuntimeError('snapshot failed')
            return ['modeled full snapshots']
        def finish_write_install(plan,records):
            self.assertEqual(events[-1][0],'umount')
            events.append(['write-finish'])
            if fault=='write-finish': raise RuntimeError('post-install snapshot differs')
            return dict(before=records)
        namespace.update(prepare_write_backups=prepare_write_backups,finish_write_install=finish_write_install)
        with patch('os.geteuid',return_value=0), patch('subprocess.run',side_effect=subprocess_run), \
                patch('subprocess.check_output',return_value='/dev/mmcblk0p1 vfat'), \
                contextlib.redirect_stdout(io.StringIO()):
            if fault:
                with self.assertRaises(RuntimeError): exec('if os.geteuid()!=0:'+body,namespace)
            else: exec('if os.geteuid()!=0:'+body,namespace)
        return roots,events,refs,old,new

    def test_exact_remote_workflow_preserves_files_and_unmounts_before_reference(self):
        roots,events,refs,old,new=self.workflow()
        self.assertEqual((roots['/mnt/xnu-probe']/'probe.bin').read_bytes(),new)
        self.assertEqual((roots['/mnt/xnu-probe']/'probe.sd-read-passed-20261012.bin').read_bytes(),old)
        self.assertEqual((roots['/home/sandrzej/xnu-gate4-hfs-boot-abcdefgh']/'sd-read-passed.bin').read_bytes(),old)
        self.assertEqual(len(refs),2); self.assertEqual(events[-1][0],'umount')
        self.assertTrue((roots['/home/sandrzej/xnu-gate4-hfs-boot-abcdefgh']/'result.json').exists())

    def test_remote_faults_never_publish_success_or_retry(self):
        for fault in ('reference','backup','remount-rw','post-reference'):
            with self.subTest(fault=fault):
                roots,events,refs,old,new=self.workflow(fault)
                self.assertFalse((roots['/home/sandrzej/xnu-gate4-hfs-boot-abcdefgh']/'result.json').exists())
                if fault!='post-reference': self.assertEqual((roots['/mnt/xnu-probe']/'probe.bin').read_bytes(),old)
                if fault=='remount-rw': self.assertEqual(events[-1][0],'umount')
                if fault in ('reference','backup'): self.assertFalse(any(event[0]=='mount' for event in events))

    def test_correction_remote_preserves_distinct_failed_and_passed_backups(self):
        roots,events,refs,old,new=self.workflow(profile='statfs-correction')
        bootdir=roots['/mnt/xnu-probe']; run=roots['/home/sandrzej/xnu-gate4-hfs-boot-abcdefgh']
        self.assertEqual((bootdir/'probe.bin').read_bytes(),new)
        self.assertEqual((bootdir/'probe.hfs-statfs-failed-20261012.bin').read_bytes(),old)
        self.assertEqual((bootdir/'probe.sd-read-passed-20261012.bin').read_bytes(),b'original passed SD-only backup')
        self.assertEqual((run/'hfs-statfs-failed.bin').read_bytes(),old)
        self.assertFalse((run/'sd-read-passed.bin').exists())
        self.assertEqual(len(refs),2); self.assertEqual(events[-1][0],'umount')

    def test_write_remote_preserves_ro_and_prior_backups_and_orders_snapshots(self):
        roots,events,refs,old,new=self.workflow(profile='write-trial')
        bootdir=roots['/mnt/xnu-probe']; run=roots['/home/sandrzej/xnu-gate4-hfs-boot-abcdefgh']
        self.assertEqual((bootdir/'probe.bin').read_bytes(),new)
        self.assertEqual((bootdir/'probe.hfs-read-passed-20261012.bin').read_bytes(),old)
        self.assertEqual((run/'hfs-read-passed.bin').read_bytes(),old)
        self.assertEqual((bootdir/'probe.sd-read-passed-20261012.bin').read_bytes(),b'original passed SD-only backup')
        self.assertEqual((bootdir/'probe.hfs-statfs-failed-20261012.bin').read_bytes(),b'preserved failed HFS image')
        self.assertEqual(len(refs),2); self.assertEqual(events[-1][0],'write-finish')
        self.assertEqual(json.loads((run/'result.json').read_text())['write_trial_backups']['before'],['modeled full snapshots'])

    def test_write_snapshot_faults_never_retry_or_publish_success(self):
        for fault in ('write-backups','write-finish'):
            roots,events,refs,old,new=self.workflow(fault,profile='write-trial')
            self.assertFalse((roots['/home/sandrzej/xnu-gate4-hfs-boot-abcdefgh']/'result.json').exists())
            if fault=='write-backups':
                self.assertEqual((roots['/mnt/xnu-probe']/'probe.bin').read_bytes(),old)
                self.assertFalse(any(event[0]=='mount' for event in events))
            else: self.assertEqual((roots['/mnt/xnu-probe']/'probe.bin').read_bytes(),new)

    def test_diagnostic_remote_keeps_passed_ro_and_preserves_failed_write_separately(self):
        roots,events,refs,old,new=self.workflow(profile='write-diagnostic')
        bootdir=roots['/mnt/xnu-probe']; run=roots['/home/sandrzej/xnu-gate4-hfs-boot-abcdefgh']
        self.assertEqual((bootdir/'probe.bin').read_bytes(),new)
        self.assertEqual((bootdir/'probe.hfs-write-no-admission-20261012.bin').read_bytes(),old)
        self.assertEqual((run/'hfs-write-no-admission.bin').read_bytes(),old)
        self.assertEqual((bootdir/'probe.hfs-read-passed-20261012.bin').read_bytes(),b'original passed RO image')
        self.assertEqual(len(refs),2); self.assertEqual(events[-1][0],'write-finish')


if __name__ == '__main__':
    unittest.main()
