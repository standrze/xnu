# SPDX-License-Identifier: BSD-2-Clause
"""Cache-diagnostic successor guards; synthetic only, no network or media."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import stage_hfs_cache_diagnostic as runner
import serial_hfs_write_trial as recorder
import capture_hfs_persistence as capture
from tools.rpi5.tests import test_hfs_write_diagnostic as old_fixtures


class CacheDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def bundle(self):
        fixture=old_fixtures.WriteDiagnosticTests(); fixture.root=self.root
        inputs,paths,old,result,current,kernel=fixture.successor_bundle()
        old.update(profile='write-diagnostic',new_image_sha256=runner.PREVIOUS_IMAGE,
            old_image_sha256=runner.previous.PREVIOUS_IMAGE,
            readonly_image_sha256=runner.installer.checker.HFS_READ_BASELINE_SHA256,
            prior_write_run='/home/sandrzej/xnu-gate4-hfs-write-abcdefgh',
            run='/home/sandrzej/xnu-gate4-hfs-write-ijklmnop',
            prior_write_backup_sha256={row['saved_as']:row['sha256'] for row in result['write_trial_backups']['before']},
            expected_boot_before_sha256='e'*64)
        result.update(image_sha256=runner.PREVIOUS_IMAGE,run=old['run'],
            preserved_sd_image_sha256=runner.previous.PREVIOUS_IMAGE,
            sd_backup='probe.hfs-write-no-admission-20261012.bin')
        current.update(old_image_sha256=old['readonly_image_sha256'])
        kernel.write_bytes(b'\0'.join(runner.DIAGNOSTICS))
        paths['previous_plan'].write_text(json.dumps(old)); paths['previous_result'].write_text(json.dumps(result))
        raw=b'\r\n'.join((runner.previous.TERMINAL_LOADER,runner.previous.WRITE_LOADER,
            b'RPI5XNU:HFS:REGISTERED',b'RPI5XNU:SD:WRITE_START_BEGIN',
            b'RPI5XNU:SD:WRITE_INIT_BEGIN',runner.FAILURE,
            b'RPI5XNU:SD:WRITE_START_FAIL STAGE=INITIALIZE',
            b'RPI5XNU:SHELL:READY',b'RPI5XNU:SHELL:READY'))+b'\r\n'
        state=dict(status='failed',error='Unsafe, old or failed boot before write input',
            image_sha256=runner.PREVIOUS_IMAGE,checks=[],reads=[],transmitted_bytes=0,write_batch_attempts=0,
            hfs_mounted=False,durability_verified=False,partition='/dev/disk0s2',baud=115200,
            linux_boot_id_before_write=old['linux_boot_id'],write_input_sha256=old['evidence_sha256'],
            evidence_sha256={name:runner.installer.checker.sha256(paths['previous_'+name]) for name in ('plan','result')},
            bytes=len(raw),serial_sha256=hashlib.sha256(raw).hexdigest())
        paths['previous_trial'].write_text(json.dumps(state)); paths['previous_trial'].with_name('serial.bin').write_bytes(raw)
        return inputs,paths,old,result,current,kernel,state,raw

    def validate(self,bundle):
        inputs,paths,old,result,current,kernel,state,raw=bundle
        with patch.object(runner,'PREVIOUS_PLAN',runner.installer.checker.sha256(paths['previous_plan'])), \
                patch.object(runner,'PREVIOUS_RESULT',runner.installer.checker.sha256(paths['previous_result'])), \
                patch.object(runner,'PREVIOUS_STATE',runner.installer.checker.sha256(paths['previous_trial'])), \
                patch.object(runner,'PREVIOUS_RAW',hashlib.sha256(raw).hexdigest()), \
                patch.object(runner.installer,'evidence_path',side_effect=Path), \
                patch.object(runner.installer,'load_plan',return_value=copy.deepcopy(current)):
            return runner.load_plan(inputs)

    def test_successor_binds_w2_failure_new_boot_both_failed_images_and_full_backups(self):
        bundle=self.bundle(); plan=self.validate(bundle); old=bundle[2]; result=bundle[3]
        self.assertEqual(plan['profile'],'write-cache-diagnostic')
        self.assertEqual(plan['old_image_sha256'],runner.PREVIOUS_IMAGE)
        self.assertEqual(plan['no_admission_image_sha256'],runner.previous.PREVIOUS_IMAGE)
        self.assertEqual(plan['readonly_image_sha256'],old['readonly_image_sha256'])
        self.assertEqual(plan['prior_cache_run'],old['run'])
        self.assertEqual(plan['prior_write_run'],old['prior_write_run'])
        self.assertEqual(plan['prior_write_backup_sha256'],old['prior_write_backup_sha256'])
        self.assertEqual(plan['expected_boot_before_sha256'],result['write_trial_backups']['after']['boot']['sha256'])
        self.assertEqual(set(plan['prior_cache_backup_sha256']),{'mbr.before-write.bin','boot-partition.before-write.img','hfs-partition.before.img'})
        source=runner.installer.remote_source(plan); compile(source,'<fixed-remote>','exec')
        for name in ('prior_cache_run','prior_cache_backup_sha256','hfs-write-cache-probe-failed.bin',
                     'no_admission_image_sha256','probe.hfs-write-cache-probe-failed-20261012.bin'):
            self.assertIn(name,source)

    def test_wrong_fresh_identity_same_boot_reused_image_or_missing_linked_diagnostics_refuses(self):
        for key in ('host','expected','fixture_sha256','current_mbr_sha256','backup_run','boot_backup_sha256',
                    'original_mbr_sha256','prior_boot_run','prior_correction_run','passed_sd_image_sha256',
                    'failed_hfs_image_sha256','old_image_sha256','linux_boot_id','new_image_sha256','diagnostics'):
            bundle=list(self.bundle()); current=bundle[4]
            if key=='diagnostics': bundle[5].write_bytes(b'not linked')
            else: current[key]=bundle[2]['linux_boot_id'] if key=='linux_boot_id' else runner.PREVIOUS_IMAGE if key=='new_image_sha256' else 'changed'
            with self.subTest(key=key),self.assertRaises(ValueError): self.validate(bundle)

    def test_zero_input_failure_fields_markers_and_original_bindings_are_strict(self):
        for fault in ('tx','txbool','batch','mounted','checks','reads','image','binding','sha','panic',
                      'admission','observed','rw','duplicate','missing-shell','different-failure','torn-failure'):
            bundle=list(self.bundle()); paths,state,raw=bundle[1],bundle[6],bundle[7]
            if fault=='tx': state['transmitted_bytes']=1
            if fault=='txbool': state['transmitted_bytes']=False
            if fault=='batch': state['write_batch_attempts']=1
            if fault=='mounted': state['hfs_mounted']=True
            if fault=='checks': state['checks']=['x']
            if fault=='reads': state['reads']=[{}]
            if fault=='image': state['image_sha256']='0'*64
            if fault=='binding': state['write_input_sha256']={'wrong':'binding'}
            if fault=='sha': state['serial_sha256']='0'*64
            additions={'panic':b'panic(cpu','admission':b'RPI5XNU:SD:WRITE_ADMITTED',
                'observed':b'RPI5XNU:SD:WRITE_CACHE_OBSERVED','rw':b'RPI5XNU:HFSRW:MOUNTED',
                'duplicate':runner.FAILURE}
            if fault in additions: raw+=additions[fault]
            if fault=='missing-shell': raw=raw.replace(b'RPI5XNU:SHELL:READY',b'not-ready')
            if fault=='different-failure': raw=raw.replace(b'RC=-5 CMD=13',b'RC=-3 CMD=13')
            if fault=='torn-failure': raw=raw.replace(runner.FAILURE,b'x'+runner.FAILURE)
            if raw!=bundle[7]: state.update(bytes=len(raw),serial_sha256=hashlib.sha256(raw).hexdigest())
            paths['previous_trial'].write_text(json.dumps(state)); paths['previous_trial'].with_name('serial.bin').write_bytes(raw)
            bundle[7]=raw
            with self.subTest(fault=fault),self.assertRaises(ValueError): self.validate(bundle)

    def test_pinned_history_and_drift_are_not_replaced_by_self_consistency(self):
        bundle=self.bundle()
        with patch.object(runner.installer,'evidence_path',side_effect=Path),self.assertRaises(ValueError):
            runner.load_plan(bundle[0])
        original=runner.installer.checker.sha256
        calls={}
        def changed(path):
            path=Path(path); calls[path]=calls.get(path,0)+1
            return '0'*64 if path==bundle[1]['current_inputs'] and calls[path]>1 else original(path)
        with patch.object(runner.installer.checker,'sha256',side_effect=changed),self.assertRaisesRegex(ValueError,'changed during'):
            self.validate(bundle)

    def test_historical_raw_changed_after_failure_validation_is_rejected(self):
        bundle=self.bundle(); original=runner.validate_failure
        def drift(*args):
            proof=original(*args)
            bundle[1]['previous_trial'].with_name('serial.bin').write_bytes(bundle[7]+b'changed afterward')
            return proof
        with patch.object(runner,'validate_failure',side_effect=drift),self.assertRaisesRegex(ValueError,'serial bytes changed during'):
            self.validate(bundle)

    def test_default_local_plan_and_bad_execute_never_connect(self):
        for bad in (False,True):
            out=self.root/('bad' if bad else 'local')
            argv=['stage_hfs_cache_diagnostic.py','--inputs','bundle','--output',str(out)]+(['--execute'] if bad else [])
            with patch.object(sys,'argv',argv),patch.object(Path,'is_relative_to',return_value=True), \
                    patch.object(runner,'load_plan',return_value={'profile':'write-cache-diagnostic'},
                        side_effect=ValueError('changed evidence') if bad else None), \
                    patch.object(runner.installer.subprocess,'run') as network,contextlib.redirect_stdout(io.StringIO()):
                if bad:
                    with self.assertRaises(ValueError): runner.main()
                else: self.assertEqual(runner.main(),0)
            network.assert_not_called(); self.assertEqual(out.exists(),not bad)

    def test_recorder_uses_complete_cache_successor_validator(self):
        bundle=self.bundle(); plan=self.validate(bundle)
        plan['run']='/home/sandrzej/xnu-gate4-hfs-write-qrstuvwx'
        result=copy.deepcopy(bundle[3]); result.update(run=plan['run'],image_sha256=plan['new_image_sha256'],
            preserved_sd_image_sha256=plan['old_image_sha256'],sd_backup='probe.hfs-write-cache-probe-failed-20261012.bin')
        result['write_trial_backups']['before'][1]['sha256']=plan['expected_boot_before_sha256']
        result['write_trial_backups']['after']['boot']['sha256']='9'*64
        result['write_trial_backups']['linux_boot_id']=plan['linux_boot_id']
        for name,value in (('plan',plan),('result',result)): (self.root/(name+'.json')).write_text(json.dumps(value))
        (self.root/'remote-source.sha256').write_text(hashlib.sha256(b'fixed').hexdigest())
        with patch.object(recorder.installer,'evidence_path',side_effect=Path), \
                patch.object(runner,'load_plan',return_value={k:v for k,v in plan.items() if k!='run'}) as loader, \
                patch.object(runner.installer,'load_plan',side_effect=AssertionError('wrong validator')), \
                patch.object(recorder.installer,'remote_source',return_value='fixed'):
            loaded,_,_=recorder.load_inputs(bundle[0],self.root)
        self.assertEqual(loaded,plan); loader.assert_called_once()

    def test_post_write_capture_retains_both_failed_images_and_all_three_snapshot_generations(self):
        bundle=self.bundle(); plan=self.validate(bundle)
        plan['run']='/home/sandrzej/xnu-gate4-hfs-write-qrstuvwx'
        plan['prior_boot_run']='/home/sandrzej/xnu-gate4-hfs-boot-abcdefgh'
        plan['prior_correction_run']='/home/sandrzej/xnu-gate4-hfs-stats-abcdefgh'
        candidate=self.root/'candidate'; candidate.write_bytes(b'opaque model image')
        plan['candidate']=str(candidate)
        with patch.object(capture,'local_image',return_value=1024), \
                patch.object(capture.installer,'evidence_path',return_value=candidate), \
                patch.object(capture.recorder,'sha256',side_effect=[capture.installer.checker.SHELL_BASELINE_SHA256,plan['new_image_sha256']]):
            rows=capture.backup_rows(plan,bundle[3])
        self.assertEqual(len(rows),20)
        by_path={row['path']:row for row in rows}
        self.assertEqual(len(by_path),20)
        expected={plan['run']+'/hfs-write-cache-probe-failed.bin':runner.PREVIOUS_IMAGE,
            plan['prior_cache_run']+'/candidate.bin':runner.PREVIOUS_IMAGE,
            plan['prior_cache_run']+'/hfs-write-no-admission.bin':runner.previous.PREVIOUS_IMAGE,
            plan['prior_write_run']+'/candidate.bin':runner.previous.PREVIOUS_IMAGE,
            plan['prior_write_run']+'/hfs-read-passed.bin':plan['readonly_image_sha256']}
        for path,sha in expected.items(): self.assertEqual(by_path[path]['sha256'],sha)
        for directory in (plan['run'],plan['prior_cache_run'],plan['prior_write_run']):
            for name,size in (('mbr.before-write.bin',512),('boot-partition.before-write.img',536870912),
                              ('hfs-partition.before.img',134217728)):
                self.assertEqual(by_path[directory+'/'+name]['bytes'],size)


if __name__=='__main__': unittest.main()
