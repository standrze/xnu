# SPDX-License-Identifier: BSD-2-Clause
"""Typed predecessor extension and unchanged executable reset trial bodies."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import phy_reset_trial_v2 as stage
from tools.rpi5 import serial_phy_reset_trial_v2 as recorder
from tools.rpi5 import phy_reset_evidence_v2 as evidence
from tools.rpi5.tests import test_phy_reset_trial_v1 as prior


def inherited(test,name):
    source=Path(prior.__file__).read_text()
    start=source.index('def inherited(');end=source.index('\n\nclass PHYResetControllerTests',start)
    body=source[start:end]
    for old,new in (('serial_phy_reset_trial_v1','serial_phy_reset_trial_v2'),
                    ('phy_reset_trial_v1','phy_reset_trial_v2'),
                    ('phy_reset_evidence_v1','phy_reset_evidence_v2')):
        body=body.replace(old,new)
    scope=dict(prior.__dict__,stage=stage,recorder=recorder,evidence=evidence)
    exec(compile(body,__file__,'exec'),scope)
    scope['inherited'](test,name)


class PHYResetControllerV2Tests(unittest.TestCase):
    def test_exact_one_new_typed_predecessor_and_original_fallback_policy(self):
        with tempfile.TemporaryDirectory(dir=stage.ROOT/'build/rpi5') as name:
            directory=Path(name).resolve()
            media=dict(controller=stage.display_xnu_v2.CONTROLLER,profile=stage.display_xnu_v2.engine.RESTORE)
            (directory/'plan.json').write_text(json.dumps({'media':media}))
            files={k:v[1] for k,v in stage.GOOD.items()}|{'config.txt':stage.compact.engine.ORIGINAL_CONFIG_SHA}
            context=dict(result={'publication':{'protected_files_sha256':files}})
            with patch.object(stage.original,'baseline',side_effect=AssertionError('Only corrected typed reader')),\
                patch.object(stage.display_xnu_v2,'restoration',return_value=context) as checked:
                self.assertIs(stage.baseline(directory,'1'*64,'2'*64),context)
                checked.assert_called_once_with(directory,'1'*64,'2'*64)
                for target in ('config.txt','probe.bin','bl31.bin'):
                    bad=copy.deepcopy(context);bad['result']['publication']['protected_files_sha256'][target]='0'*64
                    with patch.object(stage.display_xnu_v2,'restoration',return_value=bad),self.assertRaises(ValueError):
                        stage.baseline(directory,'1'*64,'2'*64)
                with patch.object(stage.display_xnu_v2,'restoration',side_effect=ValueError('bad seal')),self.assertRaisesRegex(ValueError,'seal'):
                    stage.baseline(directory,'1'*64,'2'*64)
                for profile in (stage.display_xnu_v2.engine.TRIAL,'unknown',True):
                    (directory/'plan.json').write_text(json.dumps({'media':dict(media,profile=profile)}))
                    checked.reset_mock()
                    with self.assertRaises(ValueError):stage.baseline(directory,'1'*64,'2'*64)
                    checked.assert_not_called()
            # No second fallback implementation: all old types are handed to
            # the immutable v1 allowlist, including its explicit stale354 refusal.
            (directory/'plan.json').write_text(json.dumps({'media':dict(media,controller='unknown')}))
            with patch.object(stage.original,'baseline',side_effect=ValueError('v1 policy')) as old,\
                patch.object(stage.display_xnu_v2,'restoration',side_effect=AssertionError('No unknown type')),self.assertRaisesRegex(ValueError,'v1 policy'):
                stage.baseline(directory,'1'*64,'2'*64)
            old.assert_called_once_with(directory,'1'*64,'2'*64)

    def test_actual_completed374_original_intake_still_byte_only(self):
        directory=stage.ROOT/'build/rpi5/display-compact-repeat-restored-20261014'
        with patch.object(subprocess,'run',side_effect=AssertionError('No hardware/compiler')),\
            patch.object(stage.display_xnu_v2,'restoration',side_effect=AssertionError('Not v2 display type')):
            value=stage.baseline(directory,
                'f998989aa3ecd0fa51642e9fb3862195cc10f76b6c2745977c584070e12ad503',
                '96ece5e1e42dcba5e9e25d0e82c62308db07fb893227ccd3c444923b39ff51f4')
        self.assertEqual(len(value['result']['next_catalog']),374)

    def test_actual_completed394_corrected_xnu_restore_byte_only(self):
        directory=stage.ROOT/'build/rpi5/display-xnu-v2-restored-20261014'
        seal='505e983ea03c6c5d90ddff2951be5cb668c2de6f0353e5529f96331c45f8cb30'
        plan='e356a27c94253ac7c88046a29e344ddde82ca01e43e8029852bfc06285b71b4e'
        self.assertEqual(stage.sha(directory/'result.json'),
            'd1ceef296c7dac94a4b4318c1eee8ac6d6b7d8fd7142d6eca489e171bddaca79')
        with patch.object(subprocess,'run',side_effect=AssertionError('No compiler/history/hardware')),\
            patch.object(stage.original,'baseline',side_effect=AssertionError('Must use corrected typed reader')),\
            patch.object(stage.display_xnu_v2.checker,'inspect',side_effect=AssertionError('No package audit replay')):
            context=stage.baseline(directory,seal,plan)
            with self.assertRaises(ValueError):stage.baseline(directory,'0'*64,plan)
            with self.assertRaises(ValueError):stage.baseline(directory,seal,'0'*64)
            self.assertEqual(len(context['result']['next_catalog']),394)
            self.assertEqual(context['plan']['media']['controller'],'display-xnu-config-loader-controller-v2')
            self.assertEqual(context['plan']['media']['profile'],stage.display_xnu_v2.engine.RESTORE)
            self.assertEqual(context['result']['publication']['identity']['boot_id'],
                '8f1e79b1-12c6-4f74-b233-f3aa60d71990')
            for name in ('config.txt','probe.bin','bl31.bin'):
                bad=copy.deepcopy(context)
                bad['result']['publication']['protected_files_sha256'][name]='0'*64
                with patch.object(stage.display_xnu_v2,'restoration',return_value=bad),self.assertRaises(ValueError):
                    stage.baseline(directory,seal,plan)

    def test_immutable_body_identity_and_all_new_namespaces(self):
        for name in ('_prepare_install','load_installation','completed_restore','prepare_install',
                     'prepare_restore','launch','replay','main','dispatch','valid_report'):
            self.assertIs(getattr(stage,name).__code__,getattr(stage.original,name).__code__)
        self.assertIs(stage._prepare_install.__globals__['baseline'],stage.baseline)
        self.assertIs(stage.prepare_install.__globals__['_prepare_install'],stage._prepare_install)
        self.assertIs(stage.prepare_install.__globals__['admit'],stage.admit)
        self.assertIs(stage.replay.__globals__['baseline'],stage.completed_restore)
        self.assertIs(stage.replay.__globals__['prepare_restore'],stage.prepare_restore)
        self.assertIs(stage.main.__globals__['launch'],stage.launch)
        for name in ('bound_sources','revalidate','base_bindings','bindings','main'):
            self.assertIs(getattr(recorder,name).__code__,getattr(recorder.original,name).__code__)
        for name in ('captured','collect_return','load_return','inspect_return','return_source_pins'):
            self.assertIs(getattr(evidence,name).__code__,getattr(evidence.original,name).__code__)
        pins=stage.source_pins()
        for name in ('phy_reset_trial_v2.py','serial_phy_reset_trial_v2.py','phy_reset_evidence_v2.py',
                     'tests/test_phy_reset_trial_v2.py','stage_display_xnu_trial_v2.py'):
            path=stage.ROOT/'tools/rpi5'/name;self.assertEqual(pins[str(path)],stage.sha(path))

    def test_saved_exact_report_admits_only_new_actual_receiver_namespace(self):
        self.assertEqual(stage.sha(prior.REPORT),prior.REPORT_SHA)
        self.assertEqual(stage.sha(prior.DESCRIPTOR),prior.DESCRIPTOR_SHA)
        report=json.loads(prior.REPORT.read_text())
        reference=dict(path=str(prior.DESCRIPTOR),sha256=prior.DESCRIPTOR_SHA)
        selected=stage.load_descriptor(reference)
        checkpoint=dict(payload={'media_plan':{'descriptor':reference,'preflight':report}},
                        evidence_sha256=stage.source_pins()|selected['record']['source_sha256'])
        with patch.object(selected['checker'],'inspect',side_effect=AssertionError('No checker replay')),\
            patch.object(subprocess,'run',side_effect=AssertionError('No hardware/compiler')):
            value=stage.admit(checkpoint)
            self.assertTrue(value['modem_gate_bound_before_arm']);self.assertFalse(value['hardware_executed'])
            for name in ('phy_reset_trial_v2.py','serial_phy_reset_trial_v2.py','phy_reset_evidence_v2.py'):
                bad=copy.deepcopy(checkpoint);bad['evidence_sha256'].pop(str(stage.ROOT/'tools/rpi5'/name))
                with self.assertRaises(ValueError):stage.admit(bad)
            with patch.object(stage,'valid_report',side_effect=ValueError('bad bound report')),self.assertRaisesRegex(ValueError,'bound report'):
                stage.admit(checkpoint)

    def test_actual_recorder_return_launcher_and_post_end_panic(self):
        inherited(self,'test_actual_recorder_return_launcher_and_post_end_panic')

    def test_actual_body_modem_controls_after_raw_before_arm(self):
        inherited(self,'test_actual_body_modem_controls_after_raw_before_arm')


if __name__=='__main__':unittest.main()
