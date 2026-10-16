# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic protocol/real host parser proof, never Pi or pthread acceptance."""
import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from tools.rpi5 import root42_pthread_trial_core as core
from tools.rpi5 import check_root42_pthread_root as root
from tools.rpi5.tests import test_root41_batch_trial as fixture
from tools.rpi5.tests.test_root96_trial import identity_bytes

NONCE=fixture.NONCE


def batch(files):
    old=fixture.batch(files).replace(b'\n/\n',b'\n'+b'\n'.join(core.PWD_STARTUP)+b'\n/\n')
    value=old.replace(b'B41:',b'B42:')
    final=('B42:'+NONCE+':END:0').encode()
    pthread=b'\n'.join((('B42:'+NONCE+':pthread:B').encode(),*core.PTHREAD_LINES,('B42:'+NONCE+':pthread:E:0').encode()))
    return value.replace(final,pthread+b'\n'+final)


class PthreadTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt=json.loads((root.PACKAGE/'manifest.json').read_text())
        cls.files=root.old.profile.files_from((root.PACKAGE/'ramdisk.bin').read_bytes())
        cls.report=dict(image_bytes=20971520,root_nodes=42,root_files=30,
            root_copy_marker='RPI5XNU:FIXTURE:EXACT_ROOT_COPY',kernel_copy_marker='RPI5XNU:FIXTURE:EXACT_KERNEL_COPY',
            root_mount_marker=f'RPI5XNU:RAMROOT:MOUNT NODES=42 BYTES={len((root.PACKAGE/"ramdisk.bin").read_bytes())} READONLY',
            watchdog_ready_marker=core.WATCHDOG.decode(),watchdog_ready_profile=core.WATCHDOG_PROFILE,
            trial_marker='RPI5XNU:BL33:ROOT42_PTHREAD_TRIAL TAG='+'a'*32+' CPUS=4 ROOT_NODES=42 WATCHDOG_READY_V2',
            handoff={k:True for k in ('required_by_kernel','linked_loader_handoff','descriptor_not_confused_with_kernel_string')})

    def test_strict_new_boot_and_old_profile_rejection(self):
        raw=fixture.boot(self.report)
        self.assertTrue(core.boot_ready(raw,self.report))
        old=copy.deepcopy(self.report);old['root_nodes']=41
        with self.assertRaises(RuntimeError):core.boot_ready(raw,old)
        for before,after in ((b'ROOT42_PTHREAD_TRIAL',b'ROOT96_BATCH_TRIAL'),(b'NODES=42',b'NODES=41'),
                             (core.FDT,b''),(core.DEVICE,b''),(core.WATCHDOG,b'')):
            with self.subTest(before=before):
                try:self.assertFalse(core.boot_ready(raw.replace(before,after),self.report))
                except RuntimeError:pass
        for tail in (core.WATCHDOG,core.t.ENTRY,b'Boot mode: NVME (06)',b'panic(cpu 0)'):
            with self.assertRaises(RuntimeError):core.boot_ready(raw+tail,self.report)
        self.assertFalse(core.boot_ready(raw[:raw.index(core.WATCHDOG)],self.report))

    def test_all_nine_outputs_preserve_v2_pwd_without_early_exit_claim(self):
        core.validate_root(self.receipt,self.files)
        result=core.inspect_batch(batch(self.files),NONCE,self.files)
        self.assertEqual(len(result['commands']),9)
        self.assertEqual(core.STEPS[:8],core.prior.STEPS)
        self.assertTrue(result['actual_pthread_startup_constructor_create_join_mutex_tsd_errno'])
        self.assertFalse(result['batch_process_exit_verified'])
        self.assertFalse(result['entropy_qualified'])
        for key in ('networking','ssh_transport','ssh_daemon'):self.assertFalse(result[key])

    def test_missing_duplicate_old_wrong_output_and_status_rejected(self):
        raw=batch(self.files)
        changes=((b':pthread:E:0',b':pthread:E:1'),(b'THREADS=4',b'THREADS=3'),(b'JOIN=4',b'JOIN=0'),
            (b'TSD_DTORS=4',b'TSD_DTORS=0'),(b'CTOR=1',b'CTOR=0'),(b'ERRNO=4',b'ERRNO=1'),
            (core.PTHREAD_LINES[0],b''),(b':pwd:E:0',b':pwd:E:1'),(core.PWD_STARTUP[1],b''),
            (b'B42:',b'B41:'),(b':END:0',b':END:1'))
        for before,after in changes:
            with self.subTest(before=before),self.assertRaises(ValueError):core.inspect_batch(raw.replace(before,after),NONCE,self.files)
        for body in (raw+b'\n'+core.markers(NONCE)[0],raw.replace(core.PTHREAD_LINES[0],core.PTHREAD_LINES[0]+b'\n'+core.PTHREAD_LINES[0])):
            with self.assertRaises(ValueError):core.inspect_batch(body,NONCE,self.files)

    def test_actual_parser_bounds_and_real_host_zsh_fail_fast(self):
        with tempfile.TemporaryDirectory(prefix='root42-parser-') as name:
            program=Path(name)/'parser'
            p=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                '-I'+str(root.ROOT/'tools/rpi5/user'),str(root.ROOT/'tools/rpi5/user/parser.c'),
                str(root.ROOT/'tools/rpi5/tests/root41_batch_parser_harness.c'),'-o',str(program)],capture_output=True,text=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stderr)
            command=core.batch_command(NONCE);self.assertEqual(len(command),538)
            parsed=subprocess.check_output([program,command],text=True)
            self.assertEqual(parsed.splitlines(),['/bin/zsh','-f','-c',core.script(NONCE)])
            self.assertEqual(subprocess.check_output([program,core.recovery_command(NONCE)],text=True).splitlines(),
                             ['echo','B42:'+NONCE+':RECOVERY_STATUS:17'])
        for failed in (None,'pthread'):
            steps=tuple((n,'/usr/bin/false' if n==failed else '/usr/bin/true') for n,_ in core.STEPS)
            with patch.object(core,'STEPS',steps):script=core.script(NONCE)
            p=subprocess.run(['/bin/zsh','-f','-c',script],capture_output=True,text=True,timeout=5)
            if failed is None:self.assertEqual((p.returncode,p.stdout.encode().splitlines()),(0,core.markers(NONCE)))
            else:self.assertEqual(p.returncode,1);self.assertIn(':pthread:E:1',p.stdout);self.assertNotIn(':END:0',p.stdout)

    def test_three_fresh_exchanges_and_missing_exit_never_accepted(self):
        for missing_exit in (False,True):
            state=dict(checks=[core.CHECKS[0]],exchanges=[],transmitted_bytes=0);output=io.BytesIO();calls=[]
            def exchange(fd,out,command,expected,progress,deadline):
                calls.append(command)
                if command==core.IDENTITY:value=identity_bytes(self.receipt)+b'\nxnu:/# '
                elif command==core.batch_command(NONCE):value=batch(self.files)
                elif missing_exit:raise TimeoutError('No actual recovery status')
                else:value=b'\n'+expected[0]+b'\nxnu:/# '
                out.write(value);progress['transmitted_bytes']+=len(command)+1;return value
            with patch.object(core.secrets,'token_hex',return_value=NONCE[1:]),\
                patch.object(core,'bounded_exchange',side_effect=exchange),patch.object(core,'drain_pending',return_value=b''):
                if missing_exit:
                    with self.assertRaises(TimeoutError):core.commands(-1,output,state,self.receipt,self.files,lambda:None,time.monotonic()+120)
                else:core.commands(-1,output,state,self.receipt,self.files,lambda:None,time.monotonic()+120)
            self.assertEqual(calls,[core.IDENTITY,core.batch_command(NONCE),core.recovery_command(NONCE)])
            self.assertIs(state['batch']['batch_process_exit_verified'],not missing_exit)
            self.assertEqual(state['checks'],core.CHECKS[:3] if missing_exit else core.CHECKS)

    def test_expired_budget_refuses_input(self):
        state=dict(checks=[],exchanges=[],transmitted_bytes=0)
        with patch.object(core,'bounded_exchange') as tx:
            with self.assertRaises(TimeoutError):core.commands(-1,io.BytesIO(),state,self.receipt,self.files,lambda:None,time.monotonic()+44)
            tx.assert_not_called()


if __name__=='__main__':unittest.main()
