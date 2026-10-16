# SPDX-License-Identifier: BSD-2-Clause
"""Diagnostic successor evidence guards; synthetic only, never physical I/O."""
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
import stage_hfs_write_diagnostic as runner
import serial_hfs_write_trial as recorder
from tools.rpi5.tests import test_hfs_write_installer as fixtures


class WriteDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def bundle(self):
        plan,result=fixtures.WriteInstallerTests().result_bundle()
        plan.update(profile='write-trial',new_image_sha256=runner.PREVIOUS_IMAGE,evidence_sha256={'reference':'c'*64})
        result['image_sha256']=runner.PREVIOUS_IMAGE
        raw=b'\r\n'.join((runner.TERMINAL_LOADER,runner.WRITE_LOADER,b'RPI5XNU:HFS:REGISTERED',
                          b'RPI5XNU:SHELL:READY',b'RPI5XNU:SHELL:READY'))+b'\r\n'
        state=dict(status='failed',error='No complete fresh write-image admission/HFS/shell boot; zero input',
            image_sha256=runner.PREVIOUS_IMAGE,checks=[],reads=[],transmitted_bytes=0,write_batch_attempts=0,
            hfs_mounted=False,durability_verified=False,partition='/dev/disk0s2',baud=115200,
            linux_boot_id_before_write=plan['linux_boot_id'],write_input_sha256=plan['evidence_sha256'],
            evidence_sha256={'plan':'d'*64,'result':'e'*64},bytes=len(raw),serial_sha256=hashlib.sha256(raw).hexdigest())
        path=self.root/'state.json'; path.write_text(json.dumps(state)); path.with_name('serial.bin').write_bytes(raw)
        return path,state,raw,plan,result,{'previous_plan':'d'*64,'previous_result':'e'*64}

    def validate(self,bundle):
        path,state,raw,plan,result,hashes=bundle
        with patch.object(runner,'PREVIOUS_STATE',runner.installer.checker.sha256(path)), \
                patch.object(runner,'PREVIOUS_RAW',hashlib.sha256(raw).hexdigest()), \
                patch.object(runner.installer,'evidence_path',side_effect=Path):
            return runner.validate_failure(path,plan,result,hashes)

    def test_exact_failed_zero_input_boot_is_bound(self):
        bundle=self.bundle(); proof=self.validate(bundle)
        self.assertEqual(proof['serial_sha256'],hashlib.sha256(bundle[2]).hexdigest())

    def test_any_input_batch_mount_wrong_image_binding_reset_admission_or_raw_tamper_refuses(self):
        for fault in ('tx','txbool','batch','mounted','reads','checks','image','binding','hash','panic','admission','rw','duplicate','missing-shell'):
            path,state,raw,plan,result,hashes=self.bundle()
            if fault=='tx': state['transmitted_bytes']=1
            if fault=='txbool': state['transmitted_bytes']=False
            if fault=='batch': state['write_batch_attempts']=1
            if fault=='mounted': state['hfs_mounted']=True
            if fault=='reads': state['reads']=[{}]
            if fault=='checks': state['checks']=['ready']
            if fault=='image': state['image_sha256']='0'*64
            if fault=='binding': state['write_input_sha256']={}
            if fault=='hash': state['serial_sha256']='0'*64
            if fault=='panic': raw+=b'panic(cpu'
            if fault=='admission': raw+=b'RPI5XNU:SD:WRITE_ADMITTED'
            if fault=='rw': raw+=b'RPI5XNU:HFSRW:MOUNTED'
            if fault=='duplicate': raw+=runner.TERMINAL_LOADER
            if fault=='missing-shell': raw=raw.replace(b'RPI5XNU:SHELL:READY',b'not-ready')
            if fault in ('panic','admission','rw','duplicate','missing-shell'):
                state.update(bytes=len(raw),serial_sha256=hashlib.sha256(raw).hexdigest())
            path.write_text(json.dumps(state)); path.with_name('serial.bin').write_bytes(raw)
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                self.validate((path,state,raw,plan,result,hashes))

    def test_pinned_historical_hashes_cannot_be_replaced_by_self_consistent_forgery(self):
        path,state,raw,plan,result,hashes=self.bundle()
        with patch.object(runner.installer,'evidence_path',side_effect=Path),self.assertRaises(ValueError):
            runner.validate_failure(path,plan,result,hashes)

    def test_local_only_default_and_invalid_bundle_never_connect(self):
        for rejected in (False,True):
            output=self.root/('reject' if rejected else 'local')
            argv=['stage_hfs_write_diagnostic.py','--inputs','bundle.json','--output',str(output)]
            if rejected: argv+=['--execute']
            with patch.object(sys,'argv',argv),patch.object(Path,'is_relative_to',return_value=True), \
                    patch.object(runner,'load_plan',side_effect=ValueError('changed historical artifacts') if rejected else None,
                                 return_value={'profile':'write-diagnostic'}), \
                    patch.object(runner.installer.subprocess,'run') as network,contextlib.redirect_stdout(io.StringIO()):
                if rejected:
                    with self.assertRaises(ValueError): runner.main()
                else: self.assertEqual(runner.main(),0)
            network.assert_not_called(); self.assertEqual(output.exists(),not rejected)

    def test_diagnostic_result_preserves_failed_write_and_full_prior_fat_baseline(self):
        plan,result=fixtures.WriteInstallerTests().result_bundle()
        plan.update(profile='write-diagnostic',expected_boot_before_sha256='e'*64)
        result['sd_backup']='probe.hfs-write-no-admission-20261012.bin'
        runner.installer.validate_result(result,plan)
        result['write_trial_backups']['before'][1]['sha256']='0'*64
        with self.assertRaises(ValueError): runner.installer.validate_result(result,plan)

    def test_diagnostic_recorder_uses_its_full_successor_plan_validator(self):
        plan,result=fixtures.WriteInstallerTests().result_bundle()
        plan.update(profile='write-diagnostic',expected_boot_before_sha256='e'*64)
        result['sd_backup']='probe.hfs-write-no-admission-20261012.bin'
        (self.root/'plan.json').write_text(json.dumps(plan)); (self.root/'result.json').write_text(json.dumps(result))
        (self.root/'inputs.json').write_text('{}'); (self.root/'remote-source.sha256').write_text(hashlib.sha256(b'fixed-source').hexdigest())
        with patch.object(recorder.installer,'evidence_path',side_effect=Path), \
                patch.object(runner,'load_plan',return_value={k:v for k,v in plan.items() if k!='run'}) as diagnostic, \
                patch.object(recorder.installer,'load_plan',side_effect=AssertionError('wrong validator')), \
                patch.object(recorder.installer,'remote_source',return_value='fixed-source'):
            loaded,_,_=recorder.load_inputs(self.root/'inputs.json',self.root)
        self.assertEqual(loaded,plan); diagnostic.assert_called_once()

    def successor_bundle(self):
        previous,result=fixtures.WriteInstallerTests().result_bundle()
        previous.update(profile='write-trial',new_image_sha256=runner.PREVIOUS_IMAGE,
            evidence_sha256={},host='sandrzej@192.168.4.23',expected={'exact':'identity'},fixture_sha256='d'*64,
            current_mbr_sha256='c'*64,backup_run='/home/sandrzej/xnu-gate4-hfs-stage-abcdefgh',
            boot_backup_sha256='1'*64,original_mbr_sha256='2'*64,prior_boot_run='prior-boot',
            prior_correction_run='prior-correction',passed_sd_image_sha256='3'*64,failed_hfs_image_sha256='4'*64)
        result['image_sha256']=runner.PREVIOUS_IMAGE
        current=copy.deepcopy(previous); current.pop('run')
        current.update(new_image_sha256='5'*64,linux_boot_id='54b2ad20-73c0-4dc2-a6b7-c96506b04a0b')
        actual=self.root/'kernel'; actual.write_bytes(b'\0'.join((b'RPI5XNU:SD:WRITE_START_BEGIN',
            b'RPI5XNU:SD:WRITE_INIT_BEGIN',b'RPI5XNU:SD:WRITE_INIT_FAIL STAGE=',
            b'RPI5XNU:SD:WRITE_START_FAIL STAGE=',b'RPI5XNU:SD:WRITE_CACHE_OBSERVED CACHE=')))
        build=self.root/'build.json'; build.write_text(json.dumps({'kernel_artifact':{'path':str(actual)}}))
        preflight=self.root/'preflight.json'; preflight.write_text(json.dumps({'kernel_build_manifest':str(build)}))
        reports={'previous_plan':previous,'previous_result':result,'previous_trial':{},
                 'current_inputs':{'write_preflight':str(preflight)}}
        paths={key:self.root/(key+'.json') for key in reports}
        for key,value in reports.items(): paths[key].write_text(json.dumps(value))
        inputs=self.root/'diagnostic.json'; inputs.write_text(json.dumps({k:str(v) for k,v in paths.items()}))
        return inputs,paths,previous,result,current,actual

    def load_successor(self,inputs,paths,current):
        with patch.object(runner,'PREVIOUS_PLAN',runner.installer.checker.sha256(paths['previous_plan'])), \
                patch.object(runner,'PREVIOUS_RESULT',runner.installer.checker.sha256(paths['previous_result'])), \
                patch.object(runner.installer,'evidence_path',side_effect=Path), \
                patch.object(runner.installer,'load_plan',return_value=copy.deepcopy(current)), \
                patch.object(runner,'validate_failure',return_value={'serial_sha256':'a'*64}):
            return runner.load_plan(inputs)

    def test_successor_requires_new_boot_preserves_history_and_binds_complete_fat(self):
        inputs,paths,previous,result,current,actual=self.successor_bundle()
        plan=self.load_successor(inputs,paths,current)
        self.assertEqual(plan['profile'],'write-diagnostic')
        self.assertEqual(plan['old_image_sha256'],runner.PREVIOUS_IMAGE)
        self.assertEqual(plan['readonly_image_sha256'],previous['old_image_sha256'])
        self.assertEqual(plan['expected_boot_before_sha256'],result['write_trial_backups']['after']['boot']['sha256'])
        self.assertEqual(set(plan['prior_write_backup_sha256']),{'mbr.before-write.bin','boot-partition.before-write.img','hfs-partition.before.img'})
        self.assertEqual(plan['prior_write_run'],previous['run'])
        for key in ('host','expected','fixture_sha256','current_mbr_sha256','backup_run','boot_backup_sha256',
                    'original_mbr_sha256','prior_boot_run','prior_correction_run','passed_sd_image_sha256',
                    'failed_hfs_image_sha256','old_image_sha256','linux_boot_id','new_image_sha256'):
            bad=copy.deepcopy(current)
            bad[key]=previous['linux_boot_id'] if key=='linux_boot_id' else runner.PREVIOUS_IMAGE if key=='new_image_sha256' else 'changed'
            with self.subTest(key=key),self.assertRaises(ValueError): self.load_successor(inputs,paths,bad)
        actual.write_bytes(b'no linked startup diagnostics')
        with self.assertRaises(ValueError): self.load_successor(inputs,paths,current)


if __name__=='__main__': unittest.main()
