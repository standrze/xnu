#!/usr/bin/env python3
"""Offline original pselect and scoped hook byte-tail correction evidence."""
import json
from pathlib import Path
import struct
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_file_wait_leaves as build
from tools.rpi5 import check_apple_pthread_kernel_contract as macho
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE=build.ROOT/'build/rpi5/apple-ssh-file-wait-99k0lf5s'
SHA='1160079aeaeb39bfbecfa932dfe785a1a929b61c489213f905ee5c40870f2e61'


class FileWaitClosure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE/'manifest.json')!=SHA:raise ValueError('Frozen file/wait receipt changed')
        cls.report=json.loads((PACKAGE/'manifest.json').read_text())

    def test_complete_actual_header_and_input_closure(self):
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for n,h in self.report[key].items():self.assertEqual(build.sha(n),h,n)
        actual_dependencies(self.report)
        for record in self.report['dependency_records'].values():
            self.assertEqual(record['scanned_sha256'],record['consumed_sha256'])
        bad=dict(self.report,headers_sha256=dict(self.report['headers_sha256']))
        bad['headers_sha256'].pop(next(iter(bad['headers_sha256'])))
        with self.assertRaises(ValueError):actual_dependencies(bad)

    def test_exact_source_correction_and_native_callback_error_contract(self):
        original=(build.LIBC/'darwin/libc_hooks.c').read_text()
        corrected=Path(self.report['private_source']).read_text()
        self.assertEqual(corrected,original.replace(build.HOOK_OLD,build.HOOK_NEW))
        self.assertEqual(original.count(build.HOOK_OLD),1)
        bad=subprocess.run([str(PACKAGE/'original-hooks-negative-host'),'original-oversize'],capture_output=True,text=True,timeout=10)
        self.assertNotEqual(bad.returncode,0)
        self.assertIn('AddressSanitizer: heap-buffer-overflow',bad.stderr)
        good=subprocess.run([str(PACKAGE/'original-file-wait-host')],capture_output=True,text=True,timeout=10)
        self.assertEqual((good.returncode,good.stdout,good.stderr),(0,build.EXPECTED,''))
        self.assertTrue(self.report['hook_setter_only_single_threaded'])

    def test_actual_private_syscalls_and_original_fallback_remain(self):
        calls={'pselect':394,'select':93,'pthread_sigmask':329}
        for n,number in calls.items():
            path=PACKAGE/('trap-'+n+'.o');obj=macho.MachO(path)
            address=obj.names['___'+n]['address'];words=struct.unpack('<10I',obj.at(address,40))
            self.assertEqual(words[0],0xd2800010|(number<<5));self.assertEqual(words[1],0xd4001001)
            self.assertEqual(subprocess.check_output(['xcrun','nm','-u',path],text=True).splitlines(),
                             ['_cerror_nocancel' if n=='pthread_sigmask' else '_cerror'])
        obj=macho.MachO(PACKAGE/'pselect.o')
        self.assertIn('_pselect',obj.names);self.assertIn('_rpi5_pselect_fallback_select',obj.names)
        self.assertNotIn('_select',obj.names)
        self.assertEqual(subprocess.check_output(['xcrun','nm','-u',PACKAGE/'pselect.o'],text=True).splitlines(),
                         ['___error','___pselect','___pthread_sigmask','___select'])

    def test_actual_full_link_delta_is_not_execution(self):
        r=self.report
        self.assertEqual(r['closed_symbols'],['_pselect','_strchrnul'])
        self.assertEqual(r['newly_reachable_symbols'],[]);self.assertEqual(r['target_duplicate_symbols'],[])
        self.assertEqual(len(r['target_missing_symbols']),80)
        self.assertFalse(r['target_link_complete']);self.assertFalse(r['target_executed'])
        self.assertFalse(r['provider_stubs']);self.assertTrue(r['original_openssh_config_unchanged'])


if __name__=='__main__':unittest.main()
