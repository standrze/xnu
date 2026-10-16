# SPDX-License-Identifier: BSD-2-Clause
"""Actual whole-current daemon/setsid evidence; no target binary is executed."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_daemon as b
from tools.rpi5.tests.test_apple_pthread_startup_contract import validate_closure

# Both external pins are mandatory: tests are themselves in the source closure,
# so embedding their own resulting manifest hash would be a circular receipt.
_package=os.environ.get('RPI5_APPLE_DAEMON_PACKAGE')
PACKAGE=Path(_package).resolve() if _package else None
PIN=os.environ.get('RPI5_APPLE_DAEMON_MANIFEST_SHA256')


def source_members(m):
    base=json.loads((b.BASE/'manifest.json').read_text())
    expected={str(b.BASE/'manifest.json'):b.BASE_SHA,str(Path(b.__file__).resolve()):b.sha(b.__file__),
              str(b.SOURCE):b.sha(b.SOURCE),str(b.HARNESS):b.sha(b.HARNESS),str(b.TEST):b.sha(b.TEST),
              str(b.TRAP):b.sha(b.TRAP),str(b.MASTER):b.sha(b.MASTER)}
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
        for name,digest in base[key].items():
            if name in expected and expected[name]!=digest:raise ValueError('Inherited pin conflict')
            expected[name]=digest
    paths={str(Path(subprocess.check_output(['xcrun','--find',n],text=True).strip()).resolve())
           for n in ('clang','ar','nm','ld','llvm-objdump')}
    paths.add(str(Path('/usr/bin/xcrun').resolve()))
    tools={n:b.sha(n) for n in paths}
    if m['tools_sha256']!=tools:raise ValueError('Tool membership differs')
    expected.update(tools)
    if expected!=m['source_inputs_sha256']:raise ValueError('Source membership differs')
    if set(m['dependency_records'])!={'target-daemon','host-daemon','host-caller','setsid'}:
        raise ValueError('Exact consumed compile record set required')
    for label,row in m['dependency_records'].items():
        if not isinstance(row,dict) or set(row)!={'scanned_sha256','consumed_sha256'} or row['scanned_sha256']!=row['consumed_sha256']:
            raise ValueError('Exact actual scan/consume record required')
        raw=(PACKAGE/(label+'.d')).read_text().replace('\\\n',' ').partition(':')[2]
        import shlex
        actual={str(Path(n).resolve()):b.sha(Path(n).resolve()) for n in shlex.split(raw)}
        if row['consumed_sha256']!=actual:raise ValueError('Actual compile dependencies differ')


class AppleDaemonTests(unittest.TestCase):
    def setUp(self):
        if PACKAGE is None or PIN is None or not re.fullmatch('[0-9a-f]{64}',PIN):
            self.fail('Supply RPI5_APPLE_DAEMON_PACKAGE and RPI5_APPLE_DAEMON_MANIFEST_SHA256 from the retained build receipt')
        self.assertEqual(PACKAGE.parent,b.ROOT/'build/rpi5')
        self.assertTrue(PACKAGE.name.startswith('apple-ssh-daemon-'))
        self.assertEqual(b.sha(PACKAGE/'manifest.json'),PIN)
        self.m=json.loads((PACKAGE/'manifest.json').read_text())

    def test_source_and_actual_dependency_closure_with_mutation_negatives(self):
        source_members(self.m);validate_closure(PACKAGE,self.m)
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256','tools_sha256','dependency_records'):
            for mutation in ('omit','wrong'):
                m=copy.deepcopy(self.m);name=next(iter(m[key]))
                if mutation=='omit':m[key].pop(name)
                else:m[key][name]='0'*64
                with self.subTest(group=key,mutation=mutation),self.assertRaises((ValueError,TypeError)):
                    source_members(m);validate_closure(PACKAGE,m)
        for row in self.m['dependency_records'].values():
            self.assertEqual(row['scanned_sha256'],row['consumed_sha256'])

    def test_whole_current_tu_and_normal_bootstrap_feature_remain(self):
        self.assertEqual(b.SOURCE.read_bytes(),subprocess.check_output(['git','-C',b.LIBC,'show',b.LIBC_COMMIT+':gen/FreeBSD/daemon.c']))
        rows={Path(r['stdout']).name:r['command'] for r in self.m['commands']}
        flags=rows['target-daemon-compile.stdout'];self.assertIn('-mcpu=cortex-a76',flags)
        self.assertIn(str(b.SOURCE),flags)
        self.assertFalse(any('VARIANT_PRE1050' in n or 'fixture_' in n or 'sanitize' in n for n in flags))
        original=json.loads(b.preceding.FLAGS.read_text())
        template=next(r['command'] for r in original['commands'] if r['stdout'].endswith('/readpassphrase-compile.stdout'))
        self.assertEqual(flags[:flags.index('-MD')],template[:template.index('-MD')])
        undefined=subprocess.check_output(['xcrun','nm','-ju',self.m['target_object']],text=True).splitlines()
        self.assertEqual(undefined,self.m['target_object_imports'])
        self.assertTrue({'_bootstrap_parent','_bootstrap_port','_task_set_special_port','_mach_port_deallocate'}<=set(undefined))

    def test_full176_client_exact_link_and_honest_import_delta(self):
        base=json.loads((b.BASE/'manifest.json').read_text())
        expected=list(next(r['command'] for r in base['commands'] if r['stdout'].endswith('/target-link.stdout')))
        self.assertEqual(self.m['original_full_client_link_command'],expected)
        expected[expected.index('-o')+1]=str(PACKAGE/'NOT_RUN_ssh')
        expected[expected.index('-map')+1]=str(PACKAGE/'target.map');expected.append(self.m['target_archive'])
        row=next(r for r in self.m['commands'] if r['stdout'].endswith('/target-link.stdout'))
        self.assertEqual(expected,row['command']);self.assertNotEqual(row['returncode'],0)
        imports=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',Path(row['stderr']).read_text(),re.M)))
        self.assertEqual(imports,self.m['target_missing_symbols']);self.assertEqual(len(imports),40)
        self.assertEqual(set(base['target_missing_symbols'])-set(imports),{'_daemon'})
        self.assertEqual(set(imports)-set(base['target_missing_symbols']),{'_bootstrap_parent'})
        self.assertEqual(self.m['target_duplicate_symbols'],[])
        self.assertEqual(self.m['previous_provider_groups'],b.categories(base['target_missing_symbols']))
        self.assertEqual(self.m['remaining_provider_groups'],b.categories(imports))
        client=json.loads(b.preceding.CLIENT.read_text())
        self.assertEqual(len([r for r in client['commands'] if re.search(r'/\d{3}-.*-compile.stdout$',r['stdout'])]),176)
        for key in ('accepted_runtime_modified','provider_stubs','full_client_qualified','target_executed',
                    'target_daemon_executed','target_bootstrap_service_available','target_process_creation_qualified','target_setsid_executed'):
            self.assertIs(self.m[key],False)
        self.assertFalse((PACKAGE/'NOT_RUN_ssh').exists())

    def test_actual_a76_setsid_original_trap_and_native176_oracle(self):
        self.assertRegex(b.MASTER.read_text(),r'(?m)^147\s+[^\n]*int setsid\(void\);')
        self.assertIn('SYSCALL_NONAME(setsid, 0, cerror_nocancel)',b.TRAP.read_text())
        dis=(PACKAGE/'setsid-disassembly.stdout').read_text()
        self.assertEqual(dis.count('svc\t#0x80'),1);self.assertIn('mov\tx16, #0x93',dis)
        self.assertEqual(subprocess.check_output(['xcrun','nm','-ju',self.m['target_setsid_object']],text=True),'_cerror_nocancel\n')
        for args,code in (([],0),(['bad-expectation'],37)):
            r=subprocess.run([PACKAGE/'daemon-host',*args],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,code,r.stderr)
            if not args:self.assertEqual((r.stdout,r.stderr),(b.EXPECTED,''))
            else:self.assertIn('case 1',r.stderr)
        spies=subprocess.check_output(['xcrun','nm','-ju',PACKAGE/'host-daemon.o'],text=True).splitlines()
        for name in ('_fork','_setsid','_chdir','_bootstrap_parent','_task_set_special_port','_sigaction','__exit'):
            self.assertNotIn(name,spies)
        for name in ('_fixture_fork','_fixture_setsid','_fixture_bootstrap_parent','_fixture_task_set_special_port',
                     '_fixture_open$NOCANCEL','_fixture_close$NOCANCEL'):
            self.assertIn(name,spies)


if __name__=='__main__':unittest.main()
