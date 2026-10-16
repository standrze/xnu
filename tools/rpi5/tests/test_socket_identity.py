# SPDX-License-Identifier: BSD-2-Clause
"""Runtime-root diagnosis: native files + synthetic statfs, not Pi acceptance."""
import hashlib
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import prepare_socket_identity_root as build
from tools.rpi5 import socket_identity_evidence as evidence
from tools.rpi5 import socket_identity_trial_core as trial
from tools.rpi5 import check_socket_identity_package as package
from tools.rpi5 import stage_socket_identity_trial as staging
from tools.rpi5 import serial_socket_identity_trial as recorder
from tools.rpi5 import audit_socket_identity_trial as audit
from tools.rpi5.ramroot import inspect
from tools.rpi5.tests.test_prepare_pid1 import fixture


@unittest.skipUnless(sys.platform=='darwin', 'Darwin stat ABI required')
class IdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.base=Path(cls.temp.name)
        files={name:(bytes(fixture()),0o555) for name in
               ('/sbin/launchd','/bin/sh','/bin/zsh','/sbin/ifconfig','/sbin/route')}
        files['/etc/test-data']=(bytes(range(256))*21,0o444)
        baseline=build.old.build(files)[0]
        with patch.object(build.old,'ROOT_PIN',build.old.sha(baseline)):
            rows=build.catalog(baseline)
        cls.rows=rows
        (cls.base/'rootidentity_catalog.h').write_text(build.header(rows))
        files[build.old.INSTALL_PATH]=(bytes(fixture()),0o555)
        image=build.old.build(files)[0]
        cls.receipt=dict(output_nodes=len(rows), output_bytes=len(image), identity_catalog=[])
        cls.tree=cls.base/'tree'; cls.tree.mkdir()
        directories=[]
        for row in rows:
            path=cls.tree/row['path'].lstrip('/')
            record=dict(row)
            if row['mode'] & 0o170000 == 0o40000:
                path.mkdir(parents=True,exist_ok=True); directories.append(path)
            else:
                data,mode=files[row['path']]; path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(data); path.chmod(mode)
                record.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            cls.receipt['identity_catalog'].append(record)
        for path in directories: path.chmod(0o555)
        cls.program=cls.base/'native'
        sources=[build.old.SOURCE/'rootidentity.c', build.old.ROOT/'tools/rpi5/tests/rootidentity_native.c']
        sources += [build.BEARSSL/'src'/name for name in ('hash/sha2small.c','codec/dec32be.c','codec/enc32be.c')]
        command=['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                 '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                 '-DIDENTITY_NODES='+str(len(rows)), '-DIDENTITY_BLOCKS='+str(len(image)//16384),
                 '-I'+str(cls.base),'-I'+str(build.BEARSSL/'inc'),'-I'+str(build.BEARSSL/'src'),
                 *map(str,sources),'-o',str(cls.program)]
        subprocess.run(command,check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):
        for path in cls.tree.rglob('*'):
            if path.is_dir(): path.chmod(0o755)
        cls.tree.chmod(0o755); cls.temp.cleanup()

    def native(self,scenario='none',position=0,status=0):
        result=subprocess.run([str(self.program),str(self.tree),scenario,str(position)],
                              capture_output=True,timeout=8)
        self.assertEqual(result.returncode,status,result.stdout.decode()+result.stderr.decode())
        self.assertRegex(result.stdout,rb'NATIVE:CALLS=\d+:LEAKS=0:VIOLATIONS=0\n$')
        return result.stdout

    def test_actual_native_files_metadata_hashes_and_partial_reads(self):
        for scenario in ('none','partial'):
            result=evidence.validate(self.native(scenario),self.receipt)
            self.assertTrue(result['self_digest_verified'])
            self.assertEqual(result['nodes'],len(self.rows))
        raw=self.native('one-byte',status=1)
        self.assertLessEqual(int(re.search(rb'NATIVE:CALLS=(\d+)',raw)[1]),2048)

    def test_every_operation_error_closes_owned_fd_without_retry(self):
        raw=self.native()
        count=int(re.search(rb'NATIVE:CALLS=(\d+)',raw)[1])
        for position in range(1,count+1):
            with self.subTest(position=position):
                raw=self.native(position=position,status=1)
                self.assertIn(b'ROOTIDENTITY:FAIL\n',raw)

    def test_malformed_metadata_buffer_payload_and_filesystem_reject(self):
        for scenario in ('statfs-guard','statfs-name','statfs-path','statfs-flags','statfs-nodes',
                         'statfs-free','statfs-blocks','metadata-guard','metadata-mode',
                         'metadata-size','fd-stdio','fstat-inode','fstat-guard','payload',
                         'read-guard','read-overrun','extra-eof','devfs-name','devfs-path'):
            with self.subTest(scenario=scenario):
                raw=self.native(scenario,status=1)
                with self.assertRaises(ValueError): evidence.validate(raw,self.receipt)
        with self.assertRaises(ValueError): evidence.validate(self.native('statfs-extent'),self.receipt)

    def test_replay_rejects_wrong_self_hash_extent_missing_duplicate_or_damaged_lines(self):
        raw=self.native()
        for altered in (raw.replace(b'SHA256=',b'SHA256=0',1),raw+raw,
                        raw.replace(b'ROOTIDENTITY:DIR:/',b'ROOTIDENTITY:DIR:/bad',1),
                        raw.replace(b'ROOTIDENTITY:PASS:',b'ROOTIDENTITY:FAIL:')):
            with self.assertRaises(ValueError): evidence.validate(altered,self.receipt)
        receipt=json.loads(json.dumps(self.receipt))
        receipt['identity_catalog'][-1]['sha256']='0'*64
        with self.assertRaises(ValueError): evidence.validate(raw,receipt)

    def test_real_a76_build_preserves_all_original_files_and_frozen_v1(self):
        frozen=build.old.ROOT/'build/rpi5/socketprobe-root-20261012/manifest.json'
        frozen_bytes=frozen.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            out=Path(temporary)/'root'
            report=build.build(out)
            files=build.old.files_from((out/'ramdisk.bin').read_bytes())
            helper,mode=files.pop(build.old.INSTALL_PATH)
            self.assertEqual(mode,0o555)
            self.assertEqual(files,build.old.files_from(build.old.ACCEPTED_ROOT.read_bytes()))
            self.assertEqual(report['output_nodes'],32)
            self.assertEqual(len(report['linked_sysent']['calls']),21)
            self.assertEqual(inspect((out/'ramdisk.bin').read_bytes())['sha256'],report['output_sha256'])
            self.assertEqual(next(row for row in report['identity_catalog'] if row['path']==build.old.INSTALL_PATH)['sha256'],build.old.sha(helper))
            self.assertFalse(report['pi_executed'])
            self.assertFalse(report['kernel_syscall_hang_contained'])
            for mapping in ('source_inputs_sha256','sdk_headers_sha256'):
                for path,pin in report[mapping].items(): self.assertEqual(build.old.sha(Path(path).read_bytes()),pin)
            with self.assertRaises(FileExistsError): build.build(out)
        self.assertEqual(frozen.read_bytes(),frozen_bytes)

    def test_phased_commands_never_send_socket_payload_before_full_runtime_identity(self):
        raw=self.native()
        state=dict(checks=[],transmitted_bytes=0)
        with patch.object(trial.t,'exchange',return_value=raw.replace(b'SHA256=',b'SHA256=0',1)) as exchange:
            with self.assertRaises(ValueError): trial.commands(1,None,state,self.receipt)
        self.assertEqual(exchange.call_count,1)
        self.assertEqual(exchange.call_args.args[2],trial.IDENTITY_COMMAND)
        self.assertEqual(state['checks'],[])


class TrialAdmissionTests(unittest.TestCase):
    def boot(self):
        t=trial.t
        return b'\n'.join((b'Boot mode: SD (01)',b'Read probe.bin bytes 19384000 hnd 1',t.ENTRY,
            t.TERMINAL_LOADER,trial.COPY,trial.KERNEL,t.package_check.TOPOLOGY_PASS,
            t.TRANSFER,trial.COMMIT,b'RPI5XNU:RAMROOT:MOUNT NODES=32 BYTES=1916928 READONLY',
            t.READY,b'xnu:/# '))

    def test_only_identity_query_is_admitted_when_mount_log_is_torn(self):
        raw=self.boot()
        self.assertTrue(trial.identity_query_ready(raw))
        torn=raw.replace(b' NODES=32 BYTES=',b' NODES=32 kernel chatter\n BYTES=')
        self.assertTrue(trial.identity_query_ready(torn))
        with self.assertRaises(RuntimeError):
            trial.t.boot_ready(torn,trial.IMAGE_BYTES,b'RPI5XNU:RAMROOT:MOUNT NODES=32 BYTES=1916928 READONLY')
        for bad in (raw+b'panic(cpu',raw+trial.t.ENTRY,raw.replace(b'19384000',b'19334848'),
                    raw.replace(b'NODES=32',b'NODES=27'),raw+trial.COPY):
            with self.subTest(bad=bad[-80:]),self.assertRaises(RuntimeError): trial.identity_query_ready(bad)
        for marker in (trial.COPY,trial.KERNEL,trial.COMMIT,trial.t.READY,trial.t.TERMINAL_LOADER):
            self.assertFalse(trial.identity_query_ready(raw.replace(marker,b'missing')))

    def test_exact_v2_package_and_changed_pins_reject(self):
        candidate=build.old.ROOT/'build/rpi5/bl33-probe-vszhh6o4'
        report=package.inspect(candidate)
        self.assertEqual(report['image_bytes'],trial.IMAGE_BYTES)
        self.assertEqual(len(report['checks']),35)
        for name in ('INIT_SHA','PROBE_SHA','RECEIPT_SHA'):
            with patch.object(package,name,'0'*64),self.assertRaises(ValueError): package.inspect(candidate)
        with self.assertRaises(ValueError): package.inspect(build.old.ROOT/'build/rpi5/bl33-probe-tt7iq4m9')

    def test_socket_payload_and_halfclose_replay(self):
        raw=b'\n'.join([b'SOCKETPROBE:BEGIN:RAW_DARWIN_V1',b'SOCKETPROBE:MODE=unix',
            *[b'SOCKETPROBE:STREAM_PAYLOAD_MATCH=32']*3,b'SOCKETPROBE:STREAM_EOF=0',
            b'SOCKETPROBE:OPERATIONS=26',b'SOCKETPROBE:PASS',
            b'SOCKETPROBE:END:NOT_ETHERNET_OR_SSH_PROOF',b'SOCKET_STATUS:0'])
        self.assertEqual(trial.socket_result(raw,'unix')['operations'],26)
        for bad in (raw.replace(b'SOCKET_STATUS:0',b'SOCKET_STATUS:1'),
                    raw.replace(b'=32',b'=31',1),raw+raw,raw.replace(b'=26',b'=257')):
            with self.assertRaises(ValueError): trial.socket_result(bad,'unix')

    def test_recorder_rechecks_installation_and_source_before_first_input(self):
        state=dict(checks=[],transmitted_bytes=0)
        def fail(): raise ValueError('changed')
        with patch.object(trial.t.shell,'receive',return_value=self.boot()), \
             patch.object(trial,'commands') as commands:
            with self.assertRaisesRegex(ValueError,'changed'): recorder.trial(1,None,30,state,fail)
            commands.assert_not_called()
        self.assertEqual(state['transmitted_bytes'],0)
        self.assertEqual(state['checks'],[])


class StageTests(unittest.TestCase):
    def plan(self):
        with patch.object(staging.package_check,'inspect',return_value=dict(
            image='/candidate',image_sha256=staging.NEW_SHA,image_bytes=trial.IMAGE_BYTES)):
            return staging.load_plan(staging.ROOT/'build/rpi5/bl33-probe-vszhh6o4',
                                     'deadbeef-0000-0000-0000-000000000001')

    def test_complete_chain_fixed_profile_and_no_shared_mutation(self):
        before=dict(staging.base.install_core.INSTALL_NAMES)
        plan=self.plan()
        self.assertEqual(len(plan['nvme_backups']),40)
        self.assertEqual(plan['old_image_sha256'],staging.previous.NEW_SHA)
        self.assertEqual(plan['protected_sha256']['boot'],staging.FAT_SHA)
        source=staging.remote_source(plan); compile(source,'<remote>','exec')
        self.assertIn("INSTALL_NAMES['socket-identity-trial']=",source)
        self.assertEqual(staging.remote_template().count(repr(staging.PREVIOUS_NAME)),3)
        self.assertEqual(staging.base.install_core.INSTALL_NAMES,before)
        plan['source_sha256'][str(Path(staging.__file__))]='0'*64
        with self.assertRaises(ValueError): staging.remote_source(plan)

    def test_full_result_validation_rejects_each_missing_field_and_changed_protection(self):
        plan=self.plan(); plan['run']='/home/sandrzej/xnu-gate6-socket-id-abcdefgh'
        result=json.loads((staging.HISTORY/'result.json').read_text())
        result.update(run=plan['run'],image_sha256=staging.NEW_SHA,
            preserved_sd_image_sha256=staging.OLD_SHA,nvme_previous_image_sha256=staging.OLD_SHA,
            sd_backup=staging.NAMES[0],nvme_backups_verified=plan['nvme_backups'],
            identity=dict(identity=plan['identity_binding']['expected'],boot_id=plan['linux_boot_id'],hostname='kamidana'),
            protected_files_sha256=dict(plan['protected_files'],**{'probe.bin':staging.NEW_SHA,staging.NAMES[0]:staging.OLD_SHA}))
        result['backups'][1]['sha256']=staging.FAT_SHA
        staging.validate_result(result,plan)
        for field in result:
            altered=copy.deepcopy(result); del altered[field]
            with self.subTest(field=field),self.assertRaises(ValueError): staging.validate_result(altered,plan)
        altered=copy.deepcopy(result); altered['protected_after']['hfs']['sha256']='0'*64
        with self.assertRaises(ValueError): staging.validate_result(altered,plan)

    def test_bad_history_old_boot_and_wrong_candidate_refuse(self):
        with patch.object(staging,'HISTORY_SHA',{'plan.json':'0'*64}),self.assertRaises(ValueError): self.plan()
        boot=json.loads((staging.HISTORY/'result.json').read_text())['identity']['boot_id']
        with self.assertRaises(ValueError): staging.load_plan(Path('/candidate'),boot)
        with patch.object(staging.package_check,'inspect',return_value=dict(
            image='/candidate',image_sha256='0'*64,image_bytes=trial.IMAGE_BYTES)),self.assertRaises(ValueError):
            staging.load_plan(Path('/candidate'),'deadbeef-0000-0000-0000-000000000001')


class ReplayTests(unittest.TestCase):
    def test_preserved_physical_pi_capture_replays_without_device_access(self):
        result=audit.audit(build.old.ROOT/'build/rpi5/mac-socket-identity-trial-20261012')
        self.assertEqual(result['serial_sha256'],'c42a84b9cafab48c9a05443477f049fd434a5b8ede99da3abb968ad641088baf')
        self.assertEqual(result['runtime_identity']['file_hashes'],21)
        self.assertEqual([row['operations'] for row in result['socket_results']],[26,62])

    def fixture(self):
        report=package.inspect(build.old.ROOT/'build/rpi5/bl33-probe-vszhh6o4')
        receipt=json.loads(package.INIT.with_name('manifest.json').read_text())
        lines=[b'ROOTIDENTITY:BEGIN:FIXED_CATALOG_V1',
               b'ROOTIDENTITY:MOUNT:mockfs:/:READONLY:NODES=32:BYTES=1916928']
        for row in receipt['identity_catalog']:
            if row['path']=='/dev': line='ROOTIDENTITY:OVERLAY:/dev:devfs'
            elif row['mode'] & 0o170000 == 0o40000:
                line='ROOTIDENTITY:DIR:'+row['path']+':MODE='+str(row['mode'])
            else:
                line='ROOTIDENTITY:FILE:'+row['path']+':MODE='+str(row['mode'])+':BYTES='+str(row['bytes'])+':SHA256='+row['sha256']
            lines.append(line.encode())
        identity_raw=b'\n'.join([*lines,b'ROOTIDENTITY:PASS:COMPARE_SELF_AND_EXTENT_EXTERNALLY',b'ROOT_IDENTITY_STATUS:0'])+b'\n'
        socket_outputs=[]
        for mode in ('unix','inet'):
            lines=[b'SOCKETPROBE:BEGIN:RAW_DARWIN_V1',b'SOCKETPROBE:MODE='+
                   (b'unix' if mode=='unix' else b'inet_LOOPBACK_ONLY'),
                   *[b'SOCKETPROBE:STREAM_PAYLOAD_MATCH=32']*3,b'SOCKETPROBE:STREAM_EOF=0',
                   b'SOCKETPROBE:OPERATIONS='+ (b'26' if mode=='unix' else b'62')]
            if mode=='inet': lines.extend([*[b'SOCKETPROBE:UDP_PAYLOAD_AND_PEER_MATCH=32']*2,
                                          b'SOCKETPROBE:UDP_PASS',b'SOCKETPROBE:TCP_PASS'])
            socket_outputs.append(b'\n'.join([*lines,b'SOCKETPROBE:PASS',b'SOCKETPROBE:END:NOT_ETHERNET_OR_SSH_PROOF',b'SOCKET_STATUS:0'])+b'\n')
        nonce='S0123456789abcdef'; sent=audit.commands(nonce)
        startup=b'DARWIN:ZSH:ENTRY\nDARWIN:ZSH:TSD\nDARWIN:ZSH:ENTROPY\nDARWIN:ZSH:MAIN\n'
        outputs=[startup+identity_raw,nonce.encode()+b'\n',b'\n'.join(trial.t.SMOKE_LINES)+b'\n',b'0\n',
                 *socket_outputs,('RECOVERED_'+nonce+'\n').encode()]
        raw=TrialAdmissionTests().boot()
        for command,output in zip(sent,outputs): raw+=command.encode()+b'\n'+output+b'xnu:/# '
        installed=dict(directory='/synthetic',plan_sha256='a'*64,result_sha256='b'*64)
        state=dict(status='passed',checks=audit.CHECKS.copy(),baud=115200,device='/dev/cu.usbmodem102',
            preflight=report,installation=installed,bytes=len(raw),serial_sha256=hashlib.sha256(raw).hexdigest(),
            recorder_source_sha256=recorder.source_pins(),nonce=nonce,
            started_utc='2026-10-12T21:00:00+00:00',ended_utc='2026-10-12T21:02:00+00:00',
            transmitted_bytes=sum(len(command)+1 for command in sent),
            runtime_identity=evidence.validate(identity_raw,receipt),
            socket_results=[trial.socket_result(value,mode) for value,mode in zip(socket_outputs,('unix','inet'))],
            strict_historical_mount_marker_trial_waived=False,nic_ready=False,ssh=False,durability=False)
        return state,raw,report,installed,receipt

    def test_exact_raw_command_runtime_identity_and_socket_replay(self):
        result=audit.replay(*self.fixture())
        self.assertTrue(result['runtime_identity']['self_digest_verified'])
        self.assertEqual([row['mode'] for row in result['socket_results']],['unix','inet'])
        self.assertFalse(result['nic_ready'])

    def test_rehashed_wrong_commands_root_hash_payload_and_broader_claims_reject(self):
        state,raw,report,installed,receipt=self.fixture()
        for altered in (raw.replace(b'SHA256=',b'SHA256=0',1),
                        raw.replace(b'SOCKET_STATUS:0',b'SOCKET_STATUS:1',1),
                        raw.replace(b'ROOTIDENTITY:OVERLAY:/dev:devfs',b'ROOTIDENTITY:DIR:/dev:MODE=16749'),
                        raw.replace(audit.commands(state['nonce'])[0].encode(),b'echo fake',1)):
            changed=copy.deepcopy(state); changed.update(bytes=len(altered),serial_sha256=hashlib.sha256(altered).hexdigest())
            with self.assertRaises(ValueError): audit.replay(changed,altered,report,installed,receipt)
        for name in ('nic_ready','ssh','durability','strict_historical_mount_marker_trial_waived'):
            changed=copy.deepcopy(state); changed[name]=True
            with self.assertRaises(ValueError): audit.replay(changed,raw,report,installed,receipt)

    def test_first_echo_exact_readiness_and_watchdog_interleaving_only(self):
        state,raw,report,installed,receipt=self.fixture()
        command=audit.commands(state['nonce'])[0].encode()
        frame=b'\nRPI5XNU:SHELL:READY\nxnu:/# '
        echo=command[:35]+frame+command[35:60]+b'RPI5XNU:TERMINAL:WATCHDOG_KICK RELOADS=1\n'+command[60:]+b'\n'+frame+b'\n'
        altered=raw.replace(command+b'\n',echo,1)
        changed=copy.deepcopy(state); changed.update(bytes=len(altered),serial_sha256=hashlib.sha256(altered).hexdigest())
        audit.replay(changed,altered,report,installed,receipt)
        for bad in (altered.replace(b'RELOADS=1',b'RELOADS=0'),
                    altered.replace(frame,frame+b'UNEXPECTED',1)):
            changed.update(bytes=len(bad),serial_sha256=hashlib.sha256(bad).hexdigest())
            with self.assertRaises(ValueError): audit.replay(changed,bad,report,installed,receipt)


if __name__=='__main__': unittest.main()
