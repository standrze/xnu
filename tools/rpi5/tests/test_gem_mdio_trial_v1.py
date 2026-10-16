# SPDX-License-Identifier: BSD-2-Clause
"""Actual 53-row capabilities API, typed display rollback and modem-gated RX."""
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
from tools.rpi5 import gem_mdio_trial_v1 as stage
from tools.rpi5 import serial_gem_mdio_trial_v1 as recorder
from tools.rpi5 import gem_mdio_evidence_v1 as evidence
from tools.rpi5.tests import test_root_forward_trial_v2 as previous

DESCRIPTOR=stage.ROOT/'build/rpi5/pcie-gem-mdio-case-20261014/descriptor.json'
DESCRIPTOR_SHA='56ccc496137a78a718f56babc09a051b01b985d41a8a5b5fcedeefb6fbd579d5'
REPORT=stage.ROOT/'build/rpi5/gem-mdio-controller-report-20261014/checker-report.json'
REPORT_SHA='69e25443b1a5df30e5158026328171b9b8d7127712810e56c09f20259e26e5be'


def fixture_for_report(report):
    from tools.rpi5.tests.test_pcie_gem_mdio_serial import GEMMDIOSerialTests
    from tools.rpi5 import pcie_gem_mdio_serial_core as protocol
    raw,template=GEMMDIOSerialTests().fixture()
    if (report.get('image_sha256')!='181e58ee6326b625b3c58a1d2c288d16db0e0c1498fdf4f9ed8bb965e7436026' or
        report.get('manifest_sha256')!='6c18b4c7b24346fdd08cda0f8e187d502b694e5f8d0bb8f79973641d24a44173' or
        report.get('image_bytes')!=18193720 or
        report.get('marker')!='RPI5XNU:BL33:PCIE_GEM_MDIO_TRIAL TAG=bff69a28a78d4f3087da5f4ac6ec8b22 CPUS=1 NO_CPU_ON NO_INIT ZERO_SERIAL_INPUT' or
        len(report.get('boot_markers',[]))!=len(template['boot_markers'])):
        raise ValueError('Exact checked immutable capabilities report required')
    for old,new in zip(template['boot_markers'],report['boot_markers']):
        if raw.count(old.encode())!=1:raise ValueError('Unique fixture marker required')
        raw=raw.replace(old.encode(),new.encode(),1)
    raw,count=re.subn(rb'(Read probe.bin bytes )\d+( hnd)',lambda m:m[1]+str(report['image_bytes']).encode()+m[2],raw)
    if count!=1:raise ValueError('Unique materialization byte extent required')
    result=protocol.inspect(raw,report)
    if not result['mdio_trial_pass'] or result['clock_readiness_independently_proven']:
        raise ValueError('Complete register-profile-only fixture required')
    return raw,copy.deepcopy(report)


def inherited(test,name):
    """Reuse the actual frozen receiver/launcher test body with exact name seams."""
    source=Path(previous.__file__).read_text();start=source.index('    def '+name+'(')
    finish=source.find('\n    def ',start+5)
    if finish<0:finish=source.index("\n\nif __name__",start)
    body=source[start:finish]
    for before,after in (
        ('serial_root_forward_trial_v2','serial_gem_mdio_trial_v1'),
        ('root_forward_trial_v2','gem_mdio_trial_v1'),
        ('root_forward_evidence_v2','gem_mdio_evidence_v1'),
        ('test_pcie_root_forward_serial','test_pcie_gem_mdio_serial'),
        ('pcie_root_forward_serial_core','pcie_gem_mdio_serial_core'),
        ('fixture.RootForwardSerialTests()','fixture.GEMMDIOSerialTests()'),
        ('root_forward_trial_pass','mdio_trial_pass'),
        ("adapter='pcie-root-forward'","adapter='pcie-gem-mdio'")):
        body=body.replace(before,after)
    scope=dict(previous.__dict__,stage=stage,recorder=recorder,evidence=evidence)
    exec(compile('class Actual(unittest.TestCase):\n'+body,__file__,'exec'),scope)
    getattr(scope['Actual'](name),name)()


class GEMMDIOControllerTests(unittest.TestCase):
    def test_actual_checked53_row_report_full_capture_and_admission(self):
        from tools.rpi5 import pcie_gem_mdio_serial_core as protocol
        from tools.rpi5 import check_pcie_gem_mdio_package as checker
        from tools.rpi5.tests import test_pcie_root_route_serial as full
        fresh=os.environ.get('RPI5_GEM_MDIO_AUDIT_REPORT')=='1'
        if fresh:report=checker.inspect(stage.ROOT/'build/rpi5/pcie-id-trial-qthzh5e7')
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
            for key in ('mdio_contract','capabilities_contract','selected_clock_contract','marker'):
                bad=copy.deepcopy(checkpoint);bad['payload']['media_plan']['preflight'].pop(key)
                with self.assertRaises((ValueError,KeyError)):stage.admit(bad)
            bad=copy.deepcopy(checkpoint);bad['evidence_sha256'].pop(str(Path(protocol.__file__).resolve()))
            with self.assertRaises(ValueError):stage.admit(bad)
            restored=dict(plan={'media':{'controller':'reviewed-case-active-window-v3','preflight':report,'descriptor':reference}},
                result={'publication':{'pair_sha256':{n:v[1] for n,v in stage.GOOD.items()}}})
            with patch.object(stage,'sealed_operation',return_value=restored) as intake:
                self.assertIs(stage.completed_restore('fixture','1'*64,'2'*64),restored)
                intake.assert_called_once_with('fixture','1'*64,'2'*64,stage.engine.RESTORE)
            for mutation in ('controller','probe.bin','bl31.bin','mdio_contract'):
                bad=copy.deepcopy(restored)
                if mutation=='controller':bad['plan']['media']['controller']='single-loader'
                elif mutation=='mdio_contract':bad['plan']['media']['preflight'].pop(mutation)
                else:bad['result']['publication']['pair_sha256'][mutation]='0'*64
                with patch.object(stage,'sealed_operation',return_value=bad),self.assertRaises(ValueError):
                    stage.completed_restore('fixture','1'*64,'2'*64)
        if fresh:
            REPORT.parent.mkdir(exist_ok=False);stage.save(REPORT,report)
            stage.save(REPORT.parent/'validation.json',dict(actual_report_sha256=stage.sha(REPORT),
                full_capture_pass=True,observed_field_rows=53,hardware_executed=False,fixture_not_board_evidence=True))

    def test_fixed_original_bodies_and_complete_sources(self):
        self.assertEqual(set(stage.get_descriptor.__globals__['ADAPTERS']),{'pcie-gem-mdio'})
        self.assertIs(stage._prepare_install.__code__,stage.prior._prepare_install.__code__)
        for n in ('load_installation','prepare_restore','launch','replay','dispatch'):
            self.assertIs(getattr(stage,n).__code__,getattr(stage.prior,n).__code__)
        self.assertIs(evidence.captured.__code__,evidence.original.captured.__code__)
        self.assertIs(recorder.bindings.__code__,recorder.accepted.bindings.__code__)
        self.assertIs(recorder.assert_modem_ready,recorder.accepted.assert_modem_ready)
        self.assertIs(stage.dispatch.__globals__['subprocess'],stage.upload_transport)
        pins=stage.source_pins()
        for n in ('gem_mdio_trial_v1.py','serial_gem_mdio_trial_v1.py','gem_mdio_evidence_v1.py',
            'tests/test_gem_mdio_trial_v1.py','serial_root_forward_trial_v2.py'):
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

    def test_typed_zero_config_loader_baseline_and_original_bindings(self):
        files={n:v[1] for n,v in stage.GOOD.items()}
        files['config.txt']=stage.observer.engine.ORIGINAL_CONFIG_SHA
        context=dict(result={'publication':{'protected_files_sha256':files}})
        with patch.object(stage.observer,'restoration',return_value=context) as checked, \
            patch.object(stage,'sealed_operation',side_effect=AssertionError('Not a pair baseline')):
            self.assertIs(stage.baseline('exact-zero-restore','1'*64,'2'*64),context)
            checked.assert_called_once_with('exact-zero-restore','1'*64,'2'*64)
        for name in files:
            bad=copy.deepcopy(context);bad['result']['publication']['protected_files_sha256'][name]='0'*64
            with patch.object(stage.observer,'restoration',return_value=bad),self.assertRaises(ValueError):
                stage.baseline('exact-zero-restore','1'*64,'2'*64)
        self.assertEqual(stage.observer.CONTROLLER,'display-allocation-zero-config-loader-controller-v1')

    def test_actual_completed324_zero_config_loader_restoration(self):
        directory=stage.ROOT/'build/rpi5/display-allocation-zero-restored-20261014'
        seal='0122c2cf20f3da384236718c08c21e8fb2c4f76448e7baf754c10735303ef3b2'
        plan='1a9ccbc6cc4e09906d72a408690c82d5e69848e25190a431aef277bd26850802'
        self.assertEqual(stage.sha(directory/'result.json'),'b22cfa94fbd8b3345663151260fbe5c7c83f43f52874f725ccadb8c8c9fe2d23')
        with patch.object(stage.observer.checker,'inspect',side_effect=AssertionError('No package compiler replay')),\
            patch.object(stage,'sealed_operation',side_effect=AssertionError('Not paired-publication baseline')),\
            patch.object(subprocess,'run',side_effect=AssertionError('No compiler/history/hardware transport')):
            context=stage.baseline(directory,seal,plan)
            with self.assertRaises(ValueError):stage.baseline(directory,'0'*64,plan)
            with self.assertRaises(ValueError):stage.baseline(directory,seal,'0'*64)
            with self.assertRaises(ValueError):stage.baseline(stage.ROOT/'build/rpi5/display-allocation-restored-20261014',
                'eed148f33f0668278275b4f7cc0427a1473f1c343d8a3e75512f4b8306d34e45',
                'a8294c948c32fed48f0d2c43ad7ff0d2bfb545339d682e236773ea3966cca2dc')
        self.assertEqual(len(context['result']['next_catalog']),324)
        self.assertEqual(context['plan']['media']['controller'],stage.observer.CONTROLLER)
        self.assertEqual(context['result']['publication']['identity']['boot_id'],'52bd6236-b9af-4c66-a4b3-3177a179a575')
        for name in ('bl31.bin','probe.bin','config.txt'):
            bad=copy.deepcopy(context);bad['result']['publication']['protected_files_sha256'][name]='0'*64
            with patch.object(stage.observer,'restoration',return_value=bad),self.assertRaises(ValueError):stage.baseline(directory,seal,plan)


if __name__=='__main__':unittest.main()
