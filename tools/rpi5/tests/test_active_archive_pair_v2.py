# SPDX-License-Identifier: BSD-2-Clause
"""Actual regular-file publication with explicit block/mount/identity doubles.

No device, serial, SSH or actual hardware authority. Historical archives are
deliberately nonexistent; active baseline and all copied files are real bytes.
"""
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from tools.rpi5 import active_archive_pair_v2 as engine
from tools.rpi5 import trial_checkpoint_v2 as seal
from tools.rpi5.tests import test_pcie_axi_trial as prior

ROOT=Path(__file__).resolve().parents[3]
GOOD_FW=ROOT/'build/rpi5/tfa-candidate/build/rpi5/debug/bl31.bin'
GOOD=ROOT/'build/rpi5/bl33-probe-vszhh6o4/probe.bin'
digest=lambda data:hashlib.sha256(data).hexdigest()
TAG='19'*16


class CheckpointTests(unittest.TestCase):
    def test_full_audit_once_then_only_pinned_bytes_and_exact_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'evidence';p.write_bytes(b'complete trusted input');calls=[]
            def audit():calls.append(1);return {'result':'full fixture validation'}
            value,pin=seal.create(audit,{str(p):seal.sha(p)})
            for _ in range(3):self.assertEqual(seal.revalidate(value,pin),{'result':'full fixture validation'})
            self.assertEqual(calls,[1])
            altered=copy.deepcopy(value);altered['payload']['result']='different'
            with self.assertRaisesRegex(ValueError,'retained checkpoint'):seal.revalidate(altered,pin)
            p.write_bytes(b'changed trusted input')
            with self.assertRaisesRegex(ValueError,'evidence bytes'):seal.revalidate(value,pin)

    def test_drift_during_full_audit_and_checkpoint_overwrite_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'evidence';p.write_bytes(b'one')
            def unstable():p.write_bytes(b'two');return {}
            with self.assertRaisesRegex(ValueError,'evidence bytes'):seal.create(unstable,{str(p):seal.sha(p)})
            def stable():return {'ok':True}
            value,pin=seal.create(stable,{str(p):seal.sha(p)})
            out=Path(d)/'checkpoint.json';seal.save_new(out,value,pin)
            with self.assertRaises(FileExistsError):seal.save_new(out,value,pin)

    def test_existing_automatic_source_pins_are_not_silently_refreshed(self):
        calls=[]
        def audit():calls.append(1);return {'ok':True}
        for path in (Path(seal.__file__).resolve(),Path(audit.__code__.co_filename).resolve()):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError,'automatic source pin differs'):
                    seal.create(audit,{str(path):'0'*64})
        self.assertEqual(calls,[])


class ActivePairTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self,restore=False):
        with prior.PairTests.fixture(self,restore) as row:
            plan,capture,snapshots,run,state,boot,work,*_=row
            parent=work.parent;archives=parent/'baseline';archives.mkdir()
            shutil.copyfile(GOOD,archives/'loader.bin');shutil.copyfile(GOOD_FW,archives/'firmware.bin')
            history=[dict(path=str(parent/'historical'/('archive-'+str(i))),bytes=536870912,sha256='9'*64) for i in range(108)]
            baseline={'bl31.bin':str(archives/'firmware.bin'),'probe.bin':str(archives/'loader.bin')}
            history.extend(dict(path=p,bytes=Path(p).stat().st_size,sha256=seal.sha(p)) for p in baseline.values())
            if restore:
                shutil.copyfile(GOOD_FW,work/'candidate-bl31.bin')
                plan['files'][0].update(new_sha256=engine.GOOD_FW_SHA,new_bytes=engine.GOOD_FW_BYTES)
            else:
                shutil.copyfile(GOOD_FW,boot/'bl31.bin')
                plan['files'][0].update(old_sha256=engine.GOOD_FW_SHA,old_bytes=engine.GOOD_FW_BYTES)
            plan['nvme_backups']=history;plan['profile']=engine.RESTORE if restore else engine.TRIAL
            media=copy.deepcopy(plan);media.pop('run')
            state['active_hash_paths']=[];state['audit_calls']=0
            active=engine.select_baseline(history,baseline)
            def verify(p):
                self.assertEqual(p['nvme_backups'],active);state['verifies']+=1
                for r in p['nvme_backups']:
                    state['active_hash_paths'].append(r['path'])
                    if Path(r['path']).stat().st_size!=r['bytes'] or seal.sha(r['path'])!=r['sha256']:
                        raise ValueError('Preserved active baseline differs')
            capture.verify_backups=verify
            def audit():
                state['audit_calls']+=1
                return dict(media_plan=media,history_catalog=history,baseline_paths=baseline)
            checkpoint,pin=seal.create(audit,engine.source_pins())
            outer,outer_sha=engine.plan_from_seal(checkpoint,pin,media['profile'],TAG,str(work),media)
            yield outer,outer_sha,capture,snapshots,run,state,boot,work,baseline,checkpoint,pin

    def execute(self,row):
        p,pin,c,s,run,*_=row
        return engine.execute(p,pin,c,prior.prior.watch.helper,s,prior.prior.watch.reference,prior.prior.watch.core,run)

    def test_only_two_baselines_not_110_archives_and_new_typed_receipt(self):
        for restore in (False,True):
            with self.subTest(restore=restore),self.fixture(restore) as row:
                p,_,_,_,_,state,boot,work,baseline,*_=row
                inodes={n:Path(n).stat().st_ino for n in baseline.values()}
                result=self.execute(row)
                self.assertEqual(state['audit_calls'],1);self.assertEqual(state['verifies'],2)
                self.assertEqual(state['active_hash_paths'],list(baseline.values())*2)
                self.assertEqual(result['format'],engine.RESULT)
                self.assertFalse(result['historical_archives_reverified'])
                self.assertEqual(result['preserved_archive_count'],110)
                self.assertEqual(result['created_archive_count'],5);self.assertEqual(len(result['next_catalog']),115)
                self.assertEqual(result['deleted_archives'],[])
                self.assertNotIn('nvme_backups_verified',result);self.assertNotIn('nvme_backups_verified',result['publication'])
                self.assertEqual(result['publication']['pair_publication_order'],['bl31.bin','probe.bin'])
                self.assertTrue((work/'publication.json').is_file());self.assertTrue((work/'result.json').is_file())
                self.assertEqual(inodes,{n:Path(n).stat().st_ino for n in baseline.values()})
                self.assertFalse(state['mounted'])
                for r in p['media']['files']:self.assertEqual(seal.sha(boot/r['target']),r['new_sha256'])

    def test_corrupt_active_baseline_fails_before_mount_or_copy(self):
        for name in ('bl31.bin','probe.bin'):
            with self.subTest(name=name),self.fixture() as row:
                Path(row[8][name]).write_bytes(b'corrupted baseline')
                with self.assertRaisesRegex(ValueError,'active baseline'):self.execute(row)
                self.assertEqual(row[5]['commands'],[])

    def test_sealed_plan_mutation_and_missing_selected_row_are_rejected(self):
        with self.fixture() as row:
            p=copy.deepcopy(row[0]);p['media']['files'][0]['new_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'dispatched plan'):self.execute((p,*row[1:]))
            p=copy.deepcopy(row[0]);p['historical_catalog'].pop()
            with self.assertRaises(ValueError):engine.validate_plan(p)

    def test_sealed_media_comparison_rejects_equal_but_different_json_types(self):
        with self.fixture() as row:
            data=copy.deepcopy(row[9]['payload'])
            # An auditor may retain additional typed admission diagnostics.
            # Their types must survive even if the old publisher ignores them.
            data['media_plan']['admission_diagnostics']={'ready':True,'count':1}
            def audit():return data
            checkpoint,pin=seal.create(audit,engine.source_pins())
            for key,value in (('ready',1),('count',1.0)):
                with self.subTest(key=key):
                    altered=copy.deepcopy(data['media_plan'])
                    altered['admission_diagnostics'][key]=value
                    self.assertEqual(altered,data['media_plan'])  # Python's loose comparison is insufficient.
                    with self.assertRaisesRegex(ValueError,'sealed full-audit media plan differs'):
                        engine.plan_from_seal(checkpoint,pin,engine.TRIAL,TAG,str(row[7]),altered)
            altered=copy.deepcopy(row[0]);altered['media']['nvme_backups'][0]['bytes']=float(engine.GOOD_FW_BYTES)
            with self.assertRaisesRegex(ValueError,'Active/historical archive boundary'):
                engine.validate_plan(altered)

    def test_new_receipt_is_strict_and_does_not_replay_audits(self):
        with self.fixture() as row:
            result=self.execute(row)
            engine.validate_result(result,row[0],row[1])
            self.assertEqual(row[5]['audit_calls'],1)
            changes=(lambda r:r.update(historical_archives_reverified=True),
                lambda r:r['publication'].update(boot_unmounted=1),
                lambda r:r['publication']['protected_after']['hfs'].update(sha256='0'*64),
                lambda r:r['newly_created_rollback_archives_verified'].pop(),
                lambda r:r['active_baseline_archives_verified'].clear(),
                lambda r:r.update(nvme_backups_verified=r['historical_catalog']),
                lambda r:r['next_catalog'].pop(),lambda r:r.update(deleted_archives=['old-file']))
            for change in changes:
                bad=copy.deepcopy(result);change(bad)
                with self.assertRaises(ValueError):engine.validate_result(bad,row[0],row[1])

    def test_remote_source_compiles_without_audit_replay_or_hardware_execution(self):
        with self.fixture() as row:
            code=engine.remote_source(row[9],row[10],row[0],row[1])
            self.assertIn('active_archive_pair_v2.execute(PLAN,',code)
            compile(code,'<offline-only>','exec')
            self.assertEqual(row[5]['audit_calls'],1);self.assertEqual(row[5]['commands'],[])
            self.assertEqual(row[5]['verifies'],0)
            p=copy.deepcopy(row[0]);p['historical_archives_reverified']=True
            with self.assertRaises(ValueError):engine.validate_plan(p)

    def test_each_copy_failure_stops_before_publication_and_preserves_partial(self):
        helper=prior.prior.watch.helper;original=helper.copy_image
        for at in range(1,6):
            with self.subTest(at=at),self.fixture() as row:
                calls=[];before={n:(row[6]/n).read_bytes() for n in ('bl31.bin','probe.bin')}
                def fail(*a,**kw):
                    calls.append(a[2]);original(*a,**kw)
                    if len(calls)==at:raise ValueError('injected copy failure')
                with patch.object(helper,'copy_image',side_effect=fail),patch.object(os,'rename',wraps=os.rename) as rename:
                    with self.assertRaisesRegex(ValueError,'copy failure'):self.execute(row)
                self.assertEqual(rename.call_count,0)
                self.assertEqual(before,{n:(row[6]/n).read_bytes() for n in before})
                self.assertFalse(row[5]['mounted']);self.assertFalse((row[7]/'result.json').exists())

    def test_post_rename_failure_retains_known_partial_state_no_retry(self):
        original=os.rename
        for at in (1,2):
            with self.subTest(at=at),self.fixture() as row:
                calls=[];old={n:(row[6]/n).read_bytes() for n in ('bl31.bin','probe.bin')}
                def fail(*a,**kw):
                    calls.append(a[1]);original(*a,**kw)
                    if len(calls)==at:raise ValueError('injected post rename')
                with patch.object(os,'rename',side_effect=fail):
                    with self.assertRaisesRegex(ValueError,'post rename'):self.execute(row)
                self.assertEqual(len(calls),at);self.assertFalse((row[7]/'result.json').exists())
                self.assertNotEqual((row[6]/'bl31.bin').read_bytes(),old['bl31.bin'])
                self.assertEqual((row[6]/'probe.bin').read_bytes()==old['probe.bin'],at==1)
                with self.assertRaisesRegex(ValueError,'Fresh canonical'):self.execute(row)

    def test_existing_temporary_or_journal_refuses_unknown_operation(self):
        for kind in ('temporary','journal'):
            with self.subTest(kind=kind),self.fixture() as row:
                if kind=='temporary':
                    name=engine.bound_core(TAG).NAMES[engine.TRIAL]['probe.bin'][1]
                    (row[6]/name).write_bytes(b'unknown partial')
                else:(row[7]/'pair-before-bl31.bin.json').write_text('{}')
                with self.assertRaises(ValueError):self.execute(row)
                self.assertFalse(any('remount,rw,nosuid,nodev,noexec' in c for c in row[5]['commands']))

    def test_current_baseline_and_foreign_mount_guards_unchanged(self):
        for condition in ('raw','candidate','root','mount'):
            with self.subTest(condition=condition),self.fixture() as row:
                p=copy.deepcopy(row[0]);old=(row[6]/'probe.bin').read_bytes()
                if condition=='raw':p['media']['protected_sha256']['hfs']='0'*64
                if condition=='candidate':(row[7]/'candidate-probe.bin').write_bytes(b'wrong')
                if condition=='root':row[2].command=lambda *a:'different-root'
                if condition=='mount':row[5]['replace']=True
                if condition=='raw':
                    # This deliberately models a fully sealed but wrong raw
                    # baseline: the unchanged physical guard must reject it.
                    row=(p,seal.digest(p),*row[2:])
                with self.assertRaises(ValueError):self.execute(row)
                self.assertEqual((row[6]/'probe.bin').read_bytes(),old)
                if condition=='mount':
                    self.assertTrue(row[5]['mounted']);self.assertNotIn('umount',[c[0] for c in row[5]['commands']])

    def test_actual_saved_plan_read_budget_is_linear_in_active_pair_only(self):
        path=ROOT/'build/rpi5/root41-installed-20261013/plan.json'
        rows=json.loads(path.read_text())['nvme_backups'];r=engine.legacy_read_budget(rows)
        self.assertEqual(r['historical_archives'],110)
        self.assertEqual(r['legacy_historical_hash_bytes_per_operation'],34294171256)
        self.assertEqual(r['v2_selected_baseline_hash_bytes_per_operation'],38858348)
        self.assertFalse(r['measured_speedup'])


if __name__=='__main__':unittest.main()
