# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import subprocess
import unittest
from tools.rpi5.tests.test_apple_pthread_startup_contract import sha, validate_closure, dep_paths
from tools.rpi5.link_apple_pthread_mach_state import REMOVED, SOURCE

ROOT=Path(__file__).resolve().parents[3]
PACKAGES={
    'target':('apple-pthread-log-clock-m3ct69va','47ed14c78a38d0c81f2325228e44f8205bc6a778e11cd4297b3bec6b1a821d9b'),
    'state':('apple-pthread-mach-state-8rohn6p5','6f23ca213bd8760dfd79bb12bcc3c7155e7ee54e6ebef2413ff42a43aff880dc'),
    'host':('apple-pthread-log-check-i4c34a6y','09cdaf3ecc12820c9bb3e3489ad238a7f65b100c3e3a7be23e4e00033e4cbfb8'),
}


class ApplePthreadLogProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths={k:ROOT/'build/rpi5'/v[0] for k,v in PACKAGES.items()}
        cls.reports={k:json.loads((p/'manifest.json').read_text()) for k,p in cls.paths.items()}

    def test_exact_input_generated_and_actual_consumed_membership(self):
        for key,path in self.paths.items():
            self.assertEqual(sha(path/'manifest.json'),PACKAGES[key][1])
            validate_closure(path,self.reports[key])
        target=self.reports['target']
        self.assertEqual((target['compiled_units'],target['attempted_units']),(8,8))
        for unit in target['units']:
            self.assertTrue(unit['compiled'])
            self.assertEqual(unit['actual_headers_sha256'],unit['preprocessor_headers_sha256'])
            self.assertEqual(set(unit['actual_headers_sha256']),dep_paths(self.paths['target']/(unit['label']+'.d')))
        for path,record in target['original_header_installations'].items():
            self.assertEqual(Path(path).read_bytes(),Path(record['source']).read_bytes())

    def test_true_native_clock_errno_process_and_string_services(self):
        path=self.paths['host'];report=self.reports['host']
        result=subprocess.run([path/'log-provider-host'],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stderr,'')
        self.assertEqual(result.stdout,report['native_stdout'])
        self.assertIn('STRLCPY=66306 REAL_ERRORS=5120 CLOCK_BOUNDS=2048',result.stdout)
        self.assertTrue(report['actual_host_kernel_services'])
        self.assertTrue(report['native_asan_ubsan'])
        self.assertFalse(report['host_vm_wrappers_tested'])

    def test_explicit_private_global_ownership_not_duplicate_link_acceptance(self):
        target=self.reports['target'];state=self.reports['state']
        self.assertEqual(target['target_duplicate_symbols'],['_vm_page_mask','_vm_page_shift','_vm_page_size'])
        self.assertEqual(state['target_duplicate_symbols'],[])
        self.assertEqual(state['target_missing_symbols'],[])
        self.assertTrue(state['target_link_complete'])
        expected=SOURCE.read_text()
        for definition in REMOVED:
            self.assertEqual(expected.count(definition),1)
            expected=expected.replace(definition,'')
        self.assertEqual(expected,(self.paths['state']/'darwin_static_mach_owned.c').read_text())
        before,after=state['original_archive_members_sha256'],state['private_archive_members_sha256']
        self.assertEqual(set(before),set(after))
        self.assertEqual({n for n in before if before[n]!=after[n]},{'14-darwin_static.o'})
        self.assertEqual((self.paths['state']/'target-undefined.stdout').read_text().strip(),'')

    def test_real_traps_and_feature_gated_clock_no_startup_execution_claim(self):
        path=self.paths['target']
        dis=subprocess.check_output(['xcrun','otool','-tvV',path/'log-traps.o'],text=True)
        self.assertEqual(dis.count('svc\t#0x80'),6)
        for number in (97,133,336,399,406,409): self.assertIn('mov\tx16, #'+hex(number),dis)
        clock=(path/'absolute-time.s').read_text()
        self.assertIn('CNTVCT_EL0',clock)
        self.assertIn('_mach_absolute_time_kernel',clock)
        self.assertIn('L_mach_absolute_time_user_nospec_apple',clock)
        for report in self.reports.values():
            self.assertFalse(report['target_startup_created'])
            self.assertFalse(report['target_main_thread_initialized'])
            self.assertFalse(report['pi_executed'])
        state=self.reports['state']
        self.assertTrue(state['legacy_argv_entry_retained'])
        self.assertTrue(state['legacy_bootstrap_tsd_retained'])
        self.assertFalse(state['constructors_order_wired'])


if __name__=='__main__':unittest.main()
