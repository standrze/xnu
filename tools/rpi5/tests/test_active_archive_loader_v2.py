# SPDX-License-Identifier: BSD-2-Clause
"""Real regular-file copies/rename; only block, mount and identity are doubled."""
import contextlib
import copy
import ast
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
from tools.rpi5 import active_archive_loader_v2 as engine
from tools.rpi5 import trial_checkpoint_v2 as seals
from tools.rpi5.tests import test_root96_trial as prior

TAG='25'*16


class LoaderTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self,restore=False):
        with prior.MediaTests.fixture(self,prior.media.MODES[2 if restore else 1]) as row:
            p,c,s,run,state,boot,work,new=row
            archives=work.parent/'baseline';archives.mkdir()
            paths={'bl31.bin':str(archives/'firmware.bin'),'probe.bin':str(archives/'loader.bin')}
            shutil.copyfile(prior.FIRMWARE,paths['bl31.bin']);shutil.copyfile(prior.GOOD,paths['probe.bin'])
            rows=[dict(path=str(work.parent/'history'/str(i)),bytes=536870912,sha256='9'*64) for i in range(146)]
            rows += [dict(path=p,bytes=Path(p).stat().st_size,sha256=seals.sha(p)) for p in paths.values()]
            p['profile']=engine.RESTORE if restore else engine.TRIAL;p['nvme_backups']=rows
            media=copy.deepcopy(p);media.pop('run');state['audit_calls']=0;state['active_paths']=[]
            def verify(plan):
                self.assertEqual(plan['nvme_backups'],engine.select_baseline(rows,paths));state['verifies']+=1
                for r in plan['nvme_backups']:
                    state['active_paths'].append(r['path'])
                    if Path(r['path']).stat().st_size!=r['bytes'] or seals.sha(r['path'])!=r['sha256']:raise ValueError('Active baseline changed')
            c.verify_backups=verify
            def audit():
                state['audit_calls']+=1
                return dict(media_plan=media,history_catalog=rows,baseline_paths=paths)
            checkpoint,pin=seals.create(audit,engine.source_pins())
            outer,op=engine.plan_from_seal(checkpoint,pin,media['profile'],TAG,str(work),media)
            yield outer,op,c,s,run,state,boot,work,paths,checkpoint,pin

    def execute(self,row):
        p,pin,c,s,run,*_=row
        return engine.execute(p,pin,c,prior.fixture_base.helper,s,prior.fixture_base.reference,prior.fixture_base.core,run)

    def test_install_restore_keep_firmware_and_only_hash_active_archives(self):
        for restore in (False,True):
            with self.subTest(restore=restore),self.fixture(restore) as row:
                firmware=(row[6]/'bl31.bin').stat().st_ino;backup=(row[6]/prior.media.RETAINED).stat().st_ino
                result=self.execute(row)
                self.assertEqual(row[5]['audit_calls'],1);self.assertEqual(row[5]['verifies'],2)
                self.assertEqual(row[5]['active_paths'],list(row[8].values())*2)
                self.assertEqual(result['created_archive_count'],4);self.assertEqual(len(result['next_catalog']),152)
                self.assertEqual(result['publication']['replaced_files'],['probe.bin'])
                self.assertTrue(result['publication']['no_firmware_change']);self.assertFalse(result['historical_archives_reverified'])
                self.assertEqual((row[6]/'bl31.bin').stat().st_ino,firmware)
                self.assertEqual((row[6]/prior.media.RETAINED).stat().st_ino,backup)
                self.assertEqual(seals.sha(row[6]/'bl31.bin'),prior.media.FIRMWARE_SHA)
                self.assertEqual(seals.sha(row[6]/'probe.bin'),row[0]['media']['new_sha256'])
                self.assertTrue((row[7]/'publication.json').is_file());self.assertTrue((row[7]/'result.json').is_file())
                self.assertFalse(row[5]['mounted']);engine.validate_result(result,row[0],row[1])

    def test_reclaim_old_pair_profile_and_typed_receipt_tampering_refused(self):
        with self.fixture() as row:
            for profile in (prior.media.MODES[0],prior.media.MODES[1],engine.shared.TRIAL):
                changed=copy.deepcopy(row[0]['media']);changed['profile']=profile
                with self.assertRaises(ValueError):engine.bound_core(TAG).validate(changed)
            result=self.execute(row)
            for mutate in (lambda r:r['publication'].update(no_firmware_change=1),
                lambda r:r['publication']['protected_after']['hfs'].update(sha256='0'*64),
                lambda r:r.update(created_archive_count=5),lambda r:r.update(historical_archives_reverified=True),
                lambda r:r['newly_created_rollback_archives_verified'].pop(),lambda r:r.update(deleted_archives=['old'])):
                changed=copy.deepcopy(result);mutate(changed)
                with self.assertRaises(ValueError):engine.validate_result(changed,row[0],row[1])
            self.assertEqual(row[5]['audit_calls'],1)

    def test_corrupt_baseline_and_omitted_seal_member_fail_before_mount(self):
        with self.fixture() as row:
            Path(row[8]['probe.bin']).write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError,'Active baseline'):self.execute(row)
            self.assertEqual(row[5]['commands'],[])
        with self.fixture() as row:
            altered=copy.deepcopy(row[9]);del altered['evidence_sha256'][str(engine.SOURCE)]
            with self.assertRaisesRegex(ValueError,'source closure'):
                engine.plan_from_seal(altered,seals.digest(altered),engine.TRIAL,TAG,str(row[7]),altered['payload']['media_plan'])

    def test_copy_and_post_rename_failures_preserve_rollback_and_never_retry(self):
        helper=prior.fixture_base.helper;realcopy=helper.copy_image
        for at in (1,2):
            with self.subTest(at=at),self.fixture() as row:
                calls=[]
                def fail(*args):
                    calls.append(1)
                    if len(calls)==at:raise ValueError('copy failure')
                    return realcopy(*args)
                with patch.object(helper,'copy_image',side_effect=fail):
                    with self.assertRaisesRegex(ValueError,'copy failure'):self.execute(row)
                self.assertEqual(seals.sha(row[6]/'probe.bin'),prior.media.GOOD_SHA)
                self.assertFalse(row[5]['mounted']);self.assertFalse((row[7]/'result.json').exists())
        with self.fixture() as row:
            real=os.rename;calls=[]
            def fail_after(*args,**kwargs):real(*args,**kwargs);calls.append(1);raise ValueError('post rename')
            with patch.object(os,'rename',side_effect=fail_after):
                with self.assertRaisesRegex(ValueError,'post rename'):self.execute(row)
            self.assertEqual(calls,[1]);self.assertEqual(seals.sha(row[7]/'previous.bin'),prior.media.GOOD_SHA)
            self.assertEqual(seals.sha(row[6]/'probe.bin'),row[0]['media']['new_sha256'])
            with self.assertRaisesRegex(ValueError,'Fresh canonical SSD'):self.execute(row)

    def test_remote_program_build_is_offline_and_plan_types_are_exact(self):
        with self.fixture() as row:
            code=engine.remote_source(row[9],row[10],row[0],row[1]);compile(code,'<offline>','exec')
            self.assertIn('active_archive_loader_v2.execute(PLAN,',code)
            tree=ast.parse(code)
            self.assertIsInstance(tree.body[-1],ast.Expr)
            self.assertEqual(ast.unparse(tree.body[-1]).split('(')[0],'print')
            # Instantiate the exact embedded modules in an isolated process,
            # but replace the sole mutation entry with read-only plan checks.
            tree.body[-1:]=ast.parse("active_archive_loader_v2.validate_plan(PLAN)\nprint('REMOTE_NAMESPACE_ONLY_PASS')\n").body
            native=subprocess.run([sys.executable,'-'],input=ast.unparse(tree),text=True,capture_output=True,check=True,timeout=20)
            self.assertEqual(native.stdout,'REMOTE_NAMESPACE_ONLY_PASS\n')
            self.assertEqual(row[5]['audit_calls'],1);self.assertEqual(row[5]['commands'],[])
            changed=copy.deepcopy(row[0]);changed['media']['nvme_backups'][0]['bytes']=float(engine.shared.GOOD_FW_BYTES)
            with self.assertRaises(ValueError):engine.validate_plan(changed)
