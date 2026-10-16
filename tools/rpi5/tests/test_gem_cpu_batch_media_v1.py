# SPDX-License-Identifier: BSD-2-Clause
"""Actual three-target publisher programs with local files/device doubles."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import sys
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import gem_cpu_batch_media_v1 as e
from tools.rpi5 import trial_checkpoint_v2 as seal
from tools.rpi5.tests import test_watchdog_recovery_install as prior
ROOT=Path(__file__).resolve().parents[3]
GOOD=ROOT/'build/rpi5/bl33-probe-vszhh6o4/probe.bin'
FW=ROOT/'build/rpi5/tfa-candidate/build/rpi5/debug/bl31.bin'
TAG='29'*16
class TripleMediaTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self,restore=False):
        with prior.RecoveryInstallTests.fixture(self) as r:
            plan,capture,snapshots,run,state,boot,work,*_=r
            (work/'candidate.bin').unlink()
            old={'config.txt':e.ORIGINAL_CONFIG,'bl31.bin':FW.read_bytes(),'probe.bin':GOOD.read_bytes()}
            new={'config.txt':e.TRIAL_CONFIG,'bl31.bin':e.case.FIRMWARE.read_bytes(),'probe.bin':(e.case.PACKAGE/'probe.bin').read_bytes()}
            if restore:old,new=new,old
            for name in e.TARGETS:
                (boot/name).write_bytes(old[name]);(work/('candidate-'+name)).write_bytes(new[name])
            shutil.copyfile(GOOD,boot/e.original.REUSED_ZSH_BACKUP)
            plan.update(profile=e.RESTORE if restore else e.TRIAL,files=[])
            for name in e.TARGETS:
                current,target=boot/name,work/('candidate-'+name)
                plan['files'].append(dict(target=name,candidate='candidate-'+name,old_sha256=seal.sha(current),
                    old_bytes=current.stat().st_size,new_sha256=seal.sha(target),new_bytes=target.stat().st_size))
            plan['protected_files']={e.original.REUSED_ZSH_BACKUP:e.original.GOOD_ZSH_SHA}
            archives=work.parent/'baseline';archives.mkdir();shutil.copyfile(FW,archives/'firmware.bin');shutil.copyfile(GOOD,archives/'loader.bin')
            baseline={'bl31.bin':str(archives/'firmware.bin'),'probe.bin':str(archives/'loader.bin')}
            history=[dict(path=str(work.parent/'nonexistent-history'),bytes=536870912,sha256='9'*64)]
            history.extend(dict(path=p,bytes=Path(p).stat().st_size,sha256=seal.sha(p)) for p in baseline.values())
            plan['nvme_backups']=history;media=copy.deepcopy(plan);media.pop('run')
            active=e.select_baseline(history,baseline)
            def verify(p):
                self.assertEqual(p['nvme_backups'],active);state['verifies']+=1
                for row in active:self.assertEqual(seal.sha(row['path']),row['sha256'])
            capture.verify_backups=verify
            checkpoint,pin=seal.create(lambda:dict(media_plan=media,history_catalog=history,baseline_paths=baseline),e.source_pins())
            outer,h=e.plan_from_seal(checkpoint,pin,media['profile'],TAG,str(work),media)
            yield outer,h,capture,snapshots,run,state,boot,work,checkpoint,pin
    def execute(self,r):return e.execute(r[0],r[1],r[2],prior.helper,r[3],prior.reference,prior.core,r[4])
    def test_both_exact_triples_and_six_archives(self):
        for restore in (False,True):
            with self.subTest(restore=restore),self.fixture(restore) as r:
                result=self.execute(r);p=result['publication']
                self.assertEqual(p['triple_publication_order'],list(e.TARGETS))
                self.assertTrue(p['config_changed']);self.assertTrue(p['firmware_changed'])
                self.assertEqual(result['created_archive_count'],6);self.assertFalse(r[5]['mounted'])
                for row in r[0]['media']['files']:
                    self.assertEqual(seal.sha(r[6]/row['target']),row['new_sha256'])
                    self.assertEqual(seal.sha(r[7]/p['preserved_triple'][row['target']]['nvme_backup']),row['old_sha256'])
                e.validate_result(result,r[0],r[1])
    def test_all_eight_copy_faults_precede_every_rename_no_retry(self):
        actual=prior.helper.copy_image
        for at in range(1,9):
            with self.subTest(at=at),self.fixture() as r:
                before={n:(r[6]/n).read_bytes() for n in e.TARGETS};calls=[]
                def fault(*args,**kwargs):
                    calls.append(args[2]);actual(*args,**kwargs)
                    if len(calls)==at:raise ValueError('copy fault')
                with patch.object(prior.helper,'copy_image',side_effect=fault),patch.object(os,'rename',wraps=os.rename) as rename:
                    with self.assertRaisesRegex(ValueError,'copy fault'):self.execute(r)
                    rename.assert_not_called()
                self.assertEqual(before,{n:(r[6]/n).read_bytes() for n in e.TARGETS})
                self.assertFalse(r[5]['mounted'])
                with self.assertRaises(ValueError):self.execute(r)
    def test_each_partial_rename_preserved_and_journaled_no_compensation(self):
        actual=os.rename
        for at in (1,2,3):
            with self.subTest(at=at),self.fixture() as r:
                calls=[]
                def fault(*args,**kwargs):
                    calls.append(args[1]);actual(*args,**kwargs)
                    if len(calls)==at:raise ValueError('post rename fault')
                with patch.object(os,'rename',side_effect=fault):
                    with self.assertRaisesRegex(ValueError,'post rename fault'):self.execute(r)
                self.assertEqual(calls,list(e.TARGETS[:at]))
                for i,row in enumerate(r[0]['media']['files']):
                    self.assertEqual(seal.sha(r[6]/row['target']),row['new_sha256'] if i<at else row['old_sha256'])
                self.assertTrue((r[7]/('pair-before-'+e.TARGETS[at-1]+'.json')).exists())
                self.assertFalse((r[7]/'result.json').exists())
                with self.assertRaises(ValueError):self.execute(r)
    def test_every_durable_journal_boundary_and_each_postrename_readback(self):
        phases=[('prepared',0)]+[(where+'-'+name,i+(where=='after')) for i,name in enumerate(e.TARGETS) for where in ('before','after')]
        actual_open=Path.open
        for phase,published in phases:
            with self.subTest(phase=phase),self.fixture() as r:
                def fail(path,*args,**kwargs):
                    if path==r[7]/('pair-'+phase+'.json'):raise OSError('journal fault')
                    return actual_open(path,*args,**kwargs)
                with patch.object(Path,'open',fail),patch.object(os,'rename',wraps=os.rename) as rename:
                    with self.assertRaisesRegex(OSError,'journal fault'):self.execute(r)
                    self.assertEqual(rename.call_count,published)
                self.assertFalse((r[7]/'result.json').exists())
                with self.assertRaises(ValueError):self.execute(r)
        actual_hash=prior.helper.digest_fd;actual_rename=os.rename
        for at in (1,2,3):
            with self.subTest(readback=at),self.fixture() as r:
                names=[]
                def rename(*args,**kwargs):names.append(args[1]);return actual_rename(*args,**kwargs)
                def digest(fd):
                    result=actual_hash(fd)
                    if len(names)==at and os.fstat(fd).st_ino==(r[6]/names[-1]).stat().st_ino:
                        raise ValueError('postrename readback fault')
                    return result
                with patch.object(os,'rename',side_effect=rename),patch.object(prior.helper,'digest_fd',side_effect=digest):
                    with self.assertRaisesRegex(ValueError,'postrename readback fault'):self.execute(r)
                self.assertEqual(names,list(e.TARGETS[:at]))
                self.assertFalse((r[7]/'result.json').exists())
                with self.assertRaises(ValueError):self.execute(r)
    def test_config_alias_raw_root_mount_and_strict_transition_rejection(self):
        for mode in ('config','alias','raw','root','mount','protected-target','order'):
            with self.subTest(mode=mode),self.fixture() as r:
                p=copy.deepcopy(r[0]);before=(r[6]/'config.txt').read_bytes()
                if mode=='config':(r[7]/'candidate-config.txt').write_bytes(e.TRIAL_CONFIG+b'framebuffer_depth=16\n')
                elif mode=='alias':
                    (r[7]/'candidate-config.txt').unlink();(r[7]/'candidate-config.txt').symlink_to(r[6]/'config.txt')
                elif mode=='raw':p['media']['protected_sha256']['hfs']='0'*64;r=(p,seal.digest(p),*r[2:])
                elif mode=='root':r[2].command=lambda *_:'foreign-root'
                elif mode=='mount':r[5]['replace']=True
                elif mode=='protected-target':p['media']['protected_files']['bl31.bin']='0'*64;r=(p,seal.digest(p),*r[2:])
                elif mode=='order':p['media']['files'].reverse();r=(p,seal.digest(p),*r[2:])
                with self.assertRaises((ValueError,OSError)):self.execute(r)
                self.assertEqual((r[6]/'config.txt').read_bytes(),before)
    def test_generated_remote_program_actual_three_target_engine(self):
        with self.fixture() as r:
            code=e.remote_source(r[8],r[9],r[0],r[1]);boundary=code.rindex('print(json.dumps(gem_cpu_batch_media_v1.execute(PLAN,')
            namespace={}
            with patch.dict(sys.modules,dict(sys.modules)),contextlib.redirect_stdout(io.StringIO()) as out:
                exec(compile(code[:boundary],'<sealed-triple-remote-prefix>','exec'),namespace)
                namespace.update(capture=r[2],helper=prior.helper,snapshots=r[3],reference=prior.reference,
                    guarded=types.SimpleNamespace(**{**vars(prior.core),'command':r[4]}))
                exec(compile(code[boundary:],'<actual-triple-remote-call>','exec'),namespace)
            result=json.loads(out.getvalue());self.assertEqual(result['publication']['triple_publication_order'],list(e.TARGETS))
    def test_plan_or_source_change_and_typed_truth_rejected(self):
        with self.fixture() as r:
            bad=copy.deepcopy(r[0]);bad['media']['files'][0]['new_sha256']='0'*64
            with self.assertRaises(ValueError):e.remote_source(r[8],r[9],bad,seal.digest(bad))
            result=self.execute(r)
            for key,value in (('config_changed',1),('firmware_changed',False),('triple_publication_order',list(reversed(e.TARGETS)))):
                bad=copy.deepcopy(result);bad['publication'][key]=value
                with self.assertRaises(ValueError):e.validate_result(bad,r[0],r[1])
            bad=copy.deepcopy(r[8]);bad['evidence_sha256'][str(Path(e.__file__).resolve())]='0'*64
            with self.assertRaises(ValueError):e.remote_source(bad,seal.digest(bad),r[0],r[1])
if __name__=='__main__':unittest.main()
