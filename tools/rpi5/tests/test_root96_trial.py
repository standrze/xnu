# SPDX-License-Identifier: BSD-2-Clause
"""Actual file mutation tests and UART fixtures, never hardware or target exec."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import time
import types
import tempfile
import unittest
from unittest.mock import patch
from tools.rpi5.tests import test_watchdog_recovery_install as fixture_base
from tools.rpi5 import root96_media_core as media
from tools.rpi5 import stage_root96_trial as stage
from tools.rpi5 import check_root96_ssh_package as package
from tools.rpi5 import serial_root96_trial as recorder
from tools.rpi5 import audit_root96_trial as audit
core=recorder.core
ROOT=stage.ROOT
GOOD=ROOT/'build/rpi5/bl33-probe-vszhh6o4/probe.bin'
FIRMWARE=ROOT/'build/rpi5/tfa-candidate/build/rpi5/debug/bl31.bin'
PACKAGE=ROOT/'build/rpi5/bl33-probe-gm1ci0lg'
BASELINE=ROOT/'build/rpi5/fwabi-reuse-pair-restored-20261013'
BOOT='54e0eebb-058e-4954-91b1-b1fed9aa37bd'
sha=lambda b:hashlib.sha256(b).hexdigest()


class MediaTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self,mode=media.MODES[0]):
        with fixture_base.RecoveryInstallTests.fixture(self) as row:
            plan,capture,snapshots,run,state,boot,work,old,new=row
            for name in ('probe.bin',media.RETAINED,media.REDUNDANT):shutil.copyfile(GOOD,boot/name)
            shutil.copyfile(FIRMWARE,boot/'bl31.bin')
            plan.update(profile=mode,old_sha256=media.GOOD_SHA,new_sha256=media.GOOD_SHA,
                old_bytes=media.GOOD_BYTES,new_bytes=media.GOOD_BYTES)
            if mode==media.MODES[0]:(work/'candidate.bin').unlink()
            else:
                (boot/media.REDUNDANT).unlink()
                if mode==media.MODES[1]:plan.update(new_sha256=sha(new),new_bytes=len(new))
                else:
                    (boot/'probe.bin').write_bytes(new);shutil.copyfile(GOOD,work/'candidate.bin')
                    plan.update(old_sha256=sha(new),old_bytes=len(new))
            # Path.iterdir on boot is deliberately doubled as empty-unmounted.
            names=['probe.bin','config.txt',media.RETAINED,'bl31.bin']+([media.REDUNDANT] if mode==media.MODES[0] else [])
            plan['protected_files']={name:sha((boot/name).read_bytes()) for name in names}
            yield plan,capture,snapshots,run,state,boot,work,new

    def execute(self,row):
        p,c,s,r,*_=row
        return media.execute(p,c,fixture_base.helper,s,fixture_base.reference,fixture_base.core,r)

    def test_exact_reclaim_preserves_active_and_retained_with_verified_ssd_archive(self):
        with self.fixture() as row:
            p,c,s,r,state,boot,work,new=row
            before={n:(boot/n).stat().st_ino for n in ('probe.bin',media.RETAINED)}
            result=self.execute(row)
            self.assertFalse((boot/media.REDUNDANT).exists());self.assertFalse(state['mounted'])
            self.assertEqual(result['deleted_files'],[media.REDUNDANT])
            self.assertEqual(sha((work/'previous.bin').read_bytes()),media.GOOD_SHA)
            for n,inode in before.items():
                self.assertEqual((boot/n).stat().st_ino,inode);self.assertEqual(sha((boot/n).read_bytes()),media.GOOD_SHA)
            self.assertTrue((work/'media-before-exact-unlink.json').exists())
            self.assertTrue((work/'media-after-exact-unlink.json').exists())

    def test_wrong_missing_symlink_or_unprotected_alias_never_deleted(self):
        for fault in ('hash','size','missing','symlink','unprotected'):
            with self.subTest(fault=fault),self.fixture() as row:
                p,c,s,r,state,boot,work,new=row;target=boot/media.REDUNDANT
                if fault=='hash':target.write_bytes(b'X'*media.GOOD_BYTES)
                if fault=='size':target.write_bytes(b'X')
                if fault in ('missing','symlink'):target.unlink()
                if fault=='symlink':target.symlink_to(boot/media.RETAINED)
                if fault=='unprotected':del p['protected_files'][media.REDUNDANT]
                with self.assertRaises((ValueError,OSError)):self.execute(row)
                self.assertFalse((work/'media-before-exact-unlink.json').exists())
                self.assertEqual(sha((boot/'probe.bin').read_bytes()),media.GOOD_SHA)
                self.assertEqual(sha((boot/media.RETAINED).read_bytes()),media.GOOD_SHA)
                self.assertFalse(state['mounted'])

    def test_archive_failure_no_delete_and_post_unlink_failure_never_retries(self):
        with self.fixture() as row,patch.object(fixture_base.helper,'copy_image',side_effect=ValueError('archive fault')):
            with self.assertRaisesRegex(ValueError,'archive fault'):self.execute(row)
            self.assertTrue((row[5]/media.REDUNDANT).exists());self.assertFalse(row[4]['mounted'])
        real=os.unlink
        with self.fixture() as row:
            def fail(name,*args,**kwargs):
                real(name,*args,**kwargs)
                if name==media.REDUNDANT:raise ValueError('after unlink')
            with patch.object(media.os,'unlink',side_effect=fail) as unlink:
                with self.assertRaisesRegex(ValueError,'after unlink'):self.execute(row)
                self.assertEqual(unlink.call_count,1)
            self.assertFalse((row[5]/media.REDUNDANT).exists());self.assertFalse((row[6]/'result.json').exists())
            self.assertEqual(sha((row[5]/media.RETAINED).read_bytes()),media.GOOD_SHA)
            self.assertFalse(row[4]['mounted'])

    def test_install_and_restore_use_ssd_archive_without_extra_fat_backup(self):
        for mode in media.MODES[1:]:
            with self.subTest(mode=mode),self.fixture(mode) as row:
                p,c,s,r,state,boot,work,new=row;old=(boot/'probe.bin').read_bytes()
                result=self.execute(row)
                self.assertEqual((work/'previous.bin').read_bytes(),old)
                self.assertEqual(sha((boot/'probe.bin').read_bytes()),p['new_sha256'])
                self.assertEqual(sha((boot/media.RETAINED).read_bytes()),media.GOOD_SHA)
                self.assertFalse((boot/media.REDUNDANT).exists());self.assertFalse(state['mounted'])
                self.assertEqual(result['replaced_files'],['probe.bin']);self.assertFalse(result['deleted_files'])

    def test_space_failure_happens_before_any_sd_publication(self):
        with self.fixture(media.MODES[1]) as row,patch.object(media.os,'fstatvfs',return_value=types.SimpleNamespace(f_bavail=1,f_frsize=1)):
            with self.assertRaisesRegex(ValueError,'FAT temporary'):self.execute(row)
            self.assertEqual(sha((row[5]/'probe.bin').read_bytes()),media.GOOD_SHA)
            self.assertFalse((row[6]/'previous.bin').exists());self.assertFalse(row[4]['mounted'])

    def test_exception_cleanup_rechecks_owner_after_readonly_remount(self):
        with self.fixture() as row:
            original=fixture_base.core.mount_record
            current_lookups=[0]
            def lookup(run,mode=None,required=True):
                result=original(run,mode,required)
                if result and row[4]['mode']=='ro' and (row[6]/'media-before-exact-unlink.json').exists():
                    current_lookups[0]+=1
                    if current_lookups[0]>0:result['id']+=1
                return result
            with (patch.object(media.os,'unlink',side_effect=ValueError('before unlink')),
                  patch.object(fixture_base.core,'mount_record',side_effect=lookup)):
                with self.assertRaisesRegex(ValueError,'Foreign mount after remount'):self.execute(row)
            self.assertTrue(row[4]['mounted']);self.assertTrue((row[5]/media.REDUNDANT).exists())
            self.assertNotIn('umount',[c[0] for c in row[4]['commands']])


def boot_bytes(report):
    return b'\n'.join([b'Boot mode: SD (01)',b'Read probe.bin bytes '+str(report['image_bytes']).encode()+b' hnd 0',
        core.t.ENTRY,core.t.TERMINAL_LOADER,report['root_copy_marker'].encode(),report['kernel_copy_marker'].encode(),
        core.t.package_check.TOPOLOGY_PASS,core.t.TRANSFER,core.prior.COMMIT,
        b'RPI5XNU:TERMINAL:WATCHDOG SECONDS=180',report['root_mount_marker'].encode(),core.t.READY,b'xnu:/# '])


def identity_bytes(receipt):
    lines=['ROOTIDENTITY:BEGIN:FIXED_CATALOG_V1',f'ROOTIDENTITY:MOUNT:mockfs:/:READONLY:NODES={receipt["output_nodes"]}:BYTES={receipt["output_bytes"]}']
    for row in receipt['identity_catalog']:
        if row['path']=='/dev':lines.append('ROOTIDENTITY:OVERLAY:/dev:devfs')
        elif not row['sha256']:lines.append(f'ROOTIDENTITY:DIR:{row["path"]}:MODE={row["mode"]}')
        else:lines.append(f'ROOTIDENTITY:FILE:{row["path"]}:MODE={row["mode"]}:BYTES={row["bytes"]}:SHA256={row["sha256"]}')
    lines+=['ROOTIDENTITY:PASS:COMPARE_SELF_AND_EXTENT_EXTERNALLY','ROOT_IDENTITY_STATUS:0']
    return '\n'.join(lines).encode()


class SerialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=package.inspect(PACKAGE)
        cls.receipt=json.loads(Path(cls.report['root_manifest']).read_text())

    def test_real_bounded_package_and_distinct_zero_tx_boot_guard(self):
        self.assertTrue(self.report['preflight_pass']);self.assertEqual(self.report['terminal_watchdog_seconds'],180)
        raw=boot_bytes(self.report);self.assertTrue(core.boot_ready(raw,self.report))
        for broken in (raw.replace(b'SECONDS=180',b'SECONDS=3600'),raw.replace(core.t.READY,b'')):
            self.assertFalse(core.boot_ready(broken,self.report))
        for broken in (raw+core.t.ENTRY,raw.replace(b'Boot mode: SD (01)',b'Boot mode: NVME (06)')+b'Boot mode: SD (01)'):
            with self.assertRaises(RuntimeError):core.boot_ready(broken,self.report)
        with self.assertRaises(ValueError):package.inspect(ROOT/'build/rpi5/bl33-probe-ke8q4far')

    def transcript(self):
        output=io.BytesIO();output.write(boot_bytes(self.report))
        state=dict(checks=[core.CHECKS[0]],exchanges=[],transmitted_bytes=0)
        startup=b'DARWIN:ZSH:ENTRY\nDARWIN:ZSH:TSD\nDARWIN:ZSH:ENTROPY\nDARWIN:ZSH:MAIN\n'
        def exchange(fd,stream,command,expected,state,deadline):
            if command==core.IDENTITY:content=startup+identity_bytes(self.receipt)
            else:content=b'\n'.join(expected)
            raw=command.encode()+b'\n'+content+b'\nxnu:/# '
            stream.write(raw);state['transmitted_bytes']+=len(command)+1
            return raw
        with patch.object(core,'bounded_exchange',side_effect=exchange),patch.object(core.select,'select',return_value=([],[],[])):
            core.commands(-1,output,state,self.receipt,lambda:None,time.monotonic()+120)
        state['return_capture_offset']=output.tell()
        output.write(b'\nRPi: BOOTSYS release VERSION: x\nBOOT_ORDER override: 0x000000f6\nRPi: BOOTLOADER release VERSION: x\nBoot mode: NVME (06)\n')
        raw=output.getvalue();installed={'fixture':True}
        state.update(status='passed',baud=115200,device='/dev/cu.usbmodem102',preflight=self.report,installation=installed,
            bytes=len(raw),serial_sha256=sha(raw),source_sha256=recorder.source_pins(),
            independent_linux_return_verified=False,ssh_daemon=False,networking=False,controller_initialized=False,durability=False,
            command_tests_passed=True,normal_nvme_boot_observed=True,started_utc='2026-10-13T00:00:00+00:00',ended_utc='2026-10-13T00:03:30+00:00',
            commands_complete_seconds_after_admission=20,return_seconds_after_admission=192)
        return state,raw,installed

    def test_complete_22_file_real_command_plan_replay_and_negative_controls(self):
        state,raw,installed=self.transcript()
        result=audit.replay(state,raw,self.report,installed,self.receipt)
        self.assertEqual(result['runtime_identity']['file_hashes'],22)
        for key,value in (('transmitted_bytes',0),('commands_complete_seconds_after_admission',121),('return_seconds_after_admission',float('nan'))):
            bad=copy.deepcopy(state);bad[key]=value
            with self.assertRaises(ValueError):audit.replay(bad,raw,self.report,installed,self.receipt)
        bad=raw.replace(core.PASS,b'X'*len(core.PASS));changed=copy.deepcopy(state);changed['serial_sha256']=sha(bad)
        with self.assertRaises(ValueError):audit.replay(changed,bad,self.report,installed,self.receipt)

    def test_pending_reset_and_expired_budget_never_transmit(self):
        with self.assertRaises(ValueError):core.pending_safe(b'RPi: BOOTSYS release VERSION: reset\n')
        core.pending_safe(b'RPI5XNU:TERMINAL:WATCHDOG_KICK RELOADS=12\n')
        with patch.object(core,'bounded_exchange') as send:
            with self.assertRaises(TimeoutError):core.commands(-1,io.BytesIO(),dict(checks=[],exchanges=[]),self.receipt,lambda:None,time.monotonic())
            send.assert_not_called()
        with patch.object(core.os,'write') as write:
            with self.assertRaises(TimeoutError):core.bounded_exchange(-1,io.BytesIO(),'echo hi',[b'hi'],dict(transmitted_bytes=0),time.monotonic()-1)
            write.assert_not_called()

    def test_fragmented_pending_watchdog_and_readiness_are_retained(self):
        chunks=[b'RPI5XNU:TERMINAL:WATCH',b'DOG_KICK RELOADS=12\n',b'\nRPI5XNU:SHELL:READY\nxnu:/',b'# ']
        expected=b''.join(chunks);output=io.BytesIO()
        def ready(*args):return ([1],[],[]) if chunks else ([],[],[])
        def receive(fd,stream,deadline):
            chunk=chunks.pop(0);stream.write(chunk);return chunk
        with patch.object(core.select,'select',side_effect=ready),patch.object(core.t.shell,'receive',side_effect=receive):
            self.assertEqual(core.drain_pending(1,output,time.monotonic()+1),expected)
        self.assertEqual(output.getvalue(),expected)

    def test_actual_restored_70_artifact_plan_and_remote_program_no_hardware(self):
        plan=stage.load_plan('reclaim',BOOT,BASELINE)
        self.assertEqual(len(plan['nvme_backups']),70);self.assertEqual(plan['protected_files'][media.REDUNDANT],media.GOOD_SHA)
        plan['run']='/home/sandrzej/xnu-root96-12345678'
        compile(stage.remote_source(plan),'<root96-remote>','exec')

    def test_fresh_receipt_hash_revalidation_and_independent_return_negative_controls(self):
        pins=recorder.receipt_evidence_pins(BASELINE)
        self.assertGreater(len(pins),20)
        self.assertTrue(all(stage.sha(Path(name))==digest for name,digest in pins.items()))
        plan=stage.load_plan('reclaim',BOOT,BASELINE);observed={'serial_sha256':'1'*64};installed={'directory':'fixture'}
        newboot='6414505b-8757-410f-84ef-cbf640efca6d'
        returned=dict(host=plan['host'],boot_id=newboot,
            identity=dict(identity=plan['identity_binding']['expected'],boot_id=newboot,hostname='kamidana'),
            root=plan['identity_binding']['expected']['root'].split(),bootloader={'boot-mode':6,'partition':1,'tryboot':0},
            sd_partitions_unmounted=True,read_only=True,installation=installed,serial_sha256=observed['serial_sha256'],
            return_source_sha256=audit.return_source_pins(),observed_utc='2026-10-13T00:04:00+00:00')
        self.assertEqual(audit.inspect_return(returned,plan,installed,observed),newboot)
        for key,value in (('boot_id',BOOT),('sd_partitions_unmounted',1),('bootloader',{'boot-mode':1,'partition':1,'tryboot':0})):
            bad=copy.deepcopy(returned);bad[key]=value
            with self.assertRaises(ValueError):audit.inspect_return(bad,plan,installed,observed)

    def test_receipt_transitions_70_74_78_82_and_typed_rejection(self):
        def receipt(plan):
            files=dict(plan['protected_files']);reclaim=plan['operation']=='reclaim'
            if reclaim:del files[media.REDUNDANT]
            else:files['probe.bin']=plan['new_sha256']
            return dict(status='complete',profile=plan['profile'],run=plan['run'],
                identity=dict(identity=plan['identity_binding']['expected'],boot_id=plan['linux_boot_id'],hostname='kamidana'),
                protected_files_sha256=files,nvme_backups_verified=plan['nvme_backups'],
                archived_file=media.REDUNDANT if reclaim else 'probe.bin',previous_file_name='previous.bin',
                previous_file_sha256=plan['old_sha256'],previous_file_bytes=plan['old_bytes'],
                deleted_files=[media.REDUNDANT] if reclaim else [],replaced_files=[] if reclaim else ['probe.bin'],
                retained_sd_backup=media.RETAINED,retained_sd_backup_sha256=media.GOOD_SHA,firmware_sha256=media.FIRMWARE_SHA,
                boot_unmounted=True,no_config_change=True,no_firmware_change=True,no_hfs_mount=True,no_reboot=True,
                power_loss_atomicity_claimed=False,no_implicit_retry_or_rollback=True,
                backups=[dict(device=node,bytes=length,sha256=plan['protected_sha256'][key],saved_as=name)
                    for key,node,_,length,name in stage.base.core.EXTENTS],
                protected_after={key:dict(device=node,bytes=length,sha256=plan['protected_sha256'][key])
                    for key,node,_,length,_ in stage.base.core.EXTENTS})
        with contextlib.ExitStack() as stack:
            baseline=BASELINE
            for i,operation in enumerate(('reclaim','install','restore')):
                directory=Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='root96-receipt-fixture-',dir=ROOT/'build/rpi5')))
                plan=stage.load_plan(operation,BOOT if i<2 else '6414505b-8757-410f-84ef-cbf640efca6d',baseline,PACKAGE if i==1 else None)
                self.assertEqual(len(plan['nvme_backups']),70+4*i)
                plan['run']='/home/sandrzej/xnu-root96-'+str(i)*8;result=receipt(plan)
                archive=directory/'source-snapshots';archive.mkdir()
                for p in plan['source_sha256']:shutil.copyfile(p,archive/Path(p).name)
                (directory/'plan.json').write_text(json.dumps(plan));(directory/'result.json').write_text(json.dumps(result))
                stage.validate_result(result,plan)
                bad=copy.deepcopy(result);bad['boot_unmounted']=1
                with self.assertRaises(ValueError):stage.validate_result(bad,plan)
                self.assertEqual(len(stage.inherited(plan,result,74+4*i)),74+4*i)
                baseline=directory


if __name__=='__main__':unittest.main()
