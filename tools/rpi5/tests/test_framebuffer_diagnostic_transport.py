# SPDX-License-Identifier: BSD-2-Clause
"""Real diagnostic recorder body, exact258 intake and UART/SSH doubles only."""
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
import unittest
from unittest.mock import patch
from tools.rpi5 import stage_framebuffer_diagnostic_trial as stage
from tools.rpi5 import serial_framebuffer_diagnostic_trial as recorder
from tools.rpi5 import framebuffer_diagnostic_evidence as evidence
from tools.rpi5 import arm_framebuffer_diagnostic_reboot as launcher
from tools.rpi5.tests.test_framebuffer_diagnostic_serial import DiagnosticSerialTests, preamble
ROOT=stage.ROOT;DEVICE='/dev/cu.usbmodem102';BOOT='11111111-1111-1111-1111-111111111111';RETURN='22222222-2222-2222-2222-222222222222'
class ObservationTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        DiagnosticSerialTests.setUpClass();cls.native=DiagnosticSerialTests()
        cls.report=stage.checker.inspect(stage.PACKAGE,stage.MANIFEST_SHA)
        cls.package=json.loads((stage.PACKAGE/'manifest.json').read_text())
    @classmethod
    def tearDownClass(cls):DiagnosticSerialTests.tearDownClass()
    def context(self):
        stage.transport();pins=stage.source_pins()|{str(stage.PACKAGE/'manifest.json'):stage.MANIFEST_SHA}
        for key in ('inputs_sha256','headers_sha256','generated_sha256'):pins=stage.prior.merge_pins(pins,self.package[key])
        binding=json.loads((ROOT/'build/rpi5/framebuffer-observation-restored-20261013/plan.json').read_text())['media']['identity_binding']
        return dict(installed=dict(directory=str(ROOT/'build/rpi5/offline-fb-installation'),checkpoint_sha256='1'*64,plan_sha256='2'*64,
            result_sha256='3'*64,preflight=self.report,loader_sha256=stage.IMAGE_SHA,original_linux_boot_id=BOOT),evidence=pins,
            plan={'media':{'host':stage.HOST,'linux_boot_id':BOOT,'identity_binding':binding}})
    def stream(self,fault=False):
        raw,_=self.native.actual(report=self.report)
        if isinstance(fault,tuple) and fault[0]=='precheck':
            number=fault[1]
            raw=preamble(self.report,number)+f'RPI5XNU:FBOBS:REJECT STAGE=0x{number:016X} RC=0xFFFFFFFFFFFFFFFF NO_RELOAD OBSERVATION_INCOMPLETE\r\n'.encode()
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
        context=self.context();checkpoint=dict(payload={'media_plan':{'preflight':self.report}},evidence_sha256=context['evidence'])
        result=stage.admit(checkpoint);self.assertTrue(result['zero_serial_input']);self.assertFalse(result['hardware_executed'])
        for mutation in ({'tag':'0'*32},{'root_nodes':45,'profile':'root45'},{'ownership_proven':True},
            {'early_diagnostic_stages':18},{'early_uart_firmware_preserved':False},{'precheck_rejection_is_observation':True}):
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
            self.assertIn('fault',observed['capture_error']);self.assertIn(recorder.NVME,(directory/'serial.bin').read_bytes())
    def test_complete_return_tail_faults_fail_without_losing_nvme_or_bytes(self):
        context=self.context()
        for fault in ('return-panic','return-fault','tail-panic','tail-fault'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(prefix='fb-return-fault-',dir=ROOT/'build/rpi5') as name:
                expected=b''.join(data for data,_ in self.stream(fault))
                directory=Path(name);directory.rmdir();self.assertEqual(self.runtime(context,directory,fault),1)
                state,observed,_=evidence.captured(context,directory)
                self.assertTrue(state['continuous_capture']);self.assertTrue(state['normal_nvme_boot_observed'])
                self.assertFalse(observed['capture_valid']);self.assertEqual(state['transmitted_bytes'],0)
                self.assertIn('Return firmware fault',observed['capture_error'])
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
                self.assertEqual(state['diagnostic']['failed_stage'],number);self.assertFalse(state['diagnostic']['complete_observation'])
                self.assertFalse(state['diagnostic']['framebuffer_absence_inferred']);self.assertFalse(observed['capture_valid'])
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
        self.assertIs(stage.dispatch.__code__,stage.base.dispatch.__code__);self.assertIs(stage._dispatch.__code__,stage.base._dispatch.__code__)
        self.assertIs(stage.load_installation.__code__,stage.base.load_installation.__code__)
        self.assertEqual(stage.CONTROLLER,'framebuffer-fdt-precheck-diagnostic-single-loader-v1')
        self.assertEqual(stage.engine.original.FIRMWARE_SHA,'413a050e'+stage.engine.original.FIRMWARE_SHA[8:])
    def test_actual_completed_258_observer_restoration_byte_intake(self):
        directory=ROOT/'build/rpi5/framebuffer-observation-restored-20261013'
        with patch.object(stage.checker,'inspect',side_effect=AssertionError('No package compiler in baseline intake')):
            context=stage.baseline(directory,'8a8b848181e801e5c27bf08de4666fe322c1a3d0c9b002d3da529d136f9efa4f',
                '5fcc9bfd8e8d9024d64b4db37d80e0ef241953568307d7f5c9f78a36a6265944')
        self.assertEqual(len(context['result']['next_catalog']),258)
        self.assertEqual(context['result']['publication']['identity']['boot_id'],'f98df7b0-184d-4ff9-a2aa-5f710501dd4e')
        self.assertEqual(context['result']['publication']['protected_files_sha256']['probe.bin'],stage.GOOD[1])
        self.assertEqual(context['result']['publication']['protected_files_sha256']['bl31.bin'],stage.engine.original.FIRMWARE_SHA)
    def test_exact_baseline_controller_and_profile_before_byte_intake(self):
        directory=ROOT/'build/rpi5/framebuffer-observation-restored-20261013';path=directory/'plan.json'
        plan=json.loads(path.read_text());original=Path.read_text
        for field,value in (('controller',stage.CONTROLLER),('controller','framebuffer-fdt-observation-single-loader-v1'),('profile',stage.engine.TRIAL)):
            bad=copy.deepcopy(plan);bad['media'][field]=value
            def read(p,*a,**kw):return json.dumps(bad) if p==path else original(p,*a,**kw)
            with patch.object(Path,'read_text',read),patch.object(stage.previous,'restoration') as never,self.assertRaises(ValueError):
                stage.baseline(directory,'unused','unused')
            never.assert_not_called()
if __name__=='__main__':unittest.main()
