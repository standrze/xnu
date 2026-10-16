#!/usr/bin/env python3
"""Original Darwin interface/Ethernet providers, offline target proof only."""
import json
from pathlib import Path
import re
import struct
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_interface_helpers as build
from tools.rpi5 import check_apple_pthread_kernel_contract as macho
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE = build.ROOT / 'build/rpi5/apple-ssh-interface-helpers-o1gdvmp_'
SHA = '2165e237397a2d7ce8e364f6469a8044be29ce62575d3b985a1f68b372fe6f0f'


class InterfaceHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE / 'manifest.json') != SHA: raise ValueError('Frozen interface receipt changed')
        cls.report = json.loads((PACKAGE / 'manifest.json').read_text())

    def test_whole_original_translation_units_and_actual_dependency_closure(self):
        r = self.report
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, digest in r[key].items(): self.assertEqual(build.sha(name), digest, name)
        actual_dependencies(r)
        expected = {'target-' + Path(name).stem for name in build.UNITS}
        expected |= {'native-' + Path(name).stem for name in build.NATIVE_UNITS}
        self.assertEqual(set(r['dependency_records']), expected | {'target-caller-abi', 'native-caller'})
        for record in r['dependency_records'].values():
            self.assertEqual(record['scanned_sha256'], record['consumed_sha256'])
        for name in build.NATIVE_UNITS:
            source = build.SOURCE / 'gen.subproj' / name
            self.assertEqual(source.read_bytes(), subprocess.check_output(
                ['git', '-C', str(build.SOURCE), 'show', 'HEAD:gen.subproj/' + name]))
        self.assertEqual(r['original_libinfo_macros'], list(build.libinfo.MACROS))
        self.assertTrue(r['actual_target_and_native_darwin_layout_assertions_compiled'])
        bad = dict(r, headers_sha256=dict(r['headers_sha256']))
        bad['headers_sha256'].pop(next(iter(bad['headers_sha256'])))
        with self.assertRaises(ValueError): actual_dependencies(bad)

    def test_real_local_native_route_sysctl_and_controlled_mac_parsers(self):
        result = subprocess.run([str(PACKAGE / 'host-interface-ether')], capture_output=True, text=True, timeout=20)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertRegex(result.stdout, '^' + build.EXPECTED + '$')
        native_map = (PACKAGE / 'native.map').read_text()
        for name in ('if_indextoname', 'if_nametoindex', 'ether_aton', 'ether_ntoa', 'ether_line', 'getifaddrs', 'freeifaddrs'):
            self.assertRegex(native_map, r'(?m)^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s+[2-5]\] _fixture_' + name + '$')
        undefined = subprocess.check_output(['xcrun', 'nm', '-ju', str(PACKAGE / 'native-getifaddrs.o')], text=True).splitlines()
        self.assertIn('_sysctl', undefined)
        self.assertNotIn('_getifaddrs', undefined)
        self.assertTrue(self.report['native_asan_ubsan_pass'])
        self.assertFalse(self.report['native_external_network_services'])
        self.assertTrue(self.report['original_ether_line_unbounded_hostname_scan_retained'])
        self.assertFalse(self.report['arbitrary_oversized_ether_line_input_qualified'])

    def test_actual_a76_darwin_offsets_and_original_provider_call_relocations(self):
        r = self.report
        index = macho.MachO(Path(r['objects']['if_indextoname.c']))
        address = index.names['_if_indextoname']['address']
        # Actual ldr ifa_addr +24, ldrb sa_family +1, ldrh sdl_index +2.
        for offset, word in ((0x48, 0xf9400d09), (0x50, 0x3940052a), (0x5c, 0x79400529),
                             (0x70, 0x52800202), (0x74, 0x92800003)):
            self.assertEqual(struct.unpack('<I', index.at(address + offset, 4))[0], word)
        branches = lambda image, name: {target for _, kind, target in image.function(name)['relocations'] if kind == 0x2d}
        self.assertEqual(branches(index, '_if_indextoname'),
                         {'_getifaddrs', '_freeifaddrs', '___error', '___strncpy_chk'})
        name = macho.MachO(Path(r['objects']['if_nametoindex.c']))
        self.assertEqual(branches(name, '_if_nametoindex'), {'_getifaddrs', '_freeifaddrs', '___error', '_strcmp'})
        ether = macho.MachO(Path(r['objects']['ether_addr.c']))
        self.assertEqual(branches(ether, '_ether_aton'), {'_calloc', '_sscanf'})
        self.assertEqual(branches(ether, '_ether_line'), {'_sscanf'})
        self.assertEqual(branches(ether, '_ether_ntoa'), {'_malloc', '___snprintf_chk'})
        for command in r['commands']:
            if command['stdout'].endswith('-compile.stdout') and '/target-' in command['stdout']:
                self.assertIn('-mcpu=cortex-a76', command['command'])

    def test_full_client_preserved_and_new_fortify_prerequisite_explicit(self):
        r = self.report
        missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',
            (PACKAGE / 'target-link.stderr').read_text(), re.M)))
        self.assertEqual(missing, r['target_missing_symbols'])
        self.assertEqual(r['previous_missing_count'], 52); self.assertEqual(len(missing), 50)
        self.assertEqual(r['closed_symbols'], ['_ether_aton', '_if_indextoname', '_if_nametoindex'])
        self.assertEqual(r['newly_reachable_symbols'], ['___strncpy_chk'])
        self.assertEqual(r['target_duplicate_symbols'], [])
        base = json.loads((build.BASE / 'manifest.json').read_text())
        old = list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
        new = list(next(c['command'] for c in r['commands'] if c['stdout'].endswith('/target-link.stdout')))
        for flag in ('-o', '-map'): old[old.index(flag) + 1] = new[new.index(flag) + 1]
        self.assertEqual(new, old + [r['target_archive']])
        self.assertTrue(r['original_getifaddrs_already_owned'])
        self.assertTrue(r['original_openssh_config_unchanged'])
        for key in ('target_link_complete', 'target_executed', 'accepted_runtime_modified', 'provider_stubs',
                    'target_network_runtime_qualified'):
            self.assertFalse(r[key])


if __name__ == '__main__': unittest.main()
