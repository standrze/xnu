# SPDX-License-Identifier: BSD-2-Clause
"""Linux control orchestration/evidence guards with explicit doubles only."""
import contextlib
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import capture_sd_extension_reference as runner
from tools.rpi5.tests import test_hfs_write_installer as fixtures


class ExtensionControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)

    def bundle(self):
        plan,result=fixtures.WriteInstallerTests().result_bundle()
        plan.update(profile='write-cache-diagnostic',new_image_sha256=runner.W3_IMAGE,
            evidence_sha256={'reference':'a'*64},expected={'root':runner.linux.ROOT},expected_boot_before_sha256='e'*64)
        result.update(image_sha256=runner.W3_IMAGE,sd_backup='probe.hfs-write-cache-probe-failed-20261012.bin')
        raw=runner.HEADER+b'\r\n'+b''.join(b'RPI5XNU:SD:CACHE_PROBE_BYTES OFFSET='+str(n).encode()+b' HEX='+b'0'*32+b'\r\n' for n in range(0,512,16))
        state=dict(status='failed',image_sha256=runner.W3_IMAGE,transmitted_bytes=0,write_batch_attempts=0,
            hfs_mounted=False,durability_verified=False,checks=[],reads=[],
            error='Unsafe, old or failed boot before write input',linux_boot_id_before_write=plan['linux_boot_id'],
            bytes=len(raw),write_input_sha256=plan['evidence_sha256'],serial_sha256=hashlib.sha256(raw).hexdigest())
        ready=dict(status='ready',ended_utc='2026-10-12T13:10:00+00:00',identity=dict(hostname='kamidana',
            root=runner.linux.ROOT,boot_id='54b2ad20-73c0-4dc2-a6b7-c96506b04a0b'))
        paths={key:self.root/name for key,name in (('plan','plan.json'),('installed','result.json'),
            ('trial','state.json'),('serial','serial.bin'),('ready','ready.json'))}
        for key,value in (('plan',plan),('installed',result),('trial',state),('ready',ready)):
            paths[key].write_text(json.dumps(value))
        paths['serial'].write_bytes(raw)
        return paths,plan,result,state,raw,ready

    def load(self,bundle):
        paths=bundle[0]
        pins={key:runner.history.recorder.sha256(paths[key]) for key in runner.PINS}
        backups=[{'path':'model-'+str(n)} for n in range(20)]
        with patch.object(runner,'PINS',pins),patch.object(runner.installer,'evidence_path',side_effect=Path), \
                patch.object(runner.history,'backup_rows',return_value=backups):
            return runner.load_plan(self.root,paths['trial'],paths['ready'],now=datetime(2026,10,12,13,11,tzinfo=timezone.utc))

    def test_new_ready_boot_pinned_failure_and_all_backup_generations_required(self):
        bundle=self.bundle(); plan=self.load(bundle)
        self.assertEqual(len(plan['nvme_backups']),20)
        self.assertEqual(plan['xnu_payload_sha256'],runner.ZERO_SHA)
        self.assertIs(plan['cache_admission'],False); self.assertIs(plan['durability_verified'],False)
        source=runner.remote_source(plan); compile(source,'<linux-control>','exec')
        self.assertLess(source.index('protected_before=protected_control(PLAN)'),source.index('result=observe(binding)'))
        self.assertLess(source.index('result=observe(binding)'),source.index('protected_after=protected_control(PLAN)'))
        self.assertNotIn('systemctl reboot',source)

    def test_waiting_stale_future_same_boot_wrong_root_or_admitted_trial_refuses(self):
        for fault in ('waiting','stale','future','same-boot','root','tx','txbool','batch','mounted','raw'):
            bundle=self.bundle(); paths,old,result,state,raw,ready=bundle
            if fault=='waiting': ready['status']='waiting'
            if fault=='stale': ready['ended_utc']='2026-10-12T12:00:00+00:00'
            if fault=='future': ready['ended_utc']='2026-10-12T14:00:00+00:00'
            if fault=='same-boot': ready['identity']['boot_id']=old['linux_boot_id']
            if fault=='root': ready['identity']['root']='/dev/mmcblk0p2'
            if fault=='tx': state['transmitted_bytes']=1
            if fault=='txbool': state['transmitted_bytes']=False
            if fault=='batch': state['write_batch_attempts']=1
            if fault=='mounted': state['hfs_mounted']=True
            if fault=='raw': raw=raw.replace(b'HEX=0000',b'HEX=1000',1); paths['serial'].write_bytes(raw)
            paths['trial'].write_text(json.dumps(state)); paths['ready'].write_text(json.dumps(ready))
            with self.subTest(fault=fault),self.assertRaises(ValueError): self.load(bundle)

    def test_actual_fixed_pins_reject_self_consistent_substituted_history(self):
        bundle=self.bundle(); paths=bundle[0]
        with patch.object(runner.installer,'evidence_path',side_effect=Path),self.assertRaises(ValueError):
            runner.load_plan(self.root,paths['trial'],paths['ready'])

    def test_source_drift_before_rendering_prevents_remote_program(self):
        plan=self.load(self.bundle()); plan['source_sha256']['observer']='0'*64
        with self.assertRaisesRegex(ValueError,'source changed'): runner.remote_source(plan)

    def report(self,plan,payload=bytes(512)):
        rows={key:dict(device=node,bytes=size,sha256=plan['protected_sha256'][key]) for key,node,size in
            (('mbr','/dev/mmcblk0',512),('boot','/dev/mmcblk0p1',536870912),('hfs','/dev/mmcblk0p2',134217728))}
        return dict(status='linux_reference_only',cache_admission=False,durability_verified=False,
            userspace_cmd48_ioctls=1,userspace_write_commands=0,sd_write_operations=0,sd_mount_operations=0,
            identity=dict(identity=plan['identity_binding']['expected'],hostname='kamidana',
                boot_id=plan['identity_binding']['linux_boot_id_after_write']),
            nvme_backups_verified=plan['nvme_backups'],xnu_payload_sha256=runner.ZERO_SHA,
            general_information=dict(opcode=48,argument=511,write_flag=0,is_acmd=0,blocks=1,bytes=512,flags=0x35,
                response=[0x900,0,0,0],payload_hex=payload.hex(),payload_sha256=hashlib.sha256(payload).hexdigest(),
                sentinel_unchanged=payload==bytes([0xa5])*512),same_payload_as_xnu=payload==bytes(512),
            protected_before=rows,protected_after=rows)

    def test_complete_response_and_protected_bytes_not_cache_admission(self):
        plan=self.load(self.bundle())
        for data in (bytes(512),bytes(range(256))*2,bytes([0xa5])*512): runner.validate_report(self.report(plan,data),plan)
        for fault in ('writes','bool','admission','boot','backups','fat','raw','r1','state','opcode','comparison'):
            result=self.report(plan)
            if fault=='writes': result['sd_write_operations']=1
            if fault=='bool': result['userspace_cmd48_ioctls']=True
            if fault=='admission': result['cache_admission']=True
            if fault=='boot': result['identity']['boot_id']='old'
            if fault=='backups': result['nvme_backups_verified']=[]
            if fault=='fat': result['protected_after']['boot']['sha256']='0'*64
            if fault=='raw': result['general_information']['payload_hex']='00'
            if fault=='r1': result['general_information']['response'][0]=0x400900
            if fault=='state': result['general_information']['response'][0]=0x700
            if fault=='opcode': result['general_information']['opcode']=49
            if fault=='comparison': result['same_payload_as_xnu']=False
            with self.subTest(fault=fault),self.assertRaises(ValueError): runner.validate_report(result,plan)

    def test_fixed_remote_control_orders_checks_and_never_reads_after_failed_precondition(self):
        plan=self.load(self.bundle())
        for fault in (None,'root','backup-before','protected-before','protected-after','backup-after','changed-root'):
            calls=[]; snapshots=0; backups=0; identities=0
            def identity(binding):
                nonlocal identities
                identities+=1; calls.append('identity')
                if fault=='root': raise ValueError('wrong root')
                return {'boot':2 if fault=='changed-root' and identities>1 else 1}
            def verify_backups(binding):
                nonlocal backups
                backups+=1; calls.append('backups')
                if fault==('backup-before' if backups==1 else 'backup-after'): raise ValueError('changed backup')
            def snapshot(node,capacity,length):
                nonlocal snapshots
                snapshots+=1
                key={'/dev/mmcblk0':'mbr','/dev/mmcblk0p1':'boot','/dev/mmcblk0p2':'hfs'}[node]; calls.append(key)
                sha=plan['protected_sha256'][key]
                if (fault=='protected-before' and snapshots==2) or (fault=='protected-after' and snapshots==5): sha='0'*64
                return dict(device=node,bytes=length,sha256=sha)
            def observe(binding):
                calls.append('cmd48'); return self.report(plan)
            scope=dict(PLAN=plan,identity=identity,verify_backups=verify_backups,snapshot=snapshot,observe=observe,json=json)
            with self.subTest(fault=fault),contextlib.redirect_stdout(io.StringIO()) as stdout:
                if fault:
                    with self.assertRaises(ValueError): exec(runner.REMOTE,scope)
                else:
                    exec(runner.REMOTE,scope); runner.validate_report(json.loads(stdout.getvalue()),plan)
            self.assertEqual(calls.count('cmd48'),0 if fault in ('root','backup-before','protected-before') else 1)
            if fault is None:
                self.assertEqual(calls,['identity','backups','mbr','boot','hfs','cmd48','mbr','boot','hfs','backups','identity'])

    def test_local_default_or_waiting_gate_never_connects(self):
        for bad in (False,True):
            out=self.root/('bad' if bad else 'local')
            argv=['capture_sd_extension_reference.py','--installed',str(self.root),'--trial','trial',
                '--linux-ready','ready','--output',str(out)]+(['--execute'] if bad else [])
            with patch.object(sys,'argv',argv),patch.object(Path,'is_relative_to',return_value=True), \
                    patch.object(runner,'load_plan',return_value={'local':'plan'},side_effect=ValueError('waiting') if bad else None), \
                    patch.object(runner.subprocess,'run') as ssh,contextlib.redirect_stdout(io.StringIO()):
                if bad:
                    with self.assertRaises(ValueError): runner.main()
                else: self.assertEqual(runner.main(),0)
            ssh.assert_not_called(); self.assertEqual(out.exists(),not bad)

    def test_timeout_preserves_unknown_outcome_and_never_retries(self):
        out=self.root/'unknown'; argv=['capture_sd_extension_reference.py','--installed','i','--trial','t',
            '--linux-ready','r','--output',str(out),'--execute']
        with patch.object(sys,'argv',argv),patch.object(Path,'is_relative_to',return_value=True), \
                patch.object(runner,'load_plan',return_value={'fixed':'plan'}), \
                patch.object(runner,'remote_source',return_value='fixed source'), \
                patch.object(runner.subprocess,'run',side_effect=subprocess.TimeoutExpired('ssh',300,output=b'partial')) as ssh:
            with self.assertRaises(subprocess.TimeoutExpired): runner.main()
        ssh.assert_called_once(); self.assertTrue((out/'outcome-unknown.txt').exists())
        self.assertEqual((out/'remote.stdout').read_bytes(),b'partial'); self.assertFalse((out/'result.json').exists())


if __name__=='__main__': unittest.main()
