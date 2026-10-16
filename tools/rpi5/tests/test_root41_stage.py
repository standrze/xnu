# SPDX-License-Identifier: BSD-2-Clause
"""Focused corrected-profile adapters; physical execution is never simulated as proof."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch
from tools.rpi5 import stage_root41_trial as stage
from tools.rpi5 import serial_root41_trial as recorder
from tools.rpi5 import audit_root41_trial as audit
from tools.rpi5.tests import test_root96_trial as prior
core,media=recorder.core,stage.core
ROOT=stage.ROOT
PACKAGE=Path(os.environ['RPI5_ROOT41_PACKAGE']).resolve() if 'RPI5_ROOT41_PACKAGE' in os.environ else None
from tools.rpi5.tests import test_root41_batch_trial as batch_fixture
sha=lambda data:hashlib.sha256(data).hexdigest()



class MediaTests(unittest.TestCase):
    def test_actual_file_install_restore_no_reclaim_and_original_module_unchanged(self):
        original_modes=media.original.MODES;original_temp=dict(media.original.TEMP)
        for i,mode in enumerate(media.MODES):
            with self.subTest(mode=mode),prior.MediaTests.fixture(self,media.original.MODES[i+1]) as row:
                plan,capture,snapshots,run,state,boot,work,new=row
                plan['profile']=mode;previous=(boot/'probe.bin').read_bytes()
                result=media.execute(plan,capture,prior.fixture_base.helper,snapshots,
                    prior.fixture_base.reference,prior.fixture_base.core,run)
                self.assertEqual(result['profile'],mode);self.assertFalse(result['deleted_files'])
                self.assertEqual((work/'previous.bin').read_bytes(),previous)
                self.assertEqual(sha((boot/'probe.bin').read_bytes()),plan['new_sha256'])
                self.assertFalse(state['mounted'])
                journal=json.loads((work/'media-before-probe-rename.json').read_text())
                self.assertEqual(journal['profile'],mode)
                with self.assertRaises(ValueError):media.validate(dict(plan,profile=media.original.MODES[i+1]))
                bad=copy.deepcopy(plan);bad['protected_files'][media.REDUNDANT]=media.GOOD_SHA
                with self.assertRaises(ValueError):media.validate(bad)
        self.assertEqual(media.original.MODES,original_modes);self.assertEqual(media.original.TEMP,original_temp)



class DeadlineTests(unittest.TestCase):
    def test_admission_precedes_revalidation_and_its_time_consumes_tx_budget(self):
        now=[100.0];state={'checks':[]};deadlines=[]
        def revalidate():now[0]+=4.0
        def commands(fd,output,progress,receipt,files,validate,deadline):
            deadlines.append(deadline)
            raise InterruptedError('fixture stops before any serial input')
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            (directory/'manifest.json').write_text('{}');(directory/'ramdisk.bin').write_bytes(b'fixture')
            report={'root_manifest':str(directory/'manifest.json')}
            with patch.object(recorder.time,'monotonic',side_effect=lambda:now[0]),\
                patch.object(recorder.t.shell,'receive',return_value=b'fixture boot'),\
                patch.object(core,'boot_ready',return_value=True),\
                patch.object(recorder.root_profile,'files_from',return_value={}),\
                patch.object(core,'commands',side_effect=commands):
                with self.assertRaises(InterruptedError):recorder.trial(-1,io.BytesIO(),600,report,state,revalidate)
        self.assertEqual(state['admitted_monotonic'],100.0)
        self.assertEqual(state['admission_revalidation_seconds'],4.0)
        self.assertEqual(deadlines,[220.0])


class IntegratedAdapters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if PACKAGE is None:raise unittest.SkipTest('RPI5_ROOT41_PACKAGE selects final immutable checked loader')
        cls.report=recorder.package.inspect(PACKAGE)
        cls.receipt=json.loads(Path(cls.report['root_manifest']).read_text())
        cls.files=recorder.root_profile.files_from((Path(cls.report['root_manifest']).parent/'ramdisk.bin').read_bytes())

    def test_final_actual_package_guard_and_three_exchange_replay(self):
        raw=batch_fixture.boot(self.report);self.assertTrue(core.boot_ready(raw,self.report))
        output=io.BytesIO();output.write(raw);state=dict(checks=[core.CHECKS[0]],exchanges=[],transmitted_bytes=0)
        nonce=batch_fixture.NONCE
        def exchange(fd,out,command,expected,progress,deadline):
            if command==core.IDENTITY:value=prior.identity_bytes(self.receipt)+b'\nxnu:/# '
            elif command==core.batch_command(nonce):value=batch_fixture.batch(self.files)
            else:value=b'\n'+expected[0]+b'\nxnu:/# '
            out.write(value);progress['transmitted_bytes']+=len(command)+1;return value
        with patch.object(core.secrets,'token_hex',return_value=nonce[1:]),patch.object(core,'bounded_exchange',side_effect=exchange),\
            patch.object(core,'drain_pending',return_value=b''):
            core.commands(-1,output,state,self.receipt,self.files,lambda:None,time.monotonic()+120)
        state['return_capture_offset']=output.tell()
        output.write(b'\nRPi: BOOTSYS release VERSION: fixture\nBOOT_ORDER override: 0x000000f6\nRPi: BOOTLOADER release VERSION: fixture\nBoot mode: NVME (06)\n')
        raw=output.getvalue();installed={'fixture':True}
        state.update(status='passed',baud=115200,device='/dev/cu.usbmodem102',preflight=self.report,installation=installed,
            bytes=len(raw),serial_sha256=sha(raw),source_sha256=recorder.source_pins(),
            package_evidence_sha256=recorder.package_evidence_pins(PACKAGE),
            independent_linux_return_verified=False,ssh_daemon=False,networking=False,controller_initialized=False,durability=False,
            command_tests_passed=True,normal_nvme_boot_observed=True,started_utc='2026-10-13T00:00:00+00:00',ended_utc='2026-10-13T00:03:30+00:00',
            commands_complete_seconds_after_admission=26,return_seconds_after_admission=187)
        result=audit.replay(state,raw,self.report,installed,self.receipt)
        self.assertEqual(result['runtime_identity']['file_hashes'],29);self.assertTrue(result['batch']['batch_process_exit_verified'])
        for marker in (core.WATCHDOG,self.report['trial_marker'].encode(),core.CRYPTO_PASS):
            changed=raw.replace(marker,b'X'*len(marker));bad=dict(state,serial_sha256=sha(changed))
            with self.assertRaises((ValueError,RuntimeError)):audit.replay(bad,changed,self.report,installed,self.receipt)

    def test_launch_adapter_binds_armed_package_and_executes_only_one_simulated_ssh(self):
        from tools.rpi5 import arm_root41_reboot as launcher
        from types import SimpleNamespace
        boot='386225a6-2f95-4b53-a0e5-f6f6c56327f7';installed={'directory':'fixture','plan_sha256':'a'*64,'result_sha256':'b'*64}
        with tempfile.TemporaryDirectory(prefix='root41-launch-fixture-',dir=ROOT/'build/rpi5') as temporary:
            install=Path(temporary);capture=ROOT/'build/rpi5'/('capture-'+install.name);out=ROOT/'build/rpi5'/('launch-'+install.name)
            plan=dict(package=str(PACKAGE),linux_boot_id=boot,identity_binding={'expected':{'root':'/dev/nvme0n1p2 ext4 root-uuid'}})
            (install/'plan.json').write_text(json.dumps(plan));installed['directory']=str(install)
            pins=recorder.source_pins();packages=recorder.package_evidence_pins(PACKAGE)
            def armed_once(directory,command,expected,validate,reboot):
                directory.mkdir();capture.mkdir()
                self.assertIn('--boot-wait-seconds',command);self.assertIn('600',command);self.assertIn(str(PACKAGE),command)
                self.assertEqual(expected,recorder.armed_line(self.report))
                armed=dict(pid=17,installation=installed,transmitted_bytes=0,device='/dev/cu.usbmodem102',baud=115200,
                    source_sha256=pins,preflight=self.report,checks=[],exchanges=[],receipt_evidence_sha256={},package_evidence_sha256=packages)
                (capture/'armed.json').write_text(json.dumps(armed));self.assertEqual(validate(17)['pid'],17)
                armed['package_evidence_sha256']={};(capture/'armed.json').write_text(json.dumps(armed))
                with self.assertRaises(ValueError):validate(17)
                return dict(result=reboot())
            try:
                with patch.object(launcher.recorder.package,'inspect',return_value=self.report),\
                    patch.object(launcher.recorder,'installation',return_value=installed),\
                    patch.object(launcher.recorder,'receipt_evidence_pins',return_value={}),\
                    patch.object(launcher,'arm_once',side_effect=armed_once),\
                    patch.object(launcher.subprocess,'run',return_value=SimpleNamespace(stdout='VERIFIED_SSD_LINUX_REBOOT_ONCE fixture\n',stderr='',returncode=0)) as remote:
                    self.assertEqual(launcher.main(['--installation',str(install),'--device','/dev/cu.usbmodem102',
                        '--capture',str(capture),'--output',str(out),'--linux-boot-id',boot]),0)
                    self.assertEqual(remote.call_count,1)
                    source=remote.call_args.kwargs['input'];self.assertIn(boot,source);self.assertIn('/dev/nvme0n1p2',source)
            finally:
                # These are exclusively created temporary fixture directories.
                for directory in (capture,out):
                    if directory.exists():shutil.rmtree(directory)

    def test_actual_110_baseline_and_new_114_118_typed_receipts(self):
        baseline_name=os.environ.get('RPI5_ROOT41_BASELINE')
        if not baseline_name:self.skipTest('RPI5_ROOT41_BASELINE selects the actual completed trace restoration')
        baseline=Path(baseline_name).resolve()
        before=json.loads((baseline/'result.json').read_text());boot=before['identity']['boot_id']
        next_boot='1e4ef406-901b-451a-b36d-8568df37a0a8'
        plan=stage.load_plan('install',boot,baseline,PACKAGE)
        self.assertEqual(len(plan['nvme_backups']),110)
        historical=recorder.receipt_evidence_pins(baseline)
        def receipt(p):
            files=dict(p['protected_files']);files['probe.bin']=p['new_sha256']
            return dict(status='complete',profile=p['profile'],run=p['run'],
                identity=dict(identity=p['identity_binding']['expected'],boot_id=p['linux_boot_id'],hostname='kamidana'),
                protected_files_sha256=files,nvme_backups_verified=p['nvme_backups'],
                archived_file='probe.bin',previous_file_name='previous.bin',previous_file_sha256=p['old_sha256'],previous_file_bytes=p['old_bytes'],
                deleted_files=[],replaced_files=['probe.bin'],retained_sd_backup=media.RETAINED,
                retained_sd_backup_sha256=media.GOOD_SHA,firmware_sha256=media.FIRMWARE_SHA,
                boot_unmounted=True,no_config_change=True,no_firmware_change=True,no_hfs_mount=True,no_reboot=True,
                power_loss_atomicity_claimed=False,no_implicit_retry_or_rollback=True,
                backups=[dict(device=node,bytes=length,sha256=p['protected_sha256'][key],saved_as=name)
                    for key,node,_,length,name in stage.base.core.EXTENTS],
                protected_after={key:dict(device=node,bytes=length,sha256=p['protected_sha256'][key])
                    for key,node,_,length,_ in stage.base.core.EXTENTS})
        # Real prior chain was fully validated above; isolate new transitions and
        # retain byte pins instead of repeatedly traversing historical validators.
        with tempfile.TemporaryDirectory(prefix='root96-fdt-fixture-',dir=ROOT/'build/rpi5') as name,patch.object(stage.preceding,'validate_result',return_value=None),patch.object(stage.package,'inspect',return_value=self.report):
            directory=Path(name);plan['run']='/home/sandrzej/xnu-root96-12345678';result=receipt(plan)
            archive=directory/'source-snapshots';archive.mkdir()
            for source in plan['source_sha256']:shutil.copyfile(source,archive/Path(source).name)
            (directory/'plan.json').write_text(json.dumps(plan));(directory/'result.json').write_text(json.dumps(result))
            stage.validate_result(result,plan);compile(stage.remote_source(plan),'<corrected-root96>','exec')
            recorder.installation(directory,self.report)
            restore=stage.load_plan('restore',next_boot,directory)
            restore['run']='/home/sandrzej/xnu-root96-87654321';restored=receipt(restore)
            stage.validate_result(restored,restore)
            self.assertEqual(len(restore['nvme_backups']),114)
            self.assertEqual(len(stage.inherited(restore,restored,118)),118)
            with self.assertRaises(ValueError):stage.validate_result(dict(result,boot_unmounted=1),plan)
            with self.assertRaises(ValueError):stage.load_plan('reclaim',boot,baseline)
        self.assertEqual(recorder.receipt_evidence_pins(baseline),historical)


if __name__=='__main__':unittest.main()

