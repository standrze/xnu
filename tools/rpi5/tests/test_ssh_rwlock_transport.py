# SPDX-License-Identifier: BSD-2-Clause
"""Genuine static RW-lock transport and native Mach-wrapper boundaries only."""
import copy
import json
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_rwlock_transport as b
from tools.rpi5.tests.test_apple_pthread_startup_contract import validate_closure

PACKAGE=b.ROOT/'build/rpi5/apple-ssh-rwlock-transport-a35pfswk'
PIN='7529c89500f244594b9f14f8fde7340d448950a1b4107acb3bf225ce4641a0d7'


def members(m):
    expected={str(Path(b.__file__).resolve()):b.sha(b.__file__),str(b.WRAPPER):b.sha(b.WRAPPER),
        str(b.HARNESS):b.sha(b.HARNESS),str(Path(b.prepare_pid1.__file__).resolve()):b.sha(b.prepare_pid1.__file__)}
    for directory,pin in ((b.source.BASE,b.source.BASE_SHA),(b.TIME,b.TIME_SHA)):
        path=directory/'manifest.json'
        if b.sha(path)!=pin:raise ValueError('Exact prerequisite differs')
        expected[str(path)]=pin;parent=json.loads(path.read_text())
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for name,h in parent[key].items():
                if name in expected and expected[name]!=h:raise ValueError('Pin conflict')
                expected[name]=h
    for path in [b.ROOT/'bsd/kern/syscalls.master',*[b.GENERATED/('___'+n+'.s') for n in b.CALLS]]:
        expected[str(path)]=b.sha(path)
    if expected!=m['source_inputs_sha256']:raise ValueError('Exact source membership differs')


class RwlockTransportTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(b.sha(PACKAGE/'manifest.json'),PIN)
        self.m=json.loads((PACKAGE/'manifest.json').read_text())

    def test_source_generated_header_closure_and_negative_controls(self):
        members(self.m);validate_closure(PACKAGE,self.m)
        for r in self.m['dependency_records'].values():self.assertEqual(r['scanned_sha256'],r['consumed_sha256'])
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            bad=copy.deepcopy(self.m);bad[key].pop(next(iter(bad[key])))
            with self.assertRaises(ValueError):members(bad);validate_closure(PACKAGE,bad)
            bad=copy.deepcopy(self.m);bad[key][next(iter(bad[key]))]='0'*64
            with self.assertRaises(ValueError):members(bad);validate_closure(PACKAGE,bad)
        timing=json.loads((b.TIME/'manifest.json').read_text())
        self.assertEqual(timing['compile_failures'],{})
        self.assertEqual(len(timing['objects']),6);self.assertIs(timing['notify_tz_enabled'],True)
        feature=next(p for p in timing['headers_sha256'] if p.endswith('/arm64/libc-features.h'))
        self.assertIn('#define NOTIFY_TZ 1',Path(feature).read_text())

    def test_full_client_exact_delta_keeps_service_and_environment_gaps(self):
        m=self.m;timing=json.loads((b.TIME/'manifest.json').read_text())
        self.assertEqual(m['normal_stdtime_before_count'],47)
        self.assertEqual(m['qualified_client_before_count'],41)
        self.assertEqual(len(m['target_missing_symbols']),43)
        self.assertEqual(m['closed_symbols'],sorted(['___'+n for n in b.CALLS]+['_thread_switch']))
        self.assertEqual(m['newly_reachable_symbols'],[]);self.assertEqual(m['target_duplicate_symbols'],[])
        self.assertEqual(set(m['target_missing_symbols'])-set(json.loads((b.source.BASE/'manifest.json').read_text())['target_missing_symbols']),
                         {'_getenv_copy_np','_notify_cancel','_notify_monitor_file'})
        self.assertNotIn('_localtime_r',m['target_missing_symbols'])
        command=list(next(c['command'] for c in timing['commands'] if c['stdout'].endswith('/target-link.stdout')))
        command[command.index('-o')+1]=str(PACKAGE/'NOT_RUN_ssh');command[command.index('-map')+1]=str(PACKAGE/'target.map')
        command.append(m['target_archive'])
        self.assertEqual(command,next(c['command'] for c in m['commands'] if c['stdout'].endswith('/target-link.stdout')))
        for key in ('stdtime_qualified','full_client_qualified','target_executed','host_psynch_executed','provider_stubs','accepted_runtime_modified'):
            self.assertIs(m[key],False)

    def test_exact_arm64_traps_live_rwlock_mach_and_errno_owners(self):
        m=self.m;target=Path(m['target'])
        self.assertEqual(b.sha(target),m['target_sha256']);self.assertEqual(b.prepare_pid1.inspect(target.read_bytes()),m['static_inspection'])
        self.assertEqual(subprocess.check_output(['xcrun','nm','-ju',target],text=True),'')
        dis=(PACKAGE/'target-disassembly.stdout').read_text()
        for name,number in b.CALLS.items():
            block=dis.split('('+name+'.o):',1)[1].split('\n/Users/',1)[0]
            self.assertRegex(block,r'mov\s+x16, #'+hex(number)+r'\b')
            self.assertEqual(block.count('svc\t#0x80'),1)
            self.assertIn('ARM64_RELOC_BRANCH26\t_cerror_nocancel\n',block)
            self.assertNotIn('ARM64_RELOC_BRANCH26\t_cerror\n',block)
            self.assertEqual(m['live_symbol_owners']['___'+name],m['target_archive']+'('+name+'.o)')
        self.assertEqual(m['live_symbol_owners']['_thread_switch'],m['target_archive']+'(thread-switch.o)')
        for symbol in b.FORCE:
            if symbol.startswith('_pthread_'):
                self.assertEqual(m['live_symbol_owners'][symbol],str(b.ROOT/'build/rpi5/apple-pthread-memory-4idfg5qr/libapple-pthread-platform-scoped.a')+'(pthread-pthread_rwlock.o)')
        self.assertTrue(m['live_symbol_owners']['_syscall_thread_switch'].endswith('/libapple-pthread-mach-dyld-bootstrap.a(mach-traps.o)'))
        self.assertTrue(m['live_symbol_owners']['_cerror_nocancel'].endswith('/private-abi-runtime.a(2-errno.o)'))
        final=subprocess.check_output(['xcrun','llvm-objdump','-d','--disassemble-symbols=_syscall_thread_switch',target],text=True)
        self.assertIn('svc\t#0x80',final)
        self.assertRegex(final,r'mov\s+x16, #-0x3d\b')
        self.assertNotRegex((PACKAGE/'contract.map').read_text(),r'fixture_|__asan|__ubsan')

    def test_original_native_wrapper_boundary_values_and_negative_oracle(self):
        result=subprocess.run([PACKAGE/'thread-switch-host'],capture_output=True,text=True,timeout=15)
        self.assertEqual((result.returncode,result.stdout,result.stderr),(0,b.EXPECTED,''))
        bad=subprocess.run([PACKAGE/'thread-switch-host','bad-expected'],capture_output=True,text=True,timeout=15)
        self.assertEqual((bad.returncode,bad.stderr),(37,''))
        command=next(c['command'] for c in self.m['commands'] if c['stdout'].endswith('/host-wrapper-compile.stdout'))
        for flag in ('-Dthread_switch=fixture_thread_switch','-Dsyscall_thread_switch=fixture_syscall_thread_switch',
                     '-fsanitize=address,undefined','-fno-sanitize-recover=undefined'):self.assertIn(flag,command)
        undef=subprocess.check_output(['xcrun','nm','-ju',PACKAGE/'host-wrapper.o'],text=True).splitlines()
        self.assertIn('_fixture_syscall_thread_switch',undef);self.assertNotIn('_syscall_thread_switch',undef)
        target_command=next(c['command'] for c in self.m['commands'] if c['stdout'].endswith('/thread-switch-compile.stdout'))
        self.assertFalse(any('fixture_' in x or 'sanitize' in x for x in target_command))


if __name__=='__main__':unittest.main()
