# SPDX-License-Identifier: BSD-2-Clause
"""Actual selected-package API, typed276 rollback and modem-gated receiver body."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import gem_selected_trial_v1 as stage
from tools.rpi5 import serial_gem_selected_trial_v1 as recorder
from tools.rpi5 import gem_selected_evidence_v1 as evidence
from tools.rpi5.tests import test_root_forward_trial_v2 as previous

DESCRIPTOR=stage.ROOT/'build/rpi5/pcie-gem-selected-case-20261013/descriptor.json'
DESCRIPTOR_SHA='bc92871b36b6c1e6b0e6b01120fbf48e6cb8882c43a2fa84f46521d6fc8ba254'
REPORT=stage.ROOT/'build/rpi5/gem-selected-controller-report-20261013/checker-report.json'
REPORT_SHA='8798c619d74ebb9bfa84afa901f239284693334a1f11a3433b33773a5adbc43b'


def fixture_for_report(report):
    from tools.rpi5.tests.test_pcie_gem_selected_serial import GEMSelectedSerialTests
    from tools.rpi5 import pcie_gem_selected_serial_core as protocol
    raw,template=GEMSelectedSerialTests().fixture()
    if (report.get('image_sha256')!='ca6dec70af6773bf656a955909cbba9c27eeddeaaad75b460bfcd9a9450c5dda' or
        report.get('manifest_sha256')!='a287f869e27bd1926dfcc2147ea998e673e02dd0aff8b2f9a45816324dc90904' or
        report.get('image_bytes')!=18175640 or
        report.get('marker')!='RPI5XNU:BL33:PCIE_GEM_SELECTED_TRIAL TAG=0d7a8a86a7854a6f914c8af8baffc874 CPUS=1 NO_CPU_ON NO_INIT ZERO_SERIAL_INPUT' or
        len(report.get('boot_markers',[]))!=len(template['boot_markers'])):
        raise ValueError('Exact checked selected-clock report required')
    for old,new in zip(template['boot_markers'],report['boot_markers']):
        if raw.count(old.encode())!=1:raise ValueError('Unique fixture marker required')
        raw=raw.replace(old.encode(),new.encode(),1)
    raw,count=re.subn(rb'(Read probe.bin bytes )\d+( hnd)',lambda m:m[1]+str(report['image_bytes']).encode()+m[2],raw)
    if count!=1:raise ValueError('Unique materialization byte extent required')
    result=protocol.inspect(raw,report)
    if not result['selected_clock_trial_pass'] or result['clock_readiness_independently_proven']:
        raise ValueError('Complete register-profile-only fixture required')
    return raw,copy.deepcopy(report)


def inherited(test,name):
    """Reuse the actual frozen receiver/launcher test body with exact name seams."""
    source=Path(previous.__file__).read_text();start=source.index('    def '+name+'(')
    finish=source.find('\n    def ',start+5)
    if finish<0:finish=source.index("\n\nif __name__",start)
    body=source[start:finish]
    for before,after in (
        ('serial_root_forward_trial_v2','serial_gem_selected_trial_v1'),
        ('root_forward_trial_v2','gem_selected_trial_v1'),
        ('root_forward_evidence_v2','gem_selected_evidence_v1'),
        ('test_pcie_root_forward_serial','test_pcie_gem_selected_serial'),
        ('pcie_root_forward_serial_core','pcie_gem_selected_serial_core'),
        ('fixture.RootForwardSerialTests()','fixture.GEMSelectedSerialTests()'),
        ('root_forward_trial_pass','selected_clock_trial_pass'),
        ("adapter='pcie-root-forward'","adapter='pcie-gem-selected'")):
        body=body.replace(before,after)
    scope=dict(previous.__dict__,stage=stage,recorder=recorder,evidence=evidence)
    exec(compile('class Actual(unittest.TestCase):\n'+body,__file__,'exec'),scope)
    getattr(scope['Actual'](name),name)()


class GEMSelectedControllerTests(unittest.TestCase):
    def test_actual_checked42_row_report_full_capture_and_admission(self):
        from tools.rpi5 import pcie_gem_selected_serial_core as protocol
        from tools.rpi5 import check_pcie_gem_selected_package as checker
        from tools.rpi5.tests import test_pcie_root_route_serial as full
        fresh=os.environ.get('RPI5_GEM_SELECTED_AUDIT_REPORT')=='1'
        if fresh:report=checker.inspect(stage.ROOT/'build/rpi5/pcie-id-trial-vf78_802')
        else:
            self.assertEqual(stage.sha(REPORT),REPORT_SHA);report=json.loads(REPORT.read_text())
        raw,report=fixture_for_report(report)
        method=full.RootRouteSerialTests.test_actual_full_inspect_capture_api_with_timed_boot_to_nvme
        test=type('BoundReport',(unittest.TestCase,),{'fixture':lambda _: (raw,copy.deepcopy(report))})()
        with patch.object(checker,'inspect',side_effect=AssertionError('No compiler replay after report')):
            types.FunctionType(method.__code__,dict(method.__globals__,p=protocol))(test)
            self.assertEqual(stage.sha(DESCRIPTOR),DESCRIPTOR_SHA)
            reference=dict(path=str(DESCRIPTOR),sha256=DESCRIPTOR_SHA);selected=stage.load_descriptor(reference)
            checkpoint=dict(payload={'media_plan':{'descriptor':reference,'preflight':report}},
                evidence_sha256=stage.source_pins()|selected['record']['source_sha256'])
            self.assertTrue(stage.admit(checkpoint)['modem_gate_bound_before_arm'])
            for signature in protocol.health.SIGNATURES:
                with self.assertRaises(ValueError):protocol.inspect(raw+signature+b' after END\n',report)
            for key in ('selected_clock_contract','marker'):
                bad=copy.deepcopy(checkpoint);bad['payload']['media_plan']['preflight'].pop(key)
                with self.assertRaises((ValueError,KeyError)):stage.admit(bad)
            bad=copy.deepcopy(checkpoint);bad['evidence_sha256'].pop(str(Path(protocol.__file__).resolve()))
            with self.assertRaises(ValueError):stage.admit(bad)
        if fresh:
            REPORT.parent.mkdir(exist_ok=False);stage.save(REPORT,report)
            stage.save(REPORT.parent/'validation.json',dict(actual_report_sha256=stage.sha(REPORT),
                full_capture_pass=True,observed_field_rows=42,hardware_executed=False,fixture_not_board_evidence=True))

    def test_fixed_original_bodies_and_complete_sources(self):
        self.assertEqual(set(stage.get_descriptor.__globals__['ADAPTERS']),{'pcie-gem-selected'})
        self.assertIs(stage._prepare_install.__code__,stage.prior._prepare_install.__code__)
        for n in ('load_installation','prepare_restore','launch','replay','dispatch'):
            self.assertIs(getattr(stage,n).__code__,getattr(stage.prior,n).__code__)
        self.assertIs(evidence.captured.__code__,evidence.original.captured.__code__)
        self.assertIs(recorder.bindings.__code__,recorder.accepted.bindings.__code__)
        self.assertIs(recorder.assert_modem_ready,recorder.accepted.assert_modem_ready)
        self.assertIs(stage.dispatch.__globals__['subprocess'],stage.upload_transport)
        pins=stage.source_pins()
        for n in ('gem_selected_trial_v1.py','serial_gem_selected_trial_v1.py','gem_selected_evidence_v1.py',
            'tests/test_gem_selected_trial_v1.py','serial_root_forward_trial_v2.py'):
            p=stage.ROOT/'tools/rpi5'/n;self.assertEqual(pins[str(p)],stage.sha(p))

    def test_compressed_upload_exact_forwarding_and_unchanged_ssh(self):
        original=['scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
            '/local/exact-candidate.bin',stage.HOST+':/home/sandrzej/xnu-link-v2-testabcd/candidate.bin']
        sentinel=object()
        with patch.object(stage.subprocess,'run',return_value=sentinel) as call:
            self.assertIs(stage.upload_run(original,check=True,timeout=60),sentinel)
            call.assert_called_once_with(['scp','-C',*original[1:]],check=True,timeout=180)
            self.assertNotIn('-C',original)
        for last,timeout in (('python3 -',30),('sudo -n python3 -',300)):
            command=stage.SSH+[last];kwargs=dict(input='exact source',text=True,capture_output=True,timeout=timeout)
            with patch.object(stage.subprocess,'run',return_value=sentinel) as call:
                self.assertIs(stage.upload_run(command,**kwargs),sentinel)
                call.assert_called_once_with(command,**kwargs)
        for changed,kwargs in ((['scp','-r',*original[1:]],{'check':True,'timeout':60}),
            (original,{'check':True,'timeout':180}),(original,{'check':False,'timeout':60})):
            with patch.object(stage.subprocess,'run',side_effect=AssertionError('No broadened upload')),self.assertRaises(ValueError):
                stage.upload_run(changed,**kwargs)

    def test_actual_dispatch_upload_timeout_propagates_before_sd_program_no_retry(self):
        media=dict(profile=stage.engine.TRIAL,descriptor='fixture',files=[{'target':'probe.bin','candidate':'candidate.bin'}],
            candidates={'probe.bin':'/local/exact-candidate.bin'})
        seal=types.SimpleNamespace(revalidate=lambda *_:{'media_plan':media},save_new=lambda *_:None)
        engine=types.SimpleNamespace(plan_from_seal=lambda *_:({'media':media},'1'*64),
            remote_source=lambda *_:self.fail('Upload failure cannot produce/execute SD program'))
        with tempfile.TemporaryDirectory(dir=stage.ROOT/'build/rpi5') as name:
            out=Path(name).resolve();out.rmdir();calls=[]
            def run(command,**kwargs):
                calls.append((command,kwargs))
                if command[0]=='scp':
                    self.assertEqual(command[1],'-C');self.assertEqual(kwargs,{'check':True,'timeout':180})
                    raise subprocess.TimeoutExpired(command,180)
                self.assertEqual(command,stage.SSH+['python3 -']);self.assertEqual(kwargs['timeout'],30)
                return subprocess.CompletedProcess(command,0,json.dumps({'run':'/home/sandrzej/xnu-link-v2-testabcd'}),'')
            actual=stage.private(stage.dispatch,seals=seal,engine=engine,
                descriptors=types.SimpleNamespace(get=lambda _: {'hardware_allowed':True}))
            with patch.object(stage.subprocess,'run',side_effect=run):
                with self.assertRaises(subprocess.TimeoutExpired):actual({},'2'*64,out,{},True)
                self.assertEqual(len(calls),2)
                with self.assertRaises(FileExistsError):actual({},'2'*64,out,{},True)
                self.assertEqual(len(calls),2)
            self.assertTrue((out/'plan.json').is_file())
            for file in ('dispatch-intent.json','remote-program.py','result.json','completion.json'):
                self.assertFalse((out/file).exists())

    def test_exact_completed276_pair_intake_without_compiler_or_history_replay(self):
        from tools.rpi5 import check_pcie_gem_selected_package as checker
        from tools.rpi5 import check_pcie_root_forward_package as old_checker
        directory=stage.ROOT/'build/rpi5/pcie-root-forward-restored-20261013-fresh'
        seal='bda0a185c163873ea6ca22325dcd9e5cad5dcd32471812e258702d61cf5eb9c8'
        plan='4936db726f9a163efe707d640b6077f7f8e1b4d0c22920cd6794100224803dba'
        self.assertEqual(stage.sha(directory/'result.json'),'b609aecc5d97270b22fbcb10d5ff4712d617cb523842465e7b87b001331e50cd')
        with patch.object(checker,'inspect',side_effect=AssertionError('No compile')),\
            patch.object(old_checker,'inspect',side_effect=AssertionError('No old compile')),\
            patch.object(stage.previous,'baseline',side_effect=AssertionError('No historical replay')):
            context=stage.baseline(directory,seal,plan)
            with self.assertRaises(ValueError):stage.baseline(directory,'0'*64,plan)
            with self.assertRaises(ValueError):stage.baseline(directory,seal,'0'*64)
        self.assertEqual(len(context['result']['next_catalog']),276)
        self.assertEqual(context['result']['publication']['identity']['boot_id'],'d2af120f-0361-43af-a909-c1674e7a3030')
        self.assertEqual(context['result']['publication']['pair_sha256'],{n:v[1] for n,v in stage.GOOD.items()})

    def test_pair_intake_rejects_wrong_type_and_current_pair(self):
        context=dict(plan={'media':{'controller':'reviewed-case-active-window-v3'}},
            result={'publication':{'pair_sha256':{n:v[1] for n,v in stage.GOOD.items()}}})
        for field in ('controller','bl31.bin','probe.bin'):
            bad=copy.deepcopy(context)
            if field=='controller':bad['plan']['media'][field]='single-loader'
            else:bad['result']['publication']['pair_sha256'][field]='0'*64
            with patch.object(stage,'sealed_operation',return_value=bad) as called,self.assertRaises(ValueError):
                stage.baseline('unused','1'*64,'2'*64)
            called.assert_called_once_with('unused','1'*64,'2'*64,stage.engine.RESTORE)
        with patch.object(stage,'sealed_operation',side_effect=ValueError('Invalid sealed restore')),self.assertRaises(ValueError):
            stage.baseline('unused','1'*64,'2'*64)

    def test_complete_protocol_api(self):inherited(self,'test_complete_protocol_api')
    def test_fixed_descriptor_authority(self):inherited(self,'test_fixed_descriptor_authority')
    def test_actual_prepublication_namespace(self):inherited(self,'test_actual_prepublication_namespace')
    def test_actual_recorder_return_launcher_and_post_end_panic(self):inherited(self,'test_actual_recorder_return_launcher_and_post_end_panic')
    def test_actual_body_modem_controls_after_raw_before_arm(self):inherited(self,'test_actual_body_modem_controls_after_raw_before_arm')

if __name__=='__main__':unittest.main()
