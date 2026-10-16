#!/usr/bin/env python3
"""Original once/gate algorithm, explicit private boundary and actual link delta."""
import json
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5 import build_apple_dispatch_once as build
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE = build.ROOT / 'build/rpi5/apple-dispatch-once-gr21uo30'
SHA = 'd7f02eb05b151d5dd1ca609c8dd2bd0106d02ea756c7a72eaeb680819611cbd3'


class AppleDispatchOnce(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE / 'manifest.json') != SHA: raise ValueError('Original once receipt changed')
        cls.report = json.loads((PACKAGE / 'manifest.json').read_text())

    def test_exact_original_bodies_source_and_header_closure(self):
        r = self.report
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, digest in r[key].items(): self.assertEqual(build.sha(name), digest, name)
        actual_dependencies(r)
        self.assertEqual(set(r['dependency_records']), {
            'target-once', 'target-selected-once-wait', 'native-once', 'native-selected-once-wait', 'native-caller'})
        for name, text in build.fragments().items(): self.assertEqual((PACKAGE / name).read_text(), text)
        self.assertEqual((PACKAGE / 'once.c').read_bytes(), (build.SOURCE / 'src/once.c').read_bytes())
        self.assertNotEqual((PACKAGE / 'once.c').read_bytes(), (build.SOURCE / 'src/exclavekit/once.c').read_bytes())
        bad = dict(r, headers_sha256=dict(r['headers_sha256']))
        bad['headers_sha256'].pop(next(iter(bad['headers_sha256'])))
        with self.assertRaises(ValueError): actual_dependencies(bad)
        with self.assertRaises(ValueError): build.between('start start end', 'start', 'end')
        with self.assertRaises(ValueError): build.between('start only', 'start', 'end')
        self.assertTrue(r['private_header_boundary_explicit']); self.assertFalse(r['original_full_internal_header_used'])
        self.assertTrue(r['original_lock_function_bodies_unchanged'])
        self.assertTrue(r['quiescent_counter_semantics_retained'])

    def test_native_original_concurrency_publication_context_and_recursion(self):
        result = subprocess.run([str(PACKAGE / 'host-once')], capture_output=True, text=True, timeout=20)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, build.EXPECTED, ''))
        text = (PACKAGE / 'host.map').read_text()
        for symbol in ('_dispatch_once', '_dispatch_once_f'):
            self.assertRegex(text, r'(?m)^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*2\] ' + symbol + r'$')
        for symbol in ('__dispatch_once_wait', '__dispatch_gate_broadcast_slow'):
            self.assertRegex(text, r'(?m)^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*3\] ' + symbol + r'$')
        self.assertTrue(self.report['native_counter_is_explicit_double'])
        self.assertTrue(self.report['native_actual_ulock_and_pthread'])
        self.assertFalse(self.report['target_executed'])

    def test_actual_target_atomic_counter_ulock_paths_and_full_client(self):
        r = self.report
        once = subprocess.check_output(['xcrun', 'nm', '-ju', str(PACKAGE / 'target-once.o')], text=True)
        self.assertEqual(set(once.splitlines()), {'__dispatch_once_wait', '__dispatch_gate_broadcast_slow',
            '_pthread_self', '_pthread_mach_thread_np'})
        wait = subprocess.check_output(['xcrun', 'nm', '-ju', str(PACKAGE / 'target-selected-once-wait.o')], text=True)
        self.assertEqual(set(wait.splitlines()), {'___ulock_wait', '___ulock_wake', '_pthread_self', '_pthread_mach_thread_np'})
        disassembly = (PACKAGE / 'disassembly.stdout').read_text()
        for instruction in ('ldapr', 'swpl', 'dmb', 'brk'): self.assertRegex(disassembly, r'\b' + instruction + r'\b')
        self.assertIn('#0xfffff0000', disassembly); self.assertIn('#0xc180', disassembly)
        self.assertNotIn('rpi5_native_once_generation', disassembly)
        missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',
            (PACKAGE / 'target-link.stderr').read_text(), re.M)))
        self.assertEqual(missing, r['target_missing_symbols']); self.assertEqual(len(missing), 54)
        self.assertEqual(r['closed_symbols'], ['_dispatch_once']); self.assertEqual(r['newly_reachable_symbols'], [])
        self.assertEqual(r['target_duplicate_symbols'], [])
        base = json.loads((build.BASE / 'manifest.json').read_text())
        old = list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
        new = list(next(c['command'] for c in r['commands'] if c['stdout'].endswith('/target-link.stdout')))
        for flag in ('-o', '-map'): old[old.index(flag) + 1] = new[new.index(flag) + 1]
        self.assertEqual(new, old + [r['target_archive']])
        self.assertTrue(r['original_openssh_config_unchanged']); self.assertFalse(r['complete_libdispatch_runtime_qualified'])
        self.assertFalse(r['target_link_complete']); self.assertFalse(r['accepted_runtime_modified'])


if __name__ == '__main__': unittest.main()
