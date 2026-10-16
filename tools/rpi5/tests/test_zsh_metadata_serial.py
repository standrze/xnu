# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic admission/compatibility tests only; not Pi evidence."""
import copy
import io
import unittest
from unittest.mock import patch

from tools.rpi5 import serial_zsh_metadata_trial as trial
from tools.rpi5.tests.test_statprobe_trial import diagnostic


def boot():
    t = trial.t
    return b'\n'.join((b'Boot mode: SD (01)', b'Read probe.bin bytes 18908864 hnd 0x123',
                       t.ENTRY+b'0008',t.TERMINAL_LOADER,trial.COPY,trial.KERNEL,
                       t.package_check.TOPOLOGY_PASS,t.TRANSFER,trial.COMMIT,
                       trial.ROOT_MARKER,t.READY,b'xnu:/# '))


def observations(files):
    rows = trial.diagnostic.parse_diagnostic(diagnostic())
    for index,row in enumerate(rows['paths']):
        if index == 3:
            row['stat'] = row['lstat'] = dict(rc=-2,raw_hex='a5'*144,guards=1)
            continue
        content,permission = files[row['path']] if index < 2 else (b'',0o555)
        mode = permission | (0o100000 if index < 2 else 0o040000)
        for value in [row['stat'],row['lstat']] + [opened['fstat'] for opened in row['opens']]:
            raw = bytearray(144); raw[4:6] = mode.to_bytes(2,'little')
            raw[96:104] = len(content).to_bytes(8,'little',signed=True)
            value.update(raw_hex=raw.hex(),mode=mode,is_regular=index<2,is_directory=index==2)
        for opened in row['opens']:
            opened['duplicate_read'] = dict(rc=len(content[:16]),hex=content[:16].hex())
            opened['original_read'] = dict(rc=len(content[16:32]),hex=content[16:32].hex())
    return rows


class MetadataSerialTests(unittest.TestCase):
    def files(self):
        return trial.files_from(trial.package_check.previous.INIT.read_bytes())

    def test_strict_fresh_copy_kernel_mount_order_required(self):
        self.assertTrue(trial.boot_ready(boot()))
        self.assertFalse(trial.boot_ready(trial.t.READY+b'\nxnu:/# '))
        for bad in (boot()+trial.COPY,boot()+trial.t.ENTRY,
                    boot().replace(b'18908864',b'18057920'),
                    boot().replace(trial.COPY,b'wrong copy'),
                    boot().replace(trial.KERNEL,b'old kernel'),
                    boot().replace(trial.COMMIT,b''),
                    boot().replace(trial.ROOT_MARKER,b'torn mount line'),
                    boot()+b'panic(cpu 0)',boot()+b'RPI5XNU:SD:',
                    boot().replace(trial.COPY,b'TEMP_COPY').replace(trial.KERNEL,trial.COPY).replace(b'TEMP_COPY',trial.KERNEL)):
            with self.subTest(raw=bad[:40]):
                try: self.assertFalse(trial.boot_ready(bad))
                except RuntimeError: pass

    def test_wrong_boot_cannot_transmit(self):
        state = dict(checks=[],transmitted_bytes=0)
        with patch.object(trial.t.shell,'receive',return_value=boot().replace(b'18908864',b'18057920')), \
                patch.object(trial.t.os,'write') as write, self.assertRaises(RuntimeError):
            trial.trial(1,io.BytesIO(),1,state)
        write.assert_not_called()
        self.assertEqual(state['transmitted_bytes'],0)

    def test_real_preserved_file_modes_sizes_and_prefixes_required(self):
        files = self.files()
        result = trial.accept_metadata(observations(files),files)
        self.assertTrue(result['raw_metadata_accepted'])
        for fault in ('errno','mode','raw-mode','size','guard','dup','flags','data','offset',
                      'close','missing-errno','missing-buffer','wrong-path','missing-open'):
            rows = observations(files); row = rows['paths'][0]; opened = row['opens'][0]
            if fault == 'errno': row['stat']['rc'] = -45
            if fault == 'mode': row['stat']['mode'] = 0o444
            if fault in ('raw-mode','size'):
                raw = bytearray.fromhex(row['stat']['raw_hex'])
                raw[4 if fault=='raw-mode' else 96] ^= 1
                row['stat']['raw_hex'] = raw.hex()
            if fault == 'guard': opened['fstat']['guards'] = 0
            if fault == 'dup': opened['duplicate'] = -22
            if fault == 'flags': opened['getfl'] = -1
            if fault == 'data': opened['duplicate_read']['hex'] = 'ff'*16
            if fault == 'offset': opened['original_read'] = opened['duplicate_read'].copy()
            if fault == 'close': opened['original_close'] = -5
            if fault == 'missing-errno': rows['paths'][3]['access_f_ok'] = 0
            if fault == 'missing-buffer': rows['paths'][3]['stat']['raw_hex'] = '00'*144
            if fault == 'wrong-path': row['path'] = '/wrong'
            if fault == 'missing-open': row['opens'] = row['opens'][:1]
            with self.subTest(fault=fault), self.assertRaises(ValueError): trial.accept_metadata(rows,files)

    def test_old_physical_enotsup_capture_is_not_semantic_success(self):
        raw = trial.staging.ROOT/'build/rpi5/mac-statprobe-followup-20261012/serial.bin'
        if not raw.exists(): self.skipTest('Optional old physical capture absent')
        rows = trial.diagnostic.parse_diagnostic(raw.read_bytes())
        with self.assertRaises(ValueError): trial.accept_metadata(rows,self.files())

    def test_metadata_failure_stops_before_zsh_without_cleanup_input(self):
        calls = []
        def exchange(fd,output,text,expected,prompt,state):
            calls.append(text)
            return diagnostic(stat_rc=-45) if text=='/bin/statprobe' else b'\n'.join(expected)
        state = dict(checks=[],transmitted_bytes=0,script_file_acceptance=False)
        with patch.object(trial,'wait_boot'), patch.object(trial.t,'exchange',side_effect=exchange), self.assertRaises(ValueError):
            trial.trial(1,io.BytesIO(),1,state)
        self.assertEqual(calls[1:],['/bin/statprobe','echo $?'])
        self.assertFalse(state['script_file_acceptance'])
        self.assertEqual(state['checks'],trial.CHECKS[:4])

    def test_script_failure_never_claims_acceptance_or_launches_interactive_zsh(self):
        calls = []
        def exchange(fd,output,text,expected,prompt,state):
            calls.append(text)
            if text == 'zsh -f /etc/zsh-smoke.zsh': raise TimeoutError('script failed')
            return diagnostic() if text=='/bin/statprobe' else b'\n'.join(expected)
        state = dict(checks=[],transmitted_bytes=0,script_file_acceptance=False)
        with patch.object(trial,'wait_boot'), patch.object(trial.t,'exchange',side_effect=exchange), \
                patch.object(trial,'accept_metadata',return_value=dict(raw_metadata_accepted=True)), self.assertRaises(TimeoutError):
            trial.trial(1,io.BytesIO(),1,state)
        self.assertFalse(state['script_file_acceptance'])
        self.assertEqual(state['checks'],trial.CHECKS[:5])
        self.assertNotIn(trial.t.LAUNCH,calls)

    def test_success_requires_original_script_both_instances_and_recovery(self):
        calls = []
        def exchange(fd,output,text,expected,prompt,state):
            calls.append(text)
            if text == trial.t.LAUNCH: return b'DARWIN:ZSH:MAIN\nDARWIN:ZSH:MAIN\npi-zsh# '
            return diagnostic() if text=='/bin/statprobe' else b'\n'.join(expected)
        state = dict(checks=[],transmitted_bytes=0,script_file_acceptance=False)
        with patch.object(trial,'wait_boot'), patch.object(trial.t,'exchange',side_effect=exchange), \
                patch.object(trial,'accept_metadata',return_value=dict(raw_metadata_accepted=True)):
            trial.trial(1,io.BytesIO(),1,state)
        self.assertEqual(state['checks'],trial.CHECKS)
        self.assertTrue(state['script_file_acceptance'])
        self.assertEqual(calls[3],'zsh -f /etc/zsh-smoke.zsh')
        self.assertEqual(calls[-2],'exit')
        self.assertEqual(calls[-1],'echo RECOVERED_'+state['nonce'])


if __name__ == '__main__':
    unittest.main()
