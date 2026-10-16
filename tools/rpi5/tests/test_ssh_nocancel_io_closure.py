#!/usr/bin/env python3
"""Real wrapper/trap ownership and native policy doubles, never real I/O."""
import json
from pathlib import Path
import struct
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_nocancel_io as build
from tools.rpi5 import check_apple_pthread_kernel_contract as macho
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE=build.ROOT/'build/rpi5/apple-ssh-nocancel-io-97n771iy'
SHA='9f754e50a8e2d09b8ba8420c58bbe7d043adb4a586bba59d34ff4ac44898518d'


class NocancelIO(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE/'manifest.json')!=SHA:raise ValueError('Frozen I/O receipt changed')
        cls.report=json.loads((PACKAGE/'manifest.json').read_text())

    def test_actual_source_header_membership_and_native_variadic_policy(self):
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for n,h in self.report[key].items():self.assertEqual(build.sha(n),h,n)
        actual_dependencies(self.report)
        bad=dict(self.report,headers_sha256=dict(self.report['headers_sha256']))
        bad['headers_sha256'].pop(next(iter(bad['headers_sha256'])))
        with self.assertRaises(ValueError):actual_dependencies(bad)
        run=subprocess.run([str(PACKAGE/'original-nocancel-io-host')],capture_output=True,text=True,timeout=10)
        self.assertEqual((run.returncode,run.stdout,run.stderr),(0,build.EXPECTED,''))

    def test_real_variadic_wrapper_not_incorrect_syscall_alias(self):
        wrapper=macho.MachO(PACKAGE/'open-base.o')
        self.assertIn('_open$NOCANCEL',wrapper.names);self.assertIn('_openat$NOCANCEL',wrapper.names)
        self.assertNotEqual(wrapper.names['_open$NOCANCEL']['address'],wrapper.names['_openat$NOCANCEL']['address'])
        expected={'___close_nocancel','___fcntl_nocancel','___open_nocancel','___openat_nocancel',
                  '_system_version_compat_check_path_suffix','_system_version_compat_open_shim'}
        self.assertEqual(set(subprocess.check_output(['xcrun','nm','-u',PACKAGE/'open-base.o'],text=True).splitlines()),expected)
        for n,number in build.CALLS.items():
            path=PACKAGE/('trap-'+n+'.o');obj=macho.MachO(path);at=obj.names['___'+n]['address']
            words=struct.unpack('<10I',obj.at(at,40))
            self.assertEqual(words[0],0xd2800010|(number<<5));self.assertEqual(words[1],0xd4001001)
            self.assertEqual(subprocess.check_output(['xcrun','nm','-u',path],text=True).splitlines(),['_cerror_nocancel'])
        read=macho.MachO(PACKAGE/'trap-read_nocancel.o')
        self.assertEqual(read.names['_read$NOCANCEL']['address'],read.names['___read_nocancel']['address'])
        opened=macho.MachO(PACKAGE/'trap-open_nocancel.o')
        self.assertNotIn('_open$NOCANCEL',opened.names)

    def test_forced_dependency_closure_and_honest_limits(self):
        r=self.report
        self.assertEqual(r['newly_reachable_symbols'],[]);self.assertEqual(r['target_duplicate_symbols'],[])
        self.assertEqual(len(r['target_missing_symbols']),80)
        self.assertEqual(r['forced_symbols'],['_open$NOCANCEL','_openat$NOCANCEL','_read$NOCANCEL'])
        self.assertFalse(r['source_or_config_changes']);self.assertFalse(r['host_io_executed'])
        self.assertFalse(r['target_executed']);self.assertFalse(r['target_link_complete'])
        self.assertTrue(r['original_system_version_compat_enabled'])


if __name__=='__main__':unittest.main()
