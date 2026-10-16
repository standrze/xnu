# SPDX-License-Identifier: BSD-2-Clause
"""Exact fixed authority, typed observer rollback and real zero-TX body doubles."""
import copy
import contextlib
import io
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import root_forward_trial_v2 as stage
from tools.rpi5 import serial_root_forward_trial_v2 as recorder
from tools.rpi5 import root_forward_evidence_v2 as evidence
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


class RootForwardControllerV2Tests(unittest.TestCase):
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
        else:
            path=stage.ROOT/'build/rpi5/root-forward-controller-report-20261013/checker-report.json'
            if stage.sha(path)!='7a2937e7df8b1a9d5aa585e91d2b8ba4323446a5e453d7ef4f99084c872b1665':raise ValueError('Retained report digest differs')
            report=json.loads(path.read_text())
        raw,report=fixture_for_report(report)
        method=full.RootRouteSerialTests.test_actual_full_inspect_capture_api_with_timed_boot_to_nvme
        test=type('BoundReport',(unittest.TestCase,),{'fixture':lambda _: (raw,copy.deepcopy(report))})()
        with patch.object(checker,'inspect',side_effect=AssertionError('No compiler replay after bound report')):
            types.FunctionType(method.__code__,dict(method.__globals__,p=protocol))(test)
            for signature in protocol.health.SIGNATURES:
                with self.assertRaisesRegex(ValueError,'Fault in complete original'):protocol.inspect(raw+signature+b' after END\n',report)
            reference=dict(path=str(stage.ROOT/'build/rpi5/pcie-root-forward-case-20261013/descriptor.json'),
                sha256='eb39e17fd263f55a26c818b40ea0e042f842d19a5df957ba3f01b40c2ae8c46a')
            selected=stage.load_descriptor(reference)
            checkpoint=dict(payload={'media_plan':{'descriptor':reference,'preflight':report}},
                evidence_sha256=stage.source_pins()|selected['record']['source_sha256'])
            self.assertTrue(stage.admit(checkpoint)['actual_package_report_bound'])
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
        self.assertIs(recorder.base_bindings.__code__,recorder.original.bindings.__code__)
        pins=stage.source_pins()
        for name in ('root_forward_trial_v2.py','serial_root_forward_trial_v2.py','root_forward_evidence_v2.py',
            'tests/test_root_forward_trial_v2.py','stage_framebuffer_diagnostic_trial.py',
            'serial_framebuffer_diagnostic_trial.py','framebuffer_diagnostic_evidence.py'):
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

    def test_completed_diagnostic266_intake_exact_receipt(self):
        directory=stage.ROOT/'build/rpi5/framebuffer-diagnostic-restored-20261013'
        seal='2188829311d54d1eafc36347e6a6dcb4bbb1a063ec773094949cb166af07681a'
        plan='2856ce63dd79cf88a3d2feb43a3836f86949118f580966f0830fb4df32bb30de'
        self.assertEqual(stage.sha(directory/'result.json'),'fb83d0a3ee4f9c4c70e8e7949dad1d403e3de4479b3a1dc33bde73689f31e98e')
        with patch.object(stage.observer.checker,'inspect',side_effect=AssertionError('No compiler replay')),\
            patch.object(stage.prior,'baseline',side_effect=AssertionError('Exact observer typed reader required')):
            result=stage.baseline(directory,seal,plan)
            with self.assertRaises(ValueError):stage.baseline(directory,'0'*64,plan)
            with self.assertRaises(ValueError):stage.baseline(directory,seal,'0'*64)
        self.assertEqual(result['plan']['media']['controller'],stage.observer.CONTROLLER)
        self.assertEqual(len(result['result']['next_catalog']),266)
        self.assertEqual(result['result']['publication']['identity']['boot_id'],'0bd14821-0b05-4cde-b7ba-0216c00f7640')
        for name,value in stage.GOOD.items():self.assertEqual(result['result']['publication']['protected_files_sha256'][name],value[1])

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
        pairs=(('serial_bars_assignment_trial_v1','serial_root_forward_trial_v2'),('bars_assignment_trial_v1','root_forward_trial_v2'),
            ('bars_assignment_evidence_v1','root_forward_evidence_v2'),('test_pcie_bars_assignment_serial','test_pcie_root_forward_serial'),
            ('pcie_bars_assignment_serial_core','pcie_root_forward_serial_core'),('fixture.BarsAssignmentSerialTests()','fixture.RootForwardSerialTests()'),
            ('assignment_trial_pass','root_forward_trial_pass'),
            ('stage.prior.prior.prior.base.loaded_sources()','stage.prior.prior.prior.prior.prior.prior.base.loaded_sources()'))
        for a,b in pairs:
            if a not in body:raise ValueError('Actual recorder fixture seam changed: '+a)
            body=body.replace(a,b)
        marker="        module=types.ModuleType('_assignment_actual_recorder_fixture')"
        modem="recorder.struct.pack('=I',recorder.termios.TIOCM_DTR|recorder.termios.TIOCM_RTS)"
        replacement="        text=text.replace(\"patch.object(g['fcntl'], 'ioctl')\",\"patch.object(g['fcntl'], 'ioctl', return_value="+modem+")\")\n"+marker
        self.assertEqual(body.count(marker),1);body=body.replace(marker,replacement)
        scope=dict(old.__dict__,stage=stage,recorder=recorder,evidence=evidence)
        exec(compile('class Actual(unittest.TestCase):\n'+body,__file__,'exec'),scope)
        scope['Actual']('test_real_recorder_body_capture_return_replay').test_real_recorder_body_capture_return_replay()

    def test_actual_body_modem_controls_after_raw_before_arm(self):
        from tools.rpi5 import pcie_root_forward_serial_core as protocol
        context=dict(descriptor={'protocol':protocol},installed=dict(directory=str(stage.ROOT/'build/rpi5/offline-root-forward-v2'),
            preflight={},pair_sha256={'probe.bin':'1'*64,'bl31.bin':'2'*64}),
            evidence=stage.source_pins()|{str(Path(protocol.__file__).resolve()):stage.sha(protocol.__file__)})
        for outcome in ('ready','dtr-low','rts-low','read-error'):
            with self.subTest(outcome=outcome),tempfile.TemporaryDirectory(prefix='root-forward-modem-',dir=stage.ROOT/'build/rpi5') as name,tempfile.TemporaryFile() as uart:
                output=Path(name);output.rmdir();fn=recorder.bindings(context);g=fn.__globals__;calls=[]
                required=recorder.termios.TIOCM_DTR|recorder.termios.TIOCM_RTS
                def ioctl(fd,request,arg=None):
                    if request==recorder.termios.TIOCEXCL:
                        self.assertEqual(calls,[]);calls.append('exclusive');return 0
                    if request==recorder.termios.TIOCMBIS:
                        self.assertEqual(calls,['exclusive','raw']);self.assertEqual(arg,struct.pack('=I',required));calls.append('set');return arg
                    self.assertEqual(request,recorder.termios.TIOCMGET);self.assertEqual(calls,['exclusive','raw','set'])
                    self.assertEqual(arg,struct.pack('=I',0));calls.append('get')
                    if outcome=='read-error':raise OSError('Injected modem read error')
                    return struct.pack('=I',{'ready':required,'dtr-low':recorder.termios.TIOCM_RTS,'rts-low':recorder.termios.TIOCM_DTR}[outcome])
                def configure(*_):calls.append('restore' if 'get' in calls else 'raw')
                original_open=os.open
                with patch.object(g['lease'],'hold',return_value=contextlib.nullcontext()),\
                    patch.object(g['subprocess'],'run',return_value=subprocess.CompletedProcess([],1,'','')),\
                    patch.object(g['os'],'open',side_effect=lambda p,*a,**k:os.dup(uart.fileno()) if p=='/dev/cu.usbmodemTEST' else original_open(p,*a,**k)),\
                    patch.object(g['os'],'read',side_effect=RuntimeError('End explicit recorder fixture')) as read,\
                    patch.object(g['os'],'write',side_effect=AssertionError('UART payload forbidden')),\
                    patch.object(g['fcntl'],'ioctl',side_effect=ioctl),\
                    patch.object(g['termios'],'tcgetattr',side_effect=lambda _: [0,0,0,0,0,0,[0]*32]),\
                    patch.object(g['termios'],'tcsetattr',side_effect=configure),patch.object(g['termios'],'tcflush'),\
                    patch.object(g['select'],'select',side_effect=lambda fd,*_: (fd,[],[])),contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(fn(['/dev/cu.usbmodemTEST',str(output),'--installation',context['installed']['directory'],'--seconds','600']),1)
                self.assertEqual(calls,['exclusive','raw','set','get','restore'])
                state=json.loads((output/'state.json').read_text());self.assertEqual(state['transmitted_bytes'],0)
                self.assertEqual(state['bytes'],0);self.assertEqual(state['status'],'failed')
                self.assertEqual((output/'armed.json').exists(),outcome=='ready')
                self.assertEqual((output/'serial.bin').exists(),outcome=='ready')
                self.assertEqual(read.call_count,1 if outcome=='ready' else 0)


if __name__=='__main__':unittest.main()
