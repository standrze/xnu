#!/usr/bin/env python3
"""Actual A76 providers and string boundary proof; no group syscall executes."""
import json
from pathlib import Path
import re
import struct
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_libc_prereqs as build
from tools.rpi5 import check_apple_pthread_kernel_contract as macho
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE = build.ROOT / 'build/rpi5/apple-ssh-libc-prereqs-crebas6n'
SHA = 'e50d8616f35c33e88beebab3d6e75ccfe008598669534c1ec4c06f7f9de809dd'


class LibcPrerequisites(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE / 'manifest.json') != SHA: raise ValueError('Frozen receipt changed')
        cls.report = json.loads((PACKAGE / 'manifest.json').read_text())

    def test_original_whole_source_policy_and_exact_dependency_membership(self):
        r = self.report
        for key in ('source_inputs_sha256', 'headers_sha256', 'generated_sha256'):
            for name, digest in r[key].items(): self.assertEqual(build.sha(name), digest, name)
        actual_dependencies(r)
        self.assertEqual(set(r['dependency_records']),
            {'target-strnstr', 'native-strnstr', 'native-caller', 'target-initgroups'})
        for record in r['dependency_records'].values():
            self.assertEqual(record['scanned_sha256'], record['consumed_sha256'])
        self.assertEqual(subprocess.check_output(['git', '-C', str(build.LIBC), 'show', 'HEAD:string/FreeBSD/strnstr.c']),
                         build.SOURCE.read_bytes())
        self.assertEqual(subprocess.check_output(['git', '-C', str(build.LIBC), 'rev-parse', 'HEAD'], text=True).strip(),
                         build.COMMIT)
        self.assertTrue(r['whole_original_translation_unit_compiled'])
        for command in r['commands']:
            args = command['command']
            if '-c' in args and str(build.SOURCE) in args: self.assertIn('-D_FORTIFY_SOURCE=0', args)
        bad = dict(r, headers_sha256=dict(r['headers_sha256']))
        bad['headers_sha256'].pop(next(iter(bad['headers_sha256'])))
        with self.assertRaises(ValueError): actual_dependencies(bad)

    def test_native_exhaustive_search_and_heap_page_guard_boundaries(self):
        result = subprocess.run([str(PACKAGE / 'host-strnstr')], capture_output=True, text=True, timeout=15)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, build.EXPECTED, ''))
        self.assertTrue(self.report['native_asan_ubsan_pass'])
        self.assertFalse(self.report['native_privileged_syscall_executed'])
        self.assertFalse(self.report['syscall_runtime_qualified'])

    def test_actual_a76_initgroups_number_private_alias_and_real_error_relocation(self):
        r = self.report; obj = macho.MachO(Path(r['objects']['__initgroups']))
        master = (build.ROOT / 'bsd/kern/syscalls.master').read_text()
        self.assertRegex(master, r'(?m)^243\s+[^\n]*int initgroups\(u_int gidsetsize, gid_t \*gidset, int gmuid\) NO_SYSCALL_STUB;')
        self.assertEqual(r['syscall_number'], 243)
        self.assertIn('___initgroups', obj.names)
        self.assertNotIn('_initgroups', obj.names)  # Original Libinfo owns the public wrapper.
        address = obj.names['___initgroups']['address']
        self.assertEqual(struct.unpack('<10I', obj.at(address, 40)),
            (0xd2801e70, 0xd4001001, 0x540000e3, 0xa9bf7bfd, 0x910003fd,
             0x94000000, 0x910003bf, 0xa8c17bfd, 0xd65f03c0, 0xd65f03c0))
        function = obj.function('___initgroups')
        self.assertEqual(function['relocations'], [(20, 0x2d, '_cerror_nocancel')])
        self.assertEqual((PACKAGE / 'initgroups-undefined.stdout').read_text(), '_cerror_nocancel\n')
        self.assertEqual((Path(r['generated_directory']) / 'SYS.h').read_bytes(),
                         (build.ROOT / 'libsyscall/custom/SYS.h').read_bytes())
        self.assertEqual(r['generator_environment'], {'ARCHS': 'arm64'})
        string = macho.MachO(Path(r['objects']['strnstr']))
        relocs = string.function('_strnstr')['relocations']
        self.assertEqual({name for _, _, name in relocs}, {'_strlen', '_strncmp'})
        for command in r['commands']:
            if command['stdout'].endswith(('/target-strnstr-compile.stdout', '/target-initgroups-assemble.stdout')):
                self.assertIn('-mcpu=cortex-a76', command['command'])

    def test_exact_unchanged_full_client_link_delta_and_no_duplicate_owners(self):
        r = self.report
        missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',
            (PACKAGE / 'target-link.stderr').read_text(), re.M)))
        self.assertEqual(missing, r['target_missing_symbols'])
        self.assertEqual(r['previous_missing_count'], 54); self.assertEqual(len(missing), 52)
        self.assertEqual(r['closed_symbols'], ['___initgroups', '_strnstr'])
        self.assertEqual(r['newly_reachable_symbols'], [])
        self.assertEqual(r['target_duplicate_symbols'], [])
        base = json.loads((build.BASE / 'manifest.json').read_text())
        old = list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
        new = list(next(c['command'] for c in r['commands'] if c['stdout'].endswith('/target-link.stdout')))
        for flag in ('-o', '-map'): old[old.index(flag) + 1] = new[new.index(flag) + 1]
        self.assertEqual(new, old + [r['target_archive']])
        self.assertTrue(r['original_openssh_config_unchanged'])
        for key in ('target_link_complete', 'target_executed', 'accepted_runtime_modified', 'provider_stubs'):
            self.assertFalse(r[key])


if __name__ == '__main__': unittest.main()
