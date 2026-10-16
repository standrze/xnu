# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic write recorder guards/transport, never physical write acceptance."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import serial_hfs_write_trial as runner
import hfs_write_serial_results as files
from hfs_write_results import VECTORS,payload
from tools.rpi5.tests.test_hfs_write_installer import WriteInstallerTests


class WriteRecorderTests(unittest.TestCase):
    admission=b'RPI5XNU:SD:WRITE_ADMITTED SECTORS=250347520 START=1050624 BLOCKS=262144 EPOCH=1 CACHE=1 SPEC=3 DMA=0'
    hfs=b'RPI5XNU:HFS:REGISTERED'
    shell=b'RPI5XNU:SHELL:READY'

    def raw(self,cache=1,order=False):
        rows=[runner.TERMINAL_LOADER,runner.WRITE_LOADER,self.admission.replace(b'CACHE=1',f'CACHE={cache}'.encode()),self.hfs,self.shell]
        if order: rows[2],rows[3]=rows[3],rows[2]
        return b'\r\r\n'.join(rows)+b'\r\r\n'

    def progress(self):
        return dict(checks=[],reads=[],transmitted_bytes=0,write_batch_attempts=0,hfs_mounted=False)

    def test_exact_cache_absent_or_disabled_fresh_boot_and_concurrent_registration(self):
        for cache in (1,2):
            for order in (False,True):
                result=runner.validate_boot(self.raw(cache,order))
                self.assertEqual(result['cache_state'],cache)
                self.assertEqual(result['epoch'],1)

    def test_partial_echo_or_early_shell_never_authorizes_input(self):
        raw=self.raw()
        for end in range(len(raw)):
            self.assertIsNone(runner.validate_boot(raw[:end]))
        self.assertIsNone(runner.validate_boot(raw.replace(b'\r\r\n'+self.shell,b'\r\r\necho '+self.shell)))
        early=b'\n'.join((runner.TERMINAL_LOADER,runner.WRITE_LOADER,self.shell,self.hfs,self.admission))+b'\n'
        self.assertIsNone(runner.validate_boot(early))
        self.assertIsNotNone(runner.validate_boot(early+self.shell+b'\n'))

    def test_wrong_extent_cache_unknown_torn_admission_duplicate_reset_or_panic_reject(self):
        variants=[self.raw().replace(b'EPOCH=1',b'EPOCH=0'),self.raw().replace(b'EPOCH=1',b'EPOCH=18446744073709551616'),
            self.raw().replace(b'CACHE=1',b'CACHE=3'),self.raw().replace(b'CACHE=1',b'CACHE=0'),
            self.raw().replace(b'START=1050624',b'START=2048'),self.raw().replace(b'SPEC=3',b'SPEC=7'),
            self.raw().replace(b'BLOCKS=262144',b'BLOCKS=262145'),self.raw().replace(b'SECTORS=250347520',b'SECTORS=250347521'),
            self.raw().replace(b'DMA=0',b'DMA=1'),self.raw().replace(b'CACHE=1',b'CAC\rHE=1'),
            self.raw()+runner.WRITE_LOADER+b'\n',self.raw()+b'panic(cpu',self.raw()+b'RPI5XNU:SD:READ_ONLY_READY',
            self.raw().replace(runner.TERMINAL_LOADER,runner.WRITE_LOADER,1)]
        for raw in variants:
            with self.subTest(raw=raw[-150:]),self.assertRaises(ValueError): runner.validate_boot(raw)

    def test_old_or_unready_boot_sends_no_commands(self):
        for raw in (b'RPI5XNU:BL33:HFS_READONLY_TRIAL',b'RPI5XNU:SD:READ_ONLY_READY',b'panic(cpu',
                    b'RPI5XNU:SD:WRITE_INIT_FAIL STAGE=CACHE_PROBE RC=-2',
                    b'RPI5XNU:SD:WRITE_START_FAIL STAGE=BINDING'):
            progress=self.progress()
            with patch.object(runner,'receive',return_value=raw),patch.object(runner.time,'monotonic',return_value=0), \
                    patch.object(runner,'command') as command,self.assertRaises(ValueError):
                runner.trial(1,io.BytesIO(),30,progress)
            command.assert_not_called(); self.assertEqual(progress['transmitted_bytes'],0)
        with patch.object(runner.time,'monotonic',side_effect=[0,31]),patch.object(runner,'command') as command, \
                self.assertRaises(TimeoutError): runner.trial(1,io.BytesIO(),30,self.progress())
        command.assert_not_called()

    def test_complete_batch_has_one_exercise_full_reads_and_normal_unmount(self):
        progress=self.progress(); calls=[]
        def command(fd,output,text,expected,state,**kwargs):
            calls.append(text); return b'\n'.join(expected)+b'\nxnu:/# '
        with patch.object(runner,'wait_boot',return_value={'cache_state':1}),patch.object(runner,'command',side_effect=command), \
                patch.object(runner,'read_file',side_effect=lambda fd,o,e,p:dict(e,nonce='H'+'1'*16)):
            runner.trial(1,io.BytesIO(),30,progress)
        self.assertEqual(progress['checks'],runner.CHECKS)
        self.assertEqual(progress['write_batch_attempts'],1); self.assertFalse(progress['hfs_mounted'])
        self.assertEqual(len(progress['reads']),5)
        self.assertEqual(calls.count('hfswrite exercise'),1)
        self.assertLess(calls.index('hfswrite exercise'),calls.index('hfsrw unmount'))
        self.assertFalse(any('reboot' in text or 'sync'==text for text in calls))

    def test_failure_at_each_command_or_read_never_sends_cleanup_or_retry(self):
        # Fail each of the eight command positions, and all five full-file reads.
        for failure in range(8):
            progress=self.progress(); sent=[]
            def command(fd,out,text,expected,p,**kwargs):
                sent.append(text)
                if len(sent)==failure+1: raise RuntimeError('modeled command failure')
            with patch.object(runner,'wait_boot',return_value={}),patch.object(runner,'command',side_effect=command), \
                    patch.object(runner,'read_file',return_value={}),self.assertRaises(RuntimeError):
                runner.trial(1,io.BytesIO(),30,progress)
            self.assertEqual(len(sent),failure+1)
            self.assertLessEqual(sent.count('hfswrite exercise'),1)
        for failure in range(5):
            progress=self.progress()
            with patch.object(runner,'wait_boot',return_value={}),patch.object(runner,'command') as command, \
                    patch.object(runner,'read_file',side_effect=[{}]*failure+[ValueError('bad file')]),self.assertRaises(ValueError):
                runner.trial(1,io.BytesIO(),30,progress)
            self.assertFalse(any(call.args[2]=='hfsrw unmount' for call in command.call_args_list))

    def test_full_exact_write_vectors_and_corruption_are_independently_checked(self):
        for entry,(_,length,seed) in zip(files.expected_entries(),VECTORS):
            content=payload(length,seed); nonce='H0123456789abcdef'; begin,end=files.frame_markers(nonce)
            rows=[content[n:n+16].hex(' ').encode()+(b' ' if len(content[n:n+16])<16 else b'') for n in range(0,length,16)]
            raw=b'\r\r\n'.join([begin,*rows,end])+b'\r\r\n'
            self.assertEqual(files.parse_file(raw,entry,nonce)['sha256'],entry['sha256'])
            with self.assertRaises(ValueError): files.parse_file(raw.replace(end,b'END'),entry,nonce)
            with patch.object(files,'command',return_value=raw) as command,patch.object(files.secrets,'token_hex',return_value=nonce[1:]):
                self.assertEqual(files.read_file(1,io.BytesIO(),entry,self.progress())['bytes'],length)
            self.assertEqual(command.call_args.kwargs['max_bytes'],262144)
        for entry in ({'path':'/etc/proof.txt','bytes':0,'sha256':hashlib.sha256(b'').hexdigest()},
                      dict(files.expected_entries()[0],path='/xnu-gate4-small.bin; reboot'),
                      dict(files.expected_entries()[0],bytes=True),dict(files.expected_entries()[0],sha256='f'*64)):
            with patch.object(files,'command') as command,self.assertRaises(ValueError):
                files.read_file(1,None,entry,self.progress())
            command.assert_not_called()

    def test_install_bindings_precede_port_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); inputs=root/'inputs.json'; inputs.write_text('{}')
            plan,result=WriteInstallerTests().result_bundle()
            (root/'plan.json').write_text(json.dumps(plan)); (root/'result.json').write_text(json.dumps(result))
            source=runner.installer.remote_source(dict(plan,expected={}))
            # A small rendered source double isolates evidence binding here;
            # full remote rendering and actual package checks have own tests.
            (root/'remote-source.sha256').write_text(hashlib.sha256(source.encode()).hexdigest()+'\n')
            expected={k:v for k,v in plan.items() if k!='run'}
            with patch.object(runner.installer,'evidence_path',side_effect=Path), \
                    patch.object(runner.installer,'load_plan',return_value=expected), \
                    patch.object(runner.installer,'remote_source',return_value=source):
                loaded,_,hashes=runner.load_inputs(inputs,root)
                self.assertEqual(loaded,plan); self.assertEqual(set(hashes),{'inputs','plan','result','remote_source'})
                for filename in ('plan.json','result.json','remote-source.sha256'):
                    original=(root/filename).read_bytes()
                    if filename=='plan.json': (root/filename).write_text(json.dumps(dict(plan,new_image_sha256='f'*64)))
                    elif filename=='result.json': (root/filename).write_text(json.dumps(dict(result,no_reboot=False)))
                    else: (root/filename).write_text('0'*64)
                    with self.subTest(filename=filename),self.assertRaises(ValueError): runner.load_inputs(inputs,root)
                    (root/filename).write_bytes(original)

    def test_rejected_evidence_prevents_output_directory_and_serial_open(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'rejected'
            argv=['serial_hfs_write_trial.py','/dev/cu.usbmodem102',str(output),'--inputs','bundle.json','--installed','installed']
            with patch.object(sys,'argv',argv),patch.object(runner,'valid_probe_device',return_value=True), \
                    patch.object(Path,'is_relative_to',return_value=True),patch.object(runner,'load_inputs',side_effect=ValueError('stale')), \
                    patch.object(runner.os,'open') as opened,self.assertRaises(ValueError): runner.main()
            opened.assert_not_called(); self.assertFalse(output.exists())


if __name__=='__main__': unittest.main()
