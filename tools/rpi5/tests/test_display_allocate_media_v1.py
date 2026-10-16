# SPDX-License-Identifier: BSD-2-Clause
"""Actual config+loader publisher and generated remote source, no devices."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import display_allocate_media_v1 as engine
from tools.rpi5 import trial_checkpoint_v2 as seal
from tools.rpi5.tests import test_watchdog_recovery_install as prior
ROOT=Path(__file__).resolve().parents[3]
GOOD=ROOT/'build/rpi5/bl33-probe-vszhh6o4/probe.bin'
FW=ROOT/'build/rpi5/tfa-candidate/build/rpi5/debug/bl31.bin'
TRIAL=ROOT/'build/rpi5/display-allocate-rlz04spl/probe.bin'
TAG='29'*16

class DisplayAllocateMediaTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self,restore=False):
        with prior.RecoveryInstallTests.fixture(self) as row:
            plan,capture,snapshots,run,state,boot,work,*_=row
            (work/'candidate.bin').unlink()
            (boot/'config.txt').write_bytes(engine.TRIAL_CONFIG if restore else engine.ORIGINAL_CONFIG)
            shutil.copyfile(TRIAL if restore else GOOD,boot/'probe.bin')
            shutil.copyfile(FW,boot/'bl31.bin');shutil.copyfile(GOOD,boot/engine.original.REUSED_ZSH_BACKUP)
            (work/'candidate-config.txt').write_bytes(engine.ORIGINAL_CONFIG if restore else engine.TRIAL_CONFIG)
            shutil.copyfile(GOOD if restore else TRIAL,work/'candidate-probe.bin')
            plan.update(profile=engine.RESTORE if restore else engine.TRIAL,files=[])
            for name in ('config.txt','probe.bin'):
                old,new=boot/name,work/('candidate-'+name)
                plan['files'].append(dict(target=name,candidate='candidate-'+name,old_sha256=seal.sha(old),
                    old_bytes=old.stat().st_size,new_sha256=seal.sha(new),new_bytes=new.stat().st_size))
            plan['protected_files']={'bl31.bin':engine.GOOD_FW_SHA,engine.original.REUSED_ZSH_BACKUP:engine.original.GOOD_ZSH_SHA}
            archives=work.parent/'baseline';archives.mkdir();shutil.copyfile(FW,archives/'firmware.bin');shutil.copyfile(GOOD,archives/'loader.bin')
            baseline={'bl31.bin':str(archives/'firmware.bin'),'probe.bin':str(archives/'loader.bin')}
            history=[dict(path=str(work.parent/'nonexistent-old-archive'),bytes=536870912,sha256='9'*64)]
            history.extend(dict(path=p,bytes=Path(p).stat().st_size,sha256=seal.sha(p)) for p in baseline.values())
            plan['nvme_backups']=history;media=copy.deepcopy(plan);media.pop('run')
            active=engine.select_baseline(history,baseline)
            def verify(p):
                self.assertEqual(p['nvme_backups'],active);state['verifies']+=1
                for r in active:self.assertEqual(seal.sha(r['path']),r['sha256'])
            capture.verify_backups=verify
            checkpoint,pin=seal.create(lambda:dict(media_plan=media,history_catalog=history,baseline_paths=baseline),engine.source_pins())
            outer,outer_sha=engine.plan_from_seal(checkpoint,pin,media['profile'],TAG,str(work),media)
            yield outer,outer_sha,capture,snapshots,run,state,boot,work,checkpoint,pin
    def execute(self,row):return engine.execute(row[0],row[1],row[2],prior.helper,row[3],prior.reference,prior.core,row[4])
    def test_both_exact_transitions_archive_and_original_firmware_preserved(self):
        for restore in (False,True):
            with self.subTest(restore=restore),self.fixture(restore) as row:
                before=seal.sha(row[6]/'bl31.bin');result=self.execute(row)
                self.assertEqual(result['publication']['pair_publication_order'],['config.txt','probe.bin'])
                self.assertTrue(result['publication']['config_changed']);self.assertFalse(result['publication']['firmware_changed'])
                self.assertEqual(seal.sha(row[6]/'bl31.bin'),before);self.assertFalse(row[5]['mounted'])
                self.assertEqual(row[5]['verifies'],2);self.assertEqual(result['created_archive_count'],5)
                for r in row[0]['media']['files']:self.assertEqual(seal.sha(row[6]/r['target']),r['new_sha256'])
                self.assertTrue((row[7]/'pair-before-config.txt.json').exists())
                self.assertTrue((row[7]/'pair-after-probe.bin.json').exists())
                engine.validate_result(result,row[0],row[1])
    def test_every_copy_failure_is_before_both_renames_and_retained(self):
        real=prior.helper.copy_image
        for failure in range(1,6):
            with self.subTest(failure=failure),self.fixture() as row:
                old={n:(row[6]/n).read_bytes() for n in ('config.txt','probe.bin')};calls=[]
                def fault(*a,**kw):
                    calls.append(a[2]);real(*a,**kw)
                    if len(calls)==failure:raise ValueError('copy failure')
                with patch.object(prior.helper,'copy_image',side_effect=fault),patch.object(os,'rename',wraps=os.rename) as rename:
                    with self.assertRaisesRegex(ValueError,'copy failure'):self.execute(row)
                    rename.assert_not_called()
                self.assertEqual(old,{n:(row[6]/n).read_bytes() for n in old});self.assertFalse(row[5]['mounted'])
                with self.assertRaises(ValueError):self.execute(row)
    def test_each_partial_commit_preserved_no_implicit_restore_or_retry(self):
        real=os.rename
        for at in (1,2):
            with self.subTest(at=at),self.fixture() as row:
                calls=[]
                def fault(*a,**kw):
                    calls.append(a[1]);real(*a,**kw)
                    if len(calls)==at:raise ValueError('post rename failure')
                with patch.object(os,'rename',side_effect=fault):
                    with self.assertRaisesRegex(ValueError,'post rename failure'):self.execute(row)
                self.assertEqual(len(calls),at);self.assertEqual((row[6]/'config.txt').read_bytes(),engine.TRIAL_CONFIG)
                self.assertEqual(seal.sha(row[6]/'probe.bin'),engine.original.GOOD_ZSH_SHA if at==1 else engine.IMAGE_SHA)
                self.assertFalse((row[7]/'result.json').exists());self.assertFalse(row[5]['mounted'])
                with self.assertRaises(ValueError):self.execute(row)
    def test_exact_config_and_aliases_and_fresh_raw_guards(self):
        for condition in ('config','alias','raw','mount','root'):
            with self.subTest(condition=condition),self.fixture() as row:
                p=copy.deepcopy(row[0]);old=(row[6]/'config.txt').read_bytes()
                if condition=='config':(row[7]/'candidate-config.txt').write_bytes(engine.TRIAL_CONFIG+b'framebuffer_depth=16\n')
                if condition=='alias':
                    path=row[7]/'candidate-config.txt';path.unlink();path.symlink_to(row[6]/'config.txt')
                if condition=='raw':p['media']['protected_sha256']['hfs']='0'*64;row=(p,seal.digest(p),*row[2:])
                if condition=='mount':row[5]['replace']=True
                if condition=='root':row[2].command=lambda *_:'foreign-root'
                with self.assertRaises((ValueError,OSError)):self.execute(row)
                self.assertEqual((row[6]/'config.txt').read_bytes(),old)
                if condition=='mount':self.assertTrue(row[5]['mounted']);self.assertNotIn('umount',[x[0] for x in row[5]['commands']])
    def test_exact_config_contract_and_strict_receipt_mutations(self):
        self.assertEqual(seal.digest(engine.ORIGINAL_CONFIG.decode()),seal.digest((ROOT/'build/rpi5/gate2-config.txt').read_text()))
        self.assertEqual(engine.TRIAL_CONFIG,engine.ORIGINAL_CONFIG+b'framebuffer_depth=32\n')
        for key in ('bl31.bin','config.txt'):
            with self.fixture() as row:
                p=copy.deepcopy(row[0]['media']);p['protected_files'][key]='0'*64
                with self.assertRaises(ValueError):engine.bound_core(TAG).validate_files(p)
        with self.fixture() as row:
            result=self.execute(row)
            for key,value in (('config_changed',1),('firmware_changed',True),('no_reboot',False)):
                bad=copy.deepcopy(result);bad['publication'][key]=value
                with self.assertRaises(ValueError):engine.validate_result(bad,row[0],row[1])
    def test_generated_exact_remote_program_executes_with_only_explicit_device_doubles(self):
        with self.fixture() as row:
            code=engine.remote_source(row[8],row[9],row[0],row[1])
            boundary=code.rindex('print(json.dumps(display_allocate_media_v1.execute(PLAN,')
            namespace={};modules=dict(sys.modules)
            with patch.dict(sys.modules,modules),contextlib.redirect_stdout(io.StringIO()) as out:
                exec(compile(code[:boundary],'<actual-sealed-remote-prefix>','exec'),namespace)
                namespace.update(capture=row[2],helper=prior.helper,snapshots=row[3],reference=prior.reference,
                    guarded=types.SimpleNamespace(**{**vars(prior.core),'command':row[4]}))
                exec(compile(code[boundary:],'<actual-sealed-remote-call>','exec'),namespace)
            result=json.loads(out.getvalue());self.assertEqual(result['publication']['pair_publication_order'],['config.txt','probe.bin'])
            self.assertEqual((row[6]/'config.txt').read_bytes(),engine.TRIAL_CONFIG)
            self.assertFalse(row[5]['mounted'])
    def test_remote_source_or_plan_mutation_cannot_dispatch(self):
        with self.fixture() as row:
            p=copy.deepcopy(row[0]);p['media']['files'][0]['new_sha256']='0'*64
            with self.assertRaises(ValueError):engine.remote_source(row[8],row[9],p,seal.digest(p))
            bad=copy.deepcopy(row[8]);bad['evidence_sha256'][str(Path(engine.__file__).resolve())]='0'*64
            with self.assertRaises(ValueError):engine.remote_source(bad,seal.digest(bad),row[0],row[1])
        read=Path.read_text
        def changed(path,*a,**kw):
            value=read(path,*a,**kw)
            return value+'\n# unexpected source change\n' if path==engine.SOURCE else value
        with patch.object(Path,'read_text',changed),self.assertRaisesRegex(ValueError,'Frozen actual-file-tested'):
            engine.bound_core(TAG)
if __name__=='__main__':unittest.main()
