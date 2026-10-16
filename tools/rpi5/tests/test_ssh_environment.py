# SPDX-License-Identifier: BSD-2-Clause
"""Exact whole-family ownership and bounded host qualification, never target execution."""
import copy
import json
from pathlib import Path
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_environment as b
from tools.rpi5.tests.test_apple_pthread_startup_contract import validate_closure

PACKAGE=b.ROOT/'build/rpi5/apple-ssh-environment-id9imlth'
PIN='ba01dc58574d6349761bd648314c8341898ffd2ef46b1ef54952ecf71fa667f5'


def members(m):
    expected={str(b.BASE/'manifest.json'):b.BASE_SHA,str(Path(b.__file__).resolve()):b.sha(b.__file__),
        str(b.HARNESS):b.sha(b.HARNESS),str(b.OLD):b.sha(b.OLD),str(b.FRAGMENTS):b.sha(b.FRAGMENTS)}
    base=json.loads((b.BASE/'manifest.json').read_text())
    if b.sha(b.BASE/'manifest.json')!=b.BASE_SHA:raise ValueError('Base manifest differs')
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
        for n,h in base[key].items():
            if n in expected and expected[n]!=h:raise ValueError('Input conflict')
            expected[n]=h
    for name in (*b.UNITS,'tests/getenv.c'):
        path=b.LIBC/name;expected[str(path)]=b.sha(path)
    if expected!=m['source_inputs_sha256']:raise ValueError('Exact source membership differs')


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(b.sha(PACKAGE/'manifest.json'),PIN)
        self.m=json.loads((PACKAGE/'manifest.json').read_text())

    def test_full_source_generated_dependency_closure_and_omissions(self):
        members(self.m);validate_closure(PACKAGE,self.m)
        for r in self.m['dependency_records'].values():self.assertEqual(r['scanned_sha256'],r['consumed_sha256'])
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for mutation in ('remove','wrong'):
                bad=copy.deepcopy(self.m);name=next(iter(bad[key]))
                if mutation=='remove':bad[key].pop(name)
                else:bad[key][name]='0'*64
                with self.assertRaises(ValueError):members(bad);validate_closure(PACKAGE,bad)
        original=(b.LIBC/b.UNITS[0]).read_text()
        self.assertEqual((PACKAGE/'getenv_cleanup_checked.c').read_text(),b.repaired(original))
        self.assertEqual(b.repaired(original).count('free(result_buffer);'),2)
        for text in (original.replace('++attempts > 5','++attempts > 6'),original.replace('\t\tif (!value)','\t\tif (value == 0)')):
            with self.assertRaises(ValueError):b.repaired(text)

    def test_private_archive_replacement_exact_all_remaining_objects_unchanged(self):
        old=subprocess.check_output(['xcrun','ar','-t',b.OLD],text=True).splitlines()
        private=Path(self.m['private_archive'])
        new=subprocess.check_output(['xcrun','ar','-t',private],text=True).splitlines()
        self.assertEqual(new,[n for n in old if n not in b.MEMBERS])
        for name in new:
            if name=='__.SYMDEF SORTED':continue
            self.assertEqual(subprocess.check_output(['xcrun','ar','-p',b.OLD,name]),
                             subprocess.check_output(['xcrun','ar','-p',private,name]),name)
        prior=json.loads((b.BASE/'manifest.json').read_text())
        command=list(next(c['command'] for c in prior['commands'] if c['stdout'].endswith('/target-link.stdout')))
        command[command.index(str(b.OLD))]=str(private)
        command[command.index('-o')+1]=str(PACKAGE/'NOT_RUN_ssh');command[command.index('-map')+1]=str(PACKAGE/'target.map')
        command.append(self.m['target_archive'])
        self.assertEqual(command,next(c['command'] for c in self.m['commands'] if c['stdout'].endswith('/target-link.stdout')))
        self.assertEqual(self.m['closed_symbols'],['_getenv_copy_np'])
        self.assertEqual(self.m['newly_reachable_symbols'],[]);self.assertEqual(self.m['target_duplicate_symbols'],[])
        self.assertEqual(len(self.m['target_missing_symbols']),42)
        self.assertEqual(self.m['prior_qualified_client_import_count'],41)
        for key in ('target_executed','full_client_qualified','stdtime_qualified','provider_stubs','accepted_runtime_modified',
                    'target_multithreaded_fork_coordination_qualified'):self.assertIs(self.m[key],False)
        for name in ('_notify_cancel','_notify_monitor_file'):self.assertIn(name,self.m['target_missing_symbols'])

    def test_real_static_fourteen_api_owners_and_no_native_doubles(self):
        target=Path(self.m['target']);self.assertEqual(b.sha(target),self.m['target_sha256'])
        self.assertEqual(b.prepare_pid1.inspect(target.read_bytes()),self.m['static_inspection'])
        self.assertEqual(subprocess.check_output(['xcrun','nm','-ju',target],text=True),'')
        self.assertEqual(self.m['forced_apis'],list(b.FORCE));self.assertEqual(len(b.FORCE),14)
        owners=self.m['live_symbol_owners']
        for name in b.FORCE:self.assertTrue(owners[name].startswith(self.m['target_archive']+'('),name)
        for name in ('_os_unfair_lock_lock_with_options','_os_unfair_lock_unlock'):
            self.assertTrue(owners[name].endswith('/libapple-pthread-platform-scoped.a(platform-lock.o)'))
        self.assertEqual(owners['_reallocf'],str(b.FRAGMENTS)+'(target-reallocf.o)')
        self.assertTrue(owners['__NSGetEnviron'].endswith('/private-abi-runtime.a(14-darwin_static.o)'))
        self.assertNotRegex((PACKAGE/'contract.map').read_text(),r'fixture_|__asan|__ubsan')
        for c in self.m['commands']:
            if any(c['stdout'].endswith('/'+n+'-compile.stdout') for n in ('original-getenv','getenv','setenv','putenv')):
                self.assertIn('-mcpu=cortex-a76',c['command'])
                self.assertFalse(any('fixture_' in a or 'sanitize' in a for a in c['command']))

    def test_original_two_leaks_reproduced_cleanup_and_threaded_actual_family(self):
        cases=(('original-environment-host',['original-leaks'],0,b.ORIGINAL_EXPECTED),
               ('original-environment-host',[],32,''),('environment-host',[],0,b.EXPECTED),
               ('environment-host',['original-leaks'],32,''),('environment-host',['bad-expected'],37,''))
        for file,args,code,out in cases:
            r=subprocess.run([PACKAGE/file,*args],capture_output=True,text=True,timeout=20)
            self.assertEqual((r.returncode,r.stdout,r.stderr),(code,out,''))
        self.assertEqual(self.m['original_leaks_reproduced'],2)
        self.assertIs(self.m['native_environment_pointer_and_lock_are_test_doubles'],True)
        for c in self.m['commands']:
            if any(c['stdout'].endswith('/host-'+n+'-compile.stdout') for n in ('getenv','getenv-fixed','setenv','putenv')):
                self.assertIn('-Dos_unfair_lock_lock_with_options=fixture_lock',c['command'])
                self.assertIn('-D_NSGetEnviron=fixture_NSGetEnviron',c['command'])
                self.assertIn('-fsanitize=address,undefined',c['command'])


if __name__=='__main__':unittest.main()
