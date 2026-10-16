# SPDX-License-Identifier: BSD-2-Clause
"""Real linked packet/startup evidence; this never executes the Pi target."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import unittest

from tools.rpi5 import build_apple_ssh_packet_pthread as builder
from tools.rpi5.check_apple_pthread_kernel_contract import MachO
from tools.rpi5.tests.test_apple_pthread_startup_contract import validate_closure

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / 'build/rpi5/apple-ssh-packet-pthread-iabcb1gr'
MANIFEST = 'b1ca5bec6b327284fd8df985753ac5a10bcd324295ab981c946cc7ebb4d3cef3'


def exact_closure(report):
    expected = {}
    for directory, digest in ((builder.STARTUP, builder.STARTUP_SHA),
                              (builder.PACKET, builder.PACKET_SHA)):
        manifest = directory / 'manifest.json'
        if builder.sha(manifest) != digest:
            raise ValueError('Parent drift')
        expected[str(manifest)] = digest
        parent = json.loads(manifest.read_text())
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, value in parent[key].items():
                if name in expected and expected[name] != value:
                    raise ValueError('Parent conflicts')
                expected[name] = value
    for path in (Path(builder.__file__).resolve(), builder.SOURCE / 'sshpacket_pthread_main.c',
                 builder.SOURCE / 'pthread_smoke.c', builder.CRYPTO / 'manifest.json',
                 Path(builder.prepare_pid1.__file__).resolve(), Path(builder.macho.__file__).resolve()):
        expected[str(path)] = builder.sha(path)
    if report['source_inputs_sha256'] != expected:
        raise ValueError('Source dependency membership mismatch')
    validate_closure(PACKAGE, report)


class PacketPthreadClosure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert builder.sha(PACKAGE / 'manifest.json') == MANIFEST
        cls.report = json.loads((PACKAGE / 'manifest.json').read_text())

    def test_complete_source_headers_and_generated_membership(self):
        exact_closure(self.report)
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            tampered = copy.deepcopy(self.report)
            tampered[key].pop(next(iter(tampered[key])))
            with self.assertRaisesRegex(ValueError, 'membership mismatch'):
                exact_closure(tampered)

    def test_debug_strip_keeps_all_loaded_sections_and_exact_two_ctors(self):
        report = self.report
        before, after = MachO(report['unstripped_target']), MachO(report['target'])
        self.assertEqual(before.sections, after.sections)
        proof = []
        for section in before.sections:
            if not section['offset'] or not section['size']:
                continue
            raw = before.at(section['address'], section['size'])
            self.assertEqual(raw, after.at(section['address'], section['size']))
            proof.append(dict(section=section['name'], bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
        self.assertEqual(proof, report['unchanged_stripped_sections'])
        self.assertEqual(len(proof), 6)
        self.assertTrue(any(s['type'] == 0x20 and s['name'] == '_crypto_cpu_caps_aarch64'
                            for s in before.symbols))
        self.assertFalse(any(s['type'] & 0xe0 for s in after.symbols))
        self.assertEqual(builder.prepare_pid1.inspect(after.raw), report['macho_audit'])
        ctors = next(s for s in after.sections if s['name'] == '__DATA,__mod_init_func')
        self.assertEqual(ctors['size'], 16)
        expected = ['_initialized_constructor', '_openssl_init_crypto_constructor']
        self.assertEqual(struct.unpack('<2Q', after.at(ctors['address'], 16)),
                         tuple(after.names[n]['address'] for n in expected))
        self.assertEqual(report['actual_constructor_order'], expected)
        self.assertEqual(subprocess.check_output(['xcrun', 'nm', '-ju', report['target']], text=True), '')

    def test_exact_original_startup_and_library_link_inputs(self):
        startup = json.loads((builder.STARTUP / 'manifest.json').read_text())
        old = next(c['command'] for c in startup['commands'] if c['stdout'].endswith('/target-link.stdout'))
        new = next(c['command'] for c in self.report['commands'] if c['stdout'].endswith('/target-link.stdout'))
        replacement = self.report['exact_link_replacement']
        expected = [replacement['new'] if a == replacement['old'] else a for a in old]
        expected[expected.index('-o') + 1] = self.report['unstripped_target']
        expected[expected.index('-map') + 1] = str(PACKAGE / 'target.map')
        expected += [str(PACKAGE / 'target-composition.o'), self.report['original_packet_object'],
                     self.report['original_packet_archive'], self.report['original_crypto_archive']]
        self.assertEqual(new, expected)
        self.assertIn(self.report['original_startup_object'], new)
        self.assertNotIn(replacement['old'], new)
        self.assertEqual(self.report['target_missing_symbols'], [])
        self.assertEqual(self.report['target_duplicate_symbols'], [])
        self.assertTrue(self.report['target_link_complete'])
        for key in ('entropy_qualified', 'live_keys', 'ssh_transport', 'installed', 'pi_executed',
                    'accepted_runtime_modified', 'constructors_executed_on_target'):
            self.assertFalse(self.report[key])

    def test_real_combined_native_workload_not_target_execution(self):
        executable = PACKAGE / 'sshpacket-pthread-host'
        result = subprocess.run([executable], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.stdout, self.report['native_stdout'])
        self.assertEqual(result.stdout,
            'PTHREAD:SMOKE PASS CTOR=1 THREADS=4 JOIN=4 MUTEX=2048 TSD_DTORS=4 ONCE=1 ERRNO=4 ALLOC=2048\n'
            'RPI5XNU:SSHPACKET:PASS CASES=48 REJECTED=5036 NO_TRANSPORT_OR_ENTROPY_PROOF\n')
        libraries = subprocess.check_output(['xcrun', 'otool', '-L', executable], text=True)
        self.assertNotIn('libcrypto.', libraries)
        self.assertNotIn('libssl.', libraries)
        self.assertNotIn('/opt/homebrew/', libraries)


if __name__ == '__main__':
    unittest.main()
