# SPDX-License-Identifier: BSD-2-Clause
"""Actual files for reused FAT backup; explicit existing mount/block doubles."""
import contextlib
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import types
import unittest
from unittest.mock import patch

from tools.rpi5 import firmware_pair_reuse_core as pair
from tools.rpi5 import stage_pcie_fw_reuse_trial as stage
from tools.rpi5 import serial_pcie_fw_reuse_trial as recorder
from tools.rpi5 import pcie_fw_reuse_recovery_evidence as evidence
from tools.rpi5 import capture_pcie_fw_reuse_linux_return as collector
from tools.rpi5.tests import test_pcie_fw_install as prior
from tools.rpi5.tests import test_pcie_fw_recovery_evidence as prior_evidence

BOOT=prior.BOOT
NEXT_BOOT=prior_evidence.NEW_BOOT


def receipt(plan):
    # Same typed receipt fixture as the accepted two-file profile, with the
    # explicit reuse evidence required only by this distinct implementation.
    with patch.object(prior,'pair',pair):
        result=prior.receipt(plan)
    result['reused_existing_sd_backups']={pair.NAMES[plan['profile']][r['target']][0]:r['old_sha256']
        for r in plan['files'] if pair.reuse_backup(plan,r)}
    return result


class FirmwarePairReuseTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self,profile='firmware-abi-reuse-trial'):
        with prior.FirmwarePairInstallTests.fixture(self,profile) as items:
            plan,capture,snapshots,run,state,boot,work,old,new,oldfw,newfw=items
            if profile=='firmware-abi-reuse-trial':
                (boot/pair.REUSED_ZSH_BACKUP).write_bytes(old)
                plan['protected_files'][pair.REUSED_ZSH_BACKUP]=hashlib.sha256(old).hexdigest()
            yield items

    def execute(self,items):
        plan,capture,snapshots,run,*_=items
        return pair.execute(plan,capture,prior.watch.helper,snapshots,prior.watch.reference,prior.watch.core,run)

    def test_actual_reused_backup_is_never_copy_or_rename_destination(self):
        with self.fixture() as x:
            plan,_,_,_,state,boot,work,old,new,oldfw,newfw=x
            existing=(boot/pair.REUSED_ZSH_BACKUP).stat()
            real=prior.watch.helper.copy_image
            destinations=[]
            def guarded_copy(source,directory,name,digest):
                self.assertNotEqual(name,pair.REUSED_ZSH_BACKUP)
                destinations.append(name)
                return real(source,directory,name,digest)
            with patch.object(prior.watch.helper,'copy_image',side_effect=guarded_copy):
                result=self.execute(x)
            after=(boot/pair.REUSED_ZSH_BACKUP).stat()
            self.assertEqual((after.st_dev,after.st_ino,after.st_mtime_ns,after.st_size),
                             (existing.st_dev,existing.st_ino,existing.st_mtime_ns,existing.st_size))
            self.assertEqual((boot/pair.REUSED_ZSH_BACKUP).read_bytes(),old)
            self.assertEqual((boot/'probe.bin').read_bytes(),new)
            self.assertEqual((boot/'bl31.bin').read_bytes(),newfw)
            self.assertEqual((work/'loader-before.bin').read_bytes(),old)
            self.assertEqual(result['reused_existing_sd_backups'],{pair.REUSED_ZSH_BACKUP:plan['files'][1]['old_sha256']})
            self.assertFalse(state['mounted'])
            self.assertEqual(len(destinations),5)  # two SSD copies, one FAT backup, two temporaries
            for phase in ('prepared','before-bl31.bin','after-bl31.bin','before-probe.bin','after-probe.bin'):
                self.assertTrue((work/('pair-'+phase+'.json')).is_file())

    def test_missing_wrong_digest_wrong_size_symlink_and_unprotected_backup_rejected_before_sd_write(self):
        for failure in ('missing','digest','size','symlink','unprotected'):
            with self.subTest(failure=failure),self.fixture() as x:
                plan,_,_,_,state,boot,work,old,new,oldfw,newfw=x
                backup=boot/pair.REUSED_ZSH_BACKUP
                if failure=='missing':backup.unlink()
                if failure=='digest':backup.write_bytes(b'X'*len(old))
                if failure=='size':backup.write_bytes(old+b'x')
                if failure=='symlink':backup.unlink();backup.symlink_to(boot/'probe.bin')
                if failure=='unprotected':plan['protected_files'].pop(pair.REUSED_ZSH_BACKUP)
                before={p.name:p.read_bytes() for p in boot.iterdir() if p.is_file()}
                with patch.object(prior.watch.helper,'copy_image',side_effect=AssertionError('No SD/SSD pair copy before backup rejection')):
                    with self.assertRaises((ValueError,OSError)):
                        self.execute(x)
                self.assertEqual({p.name:p.read_bytes() for p in boot.iterdir() if p.is_file()},before)
                self.assertFalse(state['mounted'])
                self.assertFalse(any(c[0]=='mount' and 'remount,rw,nosuid,nodev,noexec' in c for c in state['commands']))

    def test_each_actual_copy_failure_precedes_pair_publication(self):
        real=prior.watch.helper.copy_image
        for attempt in range(1,6):
            with self.subTest(copy=attempt),self.fixture() as x:
                count=[0]
                def fail(source,directory,name,digest):
                    count[0]+=1
                    if count[0]==attempt:raise OSError('Injected bounded copy failure')
                    return real(source,directory,name,digest)
                with patch.object(prior.watch.helper,'copy_image',side_effect=fail),self.assertRaises(OSError):
                    self.execute(x)
                self.assertEqual((x[5]/'probe.bin').read_bytes(),x[7])
                self.assertEqual((x[5]/'bl31.bin').read_bytes(),x[9])
                self.assertEqual((x[5]/pair.REUSED_ZSH_BACKUP).read_bytes(),x[7])
                self.assertFalse(x[4]['mounted'])

    def test_free_space_counts_only_new_allocations_and_restore_fits_after_trial(self):
        plan=stage.load_plan(BOOT)
        old_size=sum(r['old_bytes']+r['new_bytes'] for r in plan['files'])+1024*1024
        self.assertEqual(old_size-pair.fat_space_required(plan),19384000)
        available=6565888
        self.assertLess(pair.fat_space_required(plan),available)
        self.assertGreater(old_size,available)
        restore=copy.deepcopy(plan);restore['profile']='firmware-abi-reuse-restore'
        for row in restore['files']:
            row['old_bytes'],row['new_bytes']=row['new_bytes'],row['old_bytes']
            row['old_sha256'],row['new_sha256']=row['new_sha256'],row['old_sha256']
        copied_backup_bytes=sum(r['old_bytes'] for r in plan['files'] if not pair.reuse_backup(plan,r))
        after=available-copied_backup_bytes+sum(r['old_bytes']-r['new_bytes'] for r in plan['files'])
        self.assertGreater(after,pair.fat_space_required(restore))
        with self.fixture() as x:
            required=pair.fat_space_required(x[0])
            with patch.object(pair.os,'fstatvfs',return_value=types.SimpleNamespace(f_bavail=required-1,f_frsize=1)),self.assertRaisesRegex(ValueError,'FAT space'):
                self.execute(x)
            self.assertEqual((x[5]/'probe.bin').read_bytes(),x[7])
            self.assertFalse(x[4]['mounted'])

    def test_restore_copies_trial_files_and_preserves_existing_zsh_backup(self):
        with self.fixture('firmware-abi-reuse-restore') as x:
            backup=x[5]/pair.REUSED_ZSH_BACKUP;backup.write_bytes(x[8])
            x[0]['protected_files'][pair.REUSED_ZSH_BACKUP]=hashlib.sha256(x[8]).hexdigest()
            result=self.execute(x)
            self.assertEqual(result['reused_existing_sd_backups'],{})
            self.assertEqual(backup.read_bytes(),x[8])
            self.assertEqual((x[5]/'probe.bin').read_bytes(),x[8])
            self.assertEqual((x[5]/'probe.fwabi-trial-20261013.bin').read_bytes(),x[7])
            self.assertEqual((x[6]/'loader-trial.bin').read_bytes(),x[7])
            self.assertFalse(x[4]['mounted'])

    def test_distinct_profile_remote_program_and_receipt_sources(self):
        self.assertIs(collector.evidence,evidence)
        self.assertEqual(Path(recorder.staging.__file__).resolve(),Path(stage.__file__).resolve())
        plan=stage.load_plan(BOOT);plan['run']='/home/sandrzej/xnu-gate5-fwabi-reuse-12345678'
        self.assertEqual(plan['profile'],'firmware-abi-reuse-trial')
        self.assertEqual(len(plan['nvme_backups']),60)
        compile(stage.remote_source(plan),'<reuse-pair-remote>','exec')
        result=receipt(plan);stage.validate_result(result,plan)
        missing=copy.deepcopy(result);missing.pop('reused_existing_sd_backups')
        with self.assertRaises(ValueError):stage.validate_result(missing,plan)
        with tempfile.TemporaryDirectory(prefix='fwabi-reuse-receipt-',dir=stage.ROOT/'build/rpi5') as name:
            directory=Path(name)
            (directory/'plan.json').write_text(json.dumps(plan));(directory/'result.json').write_text(json.dumps(result))
            installed=recorder.installation(directory)
            self.assertEqual(installed['pair_sha256'],result['pair_sha256'])
            restored=stage.load_plan(NEXT_BOOT,directory);restored['run']='/home/sandrzej/xnu-gate5-fwabi-reuse-87654321'
            self.assertEqual(restored['profile'],'firmware-abi-reuse-restore')
            self.assertEqual(len(restored['nvme_backups']),65)
            restored_result=receipt(restored);stage.validate_result(restored_result,restored)
            self.assertEqual(len(stage.inherited_pair(restored,restored_result,70)),70)

    def test_complete_new_profile_capture_return_restore_replay(self):
        plan=stage.load_plan(BOOT);plan['run']='/home/sandrzej/xnu-gate5-fwabi-reuse-12345678'
        with tempfile.TemporaryDirectory(prefix='fwabi-reuse-install-',dir=stage.ROOT/'build/rpi5') as i, \
             tempfile.TemporaryDirectory(prefix='fwabi-reuse-capture-',dir=stage.ROOT/'build/rpi5') as c, \
             tempfile.TemporaryDirectory(prefix='fwabi-reuse-restore-',dir=stage.ROOT/'build/rpi5') as r:
            install,capture,restore=map(Path,(i,c,r))
            def save(directory,p):
                (directory/'plan.json').write_text(json.dumps(p));(directory/'result.json').write_text(json.dumps(receipt(p)))
                archive=directory/'source-snapshots';archive.mkdir()
                for path in p['source_sha256']:shutil.copyfile(path,archive/Path(path).name)
            save(install,plan);installed=recorder.installation(install)
            sources=stage.source_pins()|{str(Path(recorder.__file__).resolve()):stage.sha(Path(recorder.__file__)),
                str(Path(evidence.protocol.__file__).resolve()):stage.sha(Path(evidence.protocol.__file__))}
            data,rows,state,_,_=prior_evidence.fixture(installed,sources)
            (capture/'serial.bin').write_bytes(data);(capture/'state.json').write_text(json.dumps(state))
            (capture/'receive-events.jsonl').write_text(''.join(json.dumps(v)+'\n' for v in rows))
            armed={k:state[k] for k in ('started_utc','pid','device','baud','transmitted_bytes','installation','source_sha256',
                'physical_reset_return_proven','xnu_pe_runtime_proven','ethernet_proven','armed_utc','armed_monotonic')}
            armed.update(status='failed',continuous_capture=False)
            (capture/'armed.json').write_text(json.dumps(armed))
            observed=evidence.inspect_capture(data,rows,state,installed,sources)
            returned=prior_evidence.returned(plan,installed,observed);returned['return_source_sha256']=evidence.return_source_pins()
            (capture/'linux-return.json').write_text(json.dumps(returned))
            compile(collector.remote_source(plan,installed,observed['serial_sha256'],evidence.return_source_pins()),'<reuse-return>','exec')
            restored=stage.load_plan(NEXT_BOOT,install);restored['run']='/home/sandrzej/xnu-gate5-fwabi-reuse-87654321';save(restore,restored)
            report=evidence.inspect(install,capture,restore)
            self.assertTrue(report['firmware_abi_return_restore_evidence_pass'])
            self.assertEqual(report['next_inherited_artifact_count'],70)
            self.assertFalse(report['controller_initialization_admitted'])
            self.assertFalse(report['ethernet_proven'])


if __name__=='__main__':unittest.main()
