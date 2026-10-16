# SPDX-License-Identifier: BSD-2-Clause
"""Execute the real guarded recorder/launcher with explicit UART/SSH doubles.

No target code, serial device, SSH connection, SD mutation or physical proof.
"""
import contextlib
import copy
from datetime import datetime,timedelta,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import stage_display_xnu_trial as stage
from tools.rpi5 import serial_display_xnu_trial as recorder
from tools.rpi5 import display_xnu_evidence as evidence
from tools.rpi5 import arm_display_xnu_reboot as launcher
from tools.rpi5.tests.test_display_xnu_serial import boot,response,report
ROOT=stage.ROOT;DEVICE='/dev/cu.usbmodem102';BOOT='11111111-1111-1111-1111-111111111111';RETURN='22222222-2222-2222-2222-222222222222'

class DisplayXNUTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=report();cls.package=json.loads((stage.PACKAGE/'manifest.json').read_text())
    def context(self):
        stage.transport();pins=stage.source_pins()|{str(stage.PACKAGE/'manifest.json'):stage.MANIFEST_SHA}
        for key in ('inputs_sha256','actual_headers_sha256','generated_sha256'):pins=stage.prior.merge_pins(pins,self.package[key])
        binding=json.loads((ROOT/'build/rpi5/display-compact-restored-20261014/plan.json').read_text())['media']['identity_binding']
        return dict(installed=dict(directory=str(ROOT/'build/rpi5/offline-display-xnu-installation'),checkpoint_sha256='1'*64,plan_sha256='2'*64,
            result_sha256='3'*64,preflight=self.report,loader_sha256=stage.IMAGE_SHA,config_sha256=stage.engine.TRIAL_CONFIG_SHA,original_linux_boot_id=BOOT),
            evidence=pins,plan={'media':{'host':stage.HOST,'linux_boot_id':BOOT,'identity_binding':binding}})
    def media(self):
        e=stage.engine
        return dict(preflight=self.report,profile=e.TRIAL,files=[
            dict(target='config.txt',candidate='candidate-config.txt',old_sha256=e.ORIGINAL_CONFIG_SHA,new_sha256=e.TRIAL_CONFIG_SHA,
                old_bytes=len(e.ORIGINAL_CONFIG),new_bytes=len(e.TRIAL_CONFIG)),
            dict(target='probe.bin',candidate='candidate-probe.bin',old_sha256=e.original.GOOD_ZSH_SHA,new_sha256=e.IMAGE_SHA,
                old_bytes=e.original.GOOD_ZSH_BYTES,new_bytes=e.IMAGE_BYTES)],
            protected_files={'bl31.bin':e.GOOD_FW_SHA,e.original.REUSED_ZSH_BACKUP:e.original.GOOD_ZSH_SHA})
    def runtime(self,context,directory,fault=None,modem='ready'):
        p=recorder.protocol;n='D'+'a'*16;clock=[100.0];fd=812345;sent=bytearray();line=bytearray();step=[0];controls=[];raw_configured=[]
        initial=boot(self.report)
        if fault=='oldtag':initial=initial.replace(self.report['tag'].encode(),b'0'*32)
        if fault=='missingmirror':initial=initial.replace(p.MIRROR,b'MISSING_MIRROR')
        if fault=='missingroot':initial=initial.replace(p.ROOT_READY,b'MISSING_ROOT')
        chunks=[(101.0,initial)]
        tail=b'RPi: BOOTSYS release VERSION: return\r\nBOOT_ORDER override: 0x000000f6\r\nRPi: BOOTLOADER release VERSION: return\r\nBoot mode: NVME (06)\r\n'
        if fault=='tailpanic':tail+=b'panic(cpu0): after NVMe in final chunk\r\n'
        if fault=='returnfault':tail=tail.replace(p.NVME,b'RPI5XNU:RETURN:FAULT code=1\r\n'+p.NVME)
        chunks.append((296.0,tail))
        original_open=os.open;original_close=os.close;required=recorder.termios.TIOCM_DTR|recorder.termios.TIOCM_RTS
        original_revalidate=recorder.revalidate;validations=[0]
        def revalidate(value):
            original_revalidate(value);validations[0]+=1
            if fault=='slowvalidation' and validations[0]==3:clock[0]+=76
        def ioctl(actual,request,arg=None):
            self.assertEqual(actual,fd);controls.append(request)
            if request==recorder.termios.TIOCEXCL:return 0
            self.assertTrue(raw_configured)
            if request==recorder.termios.TIOCMBIS:self.assertEqual(arg,struct.pack('=I',required));return arg
            self.assertEqual(request,recorder.termios.TIOCMGET)
            if modem=='error':raise OSError('Injected modem read error')
            return struct.pack('=I',required if modem=='ready' else recorder.termios.TIOCM_RTS)
        def selected(read,write,exception,timeout):
            if write:return [],[fd],[]
            if chunks and chunks[0][0]<=clock[0]+timeout:
                clock[0]=max(clock[0],chunks[0][0]);return [fd],[],[]
            clock[0]+=timeout;return [],[],[]
        def read(actual,limit):
            self.assertEqual(actual,fd);self.assertEqual(modem,'ready')
            self.assertEqual(controls,[recorder.termios.TIOCEXCL,recorder.termios.TIOCMBIS,recorder.termios.TIOCMGET])
            stamp,data=chunks.pop(0);clock[0]=max(clock[0],stamp)
            if fault=='continuousrx' and data.startswith(b'RPI5XNU:TERMINAL:WATCHDOG_KICK '):clock[0]+=1
            if len(data)>limit:chunks.insert(0,(clock[0],data[limit:]));data=data[:limit]
            return data
        def write(actual,data):
            self.assertEqual(actual,fd);self.assertEqual(len(data),1);sent.extend(data);line.extend(data)
            if fault=='resetduringtx' and len(sent)==12:
                chunks.insert(0,(clock[0],b'RPi: BOOTSYS release VERSION: premature-reset\r\n'))
            if fault=='continuousrx' and len(sent)==12:
                chunks[:0]=[(clock[0],b'RPI5XNU:TERMINAL:WATCHDOG_KICK RELOADS=1\r\n')]*150
            if data==b'\n':
                name,expected,_,_=p.exchanges(n)[step[0]];self.assertEqual(line.decode().rstrip('\n'),expected)
                answer=response(name,n)
                if fault=='echoonly' and name=='proof':answer=expected.encode()+b'\r\npi-zsh# '
                if fault=='status1' and name=='recovery':answer=answer.replace(b'RECOVERY_STATUS:0',b'RECOVERY_STATUS:1')
                chunks.insert(0,(clock[0]+0.01,answer));line.clear();step[0]+=1
            return 1
        def utc():return (datetime(2026,10,14,20,0,tzinfo=timezone.utc)+timedelta(seconds=clock[0])).isoformat()
        config=lambda _: [0,0,0,0,0,0,[0]*32]
        with patch.object(recorder.stage.lease,'hold',return_value=contextlib.nullcontext()),\
            patch.object(recorder,'revalidate',side_effect=revalidate),\
            patch.object(recorder.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','')),\
            patch.object(recorder.os,'open',side_effect=lambda path,*a,**k:fd if str(path)==DEVICE else original_open(path,*a,**k)),\
            patch.object(recorder.os,'read',side_effect=read),patch.object(recorder.os,'write',side_effect=write),\
            patch.object(recorder.os,'close',side_effect=lambda value:None if value==fd else original_close(value)),\
            patch.object(recorder.fcntl,'ioctl',side_effect=ioctl),patch.object(recorder.termios,'tcgetattr',side_effect=config),\
            patch.object(recorder.termios,'tcsetattr',side_effect=lambda *_:raw_configured.append(True)),patch.object(recorder.termios,'tcflush'),\
            patch.object(recorder.select,'select',side_effect=selected),patch.object(recorder.time,'monotonic',side_effect=lambda:clock[0]),\
            patch.object(recorder.time,'sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)),\
            patch.object(recorder.secrets,'token_hex',return_value='a'*16),patch.object(recorder,'utc',side_effect=utc),contextlib.redirect_stdout(io.StringIO()):
            result=recorder.capture(context,DEVICE,directory)
        return result,bytes(sent)
    def test_actual_checked_report_source_and_package_admission(self):
        context=self.context();checkpoint=dict(payload={'media_plan':self.media()},evidence_sha256=context['evidence'])
        with patch.object(stage.checker,'inspect',side_effect=AssertionError('No repeated compiler/checker')):
            value=stage.admit(checkpoint);self.assertTrue(value['serial_input_guarded_by_fresh_mirror_root_prompt'])
        for change in ({'tag':'0'*32},{'terminal_watchdog_seconds':180.0},{'root_nodes':33},{'physical_visibility_proven':True}):
            bad=copy.deepcopy(checkpoint);bad['payload']['media_plan']['preflight'].update(change)
            with self.assertRaises(ValueError):stage.admit(bad)
        bad=copy.deepcopy(checkpoint);bad['evidence_sha256'].pop(str(Path(recorder.protocol.__file__).resolve()))
        with self.assertRaises(ValueError):stage.admit(bad)
    def test_actual_recorder_four_exchanges_and_independent_return(self):
        context=self.context()
        with tempfile.TemporaryDirectory(prefix='display-xnu-rx-',dir=ROOT/'build/rpi5') as name:
            directory=Path(name);directory.rmdir();rc,sent=self.runtime(context,directory)
            state=json.loads((directory/'state.json').read_text());self.assertEqual(rc,0,state)
            state,observed,_=evidence.captured(context,directory);self.assertTrue(observed['capture_valid'])
            self.assertEqual(len(sent),state['transmitted_bytes']);self.assertEqual(len(state['exchanges']),4)
            self.assertTrue(observed['diagnostic']['actual_interactive_exit_zero']);self.assertFalse(observed['diagnostic']['physical_visibility_proven'])
            expected=context['plan']['media']['identity_binding']['expected'];pins=evidence.source_pins(context)
            returned=dict(host=stage.HOST,boot_id=RETURN,identity=dict(identity=expected,boot_id=RETURN,hostname='kamidana'),
                root=expected['root'].split(),bootloader={'boot-mode':6,'partition':1,'tryboot':0},sd_partitions_unmounted=True,read_only=True,
                observed_utc='2026-10-14T20:10:00+00:00',installation=context['installed'],serial_sha256=state['serial_sha256'],return_source_sha256=pins)
            with patch.object(evidence.scope['subprocess'],'run',return_value=subprocess.CompletedProcess([],0,json.dumps(returned),'')) as called:
                result=evidence.collect_return(context,directory);self.assertEqual(called.call_count,1)
            self.assertTrue(result['capture_valid']);self.assertEqual(evidence.load_return(context,directory)[1],RETURN)
            for change in ({'boot_id':BOOT},{'root':['/dev/mmcblk0p2','ext4','wrong']},{'sd_partitions_unmounted':False}):
                with self.assertRaises(ValueError):evidence.inspect_return(returned|change,context,observed)
            with self.assertRaises(ValueError):evidence.collect_return(context,directory)
    def test_incomplete_admission_is_zero_tx_and_full_recovery_rx(self):
        context=self.context()
        for fault in ('oldtag','missingmirror','missingroot','slowvalidation'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(prefix='display-xnu-reject-',dir=ROOT/'build/rpi5') as name:
                d=Path(name);d.rmdir();rc,sent=self.runtime(context,d,fault)
                self.assertEqual(rc,1);self.assertEqual(sent,b'')
                state,observed,_=evidence.captured(context,d);self.assertFalse(observed['capture_valid']);self.assertTrue(state['normal_nvme_boot_observed'])
                if fault=='slowvalidation':
                    self.assertEqual(state['admitted_monotonic'],101.0)
                    self.assertEqual(state['trial_error'],'Insufficient absolute TX budget')
    def test_echo_only_nonzero_exit_reset_and_full_tail_faults(self):
        context=self.context()
        for fault in ('echoonly','status1','resetduringtx','tailpanic','returnfault'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(prefix='display-xnu-fault-',dir=ROOT/'build/rpi5') as name:
                d=Path(name);d.rmdir();rc,sent=self.runtime(context,d,fault)
                state,observed,_=evidence.captured(context,d);self.assertEqual(rc,1);self.assertFalse(observed['capture_valid'])
                self.assertIn(recorder.NVME,(d/'serial.bin').read_bytes())
                if fault=='resetduringtx':self.assertEqual(len(sent),12)
                if fault=='echoonly':self.assertEqual(len(state['exchanges']),1)
    def test_modem_low_read_error_never_arm_receive_or_reboot(self):
        context=self.context()
        for modem in ('low','error'):
            with self.subTest(modem=modem),tempfile.TemporaryDirectory(prefix='display-xnu-modem-',dir=ROOT/'build/rpi5') as name:
                d=Path(name);d.rmdir();rc,sent=self.runtime(context,d,modem=modem)
                self.assertEqual(rc,1);self.assertEqual(sent,b'');self.assertFalse((d/'armed.json').exists())
    def test_continuously_readable_rx_stops_tx_at_absolute_deadline(self):
        context=self.context()
        with tempfile.TemporaryDirectory(prefix='display-xnu-rx-deadline-',dir=ROOT/'build/rpi5') as name:
            d=Path(name);d.rmdir();rc,sent=self.runtime(context,d,fault='continuousrx')
            state=json.loads((d/'state.json').read_text())
            self.assertEqual(rc,1);self.assertEqual(len(sent),12)
            self.assertEqual(state['trial_error'],'Absolute pending-RX TX deadline exhausted')
            self.assertTrue(state['normal_nvme_boot_observed']);self.assertIn(recorder.NVME,(d/'serial.bin').read_bytes())
            rows=[json.loads(line) for line in (d/'receive-events.jsonl').read_text().splitlines()]
            self.assertTrue(any(v['monotonic']>state['admitted_monotonic']+120 for v in rows))
    def test_one_shot_launcher_exact_actual_armed_schema(self):
        context=self.context()
        with tempfile.TemporaryDirectory(prefix='display-xnu-arm-capture-',dir=ROOT/'build/rpi5') as capname,\
            tempfile.TemporaryDirectory(prefix='display-xnu-arm-launch-',dir=ROOT/'build/rpi5') as outname:
            cap,out=Path(capname),Path(outname);cap.rmdir();out.rmdir()
            def arm(output,command,line,validate,reboot):
                self.assertIn(str(Path(recorder.__file__).resolve()),command);self.assertEqual(line,recorder.armed_line(self.report))
                output.mkdir();cap.mkdir();state=recorder.initial(context,DEVICE,73,'2026-10-14T20:00:00+00:00')
                state.update(armed_utc='2026-10-14T20:00:01+00:00',armed_monotonic=100.0);stage.save(cap/'armed.json',state)
                witness=validate(73);stage.save(output/'reboot-intent.json',witness);return {'result':reboot()}
            with patch.object(launcher,'arm_once',side_effect=arm),patch.object(launcher.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'VERIFIED_SSD_LINUX_REBOOT_ONCE {}\n','')) as called:
                value=launcher.launch(context,DEVICE,cap,out,BOOT);self.assertTrue(value['result']['verification_marker_observed']);self.assertEqual(called.call_count,1)
            with patch.object(launcher,'arm_once') as never,self.assertRaises(ValueError):launcher.launch(context,DEVICE,cap,out,RETURN)
            never.assert_not_called()
    def test_only_new_profiles_and_exact_compact_restoration_intake(self):
        self.assertIs(stage._dispatch.__code__,stage.publisher.dispatch.__code__)
        with patch.object(stage.previous_compact,'restoration',side_effect=ValueError('Exact compact restore')) as called:
            with self.assertRaisesRegex(ValueError,'Exact compact'):stage.baseline(ROOT/'build/rpi5/offline','1'*64,'2'*64)
            called.assert_called_once()
    def test_actual_completed374_compact_repeat_restore_byte_only_intake(self):
        directory=ROOT/'build/rpi5/display-compact-repeat-restored-20261014'
        pin='f998989aa3ecd0fa51642e9fb3862195cc10f76b6c2745977c584070e12ad503'
        plan='96ece5e1e42dcba5e9e25d0e82c62308db07fb893227ccd3c444923b39ff51f4'
        self.assertEqual(stage.sha(directory/'result.json'),'b342f7668ecb98649a93f2924a357d2ec6b84e660f209ddf30f37630534e3cbc')
        with patch.object(stage.checker,'inspect',side_effect=AssertionError('No package replay in baseline intake')),\
            patch.object(subprocess,'run',side_effect=AssertionError('No compiler/history/transport')):
            context=stage.baseline(directory,pin,plan)
            with self.assertRaises(ValueError):stage.baseline(directory,'0'*64,plan)
            with self.assertRaises(ValueError):stage.baseline(directory,pin,'0'*64)
        self.assertEqual(len(context['result']['next_catalog']),374)
        self.assertEqual(context['result']['publication']['identity']['boot_id'],'388349d4-3664-4ac1-9488-7d59cc4f6566')
        for name in ('bl31.bin','config.txt','probe.bin'):
            bad=copy.deepcopy(context);bad['result']['publication']['protected_files_sha256'][name]='0'*64
            with patch.object(stage.previous_compact,'restoration',return_value=bad),self.assertRaises(ValueError):
                stage.baseline(directory,pin,plan)
    def test_actual_dispatch_upload_and_unknown_failures_never_retry(self):
        media=dict(controller=stage.CONTROLLER,profile=stage.engine.TRIAL,descriptor='display-xnu-fixed32',
            files=[{'target':'config.txt','candidate':'candidate-config.txt'},{'target':'probe.bin','candidate':'candidate-probe.bin'}],
            candidates={'config.txt':'/local/exact-config.txt','probe.bin':'/local/exact-probe.bin'})
        seals=types.SimpleNamespace(revalidate=lambda *_:{'media_plan':media},save_new=lambda *_:None)
        engine=types.SimpleNamespace(plan_from_seal=lambda *_:({'media':media},'1'*64),
            remote_source=lambda *_:'EXACT_CANONICAL_SD_PROGRAM',validate_result=lambda *_:None)
        for failure in ('upload-timeout','dispatch-timeout','malformed-result'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory(prefix='display-xnu-dispatch-',dir=ROOT/'build/rpi5') as name:
                out=Path(name);out.rmdir();calls=[]
                def run(command,**kwargs):
                    calls.append(command)
                    if command==stage.SSH+['python3 -']:
                        self.assertEqual(kwargs['timeout'],30)
                        return subprocess.CompletedProcess(command,0,json.dumps({'run':'/home/sandrzej/xnu-link-v2-testabcd'}),'')
                    if command[0]=='scp':
                        self.assertEqual(command[1],'-C');self.assertEqual(kwargs,{'check':True,'timeout':180})
                        if failure=='upload-timeout':raise subprocess.TimeoutExpired(command,180)
                        return subprocess.CompletedProcess(command,0)
                    self.assertEqual(command,stage.SSH+['sudo -n python3 -']);self.assertEqual(kwargs['timeout'],300)
                    self.assertEqual(kwargs['input'],'EXACT_CANONICAL_SD_PROGRAM')
                    self.assertTrue((out/'dispatch-intent.json').exists())
                    self.assertEqual((out/'remote-program.py').read_text(),'EXACT_CANONICAL_SD_PROGRAM')
                    if failure=='dispatch-timeout':raise subprocess.TimeoutExpired(command,300,output=b'UNCERTAIN_PUBLICATION\n')
                    return subprocess.CompletedProcess(command,0,'NOT_VALID_JSON','')
                actual=stage.private(stage._dispatch,seals=seals,engine=engine)
                with patch.object(stage.subprocess,'run',side_effect=run):
                    with self.assertRaises((subprocess.TimeoutExpired,json.JSONDecodeError)):actual({},'2'*64,out,{'full_audit_calls':1},True)
                    self.assertEqual(len(calls),2 if failure=='upload-timeout' else 4)
                    with self.assertRaises(FileExistsError):actual({},'2'*64,out,{'full_audit_calls':1},True)
                    self.assertEqual(len(calls),2 if failure=='upload-timeout' else 4)
                self.assertFalse((out/'result.json').exists());self.assertFalse((out/'completion.json').exists())
                if failure=='upload-timeout':
                    self.assertFalse((out/'dispatch-intent.json').exists());self.assertFalse((out/'remote-program.py').exists())
                else:
                    unknown=json.loads((out/'outcome-unknown.json').read_text())
                    self.assertTrue(unknown['no_retry']);self.assertTrue(unknown['no_implicit_rollback'])
                    self.assertEqual((out/'remote.stdout').read_bytes(),b'UNCERTAIN_PUBLICATION\n' if failure=='dispatch-timeout' else b'NOT_VALID_JSON')
if __name__=='__main__':unittest.main()
