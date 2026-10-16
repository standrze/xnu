# SPDX-License-Identifier: BSD-2-Clause
"""Typed real-v2 intake and offline case/controller guards, no hardware calls."""
import contextlib
import copy
import importlib
import io
import json
import os
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch
from tools.rpi5 import stage_pcie_trial_v3 as stage
from tools.rpi5 import pcie_trial_descriptor_v3 as descriptors
from tools.rpi5 import serial_pcie_trial_v3 as recorder
from tools.rpi5 import pcie_trial_evidence_v3 as evidence

ROOT=stage.ROOT
BASELINE=ROOT/'build/rpi5/rp1-link-v2-restored-20261013'
SEAL='d11d4bc17480644af92323ba383f7bc2493fcf22a0f707f2f773ab5f277b5ad0'
PLAN='cf179f9a35c158ddb18701c11ed5fa0732ee26ac4adffdf12217590e2d091d11'


class ControllerTests(unittest.TestCase):
    @contextlib.contextmanager
    def descriptor(self):
        with tempfile.TemporaryDirectory(prefix='v3-offline-case-',dir=ROOT/'build/rpi5') as name:
            directory=Path(name).resolve();path=directory/'descriptor.json'
            payload=json.loads((BASELINE/'checkpoint.json').read_text())['payload']
            report=payload['media_plan']['preflight']
            sources=('check_pcie_link_elapsed_package.py','pcie_link_elapsed_serial_core.py','tests/test_pcie_link_elapsed_serial.py')
            record=dict(format=descriptors.FORMAT,name='elapsed-reference-fixture',adapter='elapsed-reference-offline',
                package=str(ROOT/'build/rpi5/pcie-id-trial-y60h5lfb'),package_manifest_sha256='56e3ee8a55a0f6df251d14875e7f5400da2b467b5179975a61e012db1302863d',
                checker='tools.rpi5.check_pcie_link_elapsed_package',protocol='tools.rpi5.pcie_link_elapsed_serial_core',
                source_sha256={str(ROOT/'tools/rpi5'/n):stage.sha(ROOT/'tools/rpi5'/n) for n in sources},
                marker=report['marker'],firmware_sha256=report['firmware_sha256'],hardware_allowed=False)
            stage.save(path,record)
            yield {'path':str(path),'sha256':stage.sha(path)},record,report

    def test_actual_prior_v2_original_pair_intake_without_historical_audit(self):
        with patch.object(stage.base.prior,'validate_result',side_effect=AssertionError('No historical replay')):
            prior=stage.baseline(BASELINE,SEAL,PLAN)
        self.assertEqual(len(prior['result']['next_catalog']),138)
        self.assertEqual(prior['result']['publication']['pair_sha256'],{n:r[1] for n,r in stage.GOOD.items()})
        self.assertEqual(prior['plan']['media']['linux_boot_id'],'dc5737b5-2559-4830-b4bd-d406c7a77522')
        with self.assertRaises(ValueError):stage.baseline(BASELINE,'0'*64,PLAN)
        with self.assertRaises(ValueError):stage.baseline(BASELINE,SEAL,'0'*64)

    def test_descriptor_expected_digest_and_allowlisted_adapter(self):
        with self.descriptor() as (reference,record,report):
            case=descriptors.get(reference);self.assertFalse(case['hardware_allowed'])
            with self.assertRaisesRegex(ValueError,'digest differs'):descriptors.get(reference|{'sha256':'0'*64})
            for change in (dict(hardware_allowed=True),dict(checker='tools.rpi5.stage_link_trial_v2'),dict(adapter='arbitrary'),
                           dict(marker=report['marker'].replace('CPUS=1','CPUS=4'))):
                bad=record|change;Path(reference['path']).write_text(json.dumps(bad));pin=stage.sha(reference['path'])
                with self.assertRaises(ValueError):descriptors.get(reference|{'sha256':pin})

    def test_protocol_missing_or_wrong_expected_source_rejected_before_import(self):
        with self.descriptor() as (reference,record,report):
            key=str(ROOT/'tools/rpi5/pcie_link_elapsed_serial_core.py')
            for missing in (False,True):
                bad=copy.deepcopy(record)
                if missing:bad['source_sha256'].pop(key)
                else:bad['source_sha256'][key]='0'*64
                Path(reference['path']).write_text(json.dumps(bad));pin=stage.sha(reference['path'])
                with self.assertRaises(ValueError):descriptors.get(reference|{'sha256':pin})

    def test_offline_case_preparation_derives138_not_prior128_then_only_one_checker(self):
        with self.descriptor() as (reference,record,report):
            selected=descriptors.get(reference)
            with patch.object(selected['checker'],'inspect',return_value=report) as check,\
                 patch.object(stage.base.prior,'validate_result',side_effect=AssertionError('No old semantic replay')):
                checkpoint,pin,metrics=stage.prepare_install(BASELINE,SEAL,PLAN,reference,'dc5737b5-2559-4830-b4bd-d406c7a77522')
            self.assertEqual(check.call_count,1);self.assertEqual(len(checkpoint['payload']['history_catalog']),138)
            self.assertEqual(metrics['historical_semantic_audit_calls'],0);self.assertEqual(metrics['prior_catalog_count'],138)
            self.assertEqual(checkpoint['payload']['media_plan']['protected_sha256'],
                {n:r['sha256'] for n,r in json.loads((BASELINE/'result.json').read_text())['publication']['protected_after'].items()})
            with patch.object(stage.base.subprocess,'run',side_effect=AssertionError('No hardware from offline descriptor')):
                with self.assertRaisesRegex(ValueError,'Offline descriptor'):
                    stage.dispatch(checkpoint,pin,ROOT/'build/rpi5/never-created-v3-fixture',metrics,True)
            altered=copy.deepcopy(checkpoint);altered['payload']['media_plan']['linux_boot_id']='bad'
            with self.assertRaises(ValueError):stage.seals.revalidate(altered,pin)
            for key in ('root','card_cid'):
                changed=copy.deepcopy(checkpoint)
                changed['payload']['media_plan']['identity_binding']['expected'][key]='wrong'
                with self.assertRaises(ValueError):stage.seals.revalidate(changed,pin)
            changed=copy.deepcopy(checkpoint);changed['payload']['media_plan']['files'][1]['new_sha256']='0'*64
            with self.assertRaises(ValueError):stage.seals.revalidate(changed,pin)
            with tempfile.TemporaryDirectory(prefix='v3-unknown-',dir=ROOT/'build/rpi5') as name:
                out=Path(name);out.rmdir();calls=[]
                def run(command,**kw):
                    if command[0]=='scp':return subprocess.CompletedProcess(command,0)
                    if command[-1]=='python3 -':return subprocess.CompletedProcess(command,0,json.dumps({'run':'/home/sandrzej/xnu-link-v2-unknown1'}),'')
                    calls.append(command);raise subprocess.TimeoutExpired(command,300,output=b'partial receipt')
                with patch.object(stage.descriptors,'get',return_value=selected|{'hardware_allowed':True}),\
                     patch.object(stage.base.subprocess,'run',side_effect=run):
                    with self.assertRaises(subprocess.TimeoutExpired):stage.dispatch(checkpoint,pin,out,metrics,True)
                    with self.assertRaises(FileExistsError):stage.dispatch(checkpoint,pin,out,metrics,True)
                self.assertEqual(len(calls),1);unknown=json.loads((out/'outcome-unknown.json').read_text())
                self.assertTrue(unknown['no_retry']);self.assertTrue(unknown['no_implicit_rollback'])
            # A fresh digest cannot be silently substituted for a protocol/case
            # edited after package admission.
            changed=copy.deepcopy(record);changed['marker']=record['marker'].replace('TAG=','TAG=0')
            Path(reference['path']).write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError,'evidence bytes'):stage.seals.revalidate(checkpoint,pin)

    def test_new_dependency_graph_hashes_new_files_once_and_keeps_prior_closed(self):
        with tempfile.TemporaryDirectory(prefix='v3-graph-',dir=ROOT/'build/rpi5') as name:
            package=Path(name).resolve();old=package/'old.json';fresh=package/'fresh.h'
            old.write_text('{"deliberately_not_walked":true}');fresh.write_text('int fixture;')
            stage.save(package/'manifest.json',{'old':str(old),'repeated':[str(fresh)]*50})
            prior={str(old):stage.sha(old)};calls=[];real_sha=stage.sha
            def sha(path):calls.append(str(path));return real_sha(path)
            with patch.object(stage,'sha',side_effect=sha):pins=stage.package_graph(package,prior)
            self.assertEqual(calls.count(str(fresh)),1);self.assertNotIn(str(old),calls)
            old.write_text('changed')
            with self.assertRaisesRegex(ValueError,'evidence bytes'):stage.seals.check_pins(pins)

    def test_actual_v3_recorder_body_and_downgraded_capture_with_serial_doubles(self):
        with self.descriptor() as (reference,record,report),\
             tempfile.TemporaryDirectory(prefix='v3-recorder-',dir=ROOT/'build/rpi5') as name,tempfile.TemporaryFile() as uart:
            out=Path(name);out.rmdir();descriptor=stage.load_descriptor(reference)
            installed=dict(directory=str(ROOT/'build/rpi5/offline-v3-install-fixture'),checkpoint_sha256='1'*64,plan_sha256='2'*64,
                result_sha256='3'*64,preflight=report,pair_sha256={'probe.bin':report['image_sha256'],'bl31.bin':report['firmware_sha256']},
                original_linux_boot_id='dc5737b5-2559-4830-b4bd-d406c7a77522')
            context=dict(descriptor=descriptor,installed=installed,evidence=stage.source_pins()|stage.base.loaded_sources()|record['source_sha256'])
            raw=(ROOT/'build/rpi5/rp1-link-v2-serial-20261013/serial.bin').read_bytes()
            chunks=iter(raw.splitlines(keepends=True));real_open=os.open;ticks=iter(i/100 for i in range(100000));captured=io.StringIO()
            fn=recorder.bindings(context);g=fn.__globals__
            def open_(path,*a,**kw):return os.dup(uart.fileno()) if path=='/dev/cu.usbmodemTEST' else real_open(path,*a,**kw)
            with patch.object(g['lease'],'hold',return_value=contextlib.nullcontext()),\
                 patch.object(g['subprocess'],'run',return_value=subprocess.CompletedProcess([],1,'','')),\
                 patch.object(g['os'],'open',side_effect=open_),patch.object(g['os'],'read',side_effect=lambda *_:next(chunks)),\
                 patch.object(g['fcntl'],'ioctl'),patch.object(g['termios'],'tcgetattr',side_effect=lambda _:[0,0,0,0,0,0,[0]*32]),\
                 patch.object(g['termios'],'tcsetattr'),patch.object(g['termios'],'tcflush'),\
                 patch.object(g['select'],'select',side_effect=lambda fd,*a:(fd,[],[])),\
                 patch.object(g['time'],'monotonic',side_effect=lambda:next(ticks)),contextlib.redirect_stdout(captured):
                self.assertEqual(fn(['/dev/cu.usbmodemTEST',str(out),'--installation',installed['directory'],'--seconds','600']),0)
            self.assertIn('RP1_TRACE_CAPTURE_ARMED ZERO_SERIAL_TX',captured.getvalue())
            state,observed,_=evidence.captured(context,out)
            self.assertTrue(observed['trace_capture_valid']);self.assertFalse(observed['diagnostic']['rp1_id_trial_pass'])
            state.update(status='failed',continuous_capture=False,error='explicit fixture downgrade')
            (out/'state.json').write_text(json.dumps(state))
            self.assertFalse(evidence.captured(context,out)[1]['trace_capture_valid'])
            state['transmitted_bytes']=1;(out/'state.json').write_text(json.dumps(state))
            with self.assertRaisesRegex(ValueError,'zero-TX capture'):evidence.captured(context,out)

    def test_launch_private_import_selects_v3_recorder_and_rejects_wrong_boot(self):
        with self.descriptor() as (reference,record,report),tempfile.TemporaryDirectory(prefix='v3-launch-',dir=ROOT/'build/rpi5') as name:
            stage.load_descriptor(reference);actual_recorder=importlib.import_module('serial_pcie_trial_v3')
            arm=importlib.import_module('arm_pcie_trace_reboot')
            context=dict(descriptor={'hardware_allowed':True},installed=dict(directory=str(ROOT/'build/rpi5/fixture'),
                original_linux_boot_id='dc5737b5-2559-4830-b4bd-d406c7a77522',pair_sha256={'probe.bin':'1'*64,'bl31.bin':'2'*64}),
                plan={'media':{'identity_binding':{'expected':{'root':'/dev/nvme0n1p2 ext4 fixture'}}}},evidence={})
            capture=Path(name);capture.rmdir();calls=[]
            def once(output,command,expected,validate,reboot):
                calls.append(command);capture.mkdir()
                stage.save(capture/'armed.json',dict(pid=123,installation=context['installed'],transmitted_bytes=0,device='/dev/cu.usbmodemTEST',
                    baud=115200,source_sha256={},receipt_evidence_sha256={}))
                validate(123);return {'offline_fixture':True}
            with patch.object(stage,'load_installation',return_value=context),patch.object(arm,'arm_once',side_effect=once),\
                 patch.object(actual_recorder,'revalidate'),patch.object(actual_recorder,'bound_sources',return_value={}):
                with self.assertRaisesRegex(ValueError,'staged Linux boot'):
                    stage.launch(ROOT/'build/rpi5/fixture','0'*64,'1'*64,'/dev/cu.usbmodemTEST',capture,capture,'wrong')
                stage.launch(ROOT/'build/rpi5/fixture','0'*64,'1'*64,'/dev/cu.usbmodemTEST',capture,capture,context['installed']['original_linux_boot_id'])
            self.assertEqual(len(calls),1);self.assertEqual(calls[0][1],str(ROOT/'tools/rpi5/serial_pcie_trial_v3.py'))

    def test_protected_prior_result_tampering_rejected(self):
        with tempfile.TemporaryDirectory(prefix='v3-prior-tamper-',dir=ROOT/'build/rpi5') as name:
            directory=Path(name)
            for f in ('checkpoint.json','plan.json','result.json'):(directory/f).write_bytes((BASELINE/f).read_bytes())
            result=json.loads((directory/'result.json').read_text());result['publication']['pair_sha256']['probe.bin']='0'*64
            (directory/'result.json').write_text(json.dumps(result))
            with self.assertRaises(ValueError):stage.baseline(directory,SEAL,PLAN)

    def test_final_case_once_audit_without_historical_replay(self):
        path=os.environ.get('RPI5_V3_DESCRIPTOR')
        if not path:self.skipTest('Select final immutable case and retained descriptor SHA explicitly')
        reference={'path':str(Path(path).resolve()),'sha256':os.environ['RPI5_V3_DESCRIPTOR_SHA']}
        selected=stage.load_descriptor(reference);actual=selected['checker'].inspect
        with patch.object(selected['checker'],'inspect',wraps=actual) as checker,\
             patch.object(stage.base.prior,'validate_result',side_effect=AssertionError('No historical semantic replay')),\
             patch.object(stage.base,'full_install_audit',side_effect=AssertionError('No old package audit')):
            checkpoint,pin,metrics=stage.prepare_install(BASELINE,SEAL,PLAN,reference,'dc5737b5-2559-4830-b4bd-d406c7a77522')
        self.assertEqual(checker.call_count,1);self.assertEqual(len(checkpoint['payload']['history_catalog']),138)
        self.assertEqual(metrics['historical_semantic_audit_calls'],0)
        self.assertEqual(checkpoint['payload']['media_plan']['preflight']['marker'],selected['record']['marker'])
        for path in selected['record']['source_sha256']:self.assertIn(path,checkpoint['evidence_sha256'])
        if output:=os.environ.get('RPI5_V3_TEST_OUTPUT'):
            out=stage.local(output);out.mkdir(exist_ok=False)
            stage.seals.save_new(out/'checkpoint.json',checkpoint,pin);stage.save(out/'metrics.json',metrics)
            stage.save(out/'validation.json',dict(offline_only=True,hardware_executed=False,checkpoint_sha256=pin,metrics=metrics))


if __name__=='__main__':unittest.main()
