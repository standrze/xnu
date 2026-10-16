# SPDX-License-Identifier: BSD-2-Clause
"""Corrective-package rejection tests; never physical acceptance."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import check_metadata_storage_guard as guard
from tools.rpi5 import check_zsh_metadata_package as package


class StorageEntryGuardTests(unittest.TestCase):
    def bundle(self):
        code_size = guard.REJECT_ADDRESS - guard.START_ADDRESS + len(guard.EPILOGUE)
        raw = bytearray(code_size + len(guard.ARGUMENT))
        raw[:len(guard.PREFIX)] = guard.PREFIX
        raw[code_size-len(guard.EPILOGUE):code_size] = guard.EPILOGUE
        raw[code_size:] = guard.ARGUMENT
        segments = [dict(vmaddr=guard.START_ADDRESS, filesize=code_size,
                         fileoff=0, initprot=5),
                    dict(vmaddr=guard.ARG_ADDRESS, filesize=len(guard.ARGUMENT),
                         fileoff=code_size, initprot=1)]
        symbols = (f'{guard.START_ADDRESS:016x} external {guard.START}\n'
                   f'{guard.PARSE_ADDRESS:016x} external {guard.PARSE}\n')
        return raw, segments, symbols

    def test_exact_reviewed_signature_only(self):
        result = guard.inspect(*self.bundle())
        self.assertTrue(result['absent_or_not_one_returns_false'])
        self.assertTrue(result['write_provider_absent'])
        self.assertIn('not a runtime', result['scope'])

    def test_every_guard_and_argument_byte_is_bound(self):
        raw, segments, symbols = self.bundle()
        offsets = list(range(len(guard.PREFIX)))
        offsets += list(range(guard.REJECT_ADDRESS-guard.START_ADDRESS, len(raw)))
        for offset in offsets:
            changed = raw.copy()
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                guard.inspect(changed, segments, symbols)

    def test_missing_ambiguous_drifted_or_writer_symbols_rejected(self):
        raw, segments, symbols = self.bundle()
        for changed in ('', symbols + symbols,
                        symbols.replace(f'{guard.START_ADDRESS:016x}', '0000000000000000'),
                        symbols.replace(f'{guard.PARSE_ADDRESS:016x}', '0000000000000000'),
                        symbols + '0000000000000001 external BCM2712SDWriteStorage\n'):
            with self.subTest(symbols=changed), self.assertRaises(ValueError):
                guard.inspect(raw, segments, changed)
        with self.assertRaises(ValueError):
            guard.inspect(raw + b'bcm2712_sd_write_trial', segments, symbols)

    def test_mapping_protection_overlap_and_truncation_rejected(self):
        for fault in ('no-code', 'executable-argument', 'overlap', 'short-code',
                      'negative-offset', 'past-end', 'truncated'):
            raw, segments, symbols = self.bundle()
            if fault == 'no-code': segments[0]['initprot'] = 1
            if fault == 'executable-argument': segments[1]['initprot'] = 5
            if fault == 'overlap': segments.append(segments[0].copy())
            if fault == 'short-code': segments[0]['filesize'] = len(guard.PREFIX)-1
            if fault == 'negative-offset': segments[0]['fileoff'] = -1
            if fault == 'past-end': segments[1]['fileoff'] = len(raw)
            if fault == 'truncated': raw = raw[:-1]
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                guard.inspect(raw, segments, symbols)


class CorrectivePackageTests(unittest.TestCase):
    def setUp(self):
        self.directory = package.ROOT / 'build/rpi5/bl33-probe-wdmzdtem'
        if not self.directory.exists():
            self.skipTest('Distinct corrective package is not prepared')

    def test_actual_package_passes_without_runtime_claims(self):
        result = package.inspect(self.directory)
        self.assertTrue(result['preflight_pass'])
        self.assertTrue(result['corrected_metadata_kernel'])
        for key in ('pi_executed', 'abi_root_cause_proven', 'script_file_acceptance',
                    'networking', 'durability', 'sd_actions', 'serial_actions', 'reboots'):
            self.assertFalse(result[key], key)

    def test_historical_and_corrective_profiles_are_not_interchangeable(self):
        with self.assertRaises(ValueError):
            package.previous.inspect(self.directory)
        old = package.ROOT / 'build/rpi5/bl33-probe-cijenc9s'
        if old.exists():
            with self.assertRaises(ValueError): package.inspect(old)
        for name in ('KERNEL_SHA', 'BUILD_SHA'):
            with self.subTest(pin=name), patch.object(package, name, '0'*64):
                with self.assertRaises(ValueError): package.inspect(self.directory)

    def test_build_receipt_semantics_are_checked_even_with_matching_hash(self):
        original = json.loads(package.BUILD.read_text())
        for field, value in (('exit_code', False), ('exit_code', 1),
                             ('source_unchanged_during_build', False),
                             ('source_at_finish', {}), ('fresh_kernel_outputs', False),
                             ('output_root', '/not/the/preserved/build')):
            changed = {**original, field: value}
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as temporary:
                receipt = Path(temporary)/'manifest.json'
                receipt.write_text(json.dumps(changed))
                pin = hashlib.sha256(receipt.read_bytes()).hexdigest()
                with patch.object(package, 'BUILD', receipt), patch.object(package, 'BUILD_SHA', pin):
                    with self.assertRaises(ValueError): package.inspect(self.directory)


if __name__ == '__main__':
    unittest.main()
