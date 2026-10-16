# SPDX-License-Identifier: BSD-2-Clause
"""Host installer/transport/framing checks; never physical ABI evidence."""
import copy
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import json
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_statprobe_trial as stage
import serial_statprobe_trial as trial
import audit_statprobe_trial as auditor
import serial_statprobe_followup as followup
import audit_statprobe_metadata as metadata_audit
import struct


def diagnostic(mode=0o100644, duplicate=10, open_rc=3, stat_rc=0):
    lines = [trial.BEGIN]
    def number(key, value):
        lines.append(('STATPROBE:' + key + '=' + str(value)).encode())
    def data(key, value):
        lines.append(('STATPROBE:' + key + '=' + value.hex()).encode())
    def metadata(key):
        number(key, stat_rc)
        value = bytearray(b'\xa5' * 144)
        value[4:6] = mode.to_bytes(2, 'little')
        data('RAW', value); number('GUARDS', 1)
        if stat_rc == 0:
            number('MODE', mode); number('ISREG', int(mode & 0xf000 == 0x8000))
            number('ISDIR', int(mode & 0xf000 == 0x4000))
    for index, path in enumerate(trial.PATHS):
        lines.append(('STATPROBE:PATH=' + path).encode())
        number('ACCESS_F_OK', -2 if index == 3 else 0)
        number('ACCESS_R_OK', -2 if index == 3 else 0)
        metadata('STAT64'); metadata('LSTAT64')
        if index < 2:
            for flags in (0, 0x20000):
                number('OPEN_FLAGS', flags); number('OPEN', open_rc)
                if open_rc >= 0:
                    metadata('FSTAT64'); number('F_GETFD', 0); number('F_GETFL', 0)
                    number('F_DUPFD_10', duplicate)
                    if duplicate >= 0:
                        number('DUP_READ', 16); data('DUP_DATA', b'0123456789abcdef')
                        number('DUP_CLOSE', 0)
                    number('ORIGINAL_READ', 16); data('ORIGINAL_DATA', b'ghijklmnopqrstuv')
                    number('ORIGINAL_CLOSE', 0)
    number('BUFFER_DAMAGE', 0); lines.append(trial.END)
    return b'\n'.join(lines) + b'\nxnu:/# '


def boot():
    t = trial.transport
    return b'\n'.join((b'Boot mode: SD (01)', b'Read probe.bin bytes 18057920 hnd 0x123',
                      t.ENTRY + b'0008', t.TERMINAL_LOADER, t.package_check.TOPOLOGY_PASS,
                      t.TRANSFER, trial.ROOT_MARKER, t.READY, b'xnu:/# '))


class StatprobeStageTests(unittest.TestCase):
    def test_result_requires_all_identity_backup_and_protection_fields(self):
        with patch.object(stage.package_check, 'inspect', return_value=dict(image='/candidate', image_sha256='a'*64)):
            plan = stage.load_plan(Path('/candidate'), 'df67a6f1-d645-4ee5-97e3-d61276d7f2d6')
        plan['run'] = '/home/sandrzej/xnu-gate6-statprobe-abcdefgh'
        result = json.loads((stage.HISTORY / 'result.json').read_text())
        backup = stage.base.install_core.INSTALL_NAMES[stage.PROFILE][0]
        result.update(run=plan['run'], image_sha256='a'*64, preserved_sd_image_sha256=stage.OLD_SHA,
                      nvme_previous_image_sha256=stage.OLD_SHA, sd_backup=backup,
                      nvme_backups_verified=plan['nvme_backups'],
                      identity=dict(identity=plan['identity_binding']['expected'], boot_id=plan['linux_boot_id'], hostname='kamidana'),
                      protected_files_sha256=dict(plan['protected_files'], **{'probe.bin':'a'*64, backup:stage.OLD_SHA}))
        result['backups'][1]['sha256'] = stage.FAT_SHA
        result['protected_after']['boot']['sha256'] = 'b'*64
        stage.validate_result(result, plan)
        for name in result:
            bad = copy.deepcopy(result); del bad[name]
            with self.subTest(missing=name), self.assertRaises(ValueError):
                stage.validate_result(bad, plan)
        for field in ('mbr', 'hfs'):
            bad = copy.deepcopy(result); bad['protected_after'][field]['sha256'] = '0'*64
            with self.assertRaises(ValueError): stage.validate_result(bad, plan)

    def test_exact_history_chain_and_distinct_ssd_return(self):
        report = dict(image='/candidate', image_sha256='a' * 64)
        with patch.object(stage.package_check, 'inspect', return_value=report):
            plan = stage.load_plan(Path('/candidate'), 'df67a6f1-d645-4ee5-97e3-d61276d7f2d6')
        self.assertEqual(len(plan['nvme_backups']), 28)
        self.assertEqual(plan['nvme_backups'][-1]['sha256'], stage.previous.OLD_SHA)
        self.assertEqual(plan['nvme_backups'][-1]['bytes'], 17205952)
        self.assertEqual(plan['protected_sha256']['boot'], stage.FAT_SHA)
        self.assertIn('probe.pcie-topology-passed-20261012.bin', plan['protected_files'])
        compile(stage.remote_source(plan), '<statprobe-remote>', 'exec')
        self.assertEqual(stage.remote_template().count(repr(stage.PREVIOUS_NAME)), 3)
        self.assertIn(",'statprobe-trial')", stage.remote_template())
        with patch.object(stage.package_check, 'inspect', return_value=report), self.assertRaises(ValueError):
            stage.load_plan(Path('/candidate'), '67033e75-2d50-40fa-a871-1a3eb05ff10a')
        plan['source_sha256'][str(Path(stage.__file__))] = '0' * 64
        with self.assertRaises(ValueError): stage.remote_source(plan)
        with patch.object(stage.previous, 'remote_template', return_value='changed'), self.assertRaises(ValueError):
            stage.remote_template()

    def test_distinct_profile_preserves_and_never_retries(self):
        core = stage.base.install_core
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); bootdir = root / 'boot'; bootdir.mkdir()
            old, new = b'physically interactive zsh', b'raw ABI diagnostic'
            (bootdir / 'probe.bin').write_bytes(old)
            (root / 'candidate').write_bytes(new)
            (bootdir / 'probe.pcie-topology-passed-20261012.bin').write_bytes(b'topology')
            d = os.open(bootdir, os.O_RDONLY | os.O_DIRECTORY)
            c = os.open(root / 'candidate', os.O_RDONLY)
            try:
                a, b = [hashlib.sha256(value).hexdigest() for value in (old, new)]
                result = core.install(d, c, a, b, stage.PROFILE)
                self.assertEqual((bootdir / result['sd_backup']).read_bytes(), old)
                self.assertEqual((bootdir / 'probe.pcie-topology-passed-20261012.bin').read_bytes(), b'topology')
                with self.assertRaises(ValueError): core.install(d, c, a, b, stage.PROFILE)
            finally:
                os.close(c); os.close(d)


class StatprobeSerialTests(unittest.TestCase):
    def test_linked_metadata_table_bounds_and_missing_slot(self):
        raw = bytearray(256)
        symbols = '0000000000001000 (__DATA,__data) external _mockfs_vfsops\n'
        segments = [dict(vmaddr=0x1000, filesize=160, fileoff=32, initprot=3)]
        result = metadata_audit.table_slot(raw, segments, symbols)
        self.assertEqual(result['target'], '0x0')
        struct.pack_into('<Q', raw, 32+40, 0x1234)
        self.assertEqual(metadata_audit.table_slot(raw, segments, symbols)['target'], '0x1234')
        for seg, syms, data in ((segments, symbols*2, raw), ([],symbols,raw),
                                ([dict(segments[0],initprot=7)],symbols,raw),
                                ([dict(segments[0],filesize=159)],symbols,raw),
                                (segments,symbols,raw[:50]), (segments,'',raw)):
            with self.subTest(seg=seg), self.assertRaises(ValueError):
                metadata_audit.table_slot(data, seg, syms)

    def test_preserved_physical_followup_audits_without_promoting_failed_gate(self):
        directory = stage.ROOT/'build/rpi5/mac-statprobe-followup-20261012'
        if not directory.is_dir(): self.skipTest('Optional preserved hardware capture absent')
        report = auditor.audit(directory)
        self.assertEqual(report['serial_sha256'], '185f824497e05a0afede6967d0eac5665d80b4d0861f9872729f0829f0a884ed')
        self.assertFalse(report['strict_mounted_root_trial_passed'])
        self.assertFalse(report['original_zsh_script_acceptance'])
        self.assertEqual(report['observations']['paths'][0]['stat']['rc'], -45)
        original = json.loads((directory/'state.json').read_text())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'serial.bin').write_bytes((directory/'serial.bin').read_bytes())
            for key, value in [('source', {}), ('strict_mounted_root_trial_passed',True),
                               ('started_utc','2026-10-12T18:59:00+00:00')]:
                state = copy.deepcopy(original); state[key] = value
                (root/'state.json').write_text(json.dumps(state))
                with self.subTest(key=key), self.assertRaises(ValueError): auditor.audit(root)

    def test_separate_same_boot_guard_does_not_waive_mount_trial(self):
        raw = boot().replace(trial.ROOT_MARKER, b'torn root-mount log')
        raw = raw.replace(trial.transport.package_check.TOPOLOGY_PASS,
                          followup.COPY + b'\n' + followup.KERNEL + b'\n' + trial.transport.package_check.TOPOLOGY_PASS)
        raw = raw.replace(trial.transport.TRANSFER, trial.transport.TRANSFER + b'\n' + followup.COMMIT)
        self.assertTrue(followup.payload_boot(raw))
        for bad in (raw + trial.transport.ENTRY, raw.replace(b'00160000 VERIFIED', b'00150000 VERIFIED'),
                    raw.replace(followup.COMMIT, b''), raw.replace(b'18057920', b'18008768'),
                    raw.replace(b'torn root-mount log', trial.transport.package_check.RAMROOT),
                    raw + b'panic(cpu 0)', raw + b'FAILED_STOP'):
            with self.subTest(bad=bad[:50]), self.assertRaises((ValueError, RuntimeError)):
                followup.payload_boot(bad)
        complete = raw.replace(b'torn root-mount log', trial.ROOT_MARKER)
        with self.assertRaises(ValueError): followup.payload_boot(complete)
        report = dict(image_sha256=trial.IMAGE_SHA)
        now = followup.datetime.now(followup.timezone.utc).isoformat()
        state = dict(status='failed', checks=[], transmitted_bytes=0, preflight=report,
                     error='No fresh distinct zsh-root boot; zero input sent',
                     device='/dev/cu.usbmodem102', baud=115200, bytes=len(raw),
                     serial_sha256=hashlib.sha256(raw).hexdigest(), started_utc=now, ended_utc=now)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'serial.bin').write_bytes(raw)
            (root/'state.json').write_text(json.dumps(state))
            result = followup.evidence(root, state['device'], report)
            self.assertFalse(result['strict_mounted_root_trial_passed'])
            self.assertFalse(result['mounted_root_node_count_observed'])
            for key, value in [('transmitted_bytes', 1), ('checks', ['claimed pass']),
                               ('serial_sha256', '0'*64), ('error', 'fault'),
                               ('preflight', {}), ('device','/dev/cu.usbmodem999'),
                               ('started_utc','2020-01-01T00:00:00+00:00')]:
                bad = copy.deepcopy(state); bad[key] = value
                (root/'state.json').write_text(json.dumps(bad))
                with self.subTest(key=key), self.assertRaises(ValueError):
                    followup.evidence(root, state['device'], report)
            bad = copy.deepcopy(state)
            bad['started_utc'] = bad['ended_utc'] = '2020-01-01T00:00:00+00:00'
            (root/'state.json').write_text(json.dumps(bad))
            with self.assertRaises(ValueError): followup.evidence(root, state['device'], report)

    def test_offline_audit_binds_actual_raw_capture_not_state_claims(self):
        nonce = 'F0123456789abcdef'
        raw = boot() + b'\n' + nonce.encode() + b'\nxnu:/# /bin/statprobe\n' + diagnostic()
        raw += b'\n0\nxnu:/# \nRECOVERED_' + nonce.encode() + b'\nxnu:/# '
        commands = ['echo ' + nonce, '/bin/statprobe', 'echo $?', 'echo RECOVERED_' + nonce]
        report = dict(image_sha256=trial.IMAGE_SHA, image_bytes=18057920,
                      root_mount_marker=trial.ROOT_MARKER.decode(), init_sha256=trial.package_check.INIT_SHA,
                      kernel_sha256=trial.package_check.KERNEL_SHA, preflight_pass=True, checks={'synthetic':True})
        state = dict(status='diagnostic_completed', checks=trial.CHECKS, script_file_acceptance=False,
                     baud=115200, device='/dev/cu.usbmodem102', bytes=len(raw),
                     serial_sha256=hashlib.sha256(raw).hexdigest(), nonce=nonce, preflight=report,
                     transmitted_bytes=sum(len(c)+1 for c in commands), observations=trial.parse_diagnostic(raw),
                     started_utc='2026-10-12T19:00:00+00:00', ended_utc='2026-10-12T19:00:30+00:00')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'serial.bin').write_bytes(raw)
            (root/'state.json').write_text(json.dumps(state))
            result = auditor.audit(root)
            self.assertFalse(result['abi_root_cause_proven'])
            for key, value in [('transmitted_bytes', 0), ('script_file_acceptance', True),
                               ('checks', []), ('serial_sha256', '0'*64), ('observations', {})]:
                bad = copy.deepcopy(state); bad[key] = value
                (root/'state.json').write_text(json.dumps(bad))
                with self.subTest(key=key), self.assertRaises(ValueError): auditor.audit(root)
            (root/'state.json').write_text(json.dumps(state))
            (root/'serial.bin').write_bytes(raw.replace(b'RECOVERED_', b'NOT_RECOVERED_', 1))
            with self.assertRaises(ValueError): auditor.audit(root)

    def test_diagnostic_preserves_failed_calls_and_wrong_type(self):
        report = trial.parse_diagnostic(diagnostic(mode=0o644, duplicate=-22))
        self.assertFalse(report['paths'][0]['stat']['is_regular'])
        self.assertEqual(report['paths'][0]['opens'][0]['duplicate'], -22)
        self.assertFalse(report['script_file_acceptance'])
        self.assertFalse(report['abi_root_cause_proven'])
        report = trial.parse_diagnostic(diagnostic(open_rc=-6, stat_rc=-2))
        self.assertEqual(report['paths'][0]['stat']['rc'], -2)
        self.assertEqual(report['paths'][0]['opens'][1]['fd'], -6)
        self.assertNotIn('mode', report['paths'][0]['stat'])
        report = trial.parse_diagnostic(diagnostic())
        self.assertEqual(report['paths'][0]['opens'][0]['duplicate_read']['rc'], 16)

    def test_incomplete_inconsistent_or_repeated_results_rejected(self):
        raw = diagnostic()
        bad = (raw[:-30], raw + b'\n' + trial.BEGIN, raw.replace(b'GUARDS=1', b'GUARDS=0', 1),
               raw.replace(b'ISREG=1', b'ISREG=0', 1), raw.replace(b'DUP_READ=16', b'DUP_READ=17', 1),
               raw.replace(b'OPEN_FLAGS=131072', b'OPEN_FLAGS=0', 1),
               raw.replace(b'/etc/motd', b'/etc/other', 1), raw.replace(b'RAW=', b'RAW=00', 1),
               diagnostic(duplicate=3), raw.replace(b'STAT64=0', b'STAT64=+0', 1))
        for value in bad:
            with self.subTest(value=value[:80]), self.assertRaises(ValueError):
                trial.parse_diagnostic(value)

    def test_fresh_distinct_root_required_before_any_tx(self):
        t = trial.transport
        self.assertTrue(t.boot_ready(boot(), 18057920, trial.ROOT_MARKER))
        with self.assertRaises(RuntimeError): t.boot_ready(boot(), 18057920)
        bad = (boot().replace(trial.ROOT_MARKER, t.package_check.RAMROOT),
               boot().replace(b'18057920', b'18008768'), boot() + b'panic(cpu 0)',
               boot() + t.ENTRY)
        for raw in bad:
            state = dict(checks=[], transmitted_bytes=0)
            with patch.object(t.shell, 'receive', return_value=raw), patch.object(t.os, 'write') as write:
                with self.assertRaises(RuntimeError): trial.trial(1, io.BytesIO(), 1, dict(image_bytes=18057920), state)
                write.assert_not_called()
                self.assertEqual(state['transmitted_bytes'], 0)

    def test_only_diagnostic_then_exit_and_live_recovery(self):
        t = trial.transport
        state = dict(checks=[], transmitted_bytes=0)
        calls = []
        def exchange(fd, output, command, expected, prompt, state, seconds=30):
            calls.append(command)
            return diagnostic() if command == '/bin/statprobe' else b'\n'.join(expected) + b'\nxnu:/# '
        with patch.object(t, 'wait_boot') as wait, patch.object(t, 'exchange', side_effect=exchange):
            trial.trial(1, io.BytesIO(), 1, dict(image_bytes=18057920), state)
        wait.assert_called_once_with(1, unittest.mock.ANY, 1, 18057920, trial.ROOT_MARKER)
        self.assertEqual(state['checks'], trial.CHECKS)
        self.assertEqual(calls[1:3], ['/bin/statprobe', 'echo $?'])
        self.assertTrue(calls[-1].startswith('echo RECOVERED_F'))
        state = dict(checks=[], transmitted_bytes=0)
        with patch.object(t, 'wait_boot'), patch.object(t, 'exchange', return_value=b'partial') as exchange:
            with self.assertRaises(ValueError): trial.trial(1, io.BytesIO(), 1, dict(image_bytes=18057920), state)
        self.assertEqual(exchange.call_count, 2)  # No cleanup input after failed diagnosis.


if __name__ == '__main__':
    unittest.main()
