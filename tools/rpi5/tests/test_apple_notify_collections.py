# SPDX-License-Identifier: BSD-2-Clause
"""Original map/set prerequisite only: no notify/SSH or target execution claim."""
import copy
import json
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5 import build_apple_notify_collections as b
from tools.rpi5.tests.test_apple_pthread_startup_contract import validate_closure

PACKAGE=b.ROOT/'build/rpi5/apple-notify-collections-20uzs24a'
PIN='cb494ba7e766967f309e7365198c9036b7ea8b3b7ad441c58e8a3fc016296793'


def source_members(m):
    expected={str(b.BASE/'manifest.json'):b.BASE_SHA,str(b.BLOCKS/'manifest.json'):b.BLOCKS_SHA,
        str(Path(b.__file__).resolve()):b.sha(b.__file__),str(b.HARNESS):b.sha(b.HARNESS)}
    for folder in (b.BASE,b.BLOCKS):
        prior=json.loads((folder/'manifest.json').read_text())
        for group in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for n,h in prior[group].items():
                if n in expected and expected[n]!=h:raise ValueError('Source conflict')
                expected[n]=h
    for path in (b.LIBC/'collections').rglob('*'):
        if path.is_file():expected[str(path)]=b.sha(path)
    if expected!=m['source_inputs_sha256']:raise ValueError('Exact original source membership differs')


class NotifyCollectionsTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(b.sha(PACKAGE/'manifest.json'),PIN)
        self.m=json.loads((PACKAGE/'manifest.json').read_text())

    def test_complete_source_header_generated_closure_and_negatives(self):
        source_members(self.m);validate_closure(PACKAGE,self.m)
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for action in ('omit','wrong'):
                bad=copy.deepcopy(self.m);name=next(iter(bad[key]))
                if action=='omit':bad[key].pop(name)
                else:bad[key][name]='0'*64
                with self.subTest(key=key,action=action),self.assertRaises(ValueError):
                    source_members(bad);validate_closure(PACKAGE,bad)
        for path in (b.LIBC/'collections/PublicHeader').iterdir():
            self.assertEqual(path.read_bytes(),(PACKAGE/'include/os'/path.name).read_bytes())
        for record in self.m['dependency_records'].values():
            self.assertEqual(record['scanned_sha256'],record['consumed_sha256'])

    def test_whole_current_units_actual_a76_commands_and_native_separation(self):
        self.assertEqual(self.m['whole_original_units'],list(b.UNITS))
        for name in b.UNITS:
            label='target-'+Path(name).stem
            command=next(c['command'] for c in self.m['commands'] if c['stdout'].endswith('/'+label+'-compile.stdout'))
            self.assertIn(str(b.LIBC/'collections/Source'/name),command)
            self.assertIn('-mcpu=cortex-a76',command);self.assertIn('-fblocks',command)
            self.assertFalse(any('fixture_' in x or 'sanitize' in x or 'NDEBUG' in x for x in command))
            actual=self.m['dependency_records'][label]['consumed_sha256']
            self.assertIn(str(b.LIBC/'collections/Source/collections_common.in.c'),actual)
            self.assertIn(str(b.ROOT/'libkern/os/base_private.h'),actual)
            self.assertIn(str(PACKAGE/'include/os'/('collections_map.h' if name=='collections_map.c' else 'collections_set.h')),actual)
        for flag in ('original_source_modified','accepted_runtime_modified','target_executed',
                     'notification_api_provider_created','notification_service_executed','full_client_qualified'):
            self.assertIs(self.m[flag],False)
        self.assertIs(self.m['collections_require_external_serialization'],True)

    def test_57_actual_live_static_owners_and_no_imports_or_fixture(self):
        target=Path(self.m['target']);self.assertEqual(b.sha(target),self.m['target_sha256'])
        self.assertEqual(b.prepare_pid1.inspect(target.read_bytes()),self.m['static_inspection'])
        self.assertEqual(subprocess.check_output(['xcrun','nm','-ju',target],text=True),'')
        self.assertEqual(self.m['forced_apis'],list(b.FORCE));self.assertEqual(len(b.FORCE),57)
        owners=self.m['live_symbol_owners']
        for name in b.FORCE:
            member='target-collections_map.o' if name.startswith('_os_map_') else 'target-collections_set.o'
            self.assertEqual(owners[name],self.m['target_archive']+'('+member+')')
        self.assertEqual(owners['__NSConcreteStackBlock'],str(b.BLOCKS/'libapple-blocks-runtime.a')+'(target-data.o)')
        for name in ('_calloc','_free'):
            self.assertEqual(owners[name],str(b.BASE/'private-apple-runtime-current-environment.a')+'(glue-allocator.o)')
        self.assertNotRegex((PACKAGE/'contract.map').read_text(),r'fixture_|__asan|__ubsan')
        self.assertEqual(owners['___assert_rtn'],str(b.BASE/'private-apple-runtime-current-environment.a')+'(glue-adapters.o)')

    def test_exact_full_client_no_delta_not_a_notify_provider(self):
        prior=json.loads((b.BASE/'manifest.json').read_text())
        command=list(next(c['command'] for c in prior['commands'] if c['stdout'].endswith('/target-link.stdout')))
        command[command.index('-o')+1]=str(PACKAGE/'NOT_RUN_ssh')
        command[command.index('-map')+1]=str(PACKAGE/'target.map');command.append(self.m['target_archive'])
        actual=next(c for c in self.m['commands'] if c['stdout'].endswith('/target-link.stdout'))
        self.assertEqual(command,actual['command']);self.assertNotEqual(actual['returncode'],0)
        missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',Path(actual['stderr']).read_text(),re.M)))
        self.assertEqual(missing,self.m['target_missing_symbols']);self.assertEqual(missing,prior['target_missing_symbols'])
        self.assertEqual(len(missing),42);self.assertEqual(self.m['prior_qualified_client_import_count'],41)
        self.assertEqual(self.m['closed_symbols'],[]);self.assertEqual(self.m['newly_reachable_symbols'],[])
        self.assertEqual(self.m['target_duplicate_symbols'],[])
        self.assertIn('_notify_monitor_file',missing);self.assertIn('_notify_register_check',missing)

    def test_actual_native_whole_collections_with_original_blocks_and_fatal_allocation(self):
        for args,code,output in (([],0,b.EXPECTED),(['bad-oracle'],37,'')):
            result=subprocess.run([PACKAGE/'collections-host',*args],capture_output=True,text=True,timeout=30)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(code,output,''))
        command=next(c['command'] for c in self.m['commands'] if c['stdout'].endswith('/host-link.stdout'))
        for name in ('native-runtime.o','native-data.o'):self.assertIn(str(b.BLOCKS/name),command)
        mapping=(PACKAGE/'host.map').read_text()
        for name in ('host-collections_map.o','host-collections_set.o'):self.assertIn(str(PACKAGE/name),mapping)
        for c in self.m['commands']:
            if c['stdout'].endswith(('/host-collections_map-compile.stdout','/host-collections_set-compile.stdout')):
                self.assertIn('-Dcalloc=fixture_calloc',c['command']);self.assertIn('-fsanitize=address,undefined',c['command'])


if __name__=='__main__':unittest.main()
