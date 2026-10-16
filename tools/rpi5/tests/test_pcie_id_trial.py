# SPDX-License-Identifier: BSD-2-Clause
"""Distinct RP1-ID pair preservation, receive-only protocol, and receipt fixtures."""
import contextlib
import copy
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import types
import tempfile
import unittest
from unittest.mock import patch
from tools.rpi5 import pcie_id_pair_core as core
from tools.rpi5 import pcie_id_serial_core as protocol
from tools.rpi5.tests import test_pcie_fw_install as prior

ROOT=Path(__file__).resolve().parents[3]
GOOD=ROOT/'build/rpi5/bl33-probe-vszhh6o4/probe.bin'
digest=lambda b:hashlib.sha256(b).hexdigest()


class PairTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self,restore=False):
        with prior.FirmwarePairInstallTests.fixture(self,'pcie-id-pair-restore-v1' if restore else 'pcie-id-pair-trial-v1') as row:
            plan,_,_,_,_,boot,work,*_=row
            shutil.copyfile(GOOD,boot/core.REUSED_ZSH_BACKUP)
            plan['protected_files'][core.REUSED_ZSH_BACKUP]=core.GOOD_ZSH_SHA
            target=work/'candidate-probe.bin' if restore else boot/'probe.bin'
            shutil.copyfile(GOOD,target)
            plan['files'][1].update({'new_sha256' if restore else 'old_sha256':core.GOOD_ZSH_SHA,
                'new_bytes' if restore else 'old_bytes':core.GOOD_ZSH_BYTES})
            yield row

    def execute(self,row):
        p,c,s,r,*_=row
        return core.execute(p,c,prior.watch.helper,s,prior.watch.reference,prior.watch.core,r)

    def test_trial_reuses_exact_good_copy_and_restore_archives_trial_on_ssd_only(self):
        for restore in (False,True):
            with self.subTest(restore=restore),self.fixture(restore) as row:
                plan,_,_,_,state,boot,work,*_=row
                old=(boot/'probe.bin').read_bytes();new=(work/'candidate-probe.bin').read_bytes()
                retained=(boot/core.REUSED_ZSH_BACKUP).stat();calls=[];copy=prior.watch.helper.copy_image
                def record(src,fd,name,sha):calls.append(name);return copy(src,fd,name,sha)
                with patch.object(prior.watch.helper,'copy_image',side_effect=record):result=self.execute(row)
                self.assertNotIn(core.REUSED_ZSH_BACKUP,calls);self.assertEqual(len(calls),5)
                self.assertEqual((boot/core.REUSED_ZSH_BACKUP).stat().st_ino,retained.st_ino)
                self.assertEqual((boot/'probe.bin').read_bytes(),new)
                self.assertEqual((work/core.NAMES[plan['profile']]['probe.bin'][2]).read_bytes(),old)
                self.assertEqual(result['preserved_pair']['probe.bin']['sd_backup'],None if restore else core.REUSED_ZSH_BACKUP)
                self.assertFalse(state['mounted']);self.assertNotIn(None,result['protected_files_sha256'])
                self.assertEqual(result['pair_publication_order'],['bl31.bin','probe.bin'])

    def test_space_counts_no_duplicate_19_or_20_megabyte_loader(self):
        for restore in (False,True):
            with self.subTest(restore=restore),self.fixture(restore) as row:
                plan=row[0]
                allbytes=sum(r['new_bytes']+r['old_bytes'] for r in plan['files'])+1024*1024
                self.assertEqual(allbytes-core.fat_space_required(plan),plan['files'][1]['old_bytes'])
                required=core.fat_space_required(plan)
                with patch.object(core.os,'fstatvfs',return_value=types.SimpleNamespace(f_bavail=required-1,f_frsize=1)):
                    with self.assertRaisesRegex(ValueError,'FAT space'):self.execute(row)
                self.assertFalse(row[4]['mounted'])

    def test_wrong_retained_backup_is_rejected_in_both_directions(self):
        for restore in (False,True):
            with self.subTest(restore=restore),self.fixture(restore) as row:
                (row[5]/core.REUSED_ZSH_BACKUP).write_bytes(b'wrong')
                with patch.object(prior.watch.helper,'copy_image',side_effect=AssertionError('No copy before exact retained verification')):
                    with self.assertRaises(ValueError):self.execute(row)
                self.assertFalse(row[4]['mounted'])

    def test_all_five_copy_failures_precede_either_publication_and_never_retry(self):
        real=prior.watch.helper.copy_image
        for restore in (False,True):
            for failure in range(1,6):
                with self.subTest(restore=restore,copy=failure),self.fixture(restore) as row:
                    old={(n):(row[5]/n).read_bytes() for n in core.TARGETS};calls=[0]
                    def copy(*args):
                        calls[0]+=1
                        if calls[0]==failure:raise ValueError('copy fault')
                        return real(*args)
                    with patch.object(prior.watch.helper,'copy_image',side_effect=copy),patch.object(core.os,'rename',wraps=os.rename) as rename:
                        with self.assertRaisesRegex(ValueError,'copy fault'):self.execute(row)
                        rename.assert_not_called()
                    self.assertEqual(old,{n:(row[5]/n).read_bytes() for n in core.TARGETS})
                    self.assertFalse(row[4]['mounted'])


class SerialProtocolTests(unittest.TestCase):
    def fixture(self):
        report=dict(image_bytes=20000000,boot_markers=['RPI5XNU:FIXTURE:EXACT_HANDOFF'])
        lines=[b'Boot mode: SD (01)',b'Read probe.bin bytes 20000000 hnd 0',protocol.ENTRY,
            report['boot_markers'][0].encode(),protocol.TRANSFER,protocol.COMMIT,protocol.BEGIN,protocol.PREPARED,
            b'RPI5XNU:PCIEID:END OK=1 PHASE=5 LAST=5 LIFE=3 FLAGS=1f ID=00011de4 COMMAND=0000 BAR1=00000000 GEN=2 LANES=4',
            b'RPi: BOOTSYS release VERSION: fixture',b'BOOT_ORDER override: 0x000000f6',
            b'RPi: BOOTLOADER release VERSION: fixture',b'Boot mode: NVME (06)']
        return b'\r\n'.join(lines)+b'\r\n',report

    def test_exact_complete_config_identity_and_reset_not_ethernet(self):
        raw,report=self.fixture();result=protocol.inspect(raw,report)
        self.assertTrue(result['rp1_id_trial_pass']);self.assertEqual(result['link_lanes'],4)
        for key in ('dma','irq_delivery','ethernet_proven','full_production_lifecycle_proven','independent_linux_return_proven'):
            self.assertFalse(result[key])
        for old,new in ((b'ID=00011de4',b'ID=00000000'),(b'FLAGS=1f',b'FLAGS=1b'),(b'OK=1 PHASE',b'OK=0 PHASE'),
                        (b'GEN=2',b'GEN=3'),(b'BAR1=00000000',b'BAR1=00000001'),(b'CPUS=1',b'CPUS=2')):
            with self.subTest(old=old),self.assertRaises(ValueError):protocol.inspect(raw.replace(old,new),report)

    def test_boot_or_result_reorder_duplicates_wrong_extent_and_fallback_rejected(self):
        raw,report=self.fixture()
        for bad in (raw.replace(b'20000000',b'19999999'),raw+protocol.BEGIN+b'\n',
                    raw.replace(protocol.BEGIN,b'PLACEHOLDER').replace(protocol.PREPARED,protocol.BEGIN).replace(b'PLACEHOLDER',protocol.PREPARED),
                    raw.replace(b'Boot mode: NVME (06)',b'Boot mode: SD (01)')):
            with self.assertRaises(ValueError):protocol.inspect(bad,report)
        early=raw[:raw.index(protocol.BEGIN)]+raw[raw.index(b'RPi: BOOTSYS'):]
        self.assertIsNotNone(protocol.return_positions(early))
        with self.assertRaises(ValueError):protocol.inspect(early,report)


class IntegratedReceiptTests(unittest.TestCase):
    def test_actual_82_ancestor_then_new_pair_capture_return_restore_contract(self):
        # Explicit chosen final package; no discovery or hardware operations.
        package_name=os.environ.get('RPI5_ID_TEST_PACKAGE')
        if not package_name:self.skipTest('RPI5_ID_TEST_PACKAGE selects the final checked loader')
        from tools.rpi5 import stage_pcie_id_trial as stage
        from tools.rpi5 import serial_pcie_id_trial as recorder
        from tools.rpi5 import pcie_id_evidence as evidence
        from tools.rpi5 import capture_pcie_id_failed_return as failed
        package=Path(package_name).resolve();baseline=ROOT/'build/rpi5/root96-restored-20261013'
        boot='6879aaf3-a600-4bd8-9f42-1e5cfbfbad35';next_boot='ae163034-de83-4de6-b76f-70e090cab7bb'
        plan=stage.load_plan(boot,baseline,package)
        # The actual prior ancestry was fully validated once above. This test
        # isolates new transition checks while pinning historical receipt bytes.
        historical=recorder.receipt_guard.receipt_evidence_pins(baseline)
        self.assertEqual(len(plan['nvme_backups']),82)
        def receipt(p):
            protected=dict(p['protected_files']);preserved={}
            for row in p['files']:
                backup,_,nvme=core.NAMES[p['profile']][row['target']]
                protected[row['target']]=row['new_sha256']
                if backup is not None:protected[backup]=row['old_sha256']
                preserved[row['target']]=dict(sha256=row['old_sha256'],bytes=row['old_bytes'],sd_backup=backup,nvme_backup=nvme)
            return dict(status='installed',run=p['run'],pair_publication_order=list(core.TARGETS),
                reused_existing_sd_backups={core.REUSED_ZSH_BACKUP:core.GOOD_ZSH_SHA} if p['profile']==stage.TRIAL else {},
                pair_sha256={r['target']:r['new_sha256'] for r in p['files']},preserved_pair=preserved,
                nvme_previous_pair_sha256={r['target']:r['old_sha256'] for r in p['files']},
                protected_files_sha256=protected,nvme_backups_verified=p['nvme_backups'],
                identity=dict(identity=p['identity_binding']['expected'],boot_id=p['linux_boot_id'],hostname='kamidana'),
                temporary_pair_published=True,power_loss_atomicity_claimed=False,no_implicit_rollback=True,
                boot_unmounted=True,no_hfs_mount=True,no_config_change=True,no_reboot=True,firmware_changed=True,
                backups=[dict(device=node,bytes=length,sha256=p['protected_sha256'][key],saved_as=name)
                    for key,node,_,length,name in stage.base.core.EXTENTS],
                protected_after={key:dict(device=node,bytes=length,sha256=p['protected_sha256'][key])
                    for key,node,_,length,_ in stage.base.core.EXTENTS})
        def save(directory,p):
            (directory/'plan.json').write_text(json.dumps(p));(directory/'result.json').write_text(json.dumps(receipt(p)))
            (directory/'source-snapshots').mkdir()
            for name in p['source_sha256']:shutil.copyfile(name,directory/'source-snapshots'/Path(name).name)
        with contextlib.ExitStack() as stack,patch.object(stage.prior,'validate_result',return_value=None):
            install,capture,restore=[Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='rp1-id-fixture-',dir=ROOT/'build/rpi5'))) for _ in range(3)]
            plan['run']='/home/sandrzej/xnu-rp1-id-12345678';save(install,plan)
            stage.validate_result(receipt(plan),plan);compile(stage.remote_source(plan),'<rp1-pair>','exec')
            installed=recorder.installation(install)
            report=installed['preflight']
            start=datetime(2026,10,13,tzinfo=timezone.utc)
            pieces=[b'\n'.join([b'Boot mode: SD (01)',b'Read probe.bin bytes '+str(report['image_bytes']).encode()+b' hnd 0',
                protocol.ENTRY,*[v.encode() for v in report['boot_markers']],protocol.TRANSFER,protocol.COMMIT,protocol.BEGIN,protocol.PREPARED])+b'\n',
                b'RPI5XNU:PCIEID:END OK=1 PHASE=5 LAST=5 LIFE=3 FLAGS=1f ID=00011de4 COMMAND=0000 BAR1=00000000 GEN=2 LANES=4\n',
                b'RPi: BOOTSYS release VERSION: fixture\nBOOT_ORDER override: 0x000000f6\nRPi: BOOTLOADER release VERSION: fixture\nBoot mode: NVME (06)\n']
            raw=b''.join(pieces);rows=[];offset=0
            for seconds,piece in zip((2,3,18),pieces):
                rows.append(dict(offset=offset,bytes=len(piece),monotonic=100+seconds,utc=(start+timedelta(seconds=seconds)).isoformat()));offset+=len(piece)
            sources=stage.source_pins()|{str(Path(m.__file__).resolve()):stage.sha(Path(m.__file__)) for m in
                (recorder,recorder.protocol,recorder.receipt_guard)}
            armed=dict(status='failed',started_utc=start.isoformat(),armed_utc=start.isoformat(),armed_monotonic=100,
                pid=123,device='/dev/cu.usbmodem102',baud=115200,transmitted_bytes=0,installation=installed,
                source_sha256=sources,receipt_evidence_sha256=recorder.receipt_guard.receipt_evidence_pins(install),
                continuous_capture=False,physical_reset_return_proven=False,xnu_pe_runtime_proven=False,ethernet_proven=False)
            state=dict(armed,status='captured',continuous_capture=True,ended_utc=(start+timedelta(seconds=20)).isoformat(),
                bytes=len(raw),serial_sha256=digest(raw),inventory=protocol.inventory(raw),diagnostic=protocol.inspect(raw,report))
            for name,value in (('armed.json',armed),('state.json',state)):(capture/name).write_text(json.dumps(value))
            (capture/'serial.bin').write_bytes(raw);(capture/'receive-events.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
            p,i,observed=evidence.load_capture(install,capture)
            self.assertTrue(observed['rp1_id_capture_pass'])
            bad=copy.deepcopy(state);bad['transmitted_bytes']=1
            with self.assertRaises(ValueError):evidence.inspect_capture(raw,rows,bad,installed,sources)
            broken=copy.deepcopy(rows);broken[-1]['monotonic']=104
            with self.assertRaises(ValueError):evidence.inspect_capture(raw,broken,state,installed,sources)
            with self.assertRaises(ValueError):failed.failed(capture)
            returned=dict(host=stage.HOST,boot_id=next_boot,installation=installed,serial_sha256=digest(raw),
                root=plan['identity_binding']['expected']['root'].split(),
                identity=dict(identity=plan['identity_binding']['expected'],boot_id=next_boot,hostname='kamidana'),
                bootloader={'boot-mode':6,'partition':1,'tryboot':0},read_only=True,sd_partitions_unmounted=True,
                observed_utc=(start+timedelta(seconds=25)).isoformat(),return_source_sha256=evidence.return_source_pins())
            (capture/'linux-return.json').write_text(json.dumps(returned))
            restored=stage.load_plan(next_boot,install,package,True);restored['run']='/home/sandrzej/xnu-rp1-id-87654321'
            self.assertEqual(len(restored['nvme_backups']),87);save(restore,restored)
            stage.validate_result(receipt(restored),restored)
            outcome=evidence.inspect(install,capture,restore)
            self.assertEqual(outcome['next_inherited_artifact_count'],92)
        self.assertTrue(all(stage.sha(Path(name))==value for name,value in historical.items()))


if __name__=='__main__':unittest.main()
