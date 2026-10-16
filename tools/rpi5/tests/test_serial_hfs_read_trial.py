# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic recorder evidence/transport faults; not Pi HFS acceptance."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import serial_hfs_read_trial as runner
from check_sd_read_package import REQUIRED_SD_CHECKS
from tools.rpi5.tests.test_hfs_reference import baseline


class SerialHFSReadTrialTests(unittest.TestCase):
    now = datetime(2026, 10, 11, 23, 0, tzinfo=timezone.utc)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def bundle(self):
        base = Path(tempfile.mkdtemp(dir=self.tmp.name))
        sd_dir = base / 'sd'; sd_dir.mkdir()
        paths = {name: base / (name + '.json') for name in ('fixture', 'baseline', 'reference', 'preflight')}
        paths['sd_trial'] = sd_dir / 'state.json'
        fixture = dict(image_sha256='0' * 64, files=[dict(path=path, bytes=0,
                       sha256=hashlib.sha256(b'').hexdigest()) for path in runner.hfs_reference.FILE_PATHS])
        initial = baseline()
        payloads = {row['lba']: bytes([index]) * 512 for index, row in enumerate(initial['sectors'])}
        for row in initial['sectors']:
            row['sha256'] = hashlib.sha256(payloads[row['lba']]).hexdigest()
        for name, report in (('fixture', fixture), ('baseline', initial)):
            paths[name].write_text(json.dumps(report))
        reference = dict(identity=runner.hfs_reference.expected_identity(initial),
                         partition_reads=[dict(pass_number=n, bytes=runner.hfs_reference.IMAGE_BYTES,
                                               sha256=fixture['image_sha256']) for n in (1, 2)],
                         sd_write_operations=0, fixture_reference_sha256=runner.sha256(paths['fixture']),
                         sd_baseline_reference_sha256=runner.sha256(paths['baseline']),
                         capture_source_sha256=runner.sha256(Path(runner.hfs_reference.__file__)),
                         host='sandrzej@192.168.4.23', captured_at=self.now.isoformat())
        source = runner.hfs_reference.remote_source(reference['identity'], fixture['image_sha256'])
        reference['remote_source_sha256'] = hashlib.sha256(source.encode()).hexdigest()
        paths['reference'].write_text(json.dumps(reference))
        image = base / 'probe.bin'
        image.write_bytes(runner.HFS_LOADER + b' bcm2712_hfs=1 bcm2712_sd_readonly=1\0')
        preflight = dict(preflight_pass=True, sd_readonly_trial=True, hfs_readonly_trial=True,
                         image=str(image), image_sha256=runner.sha256(image),
                         linked_hfs_configuration=dict(syntax_pass=True,
                             required_fragments_present={name: True for name in runner.REQUIRED_HFS_CONFIG}),
                         checks={name: True for name in REQUIRED_SD_CHECKS | runner.REQUIRED_HFS_CHECKS})
        paths['preflight'].write_text(json.dumps(preflight))
        ready = b'RPI5XNU:SD:READ_ONLY_READY SECTORS=250347520 BLOCK=512 DMA=0 WRITES=0'
        raw = sd_dir / 'serial.bin'
        records = [runner.TERMINAL_LOADER, runner.SD_LOADER, ready, b'RPI5XNU:SHELL:READY']
        for _ in (1, 2):
            for row in initial['sectors']:
                records.append(f"RPI5XNU:SDREAD:SECTOR LBA={row['lba']} SECTORS=250347520 BLOCK=512 READONLY=1".encode())
                for index in range(16):
                    data = payloads[row['lba']][index * 32:(index + 1) * 32].hex()
                    records.append(f'RPI5XNU:SDREAD:DATA ROW={index} HEX={data}'.encode())
                records.append(b'RPI5XNU:SDREAD:END')
        raw.write_bytes(b'\n'.join(records) + b'\n')
        state = dict(status='passed', reads=[dict(lba=row['lba'], bytes=512, sha256=row['sha256'], **{'pass': n})
                                           for n in (1, 2) for row in initial['sectors']],
                     reference_sha256=runner.sha256(paths['baseline']), transmitted_bytes=123,
                     checks=['sixteen_sector_reads_match_independent_linux_hashes'],
                     bytes=raw.stat().st_size, serial_sha256=runner.sha256(raw))
        paths['sd_trial'].write_text(json.dumps(state))
        return paths

    def load(self, paths):
        # Native image/fixture validation is covered separately. These small
        # synthetic manifests isolate recorder provenance and transition guards.
        with patch.object(runner.hfs_reference, 'validate_fixture'):
            return runner.load_inputs(paths, now=self.now)

    def mutate(self, path, edit):
        report = json.loads(path.read_text())
        edit(report)
        path.write_text(json.dumps(report))

    def rewrite_raw(self, paths, edit):
        raw = paths['sd_trial'].parent / 'serial.bin'
        raw.write_bytes(edit(raw.read_bytes()))
        self.mutate(paths['sd_trial'], lambda state: state.update(
            bytes=raw.stat().st_size, serial_sha256=runner.sha256(raw)))

    def test_complete_evidence_bundle_binds_all_five_inputs(self):
        paths = self.bundle()
        reports, hashes = self.load(paths)
        self.assertEqual(set(hashes), set(paths))
        self.assertTrue(reports['preflight']['hfs_readonly_trial'])
        self.assertEqual(reports['reference']['fixture_reference_sha256'], hashes['fixture'])

    def test_missing_changed_stale_future_or_naive_reference_is_rejected(self):
        variants = [('fixture_reference_sha256', 'f' * 64), ('sd_baseline_reference_sha256', 'f' * 64),
                    ('capture_source_sha256', 'f' * 64), ('remote_source_sha256', 'f' * 64),
                    ('host', 'different-host'),
                    ('captured_at', (self.now - timedelta(seconds=1801)).isoformat()),
                    ('captured_at', (self.now + timedelta(seconds=31)).isoformat()),
                    ('captured_at', self.now.replace(tzinfo=None).isoformat())]
        for key, value in variants:
            paths = self.bundle()
            self.mutate(paths['reference'], lambda report: report.update({key: value}))
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.load(paths)

    def resume_bundle(self):
        paths = self.bundle()
        reports, hashes = self.load(paths)
        base = Path(tempfile.mkdtemp(dir=self.tmp.name))
        path = base/'state.json'
        raw = b'\n'.join((runner.TERMINAL_LOADER, runner.SD_LOADER, runner.HFS_LOADER,
                          b'RPI5XNU:HFS:REGISTERED',
                          b'RPI5XNU:SD:READ_ONLY_READY SECTORS=250347520 BLOCK=512 DMA=0 WRITES=0',
                          b'RPI5XNU:SHELL:READY'))+b'\n'
        (base/'serial.bin').write_bytes(raw)
        state = dict(status='failed',error='interrupted',device='/dev/cu.usbmodem102',partition='/dev/disk0s2',
                     checks=[],reads=[],transmitted_bytes=0,mount_cycles_completed=0,sd_data_write_commands=0,baud=115200,
                     image_sha256=reports['preflight']['image_sha256'],evidence_sha256=hashes,
                     bytes=len(raw),serial_sha256=hashlib.sha256(raw).hexdigest(),
                     started_utc=(self.now+timedelta(seconds=30)).isoformat(),
                     ended_utc=(self.now+timedelta(seconds=60)).isoformat())
        path.write_text(json.dumps(state))
        return path,reports,hashes,raw

    def resume(self, path, reports, hashes, now=None):
        return runner.load_zero_tx_resume(path,reports,hashes,'/dev/cu.usbmodem102','/dev/disk0s2',
                                         now=now or self.now+timedelta(seconds=90))

    def test_zero_tx_resume_preserves_raw_and_explicit_gap_without_repairing_encoding_banner(self):
        path,reports,hashes,raw = self.resume_bundle()
        prefix,meta = self.resume(path,reports,hashes)
        self.assertEqual(prefix,raw)
        self.assertEqual(meta['previous_raw_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(meta['capture_segments'],2)
        self.assertFalse(meta['closed_port_interval_observed'])
        self.assertFalse(meta['encoding_ready_banner_observed'])

    def test_resume_rejects_input_prior_mount_wrong_bindings_changed_capture_and_stale_boot(self):
        for key,value in (('status','passed'),('error','timeout'),('transmitted_bytes',1),
                          ('transmitted_bytes',False),('mount_cycles_completed',1),('checks',['ready']),
                          ('reads',[{}]),('evidence_sha256',{}),('image_sha256','f'*64),('baud',9600)):
            path,reports,hashes,raw = self.resume_bundle()
            self.mutate(path,lambda state: state.update({key:value}))
            with self.subTest(key=key),self.assertRaises(ValueError): self.resume(path,reports,hashes)
        for edit in (lambda raw: raw.replace(runner.HFS_LOADER,b'old_loader'),
                     lambda raw: raw+runner.TERMINAL_LOADER,
                     lambda raw: raw+b'panic(cpu 0)',
                     lambda raw: raw+b'RPI5XNU:HFSRO:MOUNTED',
                     lambda raw: raw.replace(b'RPI5XNU:HFS:REGISTERED',b'RPI5XNU:HFS:REG\nISTERED'),
                     lambda raw: raw+b'RPI5XNU:HFS:ENCODINGS_READY'):
            path,reports,hashes,raw = self.resume_bundle()
            raw=edit(raw); (path.parent/'serial.bin').write_bytes(raw)
            self.mutate(path,lambda state: state.update(bytes=len(raw),serial_sha256=hashlib.sha256(raw).hexdigest()))
            with self.subTest(edit=edit),self.assertRaises(ValueError): self.resume(path,reports,hashes)
        path,reports,hashes,raw = self.resume_bundle()
        (path.parent/'serial.bin').write_bytes(raw+b'changed')
        with self.assertRaises(ValueError): self.resume(path,reports,hashes)
        path,reports,hashes,raw = self.resume_bundle()
        with self.assertRaises(ValueError): self.resume(path,reports,hashes,self.now+timedelta(seconds=961))

    def test_encoding_dependency_must_be_proven_in_actual_linked_configuration(self):
        for edit in (lambda p: p.pop('linked_hfs_configuration'),
                     lambda p: p['linked_hfs_configuration'].update(syntax_pass=False),
                     lambda p: p['linked_hfs_configuration'].update(required_fragments_present={})):
            paths=self.bundle(); self.mutate(paths['preflight'],edit)
            with self.subTest(edit=edit),self.assertRaises(ValueError): self.load(paths)

    def test_resume_never_transmits_on_missing_fresh_shell_or_observed_reboot(self):
        for reboot in (False,True):
            progress=dict(checks=[],reads=[],transmitted_bytes=0,mount_cycles_completed=0)
            with patch.object(runner.time,'monotonic',side_effect=(0,0) if reboot else (0,16)), \
                    patch.object(runner,'receive',return_value=runner.TERMINAL_LOADER+b'RPI5XNU:SHELL:READY'), \
                    patch.object(runner,'command') as commands, self.assertRaises((ValueError,TimeoutError)):
                runner.trial(1,io.BytesIO(),30,progress,{'identity':{'bytes':128177930240}},
                             {'files':[]},'/dev/disk0s2',resume=True)
            commands.assert_not_called(); self.assertEqual(progress['transmitted_bytes'],0)

    def test_unpassed_incomplete_or_changed_sd_capture_is_rejected(self):
        for field, value in (('status', 'failed'), ('transmitted_bytes', 0),
                             ('reference_sha256', 'f' * 64), ('checks', []), ('reads', [])):
            paths = self.bundle()
            self.mutate(paths['sd_trial'], lambda report: report.update({field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.load(paths)
        paths = self.bundle()
        self.mutate(paths['sd_trial'], lambda report: report['reads'][0].update({'pass': True}))
        with self.assertRaises(ValueError):
            self.load(paths)
        paths = self.bundle()
        (paths['sd_trial'].parent / 'serial.bin').write_bytes(b'changed transport capture')
        with self.assertRaises(ValueError):
            self.load(paths)

    def test_sd_only_or_changed_hfs_package_rejected(self):
        for field, value in (('hfs_readonly_trial', False), ('checks', {}), ('image_sha256', '0' * 64)):
            paths = self.bundle()
            self.mutate(paths['preflight'], lambda report: report.update({field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.load(paths)
        paths = self.bundle()
        report = json.loads(paths['preflight'].read_text())
        Path(report['image']).write_bytes(b'not the HFS trial, even with a matching hash')
        report['image_sha256'] = runner.sha256(Path(report['image']))
        paths['preflight'].write_text(json.dumps(report))
        with self.assertRaises(ValueError):
            self.load(paths)

    def test_matching_report_hash_cannot_substitute_for_raw_sector_coverage(self):
        def frames(data):
            lines = data.splitlines(keepends=True)
            return lines[:4], [lines[i:i+18] for i in range(4, len(lines), 18)]

        def reorder(data):
            ready, reads = frames(data)
            reads[0], reads[1] = reads[1], reads[0]
            return b''.join(ready + [line for frame in reads for line in frame])

        def late_ready(data):
            ready, reads = frames(data)
            return b''.join([line for frame in reads for line in frame] + ready)

        for edit in (lambda data: b'\n'.join(data.split(b'\n')[:4]) + b'\n',
                     lambda data: b'\n'.join(data.split(b'\n')[:-19]) + b'\n',
                     lambda data: data + b''.join(frames(data)[1][0]),
                     reorder, late_ready,
                     lambda data: data.replace(b'HEX=00', b'HEX=ff', 1),
                     lambda data: data.replace(b'HEX=00', b'HEX=0\r0', 1),
                     lambda data: data.replace(b'RPI5XNU:SDREAD:DATA ROW=1 ',
                                               b'chatter\nRPI5XNU:SDREAD:DATA ROW=1 ', 1)):
            paths = self.bundle()
            self.rewrite_raw(paths, edit)
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                self.load(paths)

    def test_complete_physical_tty_line_endings_are_accepted(self):
        for ending in (b'\r\n', b'\r\r\n'):
            paths = self.bundle()
            self.rewrite_raw(paths, lambda data: data.replace(b'\n', ending))
            self.load(paths)

    def test_invalid_evidence_never_opens_serial_or_creates_output(self):
        base = Path(self.tmp.name)
        output = base / 'must-not-exist'
        argv = ['serial_hfs_read_trial.py', '/dev/cu.usbmodem102', str(output)]
        for name in ('reference', 'fixture', 'sd-baseline-reference', 'preflight', 'sd-trial'):
            argv.extend(('--' + name, str(base / (name + '.json'))))
        with patch.object(sys, 'argv', argv), patch.object(runner, 'load_inputs', side_effect=ValueError('no evidence')), \
                patch.object(runner.os, 'open') as opened:
            with self.assertRaises(ValueError):
                runner.main()
            opened.assert_not_called()
        self.assertFalse(output.exists())

    def test_old_sd_image_never_receives_input_without_hfs_readiness(self):
        host, peer = socket.socketpair()
        peer.sendall(b'\n'.join((runner.TERMINAL_LOADER, runner.SD_LOADER,
                                b'RPI5XNU:SD:READ_ONLY_READY SECTORS=250347520 BLOCK=512 DMA=0 WRITES=0',
                                b'RPI5XNU:SHELL:READY')))
        peer.setblocking(False)
        state = dict(checks=[], reads=[], transmitted_bytes=0, mount_cycles_completed=0)
        try:
            with self.assertRaises(TimeoutError):
                runner.trial(host.fileno(), io.BytesIO(), 0.05, state,
                             {'identity': {'bytes': 128177930240}}, {'files': []}, '/dev/disk0s2')
            with self.assertRaises(BlockingIOError):
                peer.recv(1)
            self.assertEqual(state['transmitted_bytes'], 0)
        finally:
            host.close(); peer.close()

    def simulate(self, fault=None):
        state = dict(checks=[], reads=[], transmitted_bytes=0, mount_cycles_completed=0)
        files = [dict(path=path, bytes=0, sha256=hashlib.sha256(b'').hexdigest())
                 for path in sorted(runner.hfs_reference.FILE_PATHS)]

        def command(fd, output, text, expected, progress, **kwargs):
            if text.startswith('sh /mnt/hfs'):
                nonce = text.split()[-1].encode()
                if fault == 'script':
                    return b'HFS_SCRIPT_END\nHFS_SCRIPT_BEGIN\n' + runner.PROOF + nonce + b'\n'
                return (b'HFS_SCRIPT_BEGIN\n' + runner.PROOF + b'HFS_SCRIPT_END\n' + nonce + b'\nxnu:/# ').replace(b'\n', b'\r\r\n')
            return b'\n'.join(expected) + b'\nxnu:/# '

        def read_file(fd, output, entry, progress):
            if fault == 'read':
                raise ValueError('complete-file hash mismatch')
            return {**entry, 'nonce': 'H0123456789abcdef', 'verification': 'synthetic_test_only'}

        with patch.object(runner, 'wait_for_boot_markers') as boot, \
                patch.object(runner.time, 'monotonic', side_effect=(0, 0, 4)), \
                patch.object(runner, 'command', side_effect=command) as commands, \
                patch.object(runner, 'read_file', side_effect=read_file):
            self.state, self.commands, self.boot = state, commands, boot
            runner.trial(1, io.BytesIO(), 30, state, {'identity': {'bytes': 128177930240}},
                         {'files': files}, '/dev/disk0s2')
        return state

    def test_two_full_mount_cycles_include_exec_and_return_to_ram_root(self):
        state = self.simulate()
        self.assertEqual(state['mount_cycles_completed'], 2)
        self.assertEqual(len(state['reads']), 10)
        self.assertEqual([row['mount_cycle'] for row in state['reads']], [1] * 5 + [2] * 5)
        texts = [call.args[2] for call in self.commands.call_args_list]
        self.assertEqual(texts.count('hfsro mount /dev/disk0s2'), 2)
        self.assertEqual(texts.count('hfsro unmount /dev/disk0s2'), 2)
        self.assertEqual(sum(text.startswith('/mnt/hfs/bin/echo ') for text in texts), 2)
        self.assertTrue(all(not text.startswith(('reboot', 'dd ', 'mkfs', 'echo x >')) for text in texts))
        self.assertIn(runner.HFS_LOADER, self.boot.call_args.kwargs['extra_markers'])
        self.assertIn(b':SD:HANDOFF RC=-', self.boot.call_args.kwargs['abort_markers'])

    def test_read_or_script_failure_stops_without_cleanup_transmission(self):
        for fault in ('read', 'script'):
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.simulate(fault)
            self.assertEqual(self.state['mount_cycles_completed'], 0)
            self.assertFalse(any(call.args[2].startswith('hfsro unmount')
                                 for call in self.commands.call_args_list))


if __name__ == '__main__':
    unittest.main()
