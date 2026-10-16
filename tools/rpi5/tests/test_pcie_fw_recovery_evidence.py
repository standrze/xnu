# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic byte/receipt/SSH fixtures only; no physical execution claims."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools.rpi5 import pcie_fw_recovery_evidence as core
from tools.rpi5 import capture_pcie_fw_linux_return as collector
from tools.rpi5.tests.test_pcie_fw_trial_serial import fixture as abi_fixture,TAG,IMAGE,FIRMWARE
from tools.rpi5.tests.test_pcie_fw_install import receipt,BOOT

NEW_BOOT='4977a538-fae5-434d-a94f-50c9422fea84'
UTC=lambda n:f'2026-10-13T00:00:{n:02d}+00:00'


def fixture(installed=None,sources=None):
    installed=installed or dict(preflight=dict(trial_tag=TAG),pair_sha256={'probe.bin':IMAGE,'bl31.bin':FIRMWARE})
    sources={} if sources is None else sources
    before=b'Boot mode: SD (01)\r\n'+abi_fixture().replace(TAG.encode(),installed['preflight']['trial_tag'].encode())
    tail=(b'RPi: BOOTSYS release VERSION: fixture\r\nBOOT_ORDER override: 0x000000f6\r\n'+
        b'RPi: BOOTLOADER release VERSION: fixture\r\nBoot mode: NVME (06)\r\n')
    data=before+tail;rows=[]
    for i,off in enumerate(range(0,len(before),4096)):
        rows.append(dict(offset=off,bytes=min(4096,len(before)-off),monotonic=2+i,utc=UTC(2+i)))
    rows.append(dict(offset=len(before),bytes=len(tail),monotonic=17,utc=UTC(17)))
    state=dict(status='captured',continuous_capture=True,pid=123,device='/dev/cu.usbmodemFixture',baud=115200,
        transmitted_bytes=0,bytes=len(data),serial_sha256=hashlib.sha256(data).hexdigest(),installation=installed,
        source_sha256=sources,armed_monotonic=1,started_utc=UTC(0),armed_utc=UTC(1),ended_utc=UTC(20),
        physical_reset_return_proven=False,xnu_pe_runtime_proven=False,ethernet_proven=False,
        diagnostic=core.protocol.inspect(data,installed['preflight']['trial_tag'],installed['pair_sha256']['probe.bin'],
            installed['pair_sha256']['bl31.bin']),inventory=core.recorder.inventory(data))
    return data,rows,state,installed,sources


def returned(plan,installed,observed):
    return dict(host=core.stage.HOST,boot_id=NEW_BOOT,installation=installed,serial_sha256=observed['serial_sha256'],
        root=plan['identity_binding']['expected']['root'].split(),
        identity=dict(identity=plan['identity_binding']['expected'],boot_id=NEW_BOOT,hostname='kamidana'),
        bootloader={'boot-mode':6,'partition':1,'tryboot':0},sd_partitions_unmounted=True,read_only=True,
        observed_utc=UTC(30),return_source_sha256=core.return_source_pins())


def refresh(data,rows,state):
    state['bytes']=len(data);state['serial_sha256']=hashlib.sha256(data).hexdigest()
    state['inventory']=core.recorder.inventory(data)
    # Reshape coverage while keeping actual trial/reset timestamp separation.
    end=data.index(b'RPi: BOOTSYS release VERSION:') if b'RPi: BOOTSYS release VERSION:' in data else len(data)
    rows.clear()
    for i,off in enumerate(range(0,end,4096)):
        rows.append(dict(offset=off,bytes=min(4096,end-off),monotonic=2+i,utc=UTC(2+i)))
    if end<len(data):rows.append(dict(offset=end,bytes=len(data)-end,monotonic=17,utc=UTC(17)))


class FirmwareRecoveryEvidenceTests(unittest.TestCase):
    def test_package_collector_and_validator_use_same_module(self):
        self.assertIs(collector.evidence,core)

    def test_complete_capture_only_does_not_prove_linux_restore_or_controller(self):
        r=core.inspect_capture(*fixture())
        self.assertTrue(r['firmware_abi_capture_pass']);self.assertEqual(r['host_armed_to_bootsys_seconds'],15)
        for field in ('independent_linux_return_proven','restored_pair_proven','controller_initialization_admitted','ethernet_proven'):
            self.assertFalse(r[field])

    def test_capture_state_source_pair_typed_flags_and_clock_mutations_refused(self):
        data,rows,state,installed,sources=fixture()
        changes={'status':'running','continuous_capture':1,'transmitted_bytes':False,'bytes':True,
            'pid':True,'baud':9600,'device':'/dev/ttyS0','serial_sha256':'0'*64,'installation':{},
            'source_sha256':{'foreign':'0'*64},'error':'interrupted','restore_error':'failed',
            'diagnostic_error':'partial','diagnostic':{},'inventory':{},'physical_reset_return_proven':True,
            'armed_monotonic':float('nan'),'started_utc':UTC(3),'ended_utc':UTC(2)}
        for k,v in changes.items():
            bad=copy.deepcopy(state);bad[k]=v
            with self.subTest(field=k),self.assertRaises(ValueError):core.inspect_capture(data,rows,bad,installed,sources)

    def test_every_journal_gap_overlap_type_time_bound_and_missing_tail_refused(self):
        data,rows,state,installed,sources=fixture()
        for i in range(len(rows)):
            for key,value in (('offset',rows[i]['offset']+1),('bytes',0),('bytes',4097),('bytes',True),
                ('monotonic',float('inf')),('monotonic',0),('utc','2026-10-13T00:00:01')):
                bad=copy.deepcopy(rows);bad[i][key]=value
                with self.subTest(row=i,field=key),self.assertRaises(ValueError):core.inspect_capture(data,bad,state,installed,sources)
        with self.assertRaises(ValueError):core.inspect_capture(data,rows[:-1],state,installed,sources)

    def test_each_missing_duplicate_wrong_override_fallback_or_wrong_timing_refused(self):
        for old,new in ((b'Boot mode: SD (01)',b'Boot mode: wrong'),
            (b'RPi: BOOTSYS release VERSION:',b'RPi: BOOTSYS missing'),
            (b'RPi: BOOTLOADER release VERSION:',b'RPi: BOOTLOADER missing'),
            (b'Boot mode: NVME (06)',b'Boot mode: NVME (07)'),
            (b'BOOT_ORDER override: 0x000000f6',b'BOOT_ORDER override: 0x00000461')):
            data,rows,state,installed,sources=fixture();data=data.replace(old,new);refresh(data,rows,state)
            with self.subTest(old=old),self.assertRaises(ValueError):core.inspect_capture(data,rows,state,installed,sources)
        for extra in (b'Boot mode: SD (01)\r\n',b'Boot mode: USB (04)\r\n',b'Boot mode: NVME (06)\r\n'):
            data,rows,state,installed,sources=fixture();data+=extra;refresh(data,rows,state)
            with self.assertRaises(ValueError):core.inspect_capture(data,rows,state,installed,sources)
        for last in (5,47):
            data,rows,state,installed,sources=fixture();rows[-1].update(monotonic=last,utc=UTC(last));state['ended_utc']=UTC(59)
            with self.assertRaisesRegex(ValueError,'bounded window'):core.inspect_capture(data,rows,state,installed,sources)

    def test_independent_new_normal_linux_identity_and_return_source_are_required(self):
        x=fixture();observed=core.inspect_capture(*x)
        plan=dict(linux_boot_id=BOOT,identity_binding=dict(expected=dict(root='SSD ext4 uuid',card={'cid':'model'})))
        good=returned(plan,x[3],observed);self.assertEqual(core.inspect_return(good,plan,x[3],observed),NEW_BOOT)
        changes={'boot_id':BOOT,'host':'other','root':['SD','ext4','uuid'],'identity':{},'installation':{},
            'serial_sha256':'0'*64,'sd_partitions_unmounted':1,'read_only':1,'return_source_sha256':{},
            'bootloader':{'boot-mode':6,'partition':1,'tryboot':True},'observed_utc':UTC(17)}
        for k,v in changes.items():
            bad=copy.deepcopy(good);bad[k]=v
            with self.subTest(field=k),self.assertRaises(ValueError):core.inspect_return(bad,plan,x[3],observed)

    def test_complete_local_receipt_replay_and_wrong_armed_or_restore_ancestry_refused(self):
        stage=core.stage;plan=stage.load_plan(BOOT);plan['run']='/home/sandrzej/xnu-gate5-fwabi-12345678'
        with tempfile.TemporaryDirectory(prefix='fwabi-evidence-install-',dir=stage.ROOT/'build/rpi5') as i, \
            tempfile.TemporaryDirectory(prefix='fwabi-evidence-capture-',dir=stage.ROOT/'build/rpi5') as c, \
            tempfile.TemporaryDirectory(prefix='fwabi-evidence-restore-',dir=stage.ROOT/'build/rpi5') as r:
            install,capture,restore=map(Path,(i,c,r))
            def save_receipt(directory,p):
                (directory/'plan.json').write_text(json.dumps(p));(directory/'result.json').write_text(json.dumps(receipt(p)))
                archive=directory/'source-snapshots';archive.mkdir()
                for name in p['source_sha256']:shutil.copyfile(name,archive/Path(name).name)
            save_receipt(install,plan)
            installed=core.recorder.installation(install)
            sources=stage.source_pins()|{str(Path(core.recorder.__file__).resolve()):stage.sha(Path(core.recorder.__file__)),
                str(Path(core.protocol.__file__).resolve()):stage.sha(Path(core.protocol.__file__))}
            data,rows,state,_,_=fixture(installed,sources)
            (capture/'serial.bin').write_bytes(data);(capture/'state.json').write_text(json.dumps(state))
            (capture/'receive-events.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
            armed={k:state[k] for k in ('started_utc','pid','device','baud','transmitted_bytes','installation','source_sha256',
                'physical_reset_return_proven','xnu_pe_runtime_proven','ethernet_proven','armed_utc','armed_monotonic')}
            armed.update(status='failed',continuous_capture=False);(capture/'armed.json').write_text(json.dumps(armed))
            observed=core.inspect_capture(data,rows,state,installed,sources)
            (capture/'linux-return.json').write_text(json.dumps(returned(plan,installed,observed)))
            restored=stage.load_plan(NEW_BOOT,install);restored['run']='/home/sandrzej/xnu-gate5-fwabi-87654321'
            save_receipt(restore,restored)
            report=core.inspect(install,capture,restore)
            self.assertTrue(report['firmware_abi_return_restore_evidence_pass']);self.assertEqual(report['next_inherited_artifact_count'],70)
            self.assertFalse(report['controller_initialization_admitted']);self.assertFalse(report['xnu_pe_runtime_proven'])
            bad=copy.deepcopy(armed);bad['pid']+=1;(capture/'armed.json').write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,'Armed snapshot'):core.inspect(install,capture,restore)
            (capture/'armed.json').write_text(json.dumps(armed))
            wrong=copy.deepcopy(restored);wrong['ancestry']['hashes']['result.json']='0'*64
            (restore/'plan.json').write_text(json.dumps(wrong))
            with self.assertRaises(ValueError):core.inspect(install,capture,restore)

    def test_collector_generated_program_compile_and_readonly_result_then_no_overwrite(self):
        stage=collector.stage
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();install=root/'build/rpi5/install';capture=root/'build/rpi5/capture'
            install.mkdir(parents=True);capture.mkdir()
            x=fixture();observed=core.inspect_capture(*x)
            plan=dict(host=stage.HOST,linux_boot_id=BOOT,identity_binding=dict(expected=dict(root='SSD ext4 uuid')))
            sources={'fixture':'a'*64};answer=returned(plan,x[3],observed);answer['return_source_sha256']=sources
            program=collector.remote_source(plan,x[3],observed['serial_sha256'],sources);compile(program,'<read-only-return>','exec')
            with patch.object(stage,'ROOT',root),patch.object(collector.lease,'hold',return_value=contextlib.nullcontext()), \
                patch.object(core,'load_capture',return_value=(plan,x[3],observed)),patch.object(core,'return_source_pins',return_value=sources), \
                patch.object(collector.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(answer),'')) as ssh, \
                contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(collector.main(['--installation',str(install),'--capture',str(capture)]),0)
                self.assertEqual(ssh.call_count,1);self.assertEqual(ssh.call_args.kwargs['input'],program)
                with self.assertRaisesRegex(ValueError,'never overwrite'):collector.main(['--installation',str(install),'--capture',str(capture)])
                self.assertEqual(ssh.call_count,1)
            saved=json.loads((capture/'linux-return.json').read_text());self.assertTrue(saved['read_only'])
            self.assertEqual(saved['boot_id'],NEW_BOOT)

    def test_collector_ssh_timeout_does_not_write_success_or_retry(self):
        stage=collector.stage
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();install=root/'build/rpi5/install';capture=root/'build/rpi5/capture';capture.mkdir(parents=True)
            x=fixture();observed=core.inspect_capture(*x)
            plan=dict(host=stage.HOST,linux_boot_id=BOOT,identity_binding=dict(expected=dict(root='SSD ext4 uuid')))
            with patch.object(stage,'ROOT',root),patch.object(collector.lease,'hold',return_value=contextlib.nullcontext()), \
                patch.object(core,'load_capture',return_value=(plan,x[3],observed)),patch.object(core,'return_source_pins',return_value={}), \
                patch.object(collector.subprocess,'run',side_effect=subprocess.TimeoutExpired('ssh',60)) as ssh:
                with self.assertRaises(subprocess.TimeoutExpired):collector.main(['--installation',str(install),'--capture',str(capture)])
                self.assertEqual(ssh.call_count,1);self.assertFalse((capture/'linux-return.json').exists())


if __name__=='__main__':unittest.main()
