# SPDX-License-Identifier: BSD-2-Clause
"""Public Apple OpenSSH asprintf provider; full client remains incomplete."""
import copy
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_asprintf as b
from tools.rpi5.tests.test_apple_pthread_startup_contract import validate_closure

PACKAGE=Path(os.environ['RPI5_ASPRINTF_PACKAGE']).resolve() if os.environ.get('RPI5_ASPRINTF_PACKAGE') else None
PIN=os.environ.get('RPI5_ASPRINTF_MANIFEST_SHA256')


def closure(m):
    base=json.loads((b.BASE/'manifest.json').read_text())
    expected=b.merge({str(b.BASE/'manifest.json'):b.BASE_SHA},
        *[base[k] for k in ('source_inputs_sha256','headers_sha256','generated_sha256')])
    for path in (Path(b.__file__).resolve(),b.SOURCE,b.ANNOTATIONS,b.HARNESS,b.TEST,b.CLOSURE_TEST,
                 b.prior.prior.preceding.FLAGS,b.ROOT/'tools/rpi5/prepare_pid1.py'):
        expected[str(path)]=b.sha(path)
    tools={str(Path(subprocess.check_output(['xcrun','--find',n],text=True).strip()).resolve()):None
           for n in ('clang','ar','nm','ld','llvm-objdump')}
    tools[str(Path('/usr/bin/xcrun').resolve())]=None;tools={n:b.sha(n) for n in tools}
    expected=b.merge(expected,tools)
    if m['tools_sha256']!=tools or m['source_inputs_sha256']!=expected:raise ValueError('Complete source/tool closure')
    if set(m['dependency_records'])!={'target-asprintf','host-asprintf','host-caller'}:raise ValueError('Complete compile membership')
    headers={}
    for label,row in m['dependency_records'].items():
        raw=(PACKAGE/(label+'.d')).read_text().replace('\\\n',' ').partition(':')[2]
        actual={str(Path(n).resolve()):b.sha(Path(n).resolve()) for n in shlex.split(raw)}
        if row!={'scanned_sha256':actual,'consumed_sha256':actual}:raise ValueError('Actual compiler dependency closure')
        headers.update(actual)
    if headers!=m['headers_sha256']:raise ValueError('Complete header union')
    validate_closure(PACKAGE,m)


class AppleOpenSSHAsprintfTests(unittest.TestCase):
    def setUp(self):
        if PACKAGE is None or PIN is None:self.fail('Supply retained package and manifest pin')
        self.assertEqual(b.sha(PACKAGE/'manifest.json'),PIN)
        self.m=json.loads((PACKAGE/'manifest.json').read_text())

    def test_exact_source_header_generated_membership(self):
        closure(self.m)
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256','tools_sha256'):
            bad=copy.deepcopy(self.m);bad[key].pop(next(iter(bad[key])))
            with self.subTest(key=key),self.assertRaises(ValueError):closure(bad)

    def test_exact_public_source_and_provider_only_configuration(self):
        raw=subprocess.check_output(['git','-C',b.OPENSSH,'show',b.COMMIT+':openssh/openbsd-compat/bsd-asprintf.c'])
        self.assertEqual(b.SOURCE.read_bytes(),raw)
        self.assertEqual(self.m['exported_apis'],['_asprintf','_vasprintf'])
        self.assertTrue(self.m['provider_selection_only']);self.assertTrue(self.m['global_openssh_config_unchanged'])
        command=next(c['command'] for c in self.m['commands'] if c['stdout'].endswith('/target-asprintf-compile.stdout'))
        self.assertIn('-mcpu=cortex-a76',command);self.assertIn('-DRPI5_APPLE_ASPRINTF=1',command)
        self.assertIn(str(b.ANNOTATIONS),command);self.assertNotIn('-fsanitize=address,undefined',command)

    def test_exact_full_client_delta_no_new_imports(self):
        base=json.loads((b.BASE/'manifest.json').read_text())
        expected=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
        self.assertEqual(self.m['original_full_client_link_command'],expected)
        expected[expected.index('-o')+1]=str(PACKAGE/'NOT_RUN_ssh');expected[expected.index('-map')+1]=str(PACKAGE/'target.map')
        expected.append(self.m['target_archive'])
        actual=next(c for c in self.m['commands'] if c['stdout'].endswith('/target-link.stdout'))
        self.assertEqual(actual['command'],expected);self.assertNotEqual(actual['returncode'],0)
        missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',Path(actual['stderr']).read_text(),re.M)))
        self.assertEqual(missing,self.m['target_missing_symbols']);self.assertEqual(len(missing),37)
        self.assertEqual(set(base['target_missing_symbols'])-set(missing),{'_asprintf','_vasprintf'})
        self.assertEqual(set(missing)-set(base['target_missing_symbols']),set());self.assertEqual(self.m['target_duplicate_symbols'],[])

    def test_forced_target_and_native_oracles(self):
        target=PACKAGE/'NOT_RUN_asprintf_contract'
        self.assertEqual(subprocess.check_output(['xcrun','nm','-ju',target],text=True),'')
        self.assertEqual(b.prior.prepare_pid1.inspect(target.read_bytes()),self.m['static_inspection'])
        for name in self.m['exported_apis']:
            self.assertTrue(self.m['live_symbol_owners'][name].startswith(self.m['target_archive']+'('))
        proc=subprocess.run([PACKAGE/'asprintf-host'],capture_output=True,text=True,timeout=20)
        self.assertEqual((proc.returncode,proc.stdout,proc.stderr),(0,self.m['native_stdout'],''))
        proc=subprocess.run([PACKAGE/'asprintf-host','bad'],capture_output=True,text=True,timeout=20)
        self.assertEqual(proc.returncode,37)
        for key in ('accepted_runtime_modified','provider_stubs','optional_features_removed','target_executed','full_client_qualified'):
            self.assertIs(self.m[key],False)


if __name__=='__main__':unittest.main()
