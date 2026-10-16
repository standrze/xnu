# SPDX-License-Identifier: BSD-2-Clause
"""Actual59-row reset API, typed display rollback and modem-gated zero-TX RX."""
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
from tools.rpi5 import phy_reset_trial_v1 as stage
from tools.rpi5 import serial_phy_reset_trial_v1 as recorder
from tools.rpi5 import phy_reset_evidence_v1 as evidence
from tools.rpi5.tests import test_root_forward_trial_v2 as previous

DESCRIPTOR=stage.ROOT/'build/rpi5/pcie-phy-reset-case-20261014/descriptor.json'
DESCRIPTOR_SHA='5e7b82e45ff31fde4b251e1d7da08ff97dbe6f7176dedb3d34730e870c8bc50d'
REPORT=stage.ROOT/'build/rpi5/pcie-phy-reset-qualification-20261014/checker-report.json'
REPORT_SHA='8228cabe8e6f0a003bd898158250df177166ca20f28df475353da7cfbc4118f1'


def fixture_for_report(report):
    from tools.rpi5.tests.test_pcie_phy_reset_serial import PHYResetSerialTests
    from tools.rpi5 import pcie_phy_reset_serial_core as protocol
    raw,template=PHYResetSerialTests().fixture()
    if (report.get('image_sha256')!='6627559f8dc8e3a78329203300b85507403a5a32c2d4b21a473834dac44c892f' or
        report.get('manifest_sha256')!='0c8b015a71ce65269e4b4d2373745f399673c95db2e5e59f86b72231f658c6fb' or
        report.get('image_bytes')!=18214120 or
        report.get('marker')!='RPI5XNU:BL33:PCIE_PHY_RESET_TRIAL TAG=617795334d2b4c95a4e7712c4ac20b65 CPUS=1 NO_CPU_ON NO_INIT ZERO_SERIAL_INPUT' or
        len(report.get('boot_markers',[]))!=len(template['boot_markers'])):
        raise ValueError('Exact checked immutable capabilities report required')
    for old,new in zip(template['boot_markers'],report['boot_markers']):
        if raw.count(old.encode())!=1:raise ValueError('Unique fixture marker required')
        raw=raw.replace(old.encode(),new.encode(),1)
    raw,count=re.subn(rb'(Read probe.bin bytes )\d+( hnd)',lambda m:m[1]+str(report['image_bytes']).encode()+m[2],raw)
    if count!=1:raise ValueError('Unique materialization byte extent required')
    result=protocol.inspect(raw,report)
    if not result['phy_reset_trial_pass'] or result['clock_readiness_independently_proven']:
        raise ValueError('Complete register-profile-only fixture required')
    return raw,copy.deepcopy(report)


def inherited(test,name):
    """Reuse the actual frozen receiver/launcher test body with exact name seams."""
    source=Path(previous.__file__).read_text();start=source.index('    def '+name+'(')
    finish=source.find('\n    def ',start+5)
    if finish<0:finish=source.index("\n\nif __name__",start)
    body=source[start:finish]
    for before,after in (
        ('serial_root_forward_trial_v2','serial_phy_reset_trial_v1'),
        ('root_forward_trial_v2','phy_reset_trial_v1'),
        ('root_forward_evidence_v2','phy_reset_evidence_v1'),
        ('test_pcie_root_forward_serial','test_pcie_phy_reset_serial'),
        ('pcie_root_forward_serial_core','pcie_phy_reset_serial_core'),
        ('fixture.RootForwardSerialTests()','fixture.PHYResetSerialTests()'),
        ('root_forward_trial_pass','phy_reset_trial_pass'),
        ("adapter='pcie-root-forward'","adapter='pcie-phy-reset'")):
        body=body.replace(before,after)
    scope=dict(previous.__dict__,stage=stage,recorder=recorder,evidence=evidence)
    exec(compile('class Actual(unittest.TestCase):\n'+body,__file__,'exec'),scope)
    getattr(scope['Actual'](name),name)()


class PHYResetControllerTests(unittest.TestCase):
    def test_actual_checked59_row_report_full_capture_and_admission(self):
        from tools.rpi5 import pcie_phy_reset_serial_core as protocol
        from tools.rpi5 import check_pcie_phy_reset_package as checker
        from tools.rpi5.tests import test_pcie_root_route_serial as full
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
            for key in ('reset_contract','capabilities_contract','selected_clock_contract','marker'):
                bad=copy.deepcopy(checkpoint);bad['payload']['media_plan']['preflight'].pop(key)
                with self.assertRaises((ValueError,KeyError)):stage.admit(bad)
            bad=copy.deepcopy(checkpoint);bad['evidence_sha256'].pop(str(Path(protocol.__file__).resolve()))
            with self.assertRaises(ValueError):stage.admit(bad)
            restored=dict(plan={'media':{'controller':'reviewed-case-active-window-v3','preflight':report,'descriptor':reference}},
                result={'publication':{'pair_sha256':{n:v[1] for n,v in stage.GOOD.items()}}})
            with patch.object(stage,'sealed_operation',return_value=restored) as intake:
                self.assertIs(stage.completed_restore('fixture','1'*64,'2'*64),restored)
                intake.assert_called_once_with('fixture','1'*64,'2'*64,stage.engine.RESTORE)
            for mutation in ('controller','probe.bin','bl31.bin','reset_contract'):
                bad=copy.deepcopy(restored)
                if mutation=='controller':bad['plan']['media']['controller']='single-loader'
                elif mutation=='reset_contract':bad['plan']['media']['preflight'].pop(mutation)
                else:bad['result']['publication']['pair_sha256'][mutation]='0'*64
                with patch.object(stage,'sealed_operation',return_value=bad),self.assertRaises(ValueError):
                    stage.completed_restore('fixture','1'*64,'2'*64)

    def test_saved_report_minus6_capture_remains_failure_with_valid_return(self):
        from tools.rpi5 import pcie_phy_reset_serial_core as protocol
        from tools.rpi5 import check_pcie_phy_reset_package as checker
        from tools.rpi5.tests.test_pcie_phy_reset_serial import PHYResetSerialTests
        from tools.rpi5.tests.test_pcie_root_route_serial import RootRouteSerialTests
        self.assertEqual(stage.sha(REPORT),REPORT_SHA)
        raw,report=fixture_for_report(json.loads(REPORT.read_text()))
        original=protocol.inspect;observed=[]
        def inspect(data,metadata):
            value=original(data,metadata)
            if b'PHYRESET STATE=3 RC=-6' in data:observed.append((data,value))
            return value
        case=PHYResetSerialTests('test_propagated_minus6_is_retained_failure_not_rehabilitation')
        with patch.object(case,'fixture',lambda:(raw,copy.deepcopy(report))),patch.object(protocol,'inspect',inspect),\
            patch.object(checker,'inspect',side_effect=AssertionError('No package compiler replay')),\
            patch.object(subprocess,'run',side_effect=AssertionError('No process/hardware')):
            case.test_propagated_minus6_is_retained_failure_not_rehabilitation()
        failed,parsed=observed[0]
        self.assertFalse(parsed['phy_reset_trial_pass']);self.assertFalse(parsed['gpio_original_fields_restored'])
        self.assertEqual(parsed['root_forward_progress']['rc'],-6)
        method=RootRouteSerialTests.test_actual_full_inspect_capture_api_with_timed_boot_to_nvme
        bound=type('BoundFailure',(unittest.TestCase,),{'fixture':lambda _: (failed,copy.deepcopy(report))})()
        with patch.object(checker,'inspect',side_effect=AssertionError('No compiler replay')),\
            patch.object(subprocess,'run',side_effect=AssertionError('No process/hardware')):
            types.FunctionType(method.__code__,dict(method.__globals__,p=protocol))(bound)

    def test_fixed_original_bodies_and_complete_sources(self):
        self.assertEqual(set(stage.get_descriptor.__globals__['ADAPTERS']),{'pcie-phy-reset'})
        self.assertIs(stage._prepare_install.__code__,stage.prior._prepare_install.__code__)
        for n in ('load_installation','prepare_restore','launch','replay','dispatch'):
            self.assertIs(getattr(stage,n).__code__,getattr(stage.prior,n).__code__)
        self.assertIs(evidence.captured.__code__,evidence.original.captured.__code__)
        self.assertIs(recorder.bindings.__code__,recorder.accepted.bindings.__code__)
        self.assertIs(recorder.assert_modem_ready,recorder.accepted.assert_modem_ready)
        self.assertIs(stage.dispatch.__globals__['subprocess'],stage.upload_transport)
        pins=stage.source_pins()
        for n in ('phy_reset_trial_v1.py','serial_phy_reset_trial_v1.py','phy_reset_evidence_v1.py',
            'tests/test_phy_reset_trial_v1.py','serial_root_forward_trial_v2.py'):
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

    def test_complete_protocol_api(self):inherited(self,'test_complete_protocol_api')
    def test_fixed_descriptor_authority(self):inherited(self,'test_fixed_descriptor_authority')
    def test_actual_recorder_return_launcher_and_post_end_panic(self):inherited(self,'test_actual_recorder_return_launcher_and_post_end_panic')
    def test_actual_body_modem_controls_after_raw_before_arm(self):inherited(self,'test_actual_body_modem_controls_after_raw_before_arm')

    def test_actual_completed374_compact_restore_byte_only(self):
        directory=stage.ROOT/'build/rpi5/display-compact-repeat-restored-20261014'
        seal='f998989aa3ecd0fa51642e9fb3862195cc10f76b6c2745977c584070e12ad503'
        plan='96ece5e1e42dcba5e9e25d0e82c62308db07fb893227ccd3c444923b39ff51f4'
        with patch.object(subprocess,'run',side_effect=AssertionError('No compiler/history/hardware')),\
            patch.object(stage.display_xnu,'restoration',side_effect=AssertionError('Wrong typed reader')):
            context=stage.baseline(directory,seal,plan)
            with self.assertRaises(ValueError):stage.baseline(directory,'0'*64,plan)
            with self.assertRaises(ValueError):stage.baseline(directory,seal,'0'*64)
        self.assertEqual(len(context['result']['next_catalog']),374)
        self.assertEqual(context['plan']['media']['controller'],stage.compact.CONTROLLER)
        for name in ('bl31.bin','probe.bin','config.txt'):
            bad=copy.deepcopy(context);bad['result']['publication']['protected_files_sha256'][name]='0'*64
            with patch.object(stage.compact,'restoration',return_value=bad),self.assertRaises(ValueError):
                stage.baseline(directory,seal,plan)

    def test_exact_new_xnu_restore_dispatch_and_no_old_fallback(self):
        directory=stage.ROOT/'build/rpi5/display-compact-repeat-restored-20261014'
        files={n:v[1] for n,v in stage.GOOD.items()}
        files['config.txt']=stage.compact.engine.ORIGINAL_CONFIG_SHA
        context=dict(result={'publication':{'protected_files_sha256':files}})
        original=Path.read_text
        def read(path,*args,**kw):
            if path==directory/'plan.json':return json.dumps(plan)
            return original(path,*args,**kw)
        plan=dict(media={'controller':stage.display_xnu.CONTROLLER,'profile':stage.display_xnu.engine.RESTORE})
        with patch.object(Path,'read_text',read),patch.object(stage.display_xnu,'restoration',return_value=context) as checked,\
            patch.object(stage.compact,'restoration',side_effect=AssertionError('Wrong typed reader')),\
            patch.object(stage.previous,'completed_restore',side_effect=AssertionError('No old354 fallback')):
            self.assertIs(stage.baseline(directory,'1'*64,'2'*64),context)
            checked.assert_called_once_with(directory,'1'*64,'2'*64)
            for name in ('config.txt','probe.bin','bl31.bin'):
                bad=copy.deepcopy(context);bad['result']['publication']['protected_files_sha256'][name]='0'*64
                with patch.object(stage.display_xnu,'restoration',return_value=bad),self.assertRaises(ValueError):
                    stage.baseline(directory,'1'*64,'2'*64)
            with patch.object(stage.display_xnu,'restoration',side_effect=ValueError('bad seal')),self.assertRaisesRegex(ValueError,'seal'):
                stage.baseline(directory,'1'*64,'2'*64)
        for controller,profile in (
            (stage.display_xnu.CONTROLLER,stage.display_xnu.engine.TRIAL),
            (stage.compact.CONTROLLER,stage.compact.engine.TRIAL),
            ('reviewed-case-active-window-v3',stage.engine.RESTORE),
            ('unknown',stage.display_xnu.engine.RESTORE),
            (stage.display_xnu.CONTROLLER,stage.compact.engine.RESTORE)):
            plan=dict(media={'controller':controller,'profile':profile})
            with patch.object(Path,'read_text',read),\
                patch.object(stage.display_xnu,'restoration',side_effect=AssertionError('No unknown type')),\
                patch.object(stage.compact,'restoration',side_effect=AssertionError('No unknown type')),\
                patch.object(stage.previous,'completed_restore',side_effect=AssertionError('No fallback')),self.assertRaises(ValueError):
                stage.baseline(directory,'1'*64,'2'*64)
        # Real old354 media is refused by its actual type before either reader.
        with patch.object(stage.display_xnu,'restoration',side_effect=AssertionError('No stale type')),\
            patch.object(stage.compact,'restoration',side_effect=AssertionError('No stale type')),self.assertRaises(ValueError):
            stage.baseline(stage.ROOT/'build/rpi5/pcie-phy-gpio-restored-20261014','0'*64,'0'*64)


if __name__=='__main__':unittest.main()
