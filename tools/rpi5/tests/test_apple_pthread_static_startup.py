# SPDX-License-Identifier: BSD-2-Clause
"""Offline private startup admission, not runtime acceptance of Pi pthreads."""
import copy
import json
from pathlib import Path
import re
import struct
import subprocess
import unittest

from tools.rpi5.check_apple_pthread_kernel_contract import MachO
from tools.rpi5.tests.test_apple_pthread_startup_contract import sha, validate_closure

ROOT=Path(__file__).resolve().parents[3]
TARGET=ROOT/'build/rpi5/apple-pthread-static-complete-gm82fjkz'
TARGET_SHA='4a22b183000378e842d59c643ed1f8a80a520e1e77d62370880a7c095adfc35a'
NATIVE=ROOT/'build/rpi5/apple-pthread-static-native-bounds-65neccqr'
NATIVE_SHA='4a3f15122ded6e16c649d286780ce807029fd81d6d7ce00c86edceb13332024d'


class ApplePthreadStaticStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target=json.loads((TARGET/'manifest.json').read_text())
        cls.native=json.loads((NATIVE/'manifest.json').read_text())

    def test_actual_complete_dependencies_and_negative_membership(self):
        for package,digest,report in ((TARGET,TARGET_SHA,self.target),(NATIVE,NATIVE_SHA,self.native)):
            self.assertEqual(sha(package/'manifest.json'),digest)
            validate_closure(package,report)
        for key in ('headers_sha256','generated_sha256'):
            report=copy.deepcopy(self.target);report[key].pop(next(iter(report[key])))
            with self.assertRaisesRegex(ValueError,'membership mismatch'):validate_closure(TARGET,report)

    def test_only_explicit_runtime_members_replaced_no_fake_key_entry(self):
        rows=self.target['exact_archive_replacements']
        self.assertEqual([r['member'] for r in rows],['14-darwin_static.o','glue-allocator.o'])
        for row in rows:
            self.assertEqual(set(row['before']),set(row['after']))
            self.assertEqual({p for p in row['before'] if row['before'][p]!=row['after'][p]},{row['member']})
        removed=self.target['removed_old_link_inputs']
        self.assertEqual(len(removed),4)
        self.assertTrue(any(p.endswith('/argv-entry.o') for p in removed))
        source=(TARGET/'darwin_abi_without_legacy_start.c').read_text()
        for bad in ('main_tsd','main_errno','zsh_main','void darwin_static_start'):
            self.assertNotIn(bad,source)
        allocator=(ROOT/'tools/rpi5/user/pthread_allocator.c').read_text()
        self.assertNotIn('int __is_threaded;',allocator)
        self.assertIn('__atomic_exchange_n(&zone_lock, 1, __ATOMIC_ACQUIRE)',allocator)
        self.assertIn('__atomic_store_n(&default_zone, zone, __ATOMIC_RELEASE)',allocator)
        link=next(c['command'] for c in self.target['commands'] if c['stdout'].endswith('/target-link.stdout'))
        for p in removed:self.assertNotIn(p,link)
        self.assertNotIn('-D__DARWIN_NON_CANCELABLE=1',next(c['command'] for c in self.target['commands'] if c['stdout'].endswith('/smoke-compile.stdout')))

    def test_actual_static_macho_ctor_pointer_and_initialization_order(self):
        target=Path(self.target['target']);self.assertEqual(sha(target),self.target['target_sha256'])
        image=MachO(target)
        self.assertIn(5,image.commands)  # LC_UNIXTHREAD; kernel emits main_stack.
        for forbidden in (0xc,0xe,0x80000018,0x80000028):self.assertNotIn(forbidden,image.commands)
        ctors=next(s for s in image.sections if s['name']=='__DATA,__mod_init_func')
        self.assertEqual(ctors['size'],8)
        self.assertEqual(struct.unpack('<Q',image.at(ctors['address'],8))[0],image.names['_initialized_constructor']['address'])
        text=(TARGET/'target-startup-disassembly.stdout').read_text().split('<_darwin_static_start>:',1)[1]
        ordered=['<___libkernel_init>','<___pthread_init>','<_malloc>','<_free>','<___pthread_late_init>']
        positions=[text.index(p) for p in ordered];self.assertEqual(positions,sorted(positions))
        runner=subprocess.check_output(['xcrun','llvm-objdump','--disassemble-symbols=_rpi5_run_initializers',target],text=True)
        self.assertIn('blr\tx8',runner)
        self.assertLess(text.index('<_rpi5_run_initializers>'),text.index('<_rpi5_pthread_smoke_main>'))
        self.assertEqual(subprocess.check_output(['xcrun','nm','-u',target],text=True).strip(),'')
        self.assertEqual(self.target['target_duplicate_symbols'],[])
        self.assertEqual(self.target['libkernel_callbacks_version'],4)
        self.assertEqual(self.target['pthread_callbacks_version'],2)

    def test_real_public_pthread_owners_and_cancellation_emitter(self):
        text=(TARGET/'target.map').read_text()
        owners={}
        for n,path in re.findall(r'^\[\s*(\d+)\]\s+(.+)$',text,re.M):owners[int(n)]=path
        expected={'_pthread_create':'pthread-private.o','_pthread_equal':'pthread-private.o',
            '_pthread_join':'original-cancelable.o','_pthread_key_create':'pthread-pthread_tsd.o',
            '_pthread_getspecific':'pthread-pthread_tsd.o','_pthread_setspecific':'pthread-pthread_tsd.o',
            '_pthread_mutex_lock':'pthread-pthread_mutex.o','___is_threaded':'pthread-private.o'}
        for symbol,object_name in expected.items():
            row=re.search(r'^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+'+re.escape(symbol)+r'$',text,re.M)
            self.assertIsNotNone(row,symbol);self.assertTrue(owners[int(row[1])].endswith('('+object_name+')'),symbol)
        disassembly=(TARGET/'target-startup-disassembly.stdout').read_text()
        self.assertIn('<_pthread_testcancel>',disassembly.split('<_pthread_join>:',1)[1].split('<_darwin_static_start>:',1)[0])
        trap=subprocess.check_output(['xcrun','llvm-objdump','-d',TARGET/'cancel.o'],text=True)
        self.assertIn('mov\tx16, #0x14d',trap);self.assertEqual(trap.count('svc\t#0x80'),1)
        self.assertIn('_cerror_nocancel',subprocess.check_output(['xcrun','nm','-u',TARGET/'cancel.o'],text=True))
        self.assertEqual(self.target['actual_pthread_canceled_syscall'],333)

    def test_short_native_adapter_and_workload_explicit_host_boundary(self):
        for exe,key in (('adapter-host','adapter_stdout'),('smoke-host','host_workload_stdout')):
            p=subprocess.run([NATIVE/exe],capture_output=True,text=True,timeout=10)
            self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'');self.assertEqual(p.stdout,self.native[key])
        for key in ('target_original_scalable_allocator_executed','target_pthread_implementation_executed','target_startup_executed','pi_executed'):
            self.assertIs(self.native[key],False)
        self.assertEqual(self.native['vector_cases'],16)
        for key in ('target_main_thread_initialized','target_created_threads','kernel_entropy_qualified','accepted_runtime_modified','pi_executed'):
            self.assertIs(self.target[key],False)


if __name__=='__main__':unittest.main()
