# SPDX-License-Identifier: BSD-2-Clause
"""Real diagnostic recorder body, exact314 config-loader intake and UART/SSH doubles only."""
import contextlib
import copy
from datetime import datetime,timedelta,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import struct
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import stage_display_allocate_zero_trial as stage
from tools.rpi5 import serial_display_allocate_zero_trial as recorder
from tools.rpi5 import display_allocate_zero_evidence as evidence
from tools.rpi5 import arm_display_allocate_zero_reboot as launcher
from tools.rpi5.tests.test_display_allocate_zero_serial import DisplayAllocateZeroSerialTests
ROOT=stage.ROOT;DEVICE='/dev/cu.usbmodem102';BOOT='11111111-1111-1111-1111-111111111111';RETURN='22222222-2222-2222-2222-222222222222'
def preamble(report,number):
    p=recorder.protocol.PREFIX
    return (f'{p}ENTRY TAG={report["tag"]} EL2 PRECHECK NO_XNU NO_CPU_ON ZERO_SERIAL_INPUT\r\n'+
        p+'UART CR=0x0000000000000301 FR=0x0000000000000090 IBRD=0x0000000000000018 FBRD=0x0000000000000000 LCRH=0x0000000000000070 FIRMWARE_PRESERVED_CLOCK_UNVERIFIED\r\n'+
        ''.join(p+f'CHECK STAGE=0x{n:016X}\r\n' for n in range(1,number+1))).encode()
class ObservationTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        DisplayAllocateZeroSerialTests.setUpClass();cls.native=DisplayAllocateZeroSerialTests()
        cls.report=stage.checker.inspect(stage.PACKAGE,stage.MANIFEST_SHA)
        cls.package=json.loads((stage.PACKAGE/'manifest.json').read_text())
    @classmethod
    def tearDownClass(cls):DisplayAllocateZeroSerialTests.tearDownClass()
    def context(self):
        stage.transport();pins=stage.source_pins()|{str(stage.PACKAGE/'manifest.json'):stage.MANIFEST_SHA}
        for key in ('inputs_sha256','headers_sha256','generated_sha256'):pins=stage.prior.merge_pins(pins,self.package[key])
        binding=json.loads((ROOT/'build/rpi5/framebuffer-observation-restored-20261013/plan.json').read_text())['media']['identity_binding']
        return dict(installed=dict(directory=str(ROOT/'build/rpi5/offline-fb-installation'),checkpoint_sha256='1'*64,plan_sha256='2'*64,
            result_sha256='3'*64,preflight=self.report,loader_sha256=stage.IMAGE_SHA,config_sha256=stage.engine.TRIAL_CONFIG_SHA,original_linux_boot_id=BOOT),evidence=pins,
            plan={'media':{'host':stage.HOST,'linux_boot_id':BOOT,'identity_binding':binding}})
    def media(self):
        e=stage.engine
        return dict(preflight=self.report,profile=e.TRIAL,files=[
            dict(target='config.txt',candidate='candidate-config.txt',old_sha256=e.ORIGINAL_CONFIG_SHA,new_sha256=e.TRIAL_CONFIG_SHA,
                old_bytes=len(e.ORIGINAL_CONFIG),new_bytes=len(e.TRIAL_CONFIG)),
            dict(target='probe.bin',candidate='candidate-probe.bin',old_sha256=e.original.GOOD_ZSH_SHA,new_sha256=e.IMAGE_SHA,
                old_bytes=e.original.GOOD_ZSH_BYTES,new_bytes=e.IMAGE_BYTES)],
            protected_files={'bl31.bin':e.GOOD_FW_SHA,e.original.REUSED_ZSH_BACKUP:e.original.GOOD_ZSH_SHA})
    def stream(self,fault=False):
        raw,_=self.native.fixture(report=self.report,failure=1 if fault=='preflight16' else 0)
        if isinstance(fault,tuple) and fault[0]=='precheck':
            number=fault[1]
            raw=preamble(self.report,number)+f'RPI5XNU:DISPLAYALLOCZERO:REJECT STAGE=0x{number:016X} RC=0xFFFFFFFFFFFFFFFF NO_RELOAD OBSERVATION_INCOMPLETE\r\n'.encode()
        if fault is True:raw+=b'panic(cpu 0): after STOP\r\n'
        first=b'RPi: BOOTSYS release VERSION: fixture-start\r\nRPi: BOOTLOADER release VERSION: fixture\r\nBoot mode: SD (01)\r\n'+raw
        reset=b'RPi: BOOTSYS release VERSION: fixture-return\r\nBOOT_ORDER override: 0x000000f6\r\nRPi: BOOTLOADER release VERSION: fixture\r\n'
        if fault in ('return-panic','return-fault'):
            reset+=(b'panic(cpu 0): return firmware\r\n' if fault=='return-panic' else b'RPI5XNU:RETURN:FAULT code=1\r\n')
        tail=b'Boot mode: NVME (06)\r\n'
        if fault in ('tail-panic','tail-fault'):
            tail+=(b'panic(cpu 0): after NVMe in final RX chunk\r\n' if fault=='tail-panic' else b'RPI5XNU:RETURN:FAULT final=1\r\n')
        chunks=[(first[n:n+4096],101+n/4096/10) for n in range(0,len(first),4096)]
        return chunks+[(reset,116),(tail,117)]
    def runtime(self,context,directory,fault=False,modem='ready'):
        chunks=self.stream(fault);clock=[100.0];fd=812345;original_open=os.open;original_close=os.close
        controls=[];raw_configured=[]
        required=recorder.termios.TIOCM_DTR|recorder.termios.TIOCM_RTS
        def ioctl(actual,request,argument=None):
            self.assertEqual(actual,fd);controls.append(request)
            if request==recorder.termios.TIOCEXCL:
                self.assertEqual(controls,[recorder.termios.TIOCEXCL]);self.assertIsNone(argument);return 0
            self.assertTrue(raw_configured)
            if request==recorder.termios.TIOCMBIS:
                self.assertEqual(argument,struct.pack('=I',required));return argument
            self.assertEqual(request,recorder.termios.TIOCMGET)
            self.assertEqual(argument,struct.pack('=I',0))
            if modem=='read-error':raise OSError('Injected modem status failure')
            return struct.pack('=I',required if modem=='ready' else recorder.termios.TIOCM_RTS)
        def read(actual,size):
            self.assertEqual(controls,[recorder.termios.TIOCEXCL,recorder.termios.TIOCMBIS,recorder.termios.TIOCMGET])
            self.assertEqual(modem,'ready');self.assertEqual(actual,fd);self.assertEqual(size,4096);data,clock[0]=chunks.pop(0);return data
        def utc():return (datetime(2026,10,13,20,0,tzinfo=timezone.utc)+timedelta(seconds=clock[0])).isoformat()
        config=lambda _: [0,0,0,0,0,0,[0]*32]
        with patch.object(recorder.stage.lease,'hold',return_value=contextlib.nullcontext()),\
            patch.object(recorder.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','')),\
            patch.object(recorder.os,'open',side_effect=lambda p,*a,**kw:fd if str(p)==DEVICE else original_open(p,*a,**kw)),\
            patch.object(recorder.os,'read',side_effect=read),\
            patch.object(recorder.os,'write',side_effect=AssertionError('Serial input forbidden')),\
            patch.object(recorder.os,'close',side_effect=lambda p:None if p==fd else original_close(p)),\
            patch.object(recorder.fcntl,'ioctl',side_effect=ioctl),patch.object(recorder.termios,'tcgetattr',side_effect=config),\
            patch.object(recorder.termios,'tcsetattr',side_effect=lambda *_:raw_configured.append(True)),patch.object(recorder.termios,'tcflush'),\
            patch.object(recorder.select,'select',return_value=([fd],[],[])),\
            patch.object(recorder.time,'monotonic',side_effect=lambda:clock[0]),patch.object(recorder,'utc',side_effect=utc),contextlib.redirect_stdout(io.StringIO()):
            rc=recorder.capture(context,DEVICE,directory,600)
        self.assertEqual(controls,[recorder.termios.TIOCEXCL,recorder.termios.TIOCMBIS,recorder.termios.TIOCMGET])
        if modem=='ready':self.assertEqual(chunks,[])
        else:self.assertTrue(chunks)
        return rc
    def test_actual_report_package_and_transport_sources_admit(self):
        context=self.context();checkpoint=dict(payload={'media_plan':self.media()},evidence_sha256=context['evidence'])
        result=stage.admit(checkpoint);self.assertTrue(result['zero_serial_input']);self.assertFalse(result['hardware_executed'])
        for mutation in ({'tag':'0'*32},{'root_nodes':45,'profile':'root45'},{'ownership_proven':True},
            {'early_diagnostic_stages':18},{'allocation_storage':{'start':151060480,'bytes':8192}},{'framebuffer_access':True}):
            bad=copy.deepcopy(checkpoint);bad['payload']['media_plan']['preflight'].update(mutation)
            with self.assertRaises(ValueError):stage.admit(bad)
        bad=copy.deepcopy(checkpoint);bad['evidence_sha256'].pop(str(Path(recorder.__file__).resolve()))
        with self.assertRaises(ValueError):stage.admit(bad)
        bad=copy.deepcopy(checkpoint);bad['evidence_sha256'][str(Path(recorder.protocol.__file__).resolve())]='0'*64
        with self.assertRaises(ValueError):stage.admit(bad)
    def test_low_or_unreadable_modem_control_cannot_arm_or_receive(self):
        context=self.context()
        for modem in ('dtr-low','read-error'):
            with self.subTest(modem=modem),tempfile.TemporaryDirectory(prefix='fb-modem-failed-',dir=ROOT/'build/rpi5') as name:
                directory=Path(name);directory.rmdir();self.assertEqual(self.runtime(context,directory,modem=modem),1)
                state=json.loads((directory/'state.json').read_text())
                self.assertEqual(state['status'],'failed');self.assertEqual(state['bytes'],0);self.assertEqual(state['transmitted_bytes'],0)
                self.assertFalse((directory/'armed.json').exists());self.assertFalse((directory/'serial.bin').exists())
                self.assertTrue(state['error']);self.assertFalse(state['continuous_capture'])
    def test_actual_receive_body_full_timing_and_independent_return(self):
        context=self.context()
        with tempfile.TemporaryDirectory(prefix='fb-receive-test-',dir=ROOT/'build/rpi5') as name:
            directory=Path(name);directory.rmdir();self.assertEqual(self.runtime(context,directory),0)
            state,observed,bound=evidence.captured(context,directory)
            self.assertTrue(observed['capture_valid']);self.assertEqual(state['transmitted_bytes'],0)
            self.assertEqual(observed['diagnostic']['armed_to_bootsys_seconds'],15)
            self.assertIn('receive-events.jsonl',bound)
            expected=context['plan']['media']['identity_binding']['expected'];pins=evidence.source_pins(context)
            returned=dict(host=stage.HOST,boot_id=RETURN,identity=dict(identity=expected,boot_id=RETURN,hostname='kamidana'),
                root=expected['root'].split(),bootloader={'boot-mode':6,'partition':1,'tryboot':0},sd_partitions_unmounted=True,read_only=True,
                observed_utc='2026-10-13T20:03:00+00:00',installation=context['installed'],serial_sha256=state['serial_sha256'],return_source_sha256=pins)
            with patch.object(evidence.scope['subprocess'],'run',return_value=subprocess.CompletedProcess([],0,json.dumps(returned),'')) as called:
                result=evidence.collect_return(context,directory);self.assertEqual(called.call_count,1)
            self.assertTrue(result['capture_valid']);self.assertEqual(evidence.load_return(context,directory)[1],RETURN)
            for change in ({'boot_id':BOOT},{'root':['/dev/mmcblk0p2','ext4','wrong']},{'sd_partitions_unmounted':False}):
                with self.assertRaises(ValueError):evidence.inspect_return(returned|change,context,observed)
            rows=[json.loads(s) for s in (directory/'receive-events.jsonl').read_text().splitlines()]
            raw=(directory/'serial.bin').read_bytes();bad=copy.deepcopy(rows);bad[1]['offset']+=1
            with self.assertRaises(ValueError):evidence.inspect_capture(raw,bad,state,context['installed'],recorder.bound_sources(context))
            bad=copy.deepcopy(rows);bad[-2]['monotonic']=140;bad[-1]['monotonic']=141
            with self.assertRaises(ValueError):evidence.inspect_capture(raw,bad,state,context['installed'],recorder.bound_sources(context))
            altered=copy.deepcopy(state);altered['transmitted_bytes']=1
            with self.assertRaises(ValueError):evidence.inspect_capture(raw,rows,altered,context['installed'],recorder.bound_sources(context))
            with patch.object(evidence.scope['subprocess'],'run') as never,self.assertRaises(ValueError):evidence.collect_return(context,directory)
            never.assert_not_called()
    def test_post_stop_fault_preserved_without_closing_capture_early(self):
        context=self.context()
        with tempfile.TemporaryDirectory(prefix='fb-fault-test-',dir=ROOT/'build/rpi5') as name:
            directory=Path(name);directory.rmdir();self.assertEqual(self.runtime(context,directory,True),1)
            state,observed,_=evidence.captured(context,directory)
            self.assertTrue(state['continuous_capture']);self.assertFalse(observed['capture_valid'])
            self.assertIn('fault',observed['capture_error'].lower());self.assertIn(recorder.NVME,(directory/'serial.bin').read_bytes())
    def test_live16_preflight_failure_records_one_get_and_no_stateful_requests(self):
        context=self.context()
        with tempfile.TemporaryDirectory(prefix='alloc-preflight16-',dir=ROOT/'build/rpi5') as name:
            directory=Path(name);directory.rmdir();self.assertEqual(self.runtime(context,directory,'preflight16'),1)
            state,observed,_=evidence.captured(context,directory)
            self.assertTrue(state['continuous_capture']);self.assertFalse(observed['capture_valid'])
            result=state['diagnostic'];self.assertFalse(result['allocation_trial_pass'])
            self.assertEqual(result['mailbox_requests'],1);self.assertEqual(result['raw_replies']['0'][4],16)
            self.assertEqual(result['session']['QUARANTINE'],15);self.assertFalse(result['framebuffer_authority'])
    def test_complete_return_tail_faults_fail_without_losing_nvme_or_bytes(self):
        context=self.context()
        for fault in ('return-panic','return-fault','tail-panic','tail-fault'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(prefix='fb-return-fault-',dir=ROOT/'build/rpi5') as name:
                expected=b''.join(data for data,_ in self.stream(fault))
                directory=Path(name);directory.rmdir();self.assertEqual(self.runtime(context,directory,fault),1)
                state,observed,_=evidence.captured(context,directory)
                self.assertTrue(state['continuous_capture']);self.assertTrue(state['normal_nvme_boot_observed'])
                self.assertFalse(observed['capture_valid']);self.assertEqual(state['transmitted_bytes'],0)
                self.assertIn('Fault in whole capture',observed['capture_error'])
                self.assertEqual((directory/'serial.bin').read_bytes(),expected)
    def test_precheck_rejection_is_failed_even_after_independent_return(self):
        context=self.context()
        for number in (1,9,17,18,19):
            with self.subTest(stage=number),tempfile.TemporaryDirectory(prefix='fb-precheck-failed-',dir=ROOT/'build/rpi5') as name:
                directory=Path(name);directory.rmdir()
                self.assertEqual(self.runtime(context,directory,('precheck',number)),1)
                state,observed,_=evidence.captured(context,directory)
                self.assertTrue(state['continuous_capture']);self.assertTrue(state['normal_nvme_boot_observed'])
                self.assertEqual(state['transmitted_bytes'],0);self.assertTrue(state['diagnostic']['precheck_failed'])
                self.assertEqual(state['diagnostic']['failed_stage'],number)
                self.assertFalse(state['diagnostic']['framebuffer_authority']);self.assertFalse(observed['capture_valid'])
                expected=context['plan']['media']['identity_binding']['expected'];pins=evidence.source_pins(context)
                returned=dict(host=stage.HOST,boot_id=RETURN,identity=dict(identity=expected,boot_id=RETURN,hostname='kamidana'),
                    root=expected['root'].split(),bootloader={'boot-mode':6,'partition':1,'tryboot':0},sd_partitions_unmounted=True,read_only=True,
                    observed_utc='2026-10-13T20:03:00+00:00',installation=context['installed'],serial_sha256=state['serial_sha256'],return_source_sha256=pins)
                with patch.object(evidence.scope['subprocess'],'run',return_value=subprocess.CompletedProcess([],0,json.dumps(returned),'')):
                    result=evidence.collect_return(context,directory)
                self.assertFalse(result['capture_valid']);self.assertIsNone(result['diagnostic'])
                self.assertEqual(evidence.load_return(context,directory)[1],RETURN)
                self.assertFalse(evidence.load_return(context,directory)[0]['capture_valid'])
    def test_one_shot_launcher_actual_arm_schema_and_no_unchecked_reboot(self):
        context=self.context()
        with tempfile.TemporaryDirectory(prefix='fb-launch-test-',dir=ROOT/'build/rpi5') as name,\
            tempfile.TemporaryDirectory(prefix='fb-arm-test-',dir=ROOT/'build/rpi5') as capture:
            out=Path(name);out.rmdir();cap=Path(capture);cap.rmdir()
            def arm(output,command,line,validate,reboot):
                self.assertIn(str(Path(recorder.__file__).resolve()),command);self.assertEqual(line,recorder.armed_line(self.report))
                output.mkdir();cap.mkdir();state=recorder.initial(context,DEVICE,73,'2026-10-13T20:00:00+00:00')
                state.update(armed_utc='2026-10-13T20:00:01+00:00',armed_monotonic=100.0);stage.save(cap/'armed.json',state)
                witness=validate(73);stage.save(output/'reboot-intent.json',witness);return {'result':reboot()}
            with patch.object(launcher,'arm_once',side_effect=arm),patch.object(launcher.subprocess,'run',
                return_value=subprocess.CompletedProcess([],0,'VERIFIED_SSD_LINUX_REBOOT_ONCE {}\n','')) as called:
                value=launcher.launch(context,DEVICE,cap,out,BOOT);self.assertTrue(value['result']['verification_marker_observed']);self.assertEqual(called.call_count,1)
                self.assertIn('actual_boot!=expected_boot or actual_root!=expected_root',called.call_args.kwargs['input'])
            with patch.object(launcher,'arm_once') as never,self.assertRaises(ValueError):launcher.launch(context,DEVICE,cap,out,RETURN)
            never.assert_not_called()
    def test_frozen_publication_engine_and_distinct_profile_bindings(self):
        self.assertIs(stage._dispatch.__code__,stage.publisher.dispatch.__code__)
        self.assertEqual(stage.CONTROLLER,'display-allocation-zero-config-loader-controller-v1')
        self.assertEqual(stage.engine.GOOD_FW_SHA,'413a050e'+stage.engine.GOOD_FW_SHA[8:])
        self.assertIs(stage._dispatch.__globals__['subprocess'],stage.upload_transport)

    def test_actual_completed314_config_loader_restore_typed_intake(self):
        directory=ROOT/'build/rpi5/display-allocation-restored-20261014'
        pin='eed148f33f0668278275b4f7cc0427a1473f1c343d8a3e75512f4b8306d34e45'
        plan='a8294c948c32fed48f0d2c43ad7ff0d2bfb545339d682e236773ea3966cca2dc'
        self.assertEqual(stage.sha(directory/'result.json'),'bb329455149275de355ef67ebbc8c9e56b02d7519aeb895f5cb4f321217ea7fe')
        with patch.object(stage.checker,'inspect',side_effect=AssertionError('No package audit in baseline intake')),\
            patch.object(stage.preceding,'completed_restore',side_effect=AssertionError('Not the old capabilities schema')):
            context=stage.baseline(directory,pin,plan)
            with self.assertRaises(ValueError):stage.baseline(directory,'0'*64,plan)
            with self.assertRaises(ValueError):stage.baseline(directory,pin,'0'*64)
        self.assertEqual(len(context['result']['next_catalog']),314)
        self.assertEqual(context['result']['publication']['identity']['boot_id'],'806018a2-252e-43d9-aa88-bac89efcf55f')
        for name in ('bl31.bin','config.txt','probe.bin'):
            bad=copy.deepcopy(context);bad['result']['publication']['protected_files_sha256'][name]='0'*64
            with patch.object(stage.previous_allocation,'restoration',return_value=bad),self.assertRaises(ValueError):
                stage.baseline(directory,pin,plan)

    def test_sealed_package_and_source_revalidation_is_byte_only(self):
        context=self.context()
        with patch.object(stage.checker,'inspect',side_effect=AssertionError('No repeated package audit')),\
            patch.object(stage.previous_allocation,'restoration',side_effect=AssertionError('No history replay')):
            recorder.revalidate(context)
            for path in (stage.PACKAGE/'manifest.json',stage.PACKAGE/'probe.bin',Path(recorder.__file__).resolve(),
                Path(recorder.protocol.__file__).resolve()):
                bad=copy.deepcopy(context);bad['evidence'][str(path)]='0'*64
                with self.assertRaises(ValueError):recorder.revalidate(bad)

    def test_compressed_upload_and_before_dispatch_timeout_no_retry(self):
        original=['scp','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
            '/local/exact-candidate.bin',stage.HOST+':/home/sandrzej/xnu-root42-v2-testabcd/candidate.bin']
        with patch.object(stage.subprocess,'run') as call:
            stage.upload_run(original,check=True,timeout=60)
            call.assert_called_once_with(['scp','-C',*original[1:]],check=True,timeout=180)
        media=dict(controller=stage.CONTROLLER,profile=stage.engine.TRIAL,descriptor='display-allocation-zero-fixed32',
            files=[{'target':'config.txt','candidate':'candidate-config.txt'}],candidates={'config.txt':'/local/exact-candidate.bin'})
        seal=types.SimpleNamespace(revalidate=lambda *_:{'media_plan':media},save_new=lambda *_:None)
        engine=types.SimpleNamespace(TRIAL=stage.engine.TRIAL,RESTORE=stage.engine.RESTORE,
            plan_from_seal=lambda *_:({'media':media},'1'*64),
            remote_source=lambda *_:self.fail('No SD program after upload timeout'))
        with tempfile.TemporaryDirectory(dir=ROOT/'build/rpi5') as name:
            out=Path(name);out.rmdir();calls=[]
            def run(command,**kwargs):
                calls.append((command,kwargs))
                if command[0]=='scp':
                    self.assertEqual(command[1],'-C');self.assertEqual(kwargs,{'check':True,'timeout':180})
                    raise subprocess.TimeoutExpired(command,180)
                self.assertEqual(command,stage.SSH+['python3 -'])
                return subprocess.CompletedProcess(command,0,json.dumps({'run':'/home/sandrzej/xnu-link-v2-testabcd'}),'')
            pins=stage.source_pins();checkpoint={'evidence_sha256':pins}
            actual=stage.private(stage._dispatch,seals=seal,engine=engine)
            with patch.object(stage.subprocess,'run',side_effect=run):
                with self.assertRaises(subprocess.TimeoutExpired):actual(checkpoint,'2'*64,out,{},True)
                self.assertEqual(len(calls),2)
                with self.assertRaises(FileExistsError):actual(checkpoint,'2'*64,out,{},True)
                self.assertEqual(len(calls),2)
            self.assertTrue((out/'plan.json').is_file())
            for n in ('dispatch-intent.json','remote-program.py','result.json','completion.json'):
                self.assertFalse((out/n).exists())
    def test_uncertain_remote_dispatch_preserves_intent_without_retry(self):
        media=dict(descriptor='display-allocation-zero-fixed32',profile=stage.engine.TRIAL,
            files=[{'target':'config.txt','candidate':'candidate-config.txt'},{'target':'probe.bin','candidate':'candidate-probe.bin'}],
            candidates={'config.txt':'/local/exact-config.txt','probe.bin':'/local/exact-probe.bin'})
        seals=types.SimpleNamespace(revalidate=lambda *_:{'media_plan':media},save_new=lambda *_:None)
        engine=types.SimpleNamespace(plan_from_seal=lambda *_:({'media':media},'1'*64),
            remote_source=lambda *_:'EXACT_CANONICAL_SD_PROGRAM')
        with tempfile.TemporaryDirectory(dir=ROOT/'build/rpi5') as name:
            out=Path(name);out.rmdir();calls=[]
            def run(command,**kwargs):
                calls.append(command)
                if command[-1]=='python3 -':return subprocess.CompletedProcess(command,0,json.dumps({'run':'/home/sandrzej/xnu-link-v2-testabcd'}),'')
                if command[0]=='scp':return subprocess.CompletedProcess(command,0)
                self.assertEqual(command,stage.SSH+['sudo -n python3 -'])
                self.assertTrue((out/'dispatch-intent.json').exists());self.assertEqual(kwargs['input'],'EXACT_CANONICAL_SD_PROGRAM')
                raise subprocess.TimeoutExpired(command,300,output=b'UNCERTAIN_PUBLICATION\n')
            actual=stage.private(stage._dispatch,seals=seals,engine=engine)
            with patch.object(stage.subprocess,'run',side_effect=run):
                with self.assertRaises(subprocess.TimeoutExpired):actual({},'2'*64,out,{'full_audit_calls':1},True)
                self.assertEqual(len(calls),4)
                with self.assertRaises(FileExistsError):actual({},'2'*64,out,{'full_audit_calls':1},True)
                self.assertEqual(len(calls),4)
            self.assertTrue((out/'dispatch-intent.json').exists());self.assertTrue((out/'outcome-unknown.json').exists())
            self.assertFalse((out/'result.json').exists());self.assertEqual((out/'remote.stdout').read_bytes(),b'UNCERTAIN_PUBLICATION\n')
if __name__=='__main__':unittest.main()

