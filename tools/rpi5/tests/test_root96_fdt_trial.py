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
from tools.rpi5 import stage_root96_fdt_trial as stage
from tools.rpi5 import serial_root96_fdt_trial as recorder
from tools.rpi5 import audit_root96_fdt_trial as audit
from tools.rpi5.tests import test_root96_trial as prior
core,media=recorder.core,stage.core
ROOT=stage.ROOT
PACKAGE=ROOT/'build/rpi5/root96-fdt-euspad_2'
sha=lambda data:hashlib.sha256(data).hexdigest()


def boot_bytes(report):
    return prior.boot_bytes(report).replace(core.t.TERMINAL_LOADER,
        b'\n'.join((core.t.TERMINAL_LOADER,core.DEVICE,core.FDT)))


class CorrectedAdapters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=recorder.package.inspect(PACKAGE)
        cls.receipt=json.loads(Path(cls.report['root_manifest']).read_text())

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

    def test_actual_package_requires_emitted_device_and_fdt_before_any_tx(self):
        report=self.report;raw=boot_bytes(report)
        self.assertTrue(report['preflight_pass']);self.assertTrue(core.boot_ready(raw,report))
        self.assertFalse(core.boot_ready(raw.replace(core.t.READY,b''),report))
        for bad in (raw.replace(core.DEVICE,b''),raw.replace(core.FDT,b''),raw+core.FDT,
                    raw.replace(core.DEVICE,b'TEMP').replace(core.FDT,core.DEVICE).replace(b'TEMP',core.FDT)):
            with self.assertRaises(RuntimeError):core.boot_ready(bad,report)
        altered=copy.deepcopy(report);altered['handoff']['linked_loader_handoff']=False
        with self.assertRaises(RuntimeError):core.boot_ready(raw,altered)
        self.assertEqual(stage.original.core.MODES[1],'root96-install-v1')
        self.assertEqual(recorder.original.package.__name__,'check_root96_ssh_package')

    def test_all_22_files_zsh_buffer_and_recovery_replay_through_new_adapter(self):
        output=io.BytesIO();output.write(boot_bytes(self.report))
        state=dict(checks=[core.CHECKS[0]],exchanges=[],transmitted_bytes=0)
        def exchange(fd,stream,command,expected,state,deadline):
            startup=b'DARWIN:ZSH:ENTRY\nDARWIN:ZSH:TSD\nDARWIN:ZSH:ENTROPY\nDARWIN:ZSH:MAIN\n'
            content=startup+prior.identity_bytes(self.receipt) if command==core.IDENTITY else b'\n'.join(expected)
            raw=command.encode()+b'\n'+content+b'\nxnu:/# '
            stream.write(raw);state['transmitted_bytes']+=len(command)+1;return raw
        with patch.object(core.original,'bounded_exchange',side_effect=exchange),patch.object(core.original.select,'select',return_value=([],[],[])):
            core.commands(-1,output,state,self.receipt,lambda:None,time.monotonic()+120)
        state['return_capture_offset']=output.tell()
        output.write(b'\nRPi: BOOTSYS release VERSION: fixture\nBOOT_ORDER override: 0x000000f6\nRPi: BOOTLOADER release VERSION: fixture\nBoot mode: NVME (06)\n')
        raw=output.getvalue();installed={'fixture':True}
        state.update(status='passed',baud=115200,device='/dev/cu.usbmodem102',preflight=self.report,installation=installed,
            bytes=len(raw),serial_sha256=sha(raw),source_sha256=recorder.source_pins(),
            independent_linux_return_verified=False,ssh_daemon=False,networking=False,controller_initialized=False,durability=False,
            command_tests_passed=True,normal_nvme_boot_observed=True,started_utc='2026-10-13T00:00:00+00:00',ended_utc='2026-10-13T00:03:30+00:00',
            commands_complete_seconds_after_admission=20,return_seconds_after_admission=192)
        result=audit.replay(state,raw,self.report,installed,self.receipt)
        self.assertEqual(result['runtime_identity']['file_hashes'],22)
        self.assertTrue(result['original_zsh_script_passed']);self.assertTrue(result['ssh_buffer_roundtrip_reset_reuse_passed'])
        self.assertFalse(result['ssh_daemon']);self.assertFalse(result['networking'])
        for marker in (core.FDT,core.PASS):
            broken=raw.replace(marker,b'X'*len(marker));bad=dict(state,serial_sha256=sha(broken))
            with self.assertRaises((ValueError,RuntimeError)):audit.replay(bad,broken,self.report,installed,self.receipt)

    def test_actual_92_baseline_and_new_96_100_typed_receipts(self):
        baseline_name=os.environ.get('RPI5_ROOT96_FDT_BASELINE')
        if not baseline_name:self.skipTest('RPI5_ROOT96_FDT_BASELINE selects the actual completed ID restoration')
        baseline=Path(baseline_name).resolve()
        before=json.loads((baseline/'result.json').read_text());boot=before['identity']['boot_id']
        next_boot='1e4ef406-901b-451a-b36d-8568df37a0a8'
        plan=stage.load_plan('install',boot,baseline,PACKAGE)
        self.assertEqual(len(plan['nvme_backups']),92)
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
        with tempfile.TemporaryDirectory(prefix='root96-fdt-fixture-',dir=ROOT/'build/rpi5') as name,patch.object(stage.preceding,'validate_result',return_value=None):
            directory=Path(name);plan['run']='/home/sandrzej/xnu-root96-12345678';result=receipt(plan)
            archive=directory/'source-snapshots';archive.mkdir()
            for source in plan['source_sha256']:shutil.copyfile(source,archive/Path(source).name)
            (directory/'plan.json').write_text(json.dumps(plan));(directory/'result.json').write_text(json.dumps(result))
            stage.validate_result(result,plan);compile(stage.remote_source(plan),'<corrected-root96>','exec')
            recorder.installation(directory,self.report)
            restore=stage.load_plan('restore',next_boot,directory)
            restore['run']='/home/sandrzej/xnu-root96-87654321';restored=receipt(restore)
            stage.validate_result(restored,restore)
            self.assertEqual(len(restore['nvme_backups']),96)
            self.assertEqual(len(stage.inherited(restore,restored,100)),100)
            with self.assertRaises(ValueError):stage.validate_result(dict(result,boot_unmounted=1),plan)
            with self.assertRaises(ValueError):stage.load_plan('reclaim',boot,baseline)
        self.assertEqual(recorder.receipt_evidence_pins(baseline),historical)


if __name__=='__main__':unittest.main()
