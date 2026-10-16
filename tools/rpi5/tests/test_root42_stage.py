# SPDX-License-Identifier: BSD-2-Clause
"""Single-loader controller seams and real file publication, never hardware."""
import contextlib
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import stage_root42_pthread_trial as stage
from tools.rpi5.tests import test_active_archive_loader_v2 as files


@contextlib.contextmanager
def directory(fresh=False):
    with tempfile.TemporaryDirectory(prefix='root42-stage-test-',dir=stage.ROOT/'build/rpi5') as name:
        path=Path(name).resolve()
        if fresh:path.rmdir()
        yield path


def pins():
    return stage.engine.source_pins()|{str(Path(stage.__file__).resolve()):stage.sha(stage.__file__),
        str(Path(__file__).resolve()):stage.sha(__file__)}


class ControllerTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        with files.LoaderTests.fixture(self) as row,directory() as saved:
            payload=copy.deepcopy(row[9]['payload']);media=payload['media_plan']
            media.update(controller=stage.CONTROLLER,package=str(stage.PACKAGE),preflight={'fixture':True},
                candidate=str(row[7]/'candidate.bin'),source_sha256=pins(),no_firmware_change=True)
            calls=[]
            def audit():calls.append(1);return payload
            with patch.object(stage,'source_pins',side_effect=pins),patch.object(stage,'transport'),\
                 patch.object(stage,'IMAGE_SHA',media['new_sha256']):
                checkpoint,pin=stage.seals.create(audit,pins())
                plan,plan_sha=stage.engine.plan_from_seal(checkpoint,pin,stage.engine.TRIAL,'25'*16,str(row[7]),media)
                result=files.LoaderTests.execute(self,(plan,plan_sha,*row[2:]))
                for n,v in (('checkpoint.json',checkpoint),('plan.json',plan),('result.json',result)):stage.save(saved/n,v)
                context=stage.load_installation(saved,pin,plan_sha)
                yield context,saved,pin,plan_sha,calls

    def test_typed_installed_context_rechecks_bytes_not_checker_or_history(self):
        with self.fixture() as (context,saved,pin,plan_sha,calls),\
             patch.object(stage.checker,'inspect',side_effect=AssertionError('No compiler replay')),\
             patch.object(stage.prior,'baseline',side_effect=AssertionError('No ancestry replay')):
            for _ in range(2):self.assertEqual(stage.load_installation(saved,pin,plan_sha)['installed'],context['installed'])
            self.assertEqual(calls,[1]);self.assertEqual(len(context['result']['next_catalog']),152)
            self.assertEqual(context['installed']['loader_sha256'],context['plan']['media']['new_sha256'])
            self.assertEqual(context['installed']['original_linux_boot_id'],context['plan']['media']['linux_boot_id'])
            with self.assertRaises(ValueError):stage.load_installation(saved,'0'*64,plan_sha)
            with self.assertRaises(ValueError):stage.load_installation(saved,pin,'0'*64)
            bad=copy.deepcopy(context['result']);bad['publication']['no_firmware_change']=1
            (saved/'result.json').write_text(json.dumps(bad))
            with self.assertRaises(ValueError):stage.load_installation(saved,pin,plan_sha)

    def test_dispatch_holds_lease_and_unknown_never_retries(self):
        with self.fixture() as (context,_,pin,_,calls):
            for fault in ('timeout','nonzero','json'):
                with self.subTest(fault=fault),directory(True) as out:
                    order=[];remote=[]
                    @contextlib.contextmanager
                    def held(*args):order.append('lease');yield;order.append('release')
                    def run(command,**kwargs):
                        self.assertEqual(order[0],'lease')
                        if command[0]=='scp':order.append('scp');self.assertTrue(command[-1].endswith('/candidate.bin'));return subprocess.CompletedProcess(command,0)
                        if command[-1]=='python3 -':return subprocess.CompletedProcess(command,0,json.dumps({'run':'/home/sandrzej/xnu-root42-v2-unknown1'}),'')
                        remote.append(command)
                        if fault=='timeout':raise subprocess.TimeoutExpired(command,300,output=b'partial',stderr=b'diagnostic')
                        return subprocess.CompletedProcess(command,1 if fault=='nonzero' else 0,'not json','remote error')
                    with patch.object(stage.lease,'hold',side_effect=held),patch.object(stage.subprocess,'run',side_effect=run):
                        with self.assertRaises((subprocess.TimeoutExpired,subprocess.CalledProcessError,json.JSONDecodeError)):
                            stage.dispatch(context['checkpoint'],pin,out,{'full_audit_calls':1},True)
                        with self.assertRaises(FileExistsError):stage.dispatch(context['checkpoint'],pin,out,{'full_audit_calls':1},True)
                    self.assertEqual(len(remote),1);self.assertEqual(order.count('scp'),1)
                    unknown=json.loads((out/'outcome-unknown.json').read_text());self.assertTrue(unknown['no_retry'])
                    self.assertTrue(unknown['no_implicit_rollback']);self.assertTrue((out/'remote.stdout').exists())
                    self.assertTrue((out/'dispatch-intent.json').exists());self.assertFalse((out/'result.json').exists())
            self.assertEqual(calls,[1])

    def test_busy_board_prevents_all_dispatch_actions(self):
        with self.fixture() as (context,_,pin,_,_),directory(True) as out,\
             patch.object(stage.lease,'hold',side_effect=ValueError('busy')),\
             patch.object(stage.subprocess,'run',side_effect=AssertionError('No SSH')):
            with self.assertRaisesRegex(ValueError,'busy'):stage.dispatch(context['checkpoint'],pin,out,{},True)
            self.assertFalse(out.exists())

    def test_missing_controller_closure_rejected_before_any_dispatch(self):
        with self.fixture() as (context,_,_,_,_),directory(True) as out,\
             patch.object(stage.subprocess,'run',side_effect=AssertionError('No SSH')):
            changed=copy.deepcopy(context['checkpoint']);del changed['evidence_sha256'][str(Path(stage.__file__).resolve())]
            with self.assertRaisesRegex(ValueError,'dispatch source closure'):
                stage.dispatch(changed,stage.seals.digest(changed),out,{'full_audit_calls':1},False)
            self.assertFalse(out.exists())

    def test_restore_requires_independent_return_and_preserves_failed_outcome(self):
        with self.fixture() as (context,saved,pin,plan_sha,_),directory() as capture:
            for name in ('armed.json','state.json','serial.bin','return.json'):stage.save(capture/name,{'fixture':True})
            boot='aee40aa0-9e66-49f7-b1c1-f5d7e3703572';receipt={'capture_valid':False,'failure':'target smoke failed'}
            evidence=types.SimpleNamespace(load_return=lambda *a:(receipt,boot))
            with patch.object(stage,'transport',return_value=evidence),patch.object(stage.checker,'inspect',side_effect=AssertionError('No package replay')):
                checkpoint,restore_pin,metrics=stage.prepare_restore(saved,pin,plan_sha,capture)
                media=checkpoint['payload']['media_plan']
                self.assertEqual(media['profile'],stage.engine.RESTORE)
                self.assertEqual(media['new_sha256'],stage.GOOD[1]);self.assertEqual(media['old_sha256'],context['installed']['loader_sha256'])
                self.assertEqual(media['linux_boot_id'],boot);self.assertTrue(media['no_firmware_change'])
                self.assertEqual(metrics['package_compiler_audit_calls'],0);self.assertEqual(metrics['prior_catalog_count'],152)
                self.assertEqual(stage.seals.revalidate(checkpoint,restore_pin)['history_catalog'],context['result']['next_catalog'])
                evidence.load_return=lambda *a:(_ for _ in ()).throw(ValueError('Independent Linux return absent'))
                with self.assertRaisesRegex(ValueError,'Independent Linux'):stage.prepare_restore(saved,pin,plan_sha,capture)

    def test_prepare_runs_new_checker_once_and_does_not_read_old_archive_payloads(self):
        with files.LoaderTests.fixture(self) as row,directory() as baseline,directory() as package:
            for name in ('checkpoint.json','plan.json','result.json'):stage.save(baseline/name,{'fixture':True})
            stage.save(package/'manifest.json',{'fixture':True});(package/'probe.bin').write_bytes(b'target fixture')
            report=dict(image=str(package/'probe.bin'),image_sha256=stage.sha(package/'probe.bin'),root_nodes=42,root_files=30)
            media=row[9]['payload']['media_plan'];boot=media['linux_boot_id']
            media['identity_binding']['linux_boot_id_before_write']='62a19cc4-2c15-49cd-a04a-6d0a54dff6a3'
            publication=dict(
                protected_files_sha256=media['protected_files'],protected_after={n:{'sha256':v} for n,v in media['protected_sha256'].items()},
                identity={'boot_id':boot})
            accepted=dict(directory=str(baseline),evidence=pins(),plan={'media':media},result={'publication':publication,
                'next_catalog':row[0]['historical_catalog']},checkpoint={'payload':{'baseline_paths':row[8]}})
            with patch.object(stage,'transport'),patch.object(stage,'source_pins',side_effect=pins),\
                 patch.object(stage,'PACKAGE',package),patch.object(stage,'MANIFEST_SHA',stage.sha(package/'manifest.json')),\
                 patch.object(stage,'IMAGE_SHA',report['image_sha256']),patch.object(stage.prior,'baseline',return_value=accepted),\
                 patch.object(stage.prior.base,'loaded_sources',return_value={}),patch.object(stage.checker,'inspect',return_value=report) as check:
                checkpoint,pin,metrics=stage.prepare_install(baseline,'1'*64,'2'*64,boot,package)
                for _ in range(3):stage.seals.revalidate(checkpoint,pin)
            self.assertEqual(check.call_count,1);self.assertEqual(metrics['full_audit_calls'],1)
            self.assertEqual(metrics['historical_semantic_audit_calls'],0);self.assertEqual(metrics['prior_catalog_count'],148)
            self.assertFalse(metrics['historical_archives_reverified'])
            self.assertEqual(checkpoint['payload']['media_plan']['new_sha256'],report['image_sha256'])

    def test_chain_replay_binds_exact_return_and_restore_without_promoting_failure(self):
        with self.fixture() as (context,saved,pin,plan_sha,_):
            boot='44b054d0-4543-49e5-b49e-4baf4877e774';checkpoint={'fixture':'exact restore'}
            returned={'capture_valid':False,'diagnostic':None,'capture_error':'pthread runtime failed'}
            restored={'checkpoint':checkpoint,'result':{'publication':{'identity':{'boot_id':boot}},
                'next_catalog':context['result']['next_catalog']+[{'fixture':i} for i in range(4)]}}
            with patch.object(stage,'transport',return_value=types.SimpleNamespace(load_return=lambda *a:(returned,boot))),\
                 patch.object(stage,'prepare_restore',return_value=(checkpoint,'3'*64,{})),\
                 patch.object(stage,'restoration',return_value=restored),\
                 patch.object(stage.checker,'inspect',side_effect=AssertionError('No compiler replay')):
                result=stage.replay(saved,pin,plan_sha,saved,saved,'3'*64,'4'*64)
                self.assertFalse(result['capture_valid']);self.assertIsNone(result['diagnostic'])
                self.assertEqual(result['historical_catalog_counts'],[148,152,156]);self.assertTrue(result['working_loader_restored'])
                self.assertEqual(result['compiler_calls'],0)
                with self.assertRaisesRegex(ValueError,'exact trial'):stage.replay(saved,pin,plan_sha,saved,saved,'5'*64,'4'*64)
                restored['result']['publication']['identity']['boot_id']='different'
                with self.assertRaisesRegex(ValueError,'exact trial'):stage.replay(saved,pin,plan_sha,saved,saved,'3'*64,'4'*64)
