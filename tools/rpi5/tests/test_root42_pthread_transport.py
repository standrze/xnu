# SPDX-License-Identifier: BSD-2-Clause
"""Actual private recorder/arm/replay bodies with serial/SSH doubles, not Pi proof."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import serial_root42_pthread_trial as recorder
from tools.rpi5 import root42_pthread_evidence as evidence
from tools.rpi5 import arm_root42_pthread_reboot as launcher
from tools.rpi5.tests import test_root42_pthread_trial as fixture

stage=recorder.staging
ROOT=stage.ROOT
BOOT='ee1f125a-112c-4da6-9f06-635451451e94'
NEWBOOT='11111111-1111-4111-8111-111111111111'
DEVICE='/dev/cu.usbmodemTEST'


@contextlib.contextmanager
def fresh():
    with tempfile.TemporaryDirectory(prefix='root42-transport-fixture-',dir=ROOT/'build/rpi5') as name:
        out=Path(name).resolve();out.rmdir();yield out


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.PthreadTrialTests.setUpClass()
        cls.receipt=fixture.PthreadTrialTests.receipt;cls.files=fixture.PthreadTrialTests.files

    def context(self):
        report=copy.deepcopy(fixture.PthreadTrialTests.report)
        report.update(image=str(stage.PACKAGE/'probe.bin'),image_sha256=stage.IMAGE_SHA,
            root_manifest=str(fixture.root.PACKAGE/'manifest.json'))
        installed=dict(directory=str(ROOT/'build/rpi5/offline-root42-install'),checkpoint_sha256='1'*64,
            plan_sha256='2'*64,result_sha256='3'*64,preflight=report,loader_sha256=stage.IMAGE_SHA,
            original_linux_boot_id=BOOT)
        identity=json.loads((ROOT/'build/rpi5/root-route-restored-20261013/plan.json').read_text())['media']['identity_binding']
        return dict(installed=installed,evidence=stage.source_pins()|stage.prior.base.loaded_sources(),
            plan={'media':{'host':stage.HOST,'linux_boot_id':BOOT,'identity_binding':identity}})

    @contextlib.contextmanager
    def run_recorder(self, fault=None):
        context=self.context();clock=[0.0];tx=[];core=recorder.core
        with fresh() as out,tempfile.TemporaryFile() as uart,patch.object(recorder,'package_pins',return_value={}):
            fn=recorder.bindings(context);g=fn.__globals__;real_open=os.open
            def open_(path,*args,**kwargs):
                return os.dup(uart.fileno()) if path==DEVICE else real_open(path,*args,**kwargs)
            def receive(fd,output,deadline):
                if clock[0]==0:
                    raw=fixture.fixture.boot(context['installed']['preflight']);clock[0]=1
                else:
                    raw=(b'panic(cpu 0 caller test): log_encode.c:120\n' if fault=='panic' else b'')
                    raw+=b'\nRPi: BOOTSYS release VERSION: test\nBOOT_ORDER override: 0x000000f6\nRPi: BOOTLOADER release VERSION: test\nBoot mode: NVME (06)\n'
                    clock[0]=181
                output.write(raw);return raw
            def exchange(fd,output,command,expected,state,deadline):
                tx.append(command);clock[0]+=1
                state['transmitted_bytes']+=len(command)+1
                if command==core.IDENTITY:raw=fixture.identity_bytes(self.receipt)+b'\nxnu:/# '
                elif command==core.batch_command(fixture.NONCE):raw=fixture.batch(self.files)
                elif fault=='missing_exit':raise TimeoutError('Actual final recovery status missing')
                else:raw=b'\n'+expected[0]+b'\nxnu:/# '
                output.write(raw);return raw
            output=io.StringIO()
            with patch.object(g['lease'],'hold',return_value=contextlib.nullcontext()),\
                patch.object(g['subprocess'],'run',return_value=subprocess.CompletedProcess([],1,'','')),\
                patch.object(g['os'],'open',side_effect=open_),patch.object(g['fcntl'],'ioctl'),\
                patch.object(g['termios'],'tcgetattr',side_effect=lambda _:[0,0,0,0,0,0,[0]*32]),\
                patch.object(g['termios'],'tcsetattr'),patch.object(g['termios'],'tcflush'),\
                patch.object(g['time'],'monotonic',side_effect=lambda:clock[0]),\
                patch.object(core.t,'utc_now',side_effect=lambda:'2026-10-13T18:00:00+00:00' if clock[0]==0 else '2026-10-13T18:03:01+00:00'),\
                patch.object(core.t.shell,'receive',side_effect=receive),\
                patch.object(core,'bounded_exchange',side_effect=exchange),patch.object(core,'drain_pending',return_value=b''),\
                patch.object(core.secrets,'token_hex',return_value=fixture.NONCE[1:]),contextlib.redirect_stdout(output):
                code=fn([DEVICE,str(out),'--installation',context['installed']['directory'],
                    '--package',str(stage.PACKAGE),'--boot-wait-seconds','600'])
            self.assertIn(recorder.armed_line(context['installed']['preflight']),output.getvalue())
            yield context,out,code,tx

    def witness(self,context,state):
        expected=context['plan']['media']['identity_binding']['expected']
        return dict(host=stage.HOST,boot_id=NEWBOOT,identity=dict(identity=expected,boot_id=NEWBOOT,hostname='kamidana'),
            root=expected['root'].split(),bootloader={'boot-mode':6,'partition':1,'tryboot':0},read_only=True,
            sd_partitions_unmounted=True,observed_utc='2026-10-13T18:04:00+00:00',installation=context['installed'],
            serial_sha256=state['serial_sha256'],return_source_sha256=evidence.source_pins(context))

    def test_actual_recorder_nine_results_exit_and_independent_return(self):
        with self.run_recorder() as (context,out,code,tx):
            self.assertEqual(code,0)
            state,observed,_=evidence.captured(context,out)
            self.assertTrue(observed['capture_valid']);self.assertEqual(len(tx),3)
            self.assertEqual(state['runtime_identity']['file_hashes'],30)
            batch=observed['diagnostic']['batch']
            self.assertEqual(len(batch['commands']),9);self.assertTrue(batch['batch_process_exit_verified'])
            self.assertTrue(batch['actual_pthread_startup_constructor_create_join_mutex_tsd_errno'])
            self.assertFalse(batch['networking']);self.assertFalse(batch['ssh_daemon'])
            returned=self.witness(context,state)
            with patch.object(evidence.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(returned),'')) as ssh:
                receipt=evidence.collect_return(context,out)
            self.assertEqual(ssh.call_count,1);self.assertTrue(receipt['capture_valid'])
            self.assertEqual(evidence.load_return(context,out),(receipt,NEWBOOT))
            for key,value in (('boot_id',BOOT),('root',['/dev/mmcblk0p2','ext4','wrong'])):
                bad=copy.deepcopy(returned);bad[key]=value
                with self.assertRaises(ValueError):evidence.inspect_return(bad,context,observed)
            altered=copy.deepcopy(state);altered['exchanges']=altered['exchanges'][:2]
            (out/'state.json').write_text(json.dumps(altered))
            self.assertFalse(evidence.captured(context,out)[1]['capture_valid'])

    def test_missing_final_status_cannot_be_upgraded_by_linux_recovery(self):
        with self.run_recorder('missing_exit') as (context,out,code,tx):
            self.assertEqual(code,1);self.assertEqual(len(tx),3)
            state,observed,_=evidence.captured(context,out)
            self.assertFalse(observed['capture_valid']);self.assertFalse(state['batch']['batch_process_exit_verified'])
            returned=self.witness(context,state)
            with patch.object(evidence.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(returned),'')):
                receipt=evidence.collect_return(context,out)
            self.assertFalse(receipt['capture_valid']);self.assertTrue(receipt['independent_normal_nvme_linux_return_verified'])

    def test_post_command_panic_is_failure_even_with_all_outputs_and_reboot(self):
        with self.run_recorder('panic') as (context,out,code,tx):
            self.assertEqual(code,1);self.assertEqual(len(tx),3)
            state,observed,_=evidence.captured(context,out)
            self.assertTrue(state['command_tests_passed']);self.assertFalse(observed['capture_valid'])
            self.assertIn('runtime fault',observed['capture_error'])
        for signature in (b'panic(cpu 0)',b'Debugger message: panic',b'panic: assertion'):
            with self.assertRaises(ValueError):recorder.clean_return(signature)

    def test_sealed_source_and_package_omission_mutation_fail_closed(self):
        context=self.context();path=str(Path(recorder.core.__file__).resolve())
        recorder.bound_sources(context)
        for value in (None,'0'*64):
            bad=copy.deepcopy(context)
            if value is None:bad['evidence'].pop(path)
            else:bad['evidence'][path]=value
            with self.assertRaises(ValueError):recorder.bound_sources(bad)
        with tempfile.TemporaryDirectory(prefix='root42-pins-',dir=ROOT/'build/rpi5') as name:
            folder=Path(name);data=folder/'input';data.write_bytes(b'fixture')
            manifest=folder/'manifest.json'
            record=dict(inputs_sha256={str(data):stage.sha(data)},headers_sha256={},generated_sha256={})
            manifest.write_text(json.dumps(record))
            context['installed']['preflight']['image']=str(folder/'probe.bin')
            context['evidence'].update({str(manifest):stage.sha(manifest),str(data):stage.sha(data)})
            self.assertIn(str(data),recorder.package_pins(context))
            context['evidence'].pop(str(data))
            with self.assertRaises(ValueError):recorder.package_pins(context)

    def test_actual_arm_once_binds_child_and_attempts_at_most_one_reboot(self):
        context=self.context();arm=__import__('arm_pcie_trace_reboot');calls=[]
        with fresh() as capture,fresh() as output,patch.object(launcher.recorder,'package_pins',return_value={}):
            # This launches no process: the original arm_once body receives a
            # synthetic child, and SSH below is an explicit test double.
            def child(command,stdout,stderr,**kwargs):
                self.assertEqual(command[1],str(ROOT/'tools/rpi5/serial_root42_pthread_trial.py'))
                capture.mkdir();pins=launcher.recorder.bound_sources(context)
                state=dict(pid=123,device=DEVICE,baud=115200,installation=context['installed'],preflight=context['installed']['preflight'],
                    status='failed',checks=[],exchanges=[],transmitted_bytes=0,source_sha256=pins,
                    receipt_evidence_sha256=context['evidence'],package_evidence_sha256={},
                    command_tests_passed=False,normal_nvme_boot_observed=False,independent_linux_return_verified=False,
                    ssh_daemon=False,networking=False,controller_initialized=False,durability=False)
                stage.save(capture/'armed.json',state)
                stdout.write((launcher.recorder.armed_line(context['installed']['preflight'])+'\n').encode())
                return types.SimpleNamespace(pid=123,poll=lambda:None)
            def ssh(command,**kwargs):
                calls.append(command);self.assertTrue((output/'reboot-intent.json').exists())
                self.assertTrue((output/'reboot-source.py').exists())
                self.assertIn(BOOT,kwargs['input']);return subprocess.CompletedProcess(command,255,'VERIFIED_SSD_LINUX_REBOOT_ONCE {}\n','disconnect')
            actual=lambda *args:arm.arm_once(*args,popen=child)
            with patch.object(launcher,'arm_once',side_effect=actual),patch.object(launcher.subprocess,'run',side_effect=ssh):
                with self.assertRaisesRegex(ValueError,'staged Linux boot'):launcher.launch(context,DEVICE,capture,output,'wrong')
                result=launcher.launch(context,DEVICE,capture,output,BOOT)
                self.assertTrue(result['result']['no_retry']);self.assertEqual(len(calls),1)
                with self.assertRaises(ValueError):launcher.launch(context,DEVICE,capture,output,BOOT)
                self.assertEqual(len(calls),1)

    def test_no_armed_child_never_reboots(self):
        arm=__import__('arm_pcie_trace_reboot')
        with fresh() as output:
            child=lambda *a,**k:types.SimpleNamespace(pid=123,poll=lambda:1)
            with self.assertRaisesRegex(ValueError,'before ARMED'):
                arm.arm_once(output,[], 'ROOT42_PTHREAD_CAPTURE_ARMED',lambda _:None,
                    lambda:self.fail('No reboot without ARMED'),popen=child)
            self.assertFalse((output/'reboot-intent.json').exists())

    def test_return_cli_acquires_board_lease_before_receipts_or_ssh(self):
        order=[]
        @contextlib.contextmanager
        def hold(*args):
            order.append('lease');yield;order.append('release')
        def load(*args):self.assertEqual(order,['lease']);order.append('load');return {}
        def collect(*args):self.assertEqual(order,['lease','load']);order.append('observe');return {'fixture':True}
        argv=['return','--installation','fixture','--seal-sha256','1'*64,'--plan-sha256','2'*64,'--capture','fixture']
        with patch.object(evidence.stage.lease,'hold',side_effect=hold),\
            patch.object(evidence.stage,'load_installation',side_effect=load),\
            patch.object(evidence,'collect_return',side_effect=collect),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(evidence.main(argv),0)
        self.assertEqual(order,['lease','load','observe','release'])


if __name__=='__main__':unittest.main()
