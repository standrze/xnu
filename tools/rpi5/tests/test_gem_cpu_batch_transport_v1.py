# SPDX-License-Identifier: BSD-2-Clause
"""Actual52-row recorder/source/modem/return and no-retry transport fixtures."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import types
import unittest
from datetime import datetime,timedelta
from unittest.mock import patch
from tools.rpi5 import stage_gem_cpu_batch_trial_v1 as stage
from tools.rpi5 import serial_gem_cpu_batch_trial_v1 as recorder
from tools.rpi5 import gem_cpu_batch_evidence_v1 as evidence
from tools.rpi5 import arm_gem_cpu_batch_reboot_v1 as launcher
from tools.rpi5.tests.test_gem_dma_batch_serial import BatchSerialTests
class CPUBatchTransportTests(unittest.TestCase):
    def fixture(self):
        return BatchSerialTests().fixture(json.loads(stage.REPORT.read_bytes()))
    def context(self):
        raw,report=self.fixture()
        installed=dict(directory=str(stage.ROOT/'build/rpi5/offline-cpu-batch-native'),preflight=report,
            pair_sha256={'probe.bin':stage.IMAGE_SHA,'bl31.bin':stage.case.FIRMWARE_SHA},
            triple_sha256={'config.txt':stage.engine.TRIAL_CONFIG_SHA,'probe.bin':stage.IMAGE_SHA,'bl31.bin':stage.case.FIRMWARE_SHA},
            original_linux_boot_id='11111111-1111-1111-1111-111111111111')
        return raw,dict(installed=installed,descriptor=stage.get_descriptor(stage.DESCRIPTOR),evidence=stage.source_pins())
    def test_actual_saved_report_and_byte_only_recorder_admission(self):
        report=json.loads(stage.REPORT.read_bytes());stage.valid_report(report)
        media=dict(profile=stage.engine.TRIAL,descriptor=stage.DESCRIPTOR,preflight=report,files=[],
            protected_files={stage.engine.original.REUSED_ZSH_BACKUP:stage.engine.original.GOOD_ZSH_SHA})
        new={'config.txt':(stage.engine.TRIAL_CONFIG_SHA,len(stage.engine.TRIAL_CONFIG)),
            'bl31.bin':(stage.case.FIRMWARE_SHA,stage.case.FIRMWARE_BYTES),'probe.bin':(stage.IMAGE_SHA,stage.engine.IMAGE_BYTES)}
        for name,(_,digest,size) in stage.GOOD.items():
            h,n=new[name];media['files'].append(dict(target=name,candidate='candidate-'+name,old_sha256=digest,old_bytes=size,new_sha256=h,new_bytes=n))
        checkpoint=dict(payload={'media_plan':media},evidence_sha256=stage.source_pins())
        with patch.object(stage.checker,'inspect',side_effect=AssertionError('No compiler/package replay')),patch.object(subprocess,'run',side_effect=AssertionError('No subprocess')):
            self.assertTrue(stage.admit(checkpoint)['modem_gate_bound_before_arm'])
            for name in ('stage_gem_cpu_batch_trial_v1.py','serial_gem_cpu_batch_trial_v1.py','gem_dma_batch_serial.py'):
                bad=copy.deepcopy(checkpoint);bad['evidence_sha256'].pop(str(stage.ROOT/'tools/rpi5'/name))
                with self.assertRaises(ValueError):stage.admit(bad)
            bad=copy.deepcopy(checkpoint);bad['payload']['media_plan']['preflight']['cpu_owned_only']=1
            with self.assertRaises(ValueError):stage.admit(bad)
    def test_only_exact_typed_pid1_restoration_and_three_originals(self):
        context=dict(result={'publication':{'protected_files_sha256':{n:v[1] for n,v in stage.GOOD.items()}}})
        with patch.object(stage.preceding,'restoration',return_value=context) as checked:
            self.assertIs(stage.baseline('unused','1'*64,'2'*64),context)
            checked.assert_called_once_with('unused','1'*64,'2'*64)
            for name in stage.GOOD:
                bad=copy.deepcopy(context);bad['result']['publication']['protected_files_sha256'][name]='0'*64
                with patch.object(stage.preceding,'restoration',return_value=bad),self.assertRaises(ValueError):stage.baseline('unused','1'*64,'2'*64)
        with patch.object(stage.preceding,'restoration',side_effect=ValueError('typed wrong seal')),self.assertRaisesRegex(ValueError,'seal'):
            stage.baseline('unused','1'*64,'2'*64)
    def test_actual_replay_restores_three_targets_without_visual_gate(self):
        checkpoint={'typed': 'native-restoration-fixture'}
        context={'plan': {'historical_catalog': [None]*454}, 'result': {'next_catalog': [None]*460}}
        returned={'capture_valid': True, 'diagnostic': {'cpu_ring_trial_pass': True}, 'capture_error': None}
        restored={'checkpoint': checkpoint, 'result': {'next_catalog': [None]*466,
            'publication': {'identity': {'boot_id': 'native-return-boot'}}}}
        with patch.object(stage,'transport',return_value=evidence),\
            patch.object(stage,'load_installation',return_value=context),\
            patch.object(evidence,'load_return',return_value=(returned,'native-return-boot')),\
            patch.object(stage,'prepare_restore',return_value=(checkpoint,'restore-seal',{})),\
            patch.object(stage,'restoration',return_value=restored),\
            patch.object(subprocess,'run',side_effect=AssertionError('No process or hardware')):
            value=stage.replay('installation','seal','plan','capture','restored','restore-seal','restore-plan')
        self.assertIs(value['visual_confirmation_required'],False)
        self.assertIs(value['physical_visibility_proven'],False)
        self.assertIs(value['framebuffer_authority'],False)
        self.assertIs(value['original_config_firmware_and_loader_restored'],True)
        self.assertIs(value['normal_firmware_restored'],True)
        self.assertEqual(value['historical_catalog_counts'],[454,460,466])
    def test_actual_body_zero_tx_full_return_and_whole_tail_fault(self):
        raw,context=self.context();parts=raw.splitlines(keepends=True)
        with tempfile.TemporaryDirectory(prefix='cpu-batch-rx-',dir=stage.ROOT/'build/rpi5') as name,tempfile.TemporaryFile() as uart:
            output=Path(name);output.rmdir();fn=recorder.bindings(context);g=fn.__globals__
            original_open=os.open;required=recorder.termios.TIOCM_DTR|recorder.termios.TIOCM_RTS
            with patch.object(g['lease'],'hold',return_value=contextlib.nullcontext()),\
                patch.object(g['subprocess'],'run',return_value=subprocess.CompletedProcess([],1,'','')),\
                patch.object(g['os'],'open',side_effect=lambda p,*a,**k:os.dup(uart.fileno()) if p=='/dev/cu.usbmodemTEST' else original_open(p,*a,**k)),\
                patch.object(g['os'],'read',side_effect=lambda *_:parts.pop(0)),\
                patch.object(g['os'],'write',side_effect=AssertionError('No UART payload')),\
                patch.object(g['fcntl'],'ioctl',return_value=struct.pack('=I',required)),\
                patch.object(g['termios'],'tcgetattr',side_effect=lambda _:[0,0,0,0,0,0,[0]*32]),\
                patch.object(g['termios'],'tcsetattr'),patch.object(g['termios'],'tcflush'),\
                patch.object(g['select'],'select',side_effect=lambda fd,*_:(fd,[],[])),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(fn(['/dev/cu.usbmodemTEST',str(output),'--installation',context['installed']['directory'],'--seconds','600']),0)
            state,observed,_=evidence.captured(context,output)
            self.assertEqual(state['transmitted_bytes'],0);self.assertTrue(observed['trace_capture_valid'])
            self.assertTrue(observed['diagnostic']['cpu_ring_trial_pass']);self.assertFalse(observed['diagnostic']['dma'])
            self.assertEqual((output/'serial.bin').read_bytes(),raw)
            # Actual independent-return validator and saved read-only replay;
            # this is a native receipt fixture, not a live Linux observation.
            media=dict(host=stage.HOST,linux_boot_id=context['installed']['original_linux_boot_id'],
                identity_binding={'expected':{'root':'/dev/nvme0n1p2 ext4 fixture-uuid'}})
            context['plan']={'media':media}
            boot='22222222-2222-2222-2222-222222222222'
            value=dict(host=stage.HOST,boot_id=boot,installation=context['installed'],
                serial_sha256=state['serial_sha256'],root=media['identity_binding']['expected']['root'].split(),
                identity={'identity':media['identity_binding']['expected'],'boot_id':boot,'hostname':'kamidana'},
                bootloader={'boot-mode':6,'partition':1,'tryboot':0},read_only=True,
                return_source_sha256=evidence.return_source_pins(),sd_partitions_unmounted=True,
                observed_utc=(datetime.fromisoformat(observed['nvme_selected_utc'])+timedelta(seconds=1)).isoformat())
            self.assertEqual(evidence.inspect_return(value,context,observed),boot)
            for bad in (value|{'boot_id':media['linux_boot_id']},value|{'bootloader':{'boot-mode':1,'partition':1,'tryboot':0}},value|{'read_only':1}):
                with self.assertRaises(ValueError):evidence.inspect_return(bad,context,observed)
            actual=evidence.collect_return.__globals__['remote']
            program=actual.remote_source(media,context['installed'],state['serial_sha256'],evidence.return_source_pins())
            saved=dict(format='rpi5-next-link-independent-return-v2',capture_valid=True,
                diagnostic=observed['diagnostic'],capture_error=None,observation=value,linux_boot_id=boot,
                capture_sha256={n:stage.sha(output/n) for n in ('armed.json','state.json','serial.bin','receive-events.jsonl')},
                installation=context['installed'],source_sha256=evidence.return_source_pins(),
                remote_source_sha256=__import__('hashlib').sha256(program.encode()).hexdigest(),zero_serial_tx=True,
                independent_normal_nvme_linux_return_verified=True,ethernet_proven=False)
            (output/'return.json').write_text(json.dumps(saved))
            with patch.object(subprocess,'run',side_effect=AssertionError('Read-only replay has no process')):
                self.assertEqual(evidence.load_return(context,output),(saved,boot))
            # Fault bytes anywhere, including after successful END, remain fatal.
            with self.assertRaises(ValueError):stage.protocol.inspect(raw+b'panic(cpu 0 caller 0x123)\n',context['installed']['preflight'])
    def test_actual_modem_controls_after_raw_before_armed(self):
        from tools.rpi5.tests import test_root_forward_trial_v2 as old
        text=Path(old.__file__).read_text();a=text.index('    def test_actual_body_modem_controls_after_raw_before_arm(')
        z=text.index('\n\nif __name__',a);body=text[a:z]
        body=body.replace('from tools.rpi5 import pcie_root_forward_serial_core as protocol','from tools.rpi5 import gem_dma_batch_serial as protocol')
        scope=dict(old.__dict__,stage=stage,recorder=recorder)
        exec(compile('class Native(unittest.TestCase):\n'+body,__file__,'exec'),scope)
        scope['Native']('test_actual_body_modem_controls_after_raw_before_arm').test_actual_body_modem_controls_after_raw_before_arm()
    def test_private_namespaces_and_unchanged_receive_launch_return_bodies(self):
        self.assertIs(recorder.bindings.__code__,recorder.original.bindings.__code__)
        self.assertIs(recorder.assert_modem_ready,recorder.accepted.assert_modem_ready)
        self.assertIs(recorder.main.__globals__['stage'],recorder.stage)
        self.assertIs(evidence.captured.__code__,evidence.original.captured.__code__)
        self.assertIs(evidence.captured.__globals__['stage'],evidence.stage)
        self.assertIs(launcher.launch.__code__,stage.publisher.launch.__code__)
        self.assertIs(launcher.launch.__globals__['load_installation'],launcher.stage.load_installation)
        self.assertIs(stage.package_graph.__globals__['stage'],stage)
        self.assertIs(stage.package_graph.__globals__['include_directory'].__globals__['stage'],stage)
    def test_actual_launcher_requires_matching_armed_child_before_one_reboot(self):
        _,context=self.context();context['plan']={'media':{'identity_binding':{'expected':{'root':'/dev/nvme0n1p2 ext4 fixture-uuid'}}}}
        with tempfile.TemporaryDirectory(prefix='cpu-batch-arm-',dir=stage.ROOT/'build/rpi5') as name:
            folder=Path(name);capture=folder.with_name(folder.name+'-capture');output=folder.with_name(folder.name+'-launch')
            self.addCleanup(lambda:__import__('shutil').rmtree(capture) if capture.exists() else None)
            self.addCleanup(lambda:__import__('shutil').rmtree(output) if output.exists() else None)
            armed_pid=4242;seen=[]
            def arm(out,command,expected,verify,reboot):
                self.assertEqual(out,output);self.assertEqual(Path(command[1]).resolve(),Path(recorder.__file__).resolve())
                self.assertIn('--seconds',command);self.assertEqual(command[-1],'600')
                self.assertEqual(expected,'RP1_TRACE_CAPTURE_ARMED ZERO_SERIAL_TX IMAGE_SHA='+stage.IMAGE_SHA+' FIRMWARE_SHA='+stage.case.FIRMWARE_SHA)
                output.mkdir();capture.mkdir()
                record=dict(pid=armed_pid,installation=context['installed'],transmitted_bytes=0,
                    device='/dev/cu.usbmodemTEST',baud=115200,source_sha256=recorder.bound_sources(context),receipt_evidence_sha256=context['evidence'])
                (capture/'armed.json').write_text(json.dumps(record))
                with self.assertRaises(ValueError):verify(armed_pid+1)
                self.assertEqual(seen,[])
                admitted=verify(armed_pid);self.assertEqual(admitted['pid'],armed_pid)
                return reboot()
            def run(command,**kwargs):
                seen.append(command);self.assertEqual(command,stage.SSH+['sudo -n python3 -'])
                self.assertIn('fixture-uuid',kwargs['input']);self.assertEqual(kwargs['timeout'],30)
                return subprocess.CompletedProcess(command,0,'VERIFIED_SSD_LINUX_REBOOT_ONCE fixture\n','')
            arm_module=__import__('arm_pcie_trace_reboot')
            actual=stage.private(launcher.launch,load_installation=lambda *_:context)
            with patch.object(arm_module,'arm_once',side_effect=arm),patch.object(stage.subprocess,'run',side_effect=run):
                value=actual('unused','1'*64,'2'*64,'/dev/cu.usbmodemTEST',capture,output,context['installed']['original_linux_boot_id'])
            self.assertEqual(len(seen),1);self.assertTrue(value['no_retry'])
            self.assertEqual(value['reboot_outcome'],'unknown_until_capture_and_independent_linux_return')
    def test_propagated_minus7_remains_failed_with_full_capture_replay(self):
        from tools.rpi5.tests.test_pcie_root_route_serial import RootRouteSerialTests
        raw,report=self.fixture();values=[];original=stage.protocol.inspect
        def inspect(data,metadata):
            value=original(data,metadata)
            if b'DMA_STAGE STATE=3 ERROR=-5' in data:values.append((data,value))
            return value
        case=BatchSerialTests('test_minus7_propagation_and_partial_memory_never_committed')
        with patch.object(case,'fixture',return_value=(raw,copy.deepcopy(report))),patch.object(stage.protocol,'inspect',side_effect=inspect):
            case.test_minus7_propagation_and_partial_memory_never_committed()
        failed,parsed=values[0];self.assertFalse(parsed['cpu_ring_trial_pass'])
        self.assertFalse(parsed['retained_memory_release_proven']);self.assertEqual(parsed['decode_telemetry']['rc'],-7)
        bound=type('FailureFixture',(unittest.TestCase,),{'fixture':lambda _: (failed,copy.deepcopy(report))})()
        method=RootRouteSerialTests.test_actual_full_inspect_capture_api_with_timed_boot_to_nvme
        with patch.object(subprocess,'run',side_effect=AssertionError('No process')):
            types.FunctionType(method.__code__,dict(method.__globals__,p=stage.protocol))(bound)
    def test_stale444_rejected_and_in_memory_audit_three_targets(self):
        from tools.rpi5 import stage_restart_init_trial as old
        directory=stage.ROOT/'build/rpi5/restart-init-restored-20261014'
        seal='373c070c66e6b4efba6030b61d80b356ed86a3a4bfe06714820a8d1b6fb14273'
        plan='0efb9d6b74c809663f4291df02743c0fedecf72be8d4535943ff2cc44e79f4e4'
        with patch.object(subprocess,'run',side_effect=AssertionError('No compiler/history/process')),\
            patch.object(stage.preceding.checker,'inspect',side_effect=AssertionError('No predecessor replay')):
            # Historical fixture only; the new controller must NOT admit this
            # earlier schema after the late-PID1 successor is selected.
            accepted=old.restoration(directory,seal,plan)
            self.assertEqual(len(accepted['result']['next_catalog']),444)
            with self.assertRaises(ValueError):stage.baseline(directory,seal,plan)
            with self.assertRaises(ValueError):stage.baseline(directory,'0'*64,plan)
            with self.assertRaises(ValueError):stage.baseline(directory,seal,'0'*64)
            byte_graph=stage.package_graph(stage.PACKAGE,accepted['evidence'])
            self.assertEqual(byte_graph[str(stage.PACKAGE/'manifest.json')],stage.MANIFEST_SHA)
        # Execute the actual new audit body in memory with an explicitly fake
        # sealing boundary. It creates no preparation artifact and gives no
        # operational checkpoint; recorder admission is tested independently.
        report=json.loads(stage.REPORT.read_bytes())
        def fake(audit,pins):return {'payload':audit(),'evidence_sha256':pins},'INERT_NOT_A_SEAL'
        with patch.object(stage,'baseline',return_value=accepted),patch.object(stage,'package_graph',return_value={}),\
            patch.object(stage,'source_pins',return_value={}),patch.object(stage.publisher,'loaded_sources',return_value={}),\
            patch.object(stage.checker,'inspect',return_value=report) as checked,patch.object(stage.seals,'create',side_effect=fake),\
            patch.object(stage,'admit',return_value={'native_fixture_only':True}):
            checkpoint,token,metrics=stage.prepare_install(directory,seal,plan,'33333333-3333-3333-3333-333333333333')
        self.assertEqual(token,'INERT_NOT_A_SEAL');self.assertEqual(metrics['full_audit_calls'],1)
        checked.assert_called_once_with(stage.PACKAGE,stage.MANIFEST_SHA,stage.case.QUALIFICATION,stage.case.QUALIFICATION_SHA)
        media=checkpoint['payload']['media_plan']
        self.assertEqual([r['target'] for r in media['files']],list(stage.engine.TARGETS))
        self.assertTrue(media['explicit_firmware_change']);self.assertTrue(media['exact_temporary_config32'])
    def test_actual_dispatch_upload_timeout_or_uncertain_result_no_retry(self):
        media=dict(profile=stage.engine.TRIAL,descriptor=stage.DESCRIPTOR,
            files=[{'target':n,'candidate':'candidate-'+n} for n in stage.engine.TARGETS],
            candidates={n:'/local/'+n for n in stage.engine.TARGETS})
        seal=types.SimpleNamespace(revalidate=lambda *_:{'media_plan':media},save_new=lambda *_:None)
        engine=types.SimpleNamespace(plan_from_seal=lambda *_:({'media':media},'1'*64),remote_source=lambda *_:'pass',validate_result=lambda *_:None)
        actual=stage.private(stage._dispatch,seals=seal,engine=engine,descriptors=types.SimpleNamespace(get=lambda _: {'hardware_allowed':True}))
        for mode in ('upload','dispatch','malformed'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(dir=stage.ROOT/'build/rpi5') as name:
                output=Path(name);output.rmdir();calls=[]
                def run(command,**kwargs):
                    calls.append((command,kwargs))
                    if command[0]=='scp':
                        self.assertEqual(command[1],'-C');self.assertEqual(kwargs,{'check':True,'timeout':180})
                        if mode=='upload':raise subprocess.TimeoutExpired(command,180)
                        return subprocess.CompletedProcess(command,0,'','')
                    if command[-1]=='python3 -':return subprocess.CompletedProcess(command,0,json.dumps({'run':'/home/sandrzej/xnu-link-v2-testabcd'}),'')
                    self.assertEqual(command[-1],'sudo -n python3 -')
                    if mode=='dispatch':raise subprocess.TimeoutExpired(command,300)
                    return subprocess.CompletedProcess(command,0,'not JSON','')
                with patch.object(stage.subprocess,'run',side_effect=run):
                    with self.assertRaises((subprocess.TimeoutExpired,json.JSONDecodeError)):actual({},'2'*64,output,{'full_audit_calls':1},True)
                    before=len(calls)
                    with self.assertRaises(FileExistsError):actual({},'2'*64,output,{},True)
                    self.assertEqual(len(calls),before)
                self.assertEqual((output/'dispatch-intent.json').exists(),mode!='upload')
                self.assertEqual((output/'outcome-unknown.json').exists(),mode!='upload')
if __name__=='__main__':unittest.main()
