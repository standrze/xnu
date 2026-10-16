#!/usr/bin/env python3
"""Actual Apple process provider objects and host doubles; no target execution."""
import json
from pathlib import Path
import re
import struct
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_process_providers as build
from tools.rpi5 import build_apple_ssh_process_providers_v2 as native
from tools.rpi5 import check_apple_pthread_kernel_contract as macho
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE=build.ROOT/'build/rpi5/apple-ssh-process-providers-0mgunedd'
SHA='3f8b0da4dee23b2c325f8356c64942cb53ae728aea289ceee41713c57ea88349'


class ProcessClosure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE/'manifest.json')!=SHA:raise ValueError('Frozen process receipt changed')
        cls.report=json.loads((PACKAGE/'manifest.json').read_text())

    def test_exact_inputs_and_consumed_headers_including_native_caller(self):
        r=self.report
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for n,h in r[key].items():self.assertEqual(build.sha(n),h,n)
        actual_dependencies(r)
        self.assertIn('host-caller',r['dependency_records'])
        self.assertEqual(len(r['dependency_records']),19) # 7 target C, 4 traps, 7 host C, caller
        for row in r['dependency_records'].values():
            self.assertEqual(row['scanned_sha256'],row['consumed_sha256'])
        bad=dict(r,headers_sha256=dict(r['headers_sha256']))
        bad['headers_sha256'].pop(next(iter(bad['headers_sha256'])))
        with self.assertRaises(ValueError):actual_dependencies(bad)

    def test_distinct_wrapper_and_trap_archive_and_actual_wait_cancellation(self):
        r=self.report
        members=subprocess.check_output(['xcrun','ar','-t',r['target_archive']],text=True).splitlines()
        members=[n for n in members if not n.startswith('__.SYMDEF')]
        self.assertEqual(len(members),11);self.assertEqual(len(set(members)),11)
        self.assertIn('rmdir.o',members);self.assertIn('trap-rmdir.o',members)
        self.assertEqual(subprocess.check_output(['xcrun','nm','-u',PACKAGE/'waitpid.o'],text=True).splitlines(),
                         ['___error','___wait4'])
        self.assertEqual(subprocess.check_output(['xcrun','nm','-u',PACKAGE/'rmdir.o'],text=True).splitlines(),
                         ['___inc_remove_counter','___rmdir'])
        for n,number in build.GENERATED.items():
            path=PACKAGE/('trap-'+n+'.o');obj=macho.MachO(path)
            symbols=[v for v in obj.names.values() if v['name'] not in ('ltmp0','ltmp1') and v['type']&14==14]
            # Every generated trap has one entry address; public aliases may share it.
            addresses={v['address'] for v in symbols}
            self.assertEqual(addresses,{0})
            words=struct.unpack('<10I',obj.at(0,40))
            self.assertEqual(words[0],0xd2800010|(number<<5))
            self.assertEqual(words[1],0xd4001001)
            self.assertEqual(words[5],0x94000000)
            undefined=subprocess.check_output(['xcrun','nm','-u',path],text=True).splitlines()
            self.assertEqual(undefined,['_cerror' if n=='wait4' else '_cerror_nocancel'])
        wait=macho.MachO(PACKAGE/'trap-wait4.o')
        self.assertIn('___wait4',wait.names);self.assertNotIn('_wait4',wait.names)
        flags=next(c['command'] for c in r['commands'] if c['stdout'].endswith('/waitpid-compile.stdout'))
        self.assertIn('-DVARIANT_CANCELABLE',flags);self.assertIn('-D__DARWIN_UNIX03=1',flags)

    def test_original_native_error_semantics_under_explicit_doubles(self):
        run=subprocess.run([str(PACKAGE/'original-process-host')],capture_output=True,text=True,timeout=10)
        self.assertEqual((run.returncode,run.stdout,run.stderr),(0,native.STDOUT,''))
        self.assertTrue(self.report['native_asan_ubsan_pass'])
        self.assertTrue(self.report['native_syscalls_are_doubles'])
        self.assertFalse(self.report['host_processes_or_sockets_executed'])
        self.assertFalse(self.report['target_executed'])

    def test_honest_full_client_delta_and_categories(self):
        r=self.report
        stderr=(PACKAGE/'target-link.stderr').read_text()
        missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',stderr,re.M)))
        self.assertEqual(missing,r['target_missing_symbols']);self.assertEqual(len(missing),82)
        self.assertEqual(r['closed_symbols'],['_execl','_execlp','_execv','_getpeereid','_getprogname',
                                               '_mkdir','_raise','_rmdir','_waitpid'])
        self.assertEqual(r['newly_reachable_symbols'],['_strchrnul'])
        self.assertEqual(r['target_duplicate_symbols'],[]);self.assertFalse(r['target_link_complete'])
        self.assertFalse(r['provider_stubs']);self.assertTrue(r['original_openssh_config_unchanged'])
        groups=r['remaining_provider_groups']
        self.assertEqual(sum(map(len,groups.values())),82)
        self.assertEqual(set().union(*map(set,groups.values())),set(missing))


if __name__=='__main__':unittest.main()
