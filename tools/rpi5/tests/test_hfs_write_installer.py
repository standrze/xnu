# SPDX-License-Identifier: BSD-2-Clause
"""Write installation guards, synthetic raw acceptance and native file publication."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import stage_hfs_write_trial as runner
from tools.rpi5.tests.test_probe_install_core import ProbeInstallTests


class WriteInstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def bundle(self):
        files=[dict(path=path,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
               for path,data in (('/etc/proof.txt',b'proof'),('/etc/empty',b''),
                   ('/etc/cross-page.bin',bytes(range(35))),('/etc/recovery.sh',b'script'),('/bin/echo',b'binary'))]
        data=[b'proof',b'',bytes(range(35)),b'script',b'binary']
        raw=b'SMP unrelated torn\rstartup\n'; reads=[]
        for cycle in (1,2):
            for op in ('MOUNTED','STATUS'): raw+=runner.boot.trial.mount_marker(op,'/dev/disk0s2')+b'\r\r\n'
            for index,(entry,content) in enumerate(zip(files,data)):
                nonce='H'+format(cycle*10+index,'016x'); begin,end=runner.frame_markers(nonce)
                rows=[content[n:n+16].hex(' ').encode()+(b' ' if len(content[n:n+16])<16 else b'')
                      for n in range(0,len(content),16)]
                frame=b'\r\r\n'.join([begin,*rows,end])+b'\r\r\n'
                raw+=frame
                reads.append(dict(runner.parse_file(frame,entry,nonce),mount_cycle=cycle))
            raw+=runner.boot.trial.mount_marker('UNMOUNTED','/dev/disk0s2')+b'\r\r\n'
        state=dict(status='passed',mount_cycles_completed=2,sd_data_write_commands=0,
            image_sha256=runner.checker.HFS_READ_BASELINE_SHA256,partition='/dev/disk0s2',baud=115200,
            checks=runner.READ_CHECKS,evidence_sha256={'prior':'a'*64},reads=reads)
        path=self.root/'state.json'
        self.save(path,state,raw)
        return path,state,raw,dict(files=files),dict(image_sha256=runner.checker.HFS_READ_BASELINE_SHA256),{'prior':'a'*64}

    def save(self,path,state,raw):
        (path.parent/'serial.bin').write_bytes(raw)
        state.update(bytes=len(raw),serial_sha256=hashlib.sha256(raw).hexdigest())
        path.write_text(json.dumps(state))

    def test_raw_empty_and_full_files_must_belong_to_each_separate_mount_cycle(self):
        path,state,raw,fixture,preflight,evidence=self.bundle()
        proof=runner.validate_read_trial(path,fixture,preflight,evidence)
        self.assertEqual(proof['serial_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertIn(b'\rstartup',raw) # unrelated raw chatter preserved, not repaired

    def test_duplicate_missing_torn_corrupt_out_of_cycle_or_misbound_proof_rejects(self):
        for fault in ('duplicate','missing','torn','corrupt','cycle','nonce','order','bool','image','checks','binding','panic','statehash'):
            path,state,raw,fixture,preflight,evidence=self.bundle()
            first=state['reads'][0]; begin,end=runner.frame_markers(first['nonce'])
            if fault=='duplicate': raw+=begin+b'\n'
            if fault=='missing': raw=raw.replace(end+b'\r\r\n',b'',1)
            if fault=='torn': raw=raw.replace(b'70 72',b'70\r 72',1)
            if fault=='corrupt': raw=raw.replace(b'70 72',b'ff 72',1)
            if fault=='cycle': state['reads'][0]['mount_cycle']=2; state['reads'][5]['mount_cycle']=1
            if fault=='nonce': state['reads'][5]['nonce']=first['nonce']
            if fault=='order': raw=raw.replace(runner.boot.trial.mount_marker('STATUS','/dev/disk0s2'),b'late_status',1)
            if fault=='bool': state['sd_data_write_commands']=False
            if fault=='image': state['image_sha256']='f'*64
            if fault=='checks': state['checks']=[]
            if fault=='binding': state['evidence_sha256']={}
            if fault=='panic': raw+=b'panic(cpu'
            self.save(path,state,raw)
            if fault=='statehash': (path.parent/'serial.bin').write_bytes(raw+b'changed')
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                runner.validate_read_trial(path,fixture,preflight,evidence)

    def argv(self,output,execute=False):
        return ['stage_hfs_write_trial.py','--inputs',str(self.root/'inputs.json'),'--output',str(output)]+(['--execute'] if execute else [])

    def test_local_plan_only_and_invalid_proof_never_connect_or_write_media(self):
        output=self.root/'local'
        with patch.object(sys,'argv',self.argv(output)),patch.object(Path,'is_relative_to',return_value=True), \
                patch.object(runner,'load_plan',return_value={'no_reboot':True}),patch.object(runner.subprocess,'run') as network, \
                contextlib.redirect_stdout(io.StringIO()): self.assertEqual(runner.main(),0)
        network.assert_not_called()
        output=self.root/'reject'
        with patch.object(sys,'argv',self.argv(output,True)),patch.object(Path,'is_relative_to',return_value=True), \
                patch.object(runner,'load_plan',side_effect=ValueError('stale reference')), \
                patch.object(runner.subprocess,'run') as network,self.assertRaises(ValueError): runner.main()
        network.assert_not_called(); self.assertFalse(output.exists())

    def test_timeout_retains_partial_output_and_exact_run_without_retry(self):
        output=self.root/'unknown'; plan=dict(candidate='candidate.bin',expected={},fixture_sha256='a'*64)
        responses=[SimpleNamespace(stdout=json.dumps(dict(run='/home/sandrzej/xnu-gate4-hfs-write-abcdefgh'))),
            SimpleNamespace(returncode=0),runner.subprocess.TimeoutExpired('ssh',300,output=b'partial',stderr=b'failed')]
        with patch.object(sys,'argv',self.argv(output,True)),patch.object(Path,'is_relative_to',return_value=True), \
                patch.object(runner,'load_plan',side_effect=lambda _:copy.deepcopy(plan)), \
                patch.object(runner.subprocess,'run',side_effect=responses) as network,self.assertRaises(runner.subprocess.TimeoutExpired):
            runner.main()
        self.assertEqual(network.call_count,3)
        self.assertEqual((output/'remote.stdout').read_bytes(),b'partial')
        self.assertTrue((output/'outcome-unknown.txt').exists()); self.assertFalse((output/'result.json').exists())

    def result_bundle(self):
        plan=dict(run='/home/sandrzej/xnu-gate4-hfs-write-abcdefgh',new_image_sha256='a'*64,old_image_sha256='b'*64,
            linux_boot_id='54b2ad20-73c0-4dc2-a6b7-c96506b04a0a',current_mbr_sha256='c'*64,fixture_sha256='d'*64)
        result=dict(status='installed',run=plan['run'],image_sha256='a'*64,preserved_sd_image_sha256='b'*64,
            sd_backup='probe.hfs-read-passed-20261012.bin',temporary_published=True,power_loss_atomicity_claimed=False,
            hfs_partition_unchanged=True,protected_boot_files_unchanged=True,boot_unmounted=True,
            no_hfs_mount=True,no_partition_change=True,no_config_change=True,no_reboot=True)
        before=[dict(device=node,bytes=size,saved_as=name,sha256=value*64)
                for node,size,name,value in (('/dev/mmcblk0',512,'mbr.before-write.bin','c'),
                    ('/dev/mmcblk0p1',536870912,'boot-partition.before-write.img','e'),
                    ('/dev/mmcblk0p2',134217728,'hfs-partition.before.img','d'))]
        after={key:dict(row,saved_as=None) for key,row in zip(('mbr','boot','hfs'),before)}
        after['boot']['sha256']='f'*64
        result['write_trial_backups']=dict(before=before,after=after,linux_boot_id=plan['linux_boot_id'],sd_data_writes=0,hfs_mounts=0)
        return plan,result

    def test_complete_snapshot_and_typed_install_result_required(self):
        plan,result=self.result_bundle(); runner.validate_result(result,plan)
        for field in result:
            changed=copy.deepcopy(result); changed[field]=None
            with self.subTest(field=field),self.assertRaises((ValueError,AttributeError)): runner.validate_result(changed,plan)
        for field in ('sd_data_writes','hfs_mounts'):
            changed=copy.deepcopy(result); changed['write_trial_backups'][field]=False
            with self.subTest(field=field),self.assertRaises(ValueError): runner.validate_result(changed,plan)
        for key in ('mbr','boot','hfs'):
            changed=copy.deepcopy(result); changed['write_trial_backups']['after'][key]['sha256']='0'*64
            if key=='boot': changed['write_trial_backups']['after'][key]['sha256']='e'*64
            with self.subTest(key=key),self.assertRaises(ValueError): runner.validate_result(changed,plan)

    def test_rendered_remote_is_valid_and_snapshots_precede_remount_and_publish(self):
        plan,_=self.result_bundle(); plan['expected']={}
        source=runner.remote_source(plan); compile(source,'write-remote','exec')
        self.assertLess(source.index('write_backups=prepare_write_backups(PLAN)'),source.index("['mount','-o','remount,rw"))
        self.assertLess(source.index("'hfs-read-passed.bin' if profile=='write-trial'"),source.index("['mount','-o','remount,rw"))
        self.assertLess(source.index("['umount','/mnt/xnu-probe']"),source.index('result[\'write_trial_backups\']=finish_write_install'))
        self.assertNotIn("['reboot'",source)


class WriteImagePublicationTests(ProbeInstallTests):
    # Inherit all real regular-file faults against the distinct write profile.
    def install(self):
        return runner.boot.core.install(self.directory,self.candidate,self.old_hash,self.new_hash,'write-trial')

    def test_publish_preserves_old_image_and_other_files(self):
        result=self.install()
        self.assertEqual(result['sd_backup'],'probe.hfs-read-passed-20261012.bin')
        self.assertEqual((self.boot/result['sd_backup']).read_bytes(),self.old)
        self.assertEqual((self.boot/'probe.bin').read_bytes(),self.new)
        self.assertEqual((self.boot/'config.txt').read_bytes(),b'unchanged boot configuration')
        self.assertFalse((self.boot/'probe.hfs-write-trial-20261012.tmp').exists())

    def test_short_write_or_interruption_is_bounded_and_original_remains(self):
        for error in (0,InterruptedError()):
            with patch.object(runner.boot.core.os,'pwrite',side_effect=error if isinstance(error,Exception) else None,
                    return_value=error) as write,self.assertRaises(RuntimeError): self.install()
            self.assertLessEqual(write.call_count,16)
            self.assertEqual((self.boot/'probe.bin').read_bytes(),self.old)
            (self.boot/'probe.hfs-read-passed-20261012.bin').unlink()

    def test_existing_partial_backup_temp_or_symlink_is_never_overwritten(self):
        for name in runner.boot.core.INSTALL_NAMES['write-trial']:
            path=self.boot/name; path.symlink_to(self.base/'missing')
            with self.subTest(name=name),self.assertRaises(ValueError): self.install()
            self.assertTrue(path.is_symlink()); path.unlink()

    def test_failed_candidate_readback_retains_backup_and_temp_without_publication(self):
        original=runner.boot.core.copy_image
        def fault(source,directory,name,expected):
            original(source,directory,name,expected)
            if name.endswith('.tmp'): raise RuntimeError('readback fault')
        with patch.object(runner.boot.core,'copy_image',side_effect=fault),self.assertRaises(RuntimeError): self.install()
        self.assertEqual((self.boot/'probe.bin').read_bytes(),self.old)
        self.assertEqual((self.boot/'probe.hfs-read-passed-20261012.bin').read_bytes(),self.old)
        self.assertTrue((self.boot/'probe.hfs-write-trial-20261012.tmp').exists())


if __name__=='__main__': unittest.main()
