# SPDX-License-Identifier: BSD-2-Clause
"""Actual two-file copying/publication; explicit mount/identity/block doubles."""
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import firmware_pair_install_core as pair
from tools.rpi5 import stage_pcie_fw_trial as stage
from tools.rpi5.tests import test_watchdog_recovery_install as watch
digest=lambda data:hashlib.sha256(data).hexdigest()
BOOT='3977a538-fae5-434d-a94f-50c9422fea84'


def receipt(plan):
    preserved={};expected=dict(plan['protected_files'])
    for r in plan['files']:
        backup,_,nvme=pair.NAMES[plan['profile']][r['target']]
        preserved[r['target']]=dict(sha256=r['old_sha256'],bytes=r['old_bytes'],sd_backup=backup,nvme_backup=nvme)
        expected[r['target']]=r['new_sha256'];expected[backup]=r['old_sha256']
    return dict(status='installed',run=plan['run'],pair_publication_order=list(pair.TARGETS),
        pair_sha256={r['target']:r['new_sha256'] for r in plan['files']},preserved_pair=preserved,
        nvme_previous_pair_sha256={r['target']:r['old_sha256'] for r in plan['files']},
        protected_files_sha256=expected,nvme_backups_verified=plan['nvme_backups'],
        identity=dict(identity=plan['identity_binding']['expected'],boot_id=plan['linux_boot_id'],hostname='kamidana'),
        temporary_pair_published=True,power_loss_atomicity_claimed=False,no_implicit_rollback=True,
        boot_unmounted=True,no_hfs_mount=True,no_config_change=True,no_reboot=True,firmware_changed=True,
        backups=[dict(device=node,bytes=length,sha256=plan['protected_sha256'][key],saved_as=name)
            for key,node,_,length,name in stage.base.core.EXTENTS],
        protected_after={key:dict(device=node,bytes=length,sha256=plan['protected_sha256'][key])
            for key,node,_,length,_ in stage.base.core.EXTENTS})


class FirmwarePairInstallTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self,profile='firmware-abi-trial'):
        with watch.RecoveryInstallTests.fixture(self) as (plan,capture,snapshots,run,state,boot,work,old,new):
            old_fw,new_fw=b'known-good-firmware'*7,b'EL3-verifier-firmware'*9
            (boot/'bl31.bin').write_bytes(old_fw);(work/'candidate-bl31.bin').write_bytes(new_fw)
            (work/'candidate.bin').rename(work/'candidate-probe.bin')
            plan.update(profile=profile,files=[dict(target=n,candidate='candidate-'+n,old_sha256=digest(a),new_sha256=digest(b),
                old_bytes=len(a),new_bytes=len(b)) for n,a,b in (('bl31.bin',old_fw,new_fw),('probe.bin',old,new))])
            yield plan,capture,snapshots,run,state,boot,work,old,new,old_fw,new_fw

    def execute(self,items):
        plan,capture,snapshots,run,*_=items
        return pair.execute(plan,capture,watch.helper,snapshots,watch.reference,watch.core,run)

    def test_actual_pair_snapshots_copy_verified_order_journal_and_closed_mount(self):
        with self.fixture() as x:
            plan,_,_,_,state,boot,work,old,new,old_fw,new_fw=x
            result=self.execute(x)
            self.assertEqual(result['pair_publication_order'],['bl31.bin','probe.bin'])
            self.assertEqual((boot/'bl31.bin').read_bytes(),new_fw);self.assertEqual((boot/'probe.bin').read_bytes(),new)
            for row,raw in zip(plan['files'],(old_fw,old)):
                backup,_,nvme=pair.NAMES[plan['profile']][row['target']]
                self.assertEqual((boot/backup).read_bytes(),raw);self.assertEqual((work/nvme).read_bytes(),raw)
            for phase in ('prepared','before-bl31.bin','after-bl31.bin','before-probe.bin','after-probe.bin'):
                self.assertEqual(json.loads((work/('pair-'+phase+'.json')).read_text())['phase'],phase)
            self.assertFalse(state['mounted']);self.assertEqual(state['verifies'],2)
            self.assertFalse(result['power_loss_atomicity_claimed']);self.assertTrue(result['no_implicit_rollback'])

    def test_each_backup_or_temporary_copy_failure_precedes_both_renames(self):
        real=watch.helper.copy_image
        for fail in range(1,7): # two SSD backups, two FAT backups, two FAT temps.
            with self.subTest(fail=fail),self.fixture() as x:
                calls=0
                def fault(*args,**kwargs):
                    nonlocal calls
                    calls+=1;real(*args,**kwargs)
                    if calls==fail:raise ValueError('copy failure')
                with patch.object(watch.helper,'copy_image',side_effect=fault),patch.object(pair.os,'rename',wraps=os.rename) as rename:
                    with self.assertRaisesRegex(ValueError,'copy failure'):self.execute(x)
                self.assertEqual(rename.call_count,0);self.assertFalse(x[4]['mounted'])
                self.assertEqual((x[5]/'probe.bin').read_bytes(),x[7]);self.assertEqual((x[5]/'bl31.bin').read_bytes(),x[9])

    def test_each_post_rename_failure_preserves_mixed_or_complete_pair_without_retry(self):
        real=os.rename
        for fail in (1,2):
            with self.subTest(fail=fail),self.fixture() as x:
                calls=0
                def fault(*args,**kwargs):
                    nonlocal calls
                    calls+=1;real(*args,**kwargs)
                    if calls==fail:raise ValueError('post-rename failure')
                with patch.object(pair.os,'rename',side_effect=fault):
                    with self.assertRaisesRegex(ValueError,'post-rename'):self.execute(x)
                self.assertEqual(calls,fail);self.assertFalse(x[4]['mounted'])
                self.assertEqual((x[5]/'bl31.bin').read_bytes(),x[10])
                self.assertEqual((x[5]/'probe.bin').read_bytes(),x[7] if fail==1 else x[8])
                self.assertTrue((x[6]/('pair-before-'+pair.TARGETS[fail-1]+'.json')).exists())
                self.assertFalse((x[6]/'result.json').exists())
                for row in x[0]['files']:self.assertTrue((x[5]/pair.NAMES[x[0]['profile']][row['target']][0]).exists())

    def test_each_ssd_journal_failure_stops_at_exact_publication_boundary(self):
        real=pair.journal
        for fail in range(1,6):
            with self.subTest(fail=fail),self.fixture() as x:
                calls=0
                def fault(*args,**kwargs):
                    nonlocal calls
                    calls+=1
                    if calls==fail:raise ValueError('journal failure')
                    real(*args,**kwargs)
                with patch.object(pair,'journal',side_effect=fault):
                    with self.assertRaisesRegex(ValueError,'journal failure'):self.execute(x)
                self.assertFalse(x[4]['mounted']);self.assertFalse((x[6]/'result.json').exists())
                self.assertEqual((x[5]/'bl31.bin').read_bytes(),x[9] if fail<=2 else x[10])
                self.assertEqual((x[5]/'probe.bin').read_bytes(),x[7] if fail<=4 else x[8])

    def test_short_ssd_space_never_snapshots_mounts_or_publishes(self):
        with self.fixture() as x,patch.object(pair.os,'statvfs',return_value=types.SimpleNamespace(f_bavail=0,f_frsize=4096)):
            with self.assertRaisesRegex(ValueError,'Insufficient SSD space'):self.execute(x)
            self.assertFalse(x[4]['commands']);self.assertEqual((x[5]/'bl31.bin').read_bytes(),x[9])

    def test_all_partial_names_refused_before_rw_and_unknown_run_not_retried(self):
        for target in pair.TARGETS:
            for index in (0,1):
                with self.subTest(target=target,index=index),self.fixture() as x:
                    (x[5]/pair.NAMES[x[0]['profile']][target][index]).write_bytes(b'unknown prior partial')
                    with self.assertRaisesRegex(ValueError,'Partial/existing'):self.execute(x)
                    self.assertFalse(any('remount,rw,nosuid,nodev,noexec' in c for c in x[4]['commands']))
                    self.assertFalse(x[4]['mounted'])
        with self.fixture() as x:
            (x[6]/'pair-prepared.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Fresh canonical'):self.execute(x)
            self.assertFalse(x[4]['commands'])

    def test_wrong_baseline_candidate_space_config_and_replaced_mount_refused(self):
        for case in ('baseline','candidate','space','config','mount'):
            with self.subTest(case=case),self.fixture() as x:
                if case=='baseline':x[0]['protected_sha256']['hfs']='0'*64
                if case=='candidate':(x[6]/'candidate-bl31.bin').write_bytes(b'wrong')
                if case=='config':(x[5]/'config.txt').write_bytes(b'[all]\narmstub=wrong\n')
                if case=='mount':x[4]['replace']=True
                patcher=patch.object(pair.os,'fstatvfs',return_value=types.SimpleNamespace(f_bavail=0,f_frsize=4096)) if case=='space' else contextlib.nullcontext()
                with patcher,self.assertRaises(ValueError):self.execute(x)
                self.assertEqual((x[5]/'bl31.bin').read_bytes(),x[9]);self.assertEqual((x[5]/'probe.bin').read_bytes(),x[7])
                if case=='mount':self.assertTrue(x[4]['mounted']);self.assertNotIn('umount',[c[0] for c in x[4]['commands']])
                else:self.assertFalse(x[4]['mounted'])

    def test_explicit_restore_uses_distinct_names_and_preserves_both_trial_files(self):
        with self.fixture('firmware-abi-restore') as x:
            r=self.execute(x)
            self.assertEqual(r['preserved_pair']['bl31.bin']['sd_backup'],'bl31.fwabi-trial-20261013.bin')
            self.assertEqual((x[6]/'firmware-trial.bin').read_bytes(),x[9])
            self.assertEqual((x[6]/'loader-trial.bin').read_bytes(),x[7])

    def test_pinned_60_artifact_plan_compiles_no_network_and_fixed_pair(self):
        real=stage.subprocess.run
        def no_network(args,*rest,**kwargs):
            if args[0] in ('ssh','scp'):raise AssertionError('Planning must not access network')
            return real(args,*rest,**kwargs)
        with patch.object(stage.subprocess,'run',side_effect=no_network):plan=stage.load_plan(BOOT)
        self.assertEqual(len(plan['nvme_backups']),60)
        self.assertEqual(plan['protected_sha256']['boot'],'fd2d20729dca2025df35310eb1165a64692d0bed3e604bb8f77355ff28ec8033')
        self.assertEqual(plan['files'][0]['old_sha256'],stage.OLD_FW_SHA)
        self.assertEqual(plan['files'][1]['new_sha256'],stage.IMAGE_SHA)
        plan['run']='/home/sandrzej/xnu-gate5-fwabi-12345678'
        compile(stage.remote_source(plan),'<actual-pair-remote>','exec')
        stage.validate_result(receipt(plan),plan)

    def test_typed_receipt_and_tampered_ancestry_or_chain_refused(self):
        plan=stage.load_plan(BOOT);plan['run']='/home/sandrzej/xnu-gate5-fwabi-12345678';r=receipt(plan)
        for key,value in (('boot_unmounted',1),('firmware_changed',1),('temporary_pair_published',1),
            ('pair_publication_order',['probe.bin','bl31.bin']),('pair_sha256',{}),('no_implicit_rollback',False)):
            bad=copy.deepcopy(r);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):stage.validate_result(bad,plan)
        for field in ('nvme_backups','protected_files','protected_sha256','ancestry','source_sha256'):
            bad=copy.deepcopy(plan);bad[field]=[] if field=='nvme_backups' else {}
            with self.subTest(field=field),self.assertRaises((ValueError,KeyError)):stage.validate_result(r,bad)

    def test_restore_plan_requires_new_boot_and_inherits_65_then_70(self):
        plan=stage.load_plan(BOOT);plan['run']='/home/sandrzej/xnu-gate5-fwabi-12345678'
        with tempfile.TemporaryDirectory(prefix='fwabi-receipt-test-',dir=stage.ROOT/'build/rpi5') as name:
            directory=Path(name);(directory/'plan.json').write_text(json.dumps(plan));(directory/'result.json').write_text(json.dumps(receipt(plan)))
            with self.assertRaisesRegex(ValueError,'Distinct SSD Linux return'):stage.load_plan(BOOT,directory)
            restored=stage.load_plan('4977a538-fae5-434d-a94f-50c9422fea84',directory)
            self.assertEqual(len(restored['nvme_backups']),65);self.assertEqual(restored['profile'],'firmware-abi-restore')
            self.assertEqual(restored['files'][0]['new_sha256'],stage.OLD_FW_SHA)
            self.assertEqual(restored['files'][1]['new_sha256'],stage.base.prior.NEW_SHA)
            restored['run']='/home/sandrzej/xnu-gate5-fwabi-87654321';result=receipt(restored)
            stage.validate_result(result,restored)
            self.assertEqual(len(stage.inherited_pair(restored,result,70)),70)


if __name__=='__main__':unittest.main()
