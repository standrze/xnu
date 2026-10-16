# SPDX-License-Identifier: BSD-2-Clause
"""Late state proof and real recorder bodies under explicit UART/SSH doubles."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import root42_ready_trial_core as core
from tools.rpi5 import serial_root42_ready_trial as recorder
from tools.rpi5 import root42_ready_evidence as evidence
from tools.rpi5 import arm_root42_ready_reboot as launcher
from tools.rpi5 import stage_root42_ready_trial as stage
from tools.rpi5.tests import test_root42_pthread_transport as old
from tools.rpi5.tests import test_root42_pthread_trial as fixture

recorder=evidence.recorder
stage=recorder.staging
core=recorder.core
ROOT,BOOT,DEVICE=old.ROOT,old.BOOT,old.DEVICE


def pins():
    names=('root42_ready_trial_core.py','stage_root42_ready_trial.py','serial_root42_ready_trial.py',
        'root42_ready_command_evidence.py','root42_ready_evidence.py','arm_root42_ready_reboot.py','tests/test_root42_ready_transport.py')
    return stage.base.source_pins()|{str(ROOT/'tools/rpi5'/n):stage.sha(ROOT/'tools/rpi5'/n) for n in names}


class ReadyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.PthreadTrialTests.setUpClass();cls.receipt=fixture.PthreadTrialTests.receipt;cls.files=fixture.PthreadTrialTests.files

    def context(self):
        context=old.TransportTests.context(self);report=context['installed']['preflight']
        report.update(trial_marker='RPI5XNU:BL33:ROOT42_READY_TRIAL TAG='+'a'*32+' CPUS=4 ROOT_NODES=42 WATCHDOG_READY_V2',
            watchdog_ready_profile=core.WATCHDOG_PROFILE,
            root_ready_marker=report['root_mount_marker'].replace('RPI5XNU:RAMROOT:MOUNT','RPI5XNU:TERMINAL:ROOT_READY SECONDS=180'),
            root_ready_max_reports=3,root_ready_requires_mounted_readonly=True,root_ready_requires_successful_reload=True)
        context['evidence']=pins();return context

    def boot(self,report,late=True):
        raw=fixture.fixture.boot(report).replace(report['root_mount_marker'].encode(),b'garbled early root printf')
        if late:raw=raw.replace(core.prior.WATCHDOG+b'\n',core.prior.WATCHDOG+b'\n'+report['root_ready_marker'].encode()+b'\n')
        return raw

    def test_requires_late_actual_state_and_rejects_old_physical_capture(self):
        report=self.context()['installed']['preflight'];raw=self.boot(report)
        self.assertTrue(core.boot_ready(raw,report));self.assertFalse(core.boot_ready(self.boot(report,False),report))
        actual=(ROOT/'build/rpi5/root42-pthread-serial-20261013/serial.bin').read_bytes()
        self.assertEqual(len(actual),39436)
        self.assertEqual(stage.sha(ROOT/'build/rpi5/root42-pthread-serial-20261013/serial.bin'),
            'cdd6cd59d5f43ba969ce52fddaa44bc8e6615966e05302ae5aee93372d51af66')
        try:self.assertFalse(core.boot_ready(actual,report))
        except RuntimeError:pass
        for key,value in (('root_ready_max_reports',True),('root_ready_requires_mounted_readonly',False),
            ('root_ready_requires_successful_reload',False),('root_ready_marker',report['root_ready_marker'].replace('NODES=42','NODES=41'))):
            bad=copy.deepcopy(report);bad[key]=value
            with self.assertRaises(ValueError):core.boot_ready(raw,bad)
        wrong=copy.deepcopy(report);wrong['watchdog_ready_profile']=core.prior.WATCHDOG_PROFILE
        with self.assertRaises(RuntimeError):core.boot_ready(raw,wrong)

    def test_bounded_repeats_contradictions_and_order(self):
        report=self.context()['installed']['preflight'];row=report['root_ready_marker'].encode();raw=self.boot(report)
        self.assertTrue(core.boot_ready(raw+b'\n'+row+b'\n'+row+b'\n',report))
        with self.assertRaises(ValueError):core.boot_ready(raw+b'\n'+(row+b'\n')*3,report)
        for before,after in ((b'NODES=42',b'NODES=41'),(b'SECONDS=180',b'SECONDS=179'),(b'BYTES=2506752',b'BYTES=2506753')):
            wrong=row.replace(before,after)
            self.assertNotEqual(wrong,row)
            with self.assertRaises(ValueError):core.boot_ready(raw+b'\n'+wrong+b'\n',report)
        with self.assertRaises(RuntimeError):core.boot_ready(row+b'\n'+raw,report)
        partial=self.boot(report,False)+b'\n'+row[:30]
        self.assertFalse(core.boot_ready(partial,report))
        self.assertTrue(core.boot_ready(partial+b' interleaved\n'+row+b'\n'+core.t.READY+b'\nxnu:/# ',report))
        # Prompt/READY from before the state snapshot cannot authorize input.
        self.assertFalse(core.boot_ready(self.boot(report,False)+b'\n'+row+b'\n',report))

    def test_consistent_periodic_snapshot_inside_outputs_is_not_data(self):
        report=self.context()['installed']['preflight'];bound=core.bind(report);row=report['root_ready_marker'].encode()
        original=fixture.batch(self.files);changed=original.replace(core.prior.PTHREAD_LINES[0],row+b'\n'+core.prior.PTHREAD_LINES[0])
        self.assertEqual(bound.inspect_batch(original,fixture.NONCE,self.files),bound.inspect_batch(changed,fixture.NONCE,self.files))
        bound.pending_safe(b'\n'+row+b'\n'+core.t.READY+b'\nxnu:/# ')
        with self.assertRaises(ValueError):bound.pending_safe(b'\n'+row.replace(b'NODES=42',b'NODES=7')+b'\n')
        for fault in (b'panic(cpu 0)',b'Debugger message: panic'):
            with self.assertRaises(ValueError):bound.returned(fault)

    @contextlib.contextmanager
    def runtime(self,missing=False,panic=False):
        context=self.context();report=context['installed']['preflight'];clock=[0.0];queue=[self.boot(report,not missing)]
        sent=bytearray();commands=[];row=report['root_ready_marker'].encode();module=core.prior.prior
        tail=b'\nRPi: BOOTSYS release VERSION: fixture\nBOOT_ORDER override: 0x000000f6\nRPi: BOOTLOADER release VERSION: fixture\nBoot mode: NVME (06)\n'
        if panic:tail=b'\npanic(cpu 0): assertion\n'+tail
        with old.fresh() as out,tempfile.TemporaryFile() as uart,patch.object(stage,'source_pins',side_effect=pins),\
            patch.object(recorder,'package_pins',return_value={}):
            fn=recorder.bindings(context);g=fn.__globals__;real_open=os.open
            def open_(path,*a,**kw):return os.dup(uart.fileno()) if path==DEVICE else real_open(path,*a,**kw)
            def receive(fd,output,deadline):
                if queue:raw=queue.pop(0);clock[0]+=0.1
                else:clock[0]=181;raw=tail
                output.write(raw);return raw
            def select_(r,w,e,timeout):
                if queue:return r,[],[]
                if w:return [],w,[]
                clock[0]+=max(timeout,0.01);return [],[],[]
            def write_(fd,data):
                sent.extend(data)
                if data==b'\n':
                    command=sent.decode().strip();sent.clear();commands.append(command)
                    if command==core.IDENTITY:raw=fixture.identity_bytes(self.receipt)+b'\n'+row+b'\nxnu:/# '
                    elif command==core.batch_command(fixture.NONCE):raw=fixture.batch(self.files).replace(core.prior.PTHREAD_LINES[0],row+b'\n'+core.prior.PTHREAD_LINES[0])
                    else:raw=b'\nB42:'+fixture.NONCE.encode()+b':RECOVERY_STATUS:0\nxnu:/# '
                    queue.append(raw)
                return len(data)
            stdout=io.StringIO()
            with patch.object(g['lease'],'hold',return_value=contextlib.nullcontext()),\
                patch.object(g['subprocess'],'run',return_value=subprocess.CompletedProcess([],1,'','')),\
                patch.object(g['os'],'open',side_effect=open_),patch.object(g['os'],'write',side_effect=write_),\
                patch.object(g['fcntl'],'ioctl'),patch.object(g['termios'],'tcgetattr',side_effect=lambda _:[0,0,0,0,0,0,[0]*32]),\
                patch.object(g['termios'],'tcsetattr'),patch.object(g['termios'],'tcflush'),\
                patch.object(module.time,'monotonic',side_effect=lambda:clock[0]),patch.object(module.time,'sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)),\
                patch.object(module.select,'select',side_effect=select_),patch.object(core.t.shell,'receive',side_effect=receive),\
                patch.object(core.t,'utc_now',side_effect=lambda:'2026-10-13T18:00:00+00:00' if clock[0]==0 else '2026-10-13T18:03:01+00:00'),\
                patch.object(core.prior.secrets,'token_hex',return_value=fixture.NONCE[1:]),contextlib.redirect_stdout(stdout):
                code=fn([DEVICE,str(out),'--installation',context['installed']['directory'],'--package',str(Path(report['image']).parent),'--boot-wait-seconds','600'])
            self.assertIn(recorder.armed_line(report),stdout.getvalue())
            yield context,out,code,commands

    def test_actual_per_byte_recorder_three_exchanges_replay_and_return(self):
        with self.runtime() as (context,out,code,commands):
            state=json.loads((out/'state.json').read_text());self.assertEqual(code,0,state.get('error'))
            self.assertEqual(len(commands),3)
            _,observed,_=evidence.captured(context,out)
            self.assertTrue(observed['capture_valid'],observed['capture_error'])
            self.assertEqual(len(core.snapshots((out/'serial.bin').read_bytes(),context['installed']['preflight'])),3)
            expected=context['plan']['media']['identity_binding']['expected']
            witness=dict(host=stage.HOST,boot_id=old.NEWBOOT,identity=dict(identity=expected,boot_id=old.NEWBOOT,hostname='kamidana'),
                root=expected['root'].split(),bootloader={'boot-mode':6,'partition':1,'tryboot':0},read_only=True,
                sd_partitions_unmounted=True,observed_utc='2026-10-13T18:04:00+00:00',installation=context['installed'],
                serial_sha256=state['serial_sha256'],return_source_sha256=evidence.source_pins(context))
            with patch.object(evidence.collect_return.__globals__['subprocess'],'run',return_value=subprocess.CompletedProcess([],0,json.dumps(witness),'')):
                result=evidence.collect_return(context,out)
            self.assertTrue(result['capture_valid']);self.assertEqual(evidence.load_return(context,out)[0],result)

    def test_missing_late_state_keeps_zero_tx_and_failed_return_classification(self):
        with self.runtime(True) as (context,out,code,commands):
            self.assertEqual(code,1);self.assertEqual(commands,[])
            state,observed,_=evidence.captured(context,out)
            self.assertEqual(state['transmitted_bytes'],0);self.assertFalse(observed['capture_valid'])

    def test_fragmented_pending_late_snapshot_and_post_command_panic(self):
        report=self.context()['installed']['preflight'];bound=core.bind(report);row=report['root_ready_marker'].encode()
        chunks=iter([b'\n'+row[:20],row[20:]+b'\n']);clock=[0.0];output=io.BytesIO();module=core.prior.previous
        def ready(*args):
            clock[0]+=0.05
            return ([7],[],[]) if clock[0]<0.15 else ([],[],[])
        def receive(fd,out,deadline):value=next(chunks);out.write(value);return value
        with patch.object(module.select,'select',side_effect=ready),patch.object(module.time,'monotonic',side_effect=lambda:clock[0]),\
            patch.object(core.t.shell,'receive',side_effect=receive):
            self.assertEqual(bound.drain_pending(7,output,1),b'\n'+row+b'\n')
        with self.runtime(panic=True) as (context,out,code,commands):
            self.assertEqual(code,1);self.assertEqual(len(commands),3)
            state,observed,_=evidence.captured(context,out)
            self.assertTrue(state['command_tests_passed']);self.assertFalse(observed['capture_valid'])
            self.assertIn('runtime fault',observed['capture_error'])

    def test_exact_successor_controller_and_recorder_main_namespace(self):
        self.assertEqual(stage.sha(stage.PACKAGE/'manifest.json'),stage.MANIFEST_SHA)
        self.assertEqual(stage.sha(stage.PACKAGE/'probe.bin'),stage.IMAGE_SHA)
        self.assertIs(stage.prior.baseline,stage.base.prior.baseline)
        self.assertEqual(stage.prepare_install.__defaults__,(stage.PACKAGE,))
        self.assertIn(str(ROOT/'tools/rpi5/tests/test_root42_confirmation_service.py'),stage.source_pins())
        context=self.context();seen=[]
        def bind(got):
            self.assertIs(got,context)
            return lambda argv:seen.append(argv) or 0
        with patch.object(stage,'load_installation',return_value=context),\
            patch.dict(recorder.main.__globals__,bindings=bind):
            self.assertEqual(recorder.main([DEVICE,'fixture','--installation','fixture',
                '--seal-sha256','1'*64,'--plan-sha256','2'*64]),0)
        self.assertEqual(seen[0][-2:],['--boot-wait-seconds','600'])
        with patch.object(stage,'source_pins',side_effect=pins),patch.object(recorder,'package_pins',return_value={}):
            bound=recorder.bindings(context)
            self.assertEqual(Path(bound.__globals__['__file__']).resolve(),ROOT/'tools/rpi5/serial_root42_ready_trial.py')

    def test_actual_one_shot_launcher_uses_new_recorder_and_live_armed_schema(self):
        context=self.context();arm=__import__('arm_pcie_trace_reboot');calls=[]
        bound_launcher=launcher.launch;g=bound_launcher.__globals__;rec=g['recorder']
        with old.fresh() as capture,old.fresh() as output,\
            patch.object(stage,'source_pins',side_effect=pins),patch.object(rec,'package_pins',return_value={}):
            def child(command,stdout,stderr,**kwargs):
                self.assertEqual(command[1],str(ROOT/'tools/rpi5/serial_root42_ready_trial.py'))
                self.assertIn('--seal-sha256',command)
                capture.mkdir();sources=rec.bound_sources(context)
                state=dict(pid=123,device=DEVICE,baud=115200,installation=context['installed'],preflight=context['installed']['preflight'],
                    status='failed',checks=[],exchanges=[],transmitted_bytes=0,source_sha256=sources,
                    receipt_evidence_sha256=context['evidence'],package_evidence_sha256={},
                    command_tests_passed=False,normal_nvme_boot_observed=False,independent_linux_return_verified=False,
                    ssh_daemon=False,networking=False,controller_initialized=False,durability=False)
                stage.save(capture/'armed.json',state)
                stdout.write((rec.armed_line(context['installed']['preflight'])+'\n').encode())
                return types.SimpleNamespace(pid=123,poll=lambda:None)
            def ssh(command,**kwargs):
                calls.append(command);self.assertTrue((output/'reboot-intent.json').exists())
                self.assertTrue((output/'reboot-source.py').exists());self.assertIn(BOOT,kwargs['input'])
                return subprocess.CompletedProcess(command,255,'VERIFIED_SSD_LINUX_REBOOT_ONCE {}\n','disconnect')
            actual=lambda *args:arm.arm_once(*args,popen=child)
            with patch.dict(g,arm_once=actual),patch.object(g['subprocess'],'run',side_effect=ssh):
                with self.assertRaisesRegex(ValueError,'staged Linux boot'):bound_launcher(context,DEVICE,capture,output,'wrong')
                result=bound_launcher(context,DEVICE,capture,output,BOOT)
                self.assertTrue(result['result']['no_retry']);self.assertEqual(len(calls),1)
                with self.assertRaises(ValueError):bound_launcher(context,DEVICE,capture,output,BOOT)
                self.assertEqual(len(calls),1)


if __name__=='__main__':unittest.main()
