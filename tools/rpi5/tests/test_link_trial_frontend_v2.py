# SPDX-License-Identifier: BSD-2-Clause
"""Offline controller seams plus real regular-file publisher, never hardware.

The opt-in final test performs the actual prior128/package audit once. Synthetic
receipt/capture tests below prove controller contracts, not Pi acceptance.
"""
import contextlib
import copy
from datetime import datetime,timedelta,timezone
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
from tools.rpi5 import stage_link_trial_v2 as stage
from tools.rpi5 import serial_link_trial_v2 as recorder
from tools.rpi5 import link_trial_evidence_v2 as evidence
from tools.rpi5.tests import test_active_archive_pair_v2 as active
from tools.rpi5.tests import test_pcie_axi_trial as serial_fixtures

ROOT=stage.ROOT


@contextlib.contextmanager
def directory(fresh=False):
    with tempfile.TemporaryDirectory(prefix='link-v2-test-',dir=ROOT/'build/rpi5') as name:
        path=Path(name)
        if fresh:path.rmdir()
        yield path


class FrontendTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        stage.load_descriptor('axi-offline')
        with active.ActivePairTests.fixture(self) as row,directory() as saved:
            payload=copy.deepcopy(row[9]['payload']);media=payload['media_plan']
            raw,report=serial_fixtures.SerialProtocolTests.fixture(self)
            payload['history_catalog'].extend(dict(path='/home/sandrzej/fixture-history/'+str(n),bytes=512,sha256='8'*64) for n in range(18))
            media.update(descriptor='axi-offline',preflight=report,source_sha256=stage.source_pins(),
                nvme_backups=payload['history_catalog'],candidates={r['target']:str(row[7]/r['candidate']) for r in media['files']})
            calls=[]
            def audit():calls.append(1);return payload
            checkpoint,pin=stage.seals.create(audit,stage.source_pins()|stage.loaded_sources())
            plan,plan_sha=stage.engine.plan_from_seal(checkpoint,pin,stage.engine.TRIAL,'25'*16,str(row[7]),media)
            result=stage.engine.execute(plan,plan_sha,row[2],active.prior.prior.watch.helper,row[3],
                active.prior.prior.watch.reference,active.prior.prior.watch.core,row[4])
            for name,value in (('checkpoint.json',checkpoint),('plan.json',plan),('result.json',result)):stage.save(saved/name,value)
            context=stage.load_installation(saved,pin,plan_sha)
            yield context,saved,pin,plan_sha,raw,calls

    def capture(self,context,directory,raw):
        now=datetime(2026,10,13,18,0,tzinfo=timezone.utc);rows=[];offset=0
        for i,line in enumerate(raw.splitlines(keepends=True)):
            rows.append(dict(offset=offset,bytes=len(line),monotonic=10+i,utc=(now+timedelta(seconds=i+1)).isoformat()));offset+=len(line)
        sources=recorder.bound_sources(context)
        armed=dict(status='failed',started_utc=now.isoformat(),armed_utc=now.isoformat(),armed_monotonic=9,
            pid=1234,device='/dev/cu.usbmodemTEST',baud=115200,transmitted_bytes=0,installation=context['installed'],
            source_sha256=sources,receipt_evidence_sha256=context['evidence'],continuous_capture=False,
            physical_reset_return_proven=False,xnu_pe_runtime_proven=False,ethernet_proven=False)
        state=copy.deepcopy(armed);state.update(status='captured',continuous_capture=True,bytes=len(raw),
            serial_sha256=hashlib.sha256(raw).hexdigest(),ended_utc=(now+timedelta(seconds=len(rows)+1)).isoformat(),
            diagnostic=context['descriptor']['protocol'].inspect(raw,context['installed']['preflight']),
            inventory=context['descriptor']['protocol'].inventory(raw))
        for name,value in (('armed.json',armed),('state.json',state)):stage.save(directory/name,value)
        stage.save_bytes(directory/'serial.bin',raw)
        stage.save_bytes(directory/'receive-events.jsonl',b''.join(stage.seals.canonical(r)+b'\n' for r in rows))
        return state

    def returned(self,context,state):
        boot='e6324624-2b59-4933-a617-b841f6fb4e59';media=context['plan']['media']
        return dict(host=stage.HOST,boot_id=boot,identity=dict(identity=media['identity_binding']['expected'],boot_id=boot,hostname='kamidana'),
            root=media['identity_binding']['expected']['root'].split(),bootloader={'boot-mode':6,'partition':1,'tryboot':0},
            read_only=True,sd_partitions_unmounted=True,observed_utc='2026-10-13T18:05:00+00:00',
            installation=context['installed'],serial_sha256=state['serial_sha256'],return_source_sha256=evidence.return_source_pins())

    def test_typed128_to133_sealed_install_and_byte_only_load(self):
        with self.fixture() as (context,saved,pin,plan_sha,raw,calls):
            self.assertEqual(len(context['result']['next_catalog']),133)
            self.assertFalse(context['result']['historical_archives_reverified'])
            with patch.object(stage,'full_install_audit',side_effect=AssertionError('No repeated full audit')):
                for _ in range(2):self.assertEqual(stage.load_installation(saved,pin,plan_sha)['installed'],context['installed'])
            self.assertEqual(calls,[1])
            with self.assertRaises(ValueError):stage.load_installation(saved,'0'*64,plan_sha)
            with self.assertRaises(ValueError):stage.load_installation(saved,pin,'0'*64)
            bad=copy.deepcopy(context['result']);bad['historical_archives_reverified']=True
            with self.assertRaises(ValueError):stage.engine.validate_result(bad,context['plan'],plan_sha)

    def test_offline_descriptor_cannot_dispatch_launch_or_open_uart(self):
        with self.fixture() as (context,saved,pin,plan_sha,raw,calls),directory(True) as out:
            with patch.object(stage.subprocess,'run',side_effect=AssertionError('No SSH or UART')):
                with self.assertRaisesRegex(ValueError,'Offline descriptor'):
                    stage.dispatch(context['checkpoint'],pin,out,{'full_audit_calls':1},True)
                with self.assertRaisesRegex(ValueError,'Offline descriptor'):
                    stage.launch(saved,pin,plan_sha,'/dev/cu.usbmodemTEST',out,out,'unused')
                with self.assertRaisesRegex(ValueError,'Offline descriptor'):
                    recorder.main(['/dev/cu.usbmodemTEST',str(out),'--installation',str(saved),'--seal-sha256',pin,'--plan-sha256',plan_sha])
            self.assertFalse(out.exists())

    def test_protocol_source_must_be_presealed_and_cannot_refresh_digest(self):
        with tempfile.TemporaryDirectory() as name:
            path=(Path(name)/'protocol.py').resolve();path.write_text('original')
            context=dict(descriptor={'protocol':types.SimpleNamespace(__file__=str(path))},
                evidence=stage.source_pins()|{str(path):stage.sha(path),str(Path(recorder.__file__).resolve()):stage.sha(recorder.__file__)})
            recorder.revalidate(context);path.write_text('changed')
            with self.assertRaisesRegex(ValueError,'evidence bytes'):recorder.revalidate(context)
            with self.assertRaisesRegex(ValueError,'absent from seal or changed'):recorder.bound_sources(context)
            context['evidence'].pop(str(path))
            with self.assertRaisesRegex(ValueError,'absent from seal or changed'):recorder.bound_sources(context)

    def test_private_recorder_uses_sealed_callbacks_not_old_ancestry(self):
        with self.fixture() as (context,saved,pin,plan_sha,raw,calls):
            fn=recorder.bindings(context);g=fn.__globals__
            with patch.object(stage.prior,'validate_result',side_effect=AssertionError('No history')):
                self.assertEqual(g['installation'](saved),context['installed'])
                self.assertEqual(g['receipt_guard'].receipt_evidence_pins(saved),context['evidence'])
            current=g['staging'].source_pins()|{str(Path(g['__file__']).resolve()):stage.sha(g['__file__']),
                str(Path(g['protocol'].__file__).resolve()):stage.sha(g['protocol'].__file__),
                str(Path(g['receipt_guard'].__file__).resolve()):stage.sha(g['receipt_guard'].__file__)}
            self.assertEqual(current,recorder.bound_sources(context));self.assertEqual(calls,[1])

    def test_actual_private_recorder_loop_arms_and_records_with_serial_doubles(self):
        with self.fixture() as (context,saved,pin,plan_sha,raw,calls),directory(True) as out,tempfile.TemporaryFile() as fake_uart:
            fn=recorder.bindings(context);g=fn.__globals__;real_open=os.open;chunks=iter(raw.splitlines(keepends=True))
            ticks=iter(range(1000));captured=io.StringIO();opened=[]
            def open_(path,*args,**kw):
                if path=='/dev/cu.usbmodemTEST':
                    fd=os.dup(fake_uart.fileno());opened.append(fd);return fd
                return real_open(path,*args,**kw)
            with patch.object(g['lease'],'hold',return_value=contextlib.nullcontext()),\
                 patch.object(g['subprocess'],'run',return_value=subprocess.CompletedProcess([],1,'','')),\
                 patch.object(g['os'],'open',side_effect=open_),patch.object(g['os'],'read',side_effect=lambda *_:next(chunks)),\
                 patch.object(g['fcntl'],'ioctl'),patch.object(g['termios'],'tcgetattr',side_effect=lambda _:[0,0,0,0,0,0,[0]*32]),\
                 patch.object(g['termios'],'tcsetattr'),patch.object(g['termios'],'tcflush'),\
                 patch.object(g['select'],'select',side_effect=lambda fd,*a:(fd,[],[])),\
                 patch.object(g['time'],'monotonic',side_effect=lambda:next(ticks)),contextlib.redirect_stdout(captured):
                self.assertEqual(fn(['/dev/cu.usbmodemTEST',str(out),'--installation',str(saved),'--seconds','600']),0)
            self.assertEqual(len(opened),1);self.assertIn('RP1_TRACE_CAPTURE_ARMED ZERO_SERIAL_TX',captured.getvalue())
            state,observed,_=evidence.captured(context,out)
            self.assertEqual(state['transmitted_bytes'],0);self.assertTrue(observed['trace_capture_valid']);self.assertEqual(calls,[1])

    def test_install_cli_holds_board_lease_before_prepare_and_dispatch(self):
        order=[]
        @contextlib.contextmanager
        def held(*args):
            order.append('lease');yield;order.append('release')
        def prepare(*a):order.append('audit');return {},'1'*64,{}
        def dispatch(*a):order.append('dispatch');return {'offline_only':True}
        with patch.object(stage.lease,'hold',side_effect=held),patch.object(stage,'prepare_install',side_effect=prepare),\
             patch.object(stage,'dispatch',side_effect=dispatch),contextlib.redirect_stdout(io.StringIO()):
            stage.main(['install','--baseline','unused','--package','unused','--linux-boot-id','unused','--output','unused'])
        self.assertEqual(order,['lease','audit','dispatch','release'])

    def test_dispatch_unknown_is_durable_for_timeout_nonzero_bad_json_and_persistence(self):
        with self.fixture() as (context,saved,pin,plan_sha,raw,calls):
            real_get=stage.descriptors.get
            for fault in ('timeout','nonzero','json','validation','result_save','completion_save'):
                with self.subTest(fault=fault),directory(True) as out:
                    dispatched=[];real_save=stage.save
                    def run(cmd,**kw):
                        if cmd[0]=='scp':return subprocess.CompletedProcess(cmd,0)
                        if cmd[-1]=='python3 -':return subprocess.CompletedProcess(cmd,0,json.dumps({'run':'/home/sandrzej/xnu-link-v2-testabcd'}),'')
                        dispatched.append(cmd)
                        self.assertTrue((out/'dispatch-intent.json').is_file());self.assertTrue((out/'remote-program.py').is_file())
                        if fault=='timeout':raise subprocess.TimeoutExpired(cmd,300,output=b'partial',stderr=b'unknown')
                        return subprocess.CompletedProcess(cmd,7 if fault=='nonzero' else 0,'not-json' if fault=='json' else '{}','retained')
                    def save(path,value):
                        if Path(path).name=={'result_save':'result.json','completion_save':'completion.json'}.get(fault):raise OSError('injected local persistence failure')
                        return real_save(path,value)
                    def get(kind):return real_get(kind)|{'hardware_allowed':True}
                    with patch.object(stage.descriptors,'get',side_effect=get),patch.object(stage.subprocess,'run',side_effect=run),\
                         patch.object(stage,'save',side_effect=save),patch.object(stage.engine,'validate_result',
                            side_effect=ValueError('injected receipt') if fault=='validation' else None):
                        with self.assertRaises((ValueError,OSError,subprocess.SubprocessError)):
                            stage.dispatch(context['checkpoint'],pin,out,{'full_audit_calls':1},True)
                        with self.assertRaises(FileExistsError):stage.dispatch(context['checkpoint'],pin,out,{'full_audit_calls':1},True)
                    unknown=json.loads((out/'outcome-unknown.json').read_text())
                    self.assertTrue(unknown['no_retry']);self.assertTrue(unknown['no_implicit_rollback']);self.assertEqual(len(dispatched),1)
                    intent=json.loads((out/'dispatch-intent.json').read_text())
                    self.assertEqual(intent['remote_source_sha256'],stage.sha(out/'remote-program.py'))
                    self.assertTrue((out/'remote.stdout').is_file());self.assertTrue((out/'remote.stderr').is_file())

    def test_capture_independent_return_restore133_to138_no_old_audit(self):
        with self.fixture() as (context,saved,pin,plan_sha,raw,calls),directory() as captured:
            # A valid OK=0 trace is still a diagnostic failure, never ID success.
            raw=raw.replace(b'OK=1 PHASE=5 LAST=5 LIFE=3',b'OK=0 PHASE=6 LAST=12 LIFE=1').replace(b'ID=00011de4',b'ID=00000000')
            state=self.capture(context,captured,raw);observation=self.returned(context,state)
            with patch.object(evidence.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(observation),'')):
                returned=evidence.collect_return(context,captured)
            self.assertTrue(returned['capture_valid']);self.assertFalse(returned['diagnostic']['rp1_id_trial_pass'])
            with patch.object(stage,'full_install_audit',side_effect=AssertionError('No old audit')):
                checkpoint,restore_pin,metrics=stage.prepare_restore(saved,pin,plan_sha,captured)
            self.assertEqual(len(checkpoint['payload']['history_catalog']),133);self.assertEqual(metrics['package_compiler_audit_calls'],0)
            p,p_sha=stage.engine.plan_from_seal(checkpoint,restore_pin,stage.engine.RESTORE,'31'*16,
                '/home/sandrzej/xnu-link-v2-restore1',checkpoint['payload']['media_plan'])
            self.assertEqual(p['media']['linux_boot_id'],observation['boot_id'])
            self.assertEqual({r['target']:r['new_sha256'] for r in p['media']['files']},
                {n:v[1] for n,v in stage.GOOD.items()})
            self.assertEqual(calls,[1])
            # The publisher's already-tested +5 archive transition yields138.
            self.assertEqual(len(p['historical_catalog'])+5,138)
            bad=copy.deepcopy(returned);bad['remote_source_sha256']='0'*64
            (captured/'return.json').write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,'observation program'):evidence.load_return(context,captured)

    def test_failed_capture_can_get_independent_return_without_claiming_acceptance(self):
        with self.fixture() as (context,saved,pin,plan_sha,raw,calls),directory() as captured:
            state=self.capture(context,captured,raw);state.update(status='failed',continuous_capture=False,error='capture timeout')
            (captured/'state.json').write_text(json.dumps(state))
            value=evidence.captured(context,captured)[1]
            self.assertFalse(value['trace_capture_valid']);self.assertFalse(value['rp1_id_trial_pass'])
            for field,value in (('transmitted_bytes',True),('physical_reset_return_proven',True),('baud',9600)):
                bad=copy.deepcopy(state);bad[field]=value;(captured/'state.json').write_text(json.dumps(bad))
                with self.assertRaises(ValueError):evidence.captured(context,captured)

    def test_real128_receipt_and_final_package_once_audit(self):
        package=os.environ.get('RPI5_LINK_TEST_PACKAGE')
        if not package:self.skipTest('Select final package explicitly for one expensive audit')
        baseline=ROOT/'build/rpi5/rp1-axi-restored-20261013'
        boot=json.loads((baseline/'result.json').read_text())['identity']['boot_id']
        checkpoint,pin,metrics=stage.prepare_install(baseline,Path(package),boot)
        self.assertEqual(len(checkpoint['payload']['history_catalog']),128)
        self.assertEqual(metrics['full_audit_calls'],1)
        self.assertIn(str(ROOT/'tools/rpi5/pcie_link_elapsed_serial_core.py'),checkpoint['evidence_sha256'])
        self.assertIn(str(ROOT/'tools/rpi5/tests/test_pcie_link_elapsed_serial.py'),checkpoint['evidence_sha256'])
        with patch.object(stage,'full_install_audit',side_effect=AssertionError('Only once')):
            stage.seals.revalidate(checkpoint,pin)
        output=os.environ.get('RPI5_LINK_TEST_OUTPUT')
        if output:
            out=stage.local(output);out.mkdir(exist_ok=False)
            stage.seals.save_new(out/'checkpoint.json',checkpoint,pin)
            stage.save(out/'metrics.json',metrics)
            stage.save(out/'validation.json',dict(offline_only=True,hardware_executed=False,checkpoint_sha256=pin,metrics=metrics))


if __name__=='__main__':unittest.main()
