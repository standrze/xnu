# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import stage_pcie_access_trial as stage

BOOT='2407dd80-a11d-47f0-9ae0-57f5c47345ef'


def receipt(plan):
    backup=stage.NAMES[plan['profile']][0]
    return dict(status='installed',run=plan['run'],image_sha256=plan['new_image_sha256'],
        preserved_sd_image_sha256=plan['old_image_sha256'],nvme_previous_image_sha256=plan['old_image_sha256'],
        boot_unmounted=True,no_hfs_mount=True,no_config_change=True,no_reboot=True,
        power_loss_atomicity_claimed=False,temporary_published=True,sd_backup=backup,nvme_backups_verified=plan['nvme_backups'],
        identity=dict(identity=plan['identity_binding']['expected'],boot_id=plan['linux_boot_id'],hostname='kamidana'),
        protected_files_sha256=dict(plan['protected_files'],**{'probe.bin':plan['new_image_sha256'],backup:plan['old_image_sha256']}),
        backups=[dict(device=node,bytes=length,sha256=plan['protected_sha256'][key],saved_as=name)
                 for key,node,_,length,name in stage.base.core.EXTENTS],
        protected_after={key:dict(device=node,bytes=length,sha256=plan['protected_sha256'][key])
                         for key,node,_,length,_ in stage.base.core.EXTENTS})


class AccessInstallTests(unittest.TestCase):
    def test_actual_restored_baseline_52_artifacts_same_boot_without_network(self):
        original=stage.subprocess.run
        def no_network(args,*rest,**kwargs):
            if args[0] in ('ssh','scp'): raise AssertionError('Plan must not use network')
            return original(args,*rest,**kwargs)
        with patch.object(stage.subprocess,'run',side_effect=no_network):
            plan=stage.load_plan(BOOT)
        self.assertEqual(len(plan['nvme_backups']),52)
        self.assertEqual(plan['identity_binding']['linux_boot_id_after_write'],BOOT)
        self.assertNotEqual(plan['identity_binding']['linux_boot_id_before_write'],BOOT)
        self.assertEqual(plan['protected_sha256']['boot'],'0999f771c93c0747efaf262b8ce5232762628497a9db4e2bc2f2c648917c76eb')
        self.assertEqual(plan['preflight']['image_sha256'],stage.IMAGE_SHA)

    def test_generated_remote_and_private_validator_leave_accepted_profile_map_unchanged(self):
        before=copy.deepcopy(stage.base.core.NAMES)
        plan=stage.load_plan(BOOT);plan['run']='/home/sandrzej/xnu-gate5-pcie-access-12345678'
        result=receipt(plan);stage.validate_result(result,plan)
        compile(stage.remote_source(plan),'<isolated-access-installer>','exec')
        self.assertEqual(stage.base.core.NAMES,before)
        with self.assertRaises(ValueError):stage.base.validate_result(result,plan)
        for key,value in (('boot_unmounted',1),('sd_backup','wrong.bin'),('image_sha256','0'*64)):
            bad=copy.deepcopy(result);bad[key]=value
            with self.assertRaises(ValueError):stage.validate_result(bad,plan)
        bad=copy.deepcopy(plan);bad['new_image_sha256']=stage.base.IMAGE_SHA
        with self.assertRaises(ValueError):stage.validate_result(result,bad)

    def test_restore_inherits_56_artifacts_only_after_new_linux_boot(self):
        plan=stage.load_plan(BOOT);plan['run']='/home/sandrzej/xnu-gate5-pcie-access-12345678'
        with tempfile.TemporaryDirectory(prefix='access-receipt-test-',dir=stage.ROOT/'build/rpi5') as name:
            directory=Path(name);(directory/'plan.json').write_text(json.dumps(plan));(directory/'result.json').write_text(json.dumps(receipt(plan)))
            with self.assertRaisesRegex(ValueError,'Distinct SSD return'):stage.load_plan(BOOT,directory)
            restored=stage.load_plan('3407dd80-a11d-47f0-9ae0-57f5c47345ef',directory)
            self.assertEqual(restored['profile'],'pcie-access-restore');self.assertEqual(len(restored['nvme_backups']),56)
            self.assertEqual(restored['new_image_sha256'],stage.base.prior.NEW_SHA)

    def test_actual_guarded_publisher_with_private_access_names(self):
        import hashlib
        module=types.ModuleType('isolated_access_publisher')
        exec(Path(stage.base.core.__file__).read_text(),module.__dict__);module.NAMES.update(stage.NAMES)
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);boot=root/'boot';boot.mkdir();old=b'tested-zsh';new=b'read-only-access'
            (boot/'probe.bin').write_bytes(old);(root/'candidate.bin').write_bytes(new)
            directory=os.open(boot,os.O_RDONLY|os.O_DIRECTORY);candidate=os.open(root/'candidate.bin',os.O_RDONLY)
            plan=dict(profile='pcie-access-trial',old_image_sha256=hashlib.sha256(old).hexdigest(),new_image_sha256=hashlib.sha256(new).hexdigest())
            calls=[]
            try:result=module.publish(directory,candidate,plan,stage.base.prior.base.install_core,lambda mode:calls.append(mode))
            finally:os.close(directory);os.close(candidate)
            self.assertEqual((boot/'probe.bin').read_bytes(),new)
            self.assertEqual((boot/result['sd_backup']).read_bytes(),old)
            self.assertTrue(calls and all(mode=='rw' for mode in calls))
        self.assertNotIn('pcie-access-trial',stage.base.core.NAMES)


if __name__=='__main__':unittest.main()
