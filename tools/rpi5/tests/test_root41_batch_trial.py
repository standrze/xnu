# SPDX-License-Identifier: BSD-2-Clause
"""Actual root bytes/parser + host shell framing; fixtures are never Pi proof."""
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from tools.rpi5 import root41_batch_trial_core as core
from tools.rpi5 import root41_batch_evidence as evidence
from tools.rpi5 import check_root96_command_package as package
from tools.rpi5.tests.test_root96_trial import identity_bytes
from tools.rpi5.tests.test_zsh_metadata_serial import observations
from tools.rpi5.tests.test_zsh_metadata_audit import diagnostic

NONCE='B0123456789abcdef'


def boot(report):
    return b'\n'.join((b'Boot mode: SD (01)',b'Read probe.bin bytes '+str(report['image_bytes']).encode()+b' hnd 0',
        core.t.ENTRY,report['trial_marker'].encode(),core.t.TERMINAL_LOADER,core.DEVICE,core.FDT,report['root_copy_marker'].encode(),
        report['kernel_copy_marker'].encode(),core.t.package_check.TOPOLOGY_PASS,core.t.TRANSFER,core.previous.prior.COMMIT,
        report['root_mount_marker'].encode(),core.t.READY,b'xnu:/# ',core.WATCHDOG,core.t.READY,b'xnu:/# '))


def batch(files,nonce=NONCE):
    motd=files['/etc/motd'][0]
    hexed=b''.join(f'{v:02x}'.encode()+(b'\n' if (i+1)%16==0 else b' ') for i,v in enumerate(motd))
    if len(motd)%16:hexed+=b'\n'
    bodies={'zsh':b'DARWIN:ZSH:MAIN\n'+b'\n'.join(core.t.SMOKE_LINES),'buffer':core.previous.BEGIN+b'\n'+core.previous.PASS,
        'crypto':core.CRYPTO_BEGIN+b'\n'+core.CRYPTO_PASS,'pwd':b'/','uname':b'Darwin',
        'wc':f'{motd.count(bytes([10]))} {len(motd.split())} {len(motd)}'.encode(),
        'hex':hexed.rstrip(b'\n'),'stat':diagnostic(observations(files))}
    markers=core.markers(nonce);rows=[markers[0]]
    for i,(name,_) in enumerate(core.STEPS):rows.extend((markers[1+2*i],bodies[name],markers[2+2*i]))
    rows.extend((markers[-1],b'xnu:/# '))
    return b'\n'+b'\n'.join(rows)


class BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preflight=package.inspect(package.PACKAGE)
        cls.receipt=json.loads((package.PACKAGE/'manifest.json').read_text())
        cls.files=package.builder.profile.files_from((package.PACKAGE/'ramdisk.bin').read_bytes())
        cls.report=dict(image_bytes=20971520,root_copy_marker='RPI5XNU:FIXTURE:EXACT_ROOT_COPY',
            kernel_copy_marker='RPI5XNU:FIXTURE:EXACT_KERNEL_COPY',
            root_mount_marker=f'RPI5XNU:RAMROOT:MOUNT NODES=41 BYTES={cls.preflight["root_bytes"]} READONLY',
            watchdog_ready_marker=core.WATCHDOG.decode(),watchdog_ready_profile=core.WATCHDOG_PROFILE,
            trial_marker='RPI5XNU:BL33:ROOT96_BATCH_TRIAL TAG='+'a'*32+' CPUS=4 ROOT_NODES=41 WATCHDOG_READY_V2',
            handoff={k:True for k in ('required_by_kernel','linked_loader_handoff','descriptor_not_confused_with_kernel_string')})

    def test_watchdog_requires_later_prompt_not_first_ready(self):
        raw=boot(self.report);self.assertTrue(core.boot_ready(raw,self.report))
        prefix=raw[:raw.index(core.WATCHDOG)]
        self.assertFalse(core.boot_ready(prefix,self.report))
        self.assertFalse(core.boot_ready(prefix+core.WATCHDOG+b'\n',self.report))
        self.assertFalse(core.boot_ready(prefix+core.WATCHDOG+b'\nxnu:/# ',self.report))
        self.assertFalse(core.boot_ready(prefix+core.WATCHDOG+b'\n'+core.t.READY,self.report))
        for old,new in ((b'20971520',b'20971519'),(b'NODES=41',b'NODES=33'),
                        (core.FDT,b''),(core.DEVICE,b''),(core.previous.prior.COMMIT,b'')):
            with self.subTest(old=old):
                try:self.assertFalse(core.boot_ready(raw.replace(old,new),self.report))
                except RuntimeError:pass
        self.assertFalse(core.boot_ready(raw.replace(self.report['trial_marker'].encode(),b'wrong-tag'),self.report))
        for tail in (core.WATCHDOG,core.t.ENTRY,b'Boot mode: NVME (06)',b'panic(cpu 0)'):
            with self.subTest(tail=tail),self.assertRaises(RuntimeError):core.boot_ready(raw+tail,self.report)
        for old in (core.WATCHDOG,self.report['trial_marker'].encode()):
            with self.assertRaises(RuntimeError):core.boot_ready(raw.replace(old,old+b'X'),self.report)

    def test_actual_41node_29file_self_identity_and_batch_outputs(self):
        self.assertEqual(core.identity.validate(identity_bytes(self.receipt),self.receipt)['file_hashes'],29)
        value=core.inspect_batch(batch(self.files),NONCE,self.files)
        self.assertEqual(len(value['commands']),8);self.assertTrue(value['metadata']['raw_metadata_accepted'])
        self.assertFalse(value['batch_process_exit_verified']);self.assertFalse(value['ssh_transport'])
        with self.assertRaises(ValueError):core.identity.validate(identity_bytes(self.receipt).replace(b'SHA256=',b'SHA256=0',1),self.receipt)

    def test_missing_duplicate_nonzero_wrong_output_and_crypto_fail_rejected(self):
        raw=batch(self.files)
        changes=((b':pwd:E:0',b':pwd:E:1'),(b'\n/\n',b'\n/etc\n'),(b'\nDarwin\n',b'\nLinux\n'),
            (core.CRYPTO_PASS,b'RPI5XNU:SSHCRYPTO:FAIL'),(core.previous.PASS,b''),
            (b'RPI5XNU:ZSH:SMOKE_DONE',b''),(b'STATPROBE:BUFFER_DAMAGE=0',b'STATPROBE:BUFFER_DAMAGE=1'),
            (b':hex:B',b':wrong:B'),(b':END:0',b':END:1'))
        for before,after in changes:
            with self.subTest(before=before),self.assertRaises(ValueError):core.inspect_batch(raw.replace(before,after),NONCE,self.files)
        for bad in (raw+b'\n'+core.markers(NONCE)[0]+b'\n',raw.replace(NONCE.encode(),b'Bffffffffffffffff')):
            with self.assertRaises(ValueError):core.inspect_batch(bad,NONCE,self.files)

    def test_actual_recovery_parser_preserves_full_single_zsh_argument_and_exit_query(self):
        root=package.ROOT
        with tempfile.TemporaryDirectory(prefix='root41-parser-') as temporary:
            binary=Path(temporary)/'parser'
            result=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                '-I'+str(root/'tools/rpi5/user'),str(root/'tools/rpi5/user/parser.c'),
                str(root/'tools/rpi5/tests/root41_batch_parser_harness.c'),'-o',str(binary)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            command=core.batch_command(NONCE);self.assertLessEqual(len(command),1023)
            parsed=subprocess.run([str(binary),command],capture_output=True,text=True,timeout=5,check=True)
            self.assertEqual(parsed.stdout.splitlines(),['/bin/zsh','-f','-c',core.script(NONCE)])
            parsed=subprocess.run([str(binary),core.recovery_command(NONCE)],capture_output=True,text=True,timeout=5,check=True)
            self.assertEqual(parsed.stdout.splitlines(),['echo','B41:'+NONCE+':RECOVERY_STATUS:17'])

    def test_host_zsh_function_framing_and_fail_fast_are_real_but_not_target_execution(self):
        for failure in (None,'crypto'):
            cases=tuple((name,'/usr/bin/false' if name==failure else '/usr/bin/true') for name,_ in core.STEPS)
            with patch.object(core,'STEPS',cases):source=core.script(NONCE)
            result=subprocess.run(['/bin/zsh','-f','-c',source],capture_output=True,text=True,timeout=5)
            if failure is None:
                self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.encode().splitlines(),core.markers(NONCE))
            else:
                self.assertEqual(result.returncode,1);self.assertIn(':crypto:E:1',result.stdout)
                self.assertNotIn(':pwd:B',result.stdout);self.assertNotIn(':END:0',result.stdout)

    def test_three_exchanges_identity_then_batch_then_true_recovery_status(self):
        state=dict(checks=[core.CHECKS[0]],exchanges=[],transmitted_bytes=0);output=io.BytesIO();output.write(boot(self.report));calls=[]
        def exchange(fd,out,command,expected,progress,deadline):
            calls.append(command)
            if command==core.IDENTITY:value=identity_bytes(self.receipt)+b'\nxnu:/# '
            elif command==core.batch_command(NONCE):value=batch(self.files)
            else:value=b'\n'+expected[0]+b'\nxnu:/# '
            out.write(value);progress['transmitted_bytes']+=len(command)+1;return value
        with patch.object(core.secrets,'token_hex',return_value=NONCE[1:]),\
            patch.object(core,'bounded_exchange',side_effect=exchange),patch.object(core,'drain_pending',return_value=b''):
            core.commands(-1,output,state,self.receipt,self.files,lambda:None,time.monotonic()+120)
        self.assertEqual(calls,[core.IDENTITY,core.batch_command(NONCE),core.recovery_command(NONCE)])
        self.assertEqual(state['checks'],core.CHECKS);self.assertTrue(state['batch']['batch_process_exit_verified'])
        self.assertLess(state['transmitted_bytes']*0.025,30)
        raw=output.getvalue();state.update(bytes=len(raw),serial_sha256=hashlib.sha256(raw).hexdigest(),
            commands_complete_seconds_after_admission=26,return_capture_offset=len(raw))
        replay=evidence.replay_commands(state,raw,self.report,self.receipt,self.files)
        self.assertTrue(replay['batch']['batch_process_exit_verified']);self.assertFalse(replay['ssh_transport'])
        for key,value in (('transmitted_bytes',0),('commands_complete_seconds_after_admission',120),
                          ('commands_complete_seconds_after_admission',float('nan'))):
            bad=copy.deepcopy(state);bad[key]=value
            with self.assertRaises(ValueError):evidence.replay_commands(bad,raw,self.report,self.receipt,self.files)
        bad=copy.deepcopy(state);bad['batch']['batch_process_exit_verified']=False
        with self.assertRaises(ValueError):evidence.replay_commands(bad,raw,self.report,self.receipt,self.files)
        changed=dict(self.files);changed['/etc/motd']=(b'changed',0o444)
        with self.assertRaises(ValueError):core.validate_root(self.receipt,changed)

    def test_budget_and_pending_reboot_refuse_all_further_input(self):
        state=dict(checks=[],exchanges=[],transmitted_bytes=0)
        with patch.object(core,'bounded_exchange') as tx:
            with self.assertRaises(TimeoutError):core.commands(-1,io.BytesIO(),state,self.receipt,self.files,lambda:None,time.monotonic()+44)
            tx.assert_not_called()
        with patch.object(core,'drain_pending',return_value=b'RPi: BOOTSYS release VERSION: reset\n'),patch.object(core,'bounded_exchange') as tx:
            with self.assertRaises(ValueError):core.commands(-1,io.BytesIO(),state,self.receipt,self.files,lambda:None,time.monotonic()+120)
            tx.assert_not_called()
        with patch.object(core.os,'write') as tx:
            with self.assertRaises(TimeoutError):core.bounded_exchange(-1,io.BytesIO(),'echo no',[],state,time.monotonic()-1)
            tx.assert_not_called()

    def test_identity_failure_never_enters_batched_executables(self):
        state=dict(checks=[],exchanges=[],transmitted_bytes=0);calls=[]
        def exchange(fd,out,command,expected,progress,deadline):
            calls.append(command);raw=identity_bytes(self.receipt).replace(b'SHA256=',b'SHA256=f',1)+b'\nxnu:/# '
            out.write(raw);return raw
        with patch.object(core,'bounded_exchange',side_effect=exchange),patch.object(core,'drain_pending',return_value=b''):
            with self.assertRaises(ValueError):core.commands(-1,io.BytesIO(),state,self.receipt,self.files,lambda:None,time.monotonic()+120)
        self.assertEqual(calls,[core.IDENTITY])

    def test_reset_during_tx_and_absolute_per_byte_deadline_stop_writes(self):
        state=dict(transmitted_bytes=0)
        with patch.object(core.select,'select',return_value=([7],[],[])),\
            patch.object(core.t.shell,'receive',return_value=b'RPi: BOOTSYS release VERSION: reset\n'),patch.object(core.os,'write') as tx:
            with self.assertRaisesRegex(RuntimeError,'Reset'):core.bounded_exchange(7,io.BytesIO(),'echo no',[],state,time.monotonic()+120)
            tx.assert_not_called()
        clock=[0.0]
        def select_ready(read,write,error,timeout):return ([],write,[])
        def advance(seconds):clock[0]+=seconds
        with patch.object(core.time,'monotonic',side_effect=lambda:clock[0]),patch.object(core.time,'sleep',side_effect=advance),\
            patch.object(core.select,'select',side_effect=select_ready),patch.object(core.os,'write',return_value=1) as tx:
            with self.assertRaises(TimeoutError):core.bounded_exchange(7,io.BytesIO(),'echo no',[],state,0.026)
            self.assertEqual(tx.call_count,2);self.assertEqual(state['transmitted_bytes'],2)


if __name__=='__main__':unittest.main()
