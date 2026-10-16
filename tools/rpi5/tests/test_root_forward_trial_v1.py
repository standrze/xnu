# SPDX-License-Identifier: BSD-2-Clause
"""Exact fixed authority, typed observer rollback and real zero-TX body doubles."""
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import root_forward_trial_v1 as stage
from tools.rpi5 import serial_root_forward_trial_v1 as recorder
from tools.rpi5 import root_forward_evidence_v1 as evidence
from tools.rpi5.tests import test_bars_assignment_trial_v1 as old
from tools.rpi5.tests import test_gem_identify_trial_v1 as gem


def fixture_for_report(report):
    """Project synthetic hardware values onto the exact actually checked image.

    This is not hardware evidence. It binds real TAG, byte extent, Device/FDT
    markers and checker contracts without re-running a compiler during replay.
    """
    from tools.rpi5.tests.test_pcie_root_forward_serial import RootForwardSerialTests
    from tools.rpi5 import pcie_root_forward_serial_core as protocol
    raw,template=RootForwardSerialTests().fixture()
    if (report.get('image_sha256')!='cbc208206bf4d8b15afd793697031d0b2cba84b49b6925dfa51cda1a2fe5c8d6' or
        report.get('manifest_sha256')!='2754ff2de036d035219a2a93bd85474f8095da17339b2bab40b2ae629eecc988' or
        report.get('image_bytes')!=18175640 or
        report.get('marker')!='RPI5XNU:BL33:PCIE_ROOT_FORWARD_TRIAL TAG=a5ff51c9c9484002b5a80494742bf271 CPUS=1 NO_CPU_ON NO_INIT ZERO_SERIAL_INPUT' or
        len(report.get('boot_markers',[]))!=len(template['boot_markers'])):
        raise ValueError('Exact checked frozen root-forward package report required')
    for old_marker,new_marker in zip(template['boot_markers'],report['boot_markers']):
        if raw.count(old_marker.encode())!=1:raise ValueError('Unique fixture boot marker required')
        raw=raw.replace(old_marker.encode(),new_marker.encode(),1)
    raw,count=re.subn(rb'(Read probe.bin bytes )\d+( hnd)',lambda m:m[1]+str(report['image_bytes']).encode()+m[2],raw)
    if count!=1:raise ValueError('Unique materialization byte extent required')
    exact=copy.deepcopy(report)
    if not protocol.inspect(raw,exact)['root_forward_trial_pass']:raise ValueError('Complete42-row fixture required')
    return raw,exact


class RootForwardControllerTests(unittest.TestCase):
    def test_actual_checked42_row_report_and_full_capture(self):
        from tools.rpi5 import pcie_root_forward_serial_core as protocol
        from tools.rpi5 import check_pcie_root_forward_package as checker
        from tools.rpi5.tests import test_pcie_root_route_serial as full
        report_path=os.environ.get('RPI5_ROOT_FORWARD_CHECKED_REPORT')
        if report_path:
            path=Path(report_path)
            if stage.sha(path)!=os.environ['RPI5_ROOT_FORWARD_CHECKED_REPORT_SHA']:raise ValueError('Retained report digest differs')
            report=json.loads(path.read_text())
        elif os.environ.get('RPI5_ROOT_FORWARD_AUDIT_REPORT')=='1':
            report=checker.inspect(stage.ROOT/'build/rpi5/pcie-id-trial-adb7yr9w')
        else:self.skipTest('Actual saved report or explicit one offline package audit required')
        raw,report=fixture_for_report(report)
        method=full.RootRouteSerialTests.test_actual_full_inspect_capture_api_with_timed_boot_to_nvme
        test=type('BoundReport',(unittest.TestCase,),{'fixture':lambda _: (raw,copy.deepcopy(report))})()
        with patch.object(checker,'inspect',side_effect=AssertionError('No compiler replay after bound report')):
            types.FunctionType(method.__code__,dict(method.__globals__,p=protocol))(test)
            for signature in protocol.health.SIGNATURES:
                with self.assertRaisesRegex(ValueError,'Fault in complete original'):protocol.inspect(raw+signature+b' after END\n',report)
        if output:=os.environ.get('RPI5_ROOT_FORWARD_REPORT_OUTPUT'):
            folder=Path(output);folder.mkdir(exist_ok=False)
            stage.save(folder/'checker-report.json',report)
            stage.save(folder/'validation.json',dict(actual_report_sha256=stage.sha(folder/'checker-report.json'),
                full_capture_pass=True,observed_field_rows=42,hardware_executed=False,fixture_not_board_evidence=True))

    def test_fixed_adapter_original_bodies_and_complete_sources(self):
        self.assertEqual(set(stage.get_descriptor.__globals__['ADAPTERS']),{'pcie-root-forward'})
        self.assertIs(stage._prepare_install.__code__,stage.prior._prepare_install.__code__)
        for name in ('load_installation','prepare_restore','launch','replay','dispatch'):
            self.assertIs(getattr(stage,name).__code__,getattr(stage.prior,name).__code__)
        self.assertIs(evidence.captured.__code__,evidence.original.captured.__code__)
        self.assertIs(recorder.bindings.__code__,recorder.original.bindings.__code__)
        pins=stage.source_pins()
        for name in ('root_forward_trial_v1.py','serial_root_forward_trial_v1.py','root_forward_evidence_v1.py',
            'tests/test_root_forward_trial_v1.py','stage_framebuffer_observation_trial_v2.py',
            'serial_framebuffer_observation_trial_v2.py','framebuffer_observation_evidence_v2.py'):
            path=stage.ROOT/'tools/rpi5'/name;self.assertEqual(pins[str(path)],stage.sha(path))

    def test_typed_observer_intake_rejects_bad_pair_seal_and_type(self):
        with tempfile.TemporaryDirectory(prefix='root-forward-intake-',dir=stage.ROOT/'build/rpi5') as name:
            path=Path(name);plan={'media':{'profile':stage.observer.engine.RESTORE,'controller':stage.observer.CONTROLLER}}
            (path/'plan.json').write_text(json.dumps(plan))
            context={'result':{'publication':{'protected_files_sha256':{n:v[1] for n,v in stage.GOOD.items()}}}}
            with patch.object(stage.observer,'restoration',return_value=context) as called,\
                patch.object(stage.prior,'baseline',side_effect=AssertionError('Exact observer typed reader required')):
                self.assertIs(stage.baseline(path,'a'*64,'b'*64),context);called.assert_called_once_with(path,'a'*64,'b'*64)
            for key in stage.GOOD:
                altered=copy.deepcopy(context);altered['result']['publication']['protected_files_sha256'][key]='0'*64
                with patch.object(stage.observer,'restoration',return_value=altered),self.assertRaises(ValueError):stage.baseline(path,'a'*64,'b'*64)
            with patch.object(stage.observer,'restoration',side_effect=ValueError('bad seal')),self.assertRaisesRegex(ValueError,'seal'):
                stage.baseline(path,'a'*64,'b'*64)
            for field in ('profile','controller'):
                changed=copy.deepcopy(plan);changed['media'][field]='unknown';(path/'plan.json').write_text(json.dumps(changed))
                with patch.object(stage.observer,'restoration') as wrong,self.assertRaises(Exception):stage.baseline(path,'a'*64,'b'*64)
                wrong.assert_not_called()

    def test_actual_original_pair250_intake_without_compiler_replay(self):
        directory=stage.ROOT/'build/rpi5/pcie-gem-identify-restored-20261013'
        seal='0115e916311ff95663a641b98b9d17adf2e9ee8c93c9ae6ddb2e0c9e17116500'
        plan='36ebbbb3d9664fc9fbf2f66429110ffe7bb2310757fc131dbef090b8e3981b9a'
        with patch.object(stage.observer,'restoration',side_effect=AssertionError('Not an observer restoration')),\
            patch.object(stage.observer.checker,'inspect',side_effect=AssertionError('No compiler replay')):
            context=stage.baseline(directory,seal,plan)
        self.assertEqual(len(context['result']['next_catalog']),250)
        for name,value in stage.GOOD.items():self.assertEqual(context['result']['publication']['protected_files_sha256'][name],value[1])

    def test_completed_observer_intake_when_pins_supplied(self):
        directory=os.environ.get('RPI5_ROOT_FORWARD_BASELINE')
        if not directory:self.skipTest('Observer has not completed restoration; no invented receipt')
        with patch.object(stage.observer.checker,'inspect',side_effect=AssertionError('No compiler replay')),\
            patch.object(stage.prior,'baseline',side_effect=AssertionError('Exact observer typed reader required')):
            result=stage.baseline(Path(directory),os.environ['RPI5_ROOT_FORWARD_BASELINE_SEAL'],os.environ['RPI5_ROOT_FORWARD_BASELINE_PLAN'])
        self.assertEqual(result['plan']['media']['controller'],stage.observer.CONTROLLER)
        self.assertGreater(len(result['result']['next_catalog']),250)

    def test_complete_protocol_api(self):
        method=old.AssignmentControllerTests.test_complete_protocol_api_required_before_descriptor_admission
        types.FunctionType(method.__code__,dict(method.__globals__,stage=stage))(self)

    def test_fixed_descriptor_authority(self):
        method=gem.GEMControllerTests.test_fixed_descriptor_rejects_wrong_authority
        text=Path(gem.__file__).read_text();start=text.index('    def test_fixed_descriptor_rejects_wrong_authority(self):')
        end=text.index('\n    def ',start+5);body=text[start:end].replace("adapter='pcie-gem-identify'","adapter='pcie-root-forward'")
        scope=dict(method.__globals__,stage=stage);exec(compile('class Fixed(unittest.TestCase):\n'+body,__file__,'exec'),scope)
        scope['Fixed']('test_fixed_descriptor_rejects_wrong_authority').test_fixed_descriptor_rejects_wrong_authority()

    def test_actual_prepublication_namespace(self):
        text=Path(gem.__file__).read_text();start=text.index('    def test_prepublication_actual_recorder_namespace_and_report(self):')
        end=text.index('\n    def ',start+5);body=text[start:end]
        for a,b in (('test_pcie_gem_identify_serial','test_pcie_root_forward_serial'),('pcie_gem_identify_serial_core','pcie_root_forward_serial_core'),
            ('fixture.GEMIdentifySerialTests()','fixture.RootForwardSerialTests()')):body=body.replace(a,b)
        scope=dict(gem.__dict__,stage=stage,recorder=recorder);exec(compile('class Admission(unittest.TestCase):\n'+body,__file__,'exec'),scope)
        scope['Admission']('test_prepublication_actual_recorder_namespace_and_report').test_prepublication_actual_recorder_namespace_and_report()

    def test_actual_recorder_return_launcher_and_post_end_panic(self):
        text=Path(old.__file__).read_text();start=text.index('    def test_real_recorder_body_capture_return_replay(self):')
        end=text.index('\n\nif __name__',start);body=text[start:end]
        pairs=(('serial_bars_assignment_trial_v1','serial_root_forward_trial_v1'),('bars_assignment_trial_v1','root_forward_trial_v1'),
            ('bars_assignment_evidence_v1','root_forward_evidence_v1'),('test_pcie_bars_assignment_serial','test_pcie_root_forward_serial'),
            ('pcie_bars_assignment_serial_core','pcie_root_forward_serial_core'),('fixture.BarsAssignmentSerialTests()','fixture.RootForwardSerialTests()'),
            ('assignment_trial_pass','root_forward_trial_pass'),
            ('stage.prior.prior.prior.base.loaded_sources()','stage.prior.prior.prior.prior.prior.prior.base.loaded_sources()'))
        for a,b in pairs:
            if a not in body:raise ValueError('Actual recorder fixture seam changed: '+a)
            body=body.replace(a,b)
        scope=dict(old.__dict__,stage=stage,recorder=recorder,evidence=evidence)
        exec(compile('class Actual(unittest.TestCase):\n'+body,__file__,'exec'),scope)
        scope['Actual']('test_real_recorder_body_capture_return_replay').test_real_recorder_body_capture_return_replay()


if __name__=='__main__':unittest.main()
