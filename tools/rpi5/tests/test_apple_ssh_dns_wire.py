# SPDX-License-Identifier: BSD-2-Clause
"""Original DNS wire units, exact bounded corrections, no network or target run."""
import copy
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_dns_wire as b
from tools.rpi5.tests.test_apple_pthread_startup_contract import validate_closure

PACKAGE=Path(os.environ['RPI5_DNS_WIRE_PACKAGE']).resolve() if os.environ.get('RPI5_DNS_WIRE_PACKAGE') else None
PIN=os.environ.get('RPI5_DNS_WIRE_MANIFEST_SHA256')

def closure(m):
    base=json.loads((b.BASE/'manifest.json').read_text())
    expected=b.merge({str(b.BASE/'manifest.json'):b.BASE_SHA},*[base[k] for k in ('source_inputs_sha256','headers_sha256','generated_sha256')])
    for path in (Path(b.__file__).resolve(),b.HARNESS,b.TEST,b.CLOSURE_TEST,b.prior.preceding.FLAGS,
                 b.ROOT/'tools/rpi5/prepare_pid1.py',*[b.SOURCE/n for n in b.UNITS]):expected[str(path)]=b.sha(path)
    tools={str(Path(subprocess.check_output(['xcrun','--find',n],text=True).strip()).resolve()):None for n in ('clang','ar','nm','ld','llvm-objdump')}
    tools[str(Path('/usr/bin/xcrun').resolve())]=None
    tools={n:b.sha(n) for n in tools};expected=b.merge(expected,tools)
    if m['tools_sha256']!=tools or m['source_inputs_sha256']!=expected:raise ValueError('Complete original/source/tool closure')
    labels={'host-caller'}|{prefix+Path(n).stem for prefix in ('original-','target-','host-') for n in b.UNITS}
    if set(m['dependency_records'])!=labels:raise ValueError('Complete compile membership')
    headers={}
    for label,row in m['dependency_records'].items():
        raw=(PACKAGE/(label+'.d')).read_text().replace('\\\n',' ').partition(':')[2]
        actual={str(Path(n).resolve()):b.sha(Path(n).resolve()) for n in shlex.split(raw)}
        if row!={'scanned_sha256':actual,'consumed_sha256':actual}:raise ValueError('Actual consumed header closure')
        headers.update(actual)
    if headers!=m['headers_sha256']:raise ValueError('Complete header union')
    validate_closure(PACKAGE,m)

def command_contract(m):
    flags_doc=json.loads(b.prior.preceding.FLAGS.read_text())
    template=next(c['command'] for c in flags_doc['commands'] if c['stdout'].endswith('/readpassphrase-compile.stdout'))
    target=template[:template.index('-MD')]+['-I',str(b.SOURCE)]
    native=[n for n in target if n not in ('-ffreestanding','-mcpu=cortex-a76')]
    at=native.index('-target');del native[at:at+2]
    native+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=undefined']
    rows={}
    for row in m['commands']:
        label=Path(row['stdout']).name.removesuffix('.stdout')
        if label in rows or row['cwd']!=str(b.ROOT) or row['stdout']!=str(PACKAGE/(label+'.stdout')) or row['stderr']!=str(PACKAGE/(label+'.stderr')):
            raise ValueError('Exact command identity/cwd/output required')
        rows[label]=row
    expected={'host-caller':(native,b.HARNESS)}
    for name in b.UNITS:
        expected['original-'+Path(name).stem]=(native,b.SOURCE/name)
        expected['target-'+Path(name).stem]=(target,PACKAGE/'overlay'/name)
        expected['host-'+Path(name).stem]=(native,PACKAGE/'overlay'/name)
    for label,(flags,path) in expected.items():
        for suffix,args in (('-scan',[*flags,'-M',str(path)]),
                ('-compile',[*flags,'-MD','-MF',str(PACKAGE/(label+'.d')),'-c',str(path),'-o',str(PACKAGE/(label+'.o'))])):
            if rows[label+suffix]['command']!=args or rows[label+suffix]['returncode']!=0:
                raise ValueError('Exact original compiler flags/units required')
    actual_compile={n for n in rows if n.endswith(('-compile','-scan'))}
    if actual_compile!={n+s for n in expected for s in ('-compile','-scan')}:
        raise ValueError('No missing/extra compile unit')
    directory=json.loads((b.prior.BASE/'manifest.json').read_text())
    contract=list(next(c['command'] for c in directory['commands'] if c['stdout'].endswith('/contract-link.stdout')))
    contract[contract.index('-o')+1]=str(PACKAGE/'NOT_RUN_dns_contract')
    contract[contract.index('-map')+1]=str(PACKAGE/'contract.map')
    contract += [m['target_archive']]+[value for symbol in m['forced_apis'] for value in ('-u',symbol)]
    if rows['contract-link']['command']!=contract or rows['contract-link']['returncode']!=0:
        raise ValueError('Exact genuine forced static link required')

class AppleDNSWireTests(unittest.TestCase):
    def setUp(self):
        if PACKAGE is None or PIN is None:self.fail('Supply retained RPI5_DNS_WIRE_PACKAGE and RPI5_DNS_WIRE_MANIFEST_SHA256')
        self.assertEqual(b.sha(PACKAGE/'manifest.json'),PIN)
        self.m=json.loads((PACKAGE/'manifest.json').read_text())

    def test_actual_source_header_generated_membership_and_omissions(self):
        closure(self.m)
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256','tools_sha256','dependency_records'):
            bad=copy.deepcopy(self.m);bad[key].pop(next(iter(bad[key])))
            with self.subTest(key=key),self.assertRaises(ValueError):closure(bad)

    def test_whole_original_units_minimal_derivation_and_actual_a76(self):
        for name in b.UNITS:
            raw=(b.SOURCE/name).read_bytes()
            self.assertEqual(raw,subprocess.check_output(['git','-C',b.SOURCE,'show',b.COMMIT+':'+name]))
            self.assertEqual((PACKAGE/'overlay'/name).read_text(),b.checked(name,raw.decode()))
            if name in ('ns_parse.c','ns_netint.c'):self.assertEqual((PACKAGE/'overlay'/name).read_bytes(),raw)
            command=next(c['command'] for c in self.m['commands'] if c['stdout'].endswith('/target-'+Path(name).stem+'-compile.stdout'))
            self.assertIn('-mcpu=cortex-a76',command)
            self.assertFalse(any('fixture_' in a or 'sanitize' in a for a in command))
        self.assertEqual(self.m['derived_units'],['res_comp.c','ns_name.c'])
        self.assertTrue(self.m['whole_translation_units'])

    def test_exact_compiler_and_forced_link_commands_with_negatives(self):
        command_contract(self.m)
        for label in ('target-res_comp-compile','host-ns_name-compile','contract-link'):
            bad=copy.deepcopy(self.m)
            row=next(c for c in bad['commands'] if c['stdout'].endswith('/'+label+'.stdout'))
            row['command'].append('-DFAKE_PROVIDER=1')
            with self.subTest(label=label),self.assertRaises(ValueError):command_contract(bad)
        bad=copy.deepcopy(self.m);bad['commands'][0]['cwd']='/tmp'
        with self.assertRaises(ValueError):command_contract(bad)

    def test_exact_full_client_link_delta_and_no_new_dependencies(self):
        base=json.loads((b.BASE/'manifest.json').read_text())
        expected=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
        self.assertEqual(self.m['original_full_client_link_command'],expected)
        expected[expected.index('-o')+1]=str(PACKAGE/'NOT_RUN_ssh');expected[expected.index('-map')+1]=str(PACKAGE/'target.map')
        expected.append(self.m['target_archive'])
        actual=next(c for c in self.m['commands'] if c['stdout'].endswith('/target-link.stdout'))
        self.assertEqual(actual['command'],expected);self.assertNotEqual(actual['returncode'],0)
        missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',Path(actual['stderr']).read_text(),re.M)))
        self.assertEqual(missing,self.m['target_missing_symbols']);self.assertEqual(len(missing),39)
        self.assertEqual(set(base['target_missing_symbols'])-set(missing),{'_res_9_dn_expand'})
        self.assertEqual(set(missing)-set(base['target_missing_symbols']),set())
        self.assertEqual(self.m['target_duplicate_symbols'],[])
        for key in ('network_operations','resolver_transport_qualified','resolver_service_qualified','full_client_qualified',
                    'target_executed','private_FILE_abi_mixed','accepted_runtime_modified','provider_stubs'):
            self.assertIs(self.m[key],False)

    def test_forced_actual_target_all_apis_real_owners_and_no_imports(self):
        target=PACKAGE/'NOT_RUN_dns_contract'
        self.assertEqual(subprocess.check_output(['xcrun','nm','-ju',target],text=True),'')
        self.assertEqual(b.prepare_pid1.inspect(target.read_bytes()),self.m['static_inspection'])
        exported=[]
        for name in b.UNITS:exported+=subprocess.check_output(['xcrun','nm','-gjU',PACKAGE/('target-'+Path(name).stem+'.o')],text=True).splitlines()
        self.assertEqual(sorted(set(exported)),self.m['forced_apis'])
        self.assertEqual(len(exported),len(set(exported)))
        for name in exported:self.assertTrue(self.m['live_symbol_owners'][name].startswith(self.m['target_archive']+'('))
        self.assertEqual(self.m['live_symbol_owners']['___error'],str(b.ROOT/'build/rpi5/apple-pthread-static-complete-gm82fjkz/private-abi-runtime.a')+'(2-errno.o)')

    def test_original_failures_retained_and_checked_native_oracles(self):
        for case in b.BOUNDARIES:
            record=self.m['original_boundary_failures'][case]
            self.assertNotEqual(record['returncode'],0)
            if case=='short-extended-unpack':
                self.assertTrue(record['sanitizer_heap_read'])
                self.assertIn('AddressSanitizer: heap-buffer-overflow',(PACKAGE/('original-'+case+'.stderr')).read_text())
            elif case=='negative-expand':
                self.assertTrue(record['sanitizer_pointer_overflow'])
                stderr=(PACKAGE/('original-'+case+'.stderr')).read_text()
                self.assertIn('runtime error: addition of unsigned offset',stderr)
                self.assertIn('UndefinedBehaviorSanitizer: undefined-behavior',stderr)
            else:self.assertEqual(record['stdout'],'APPLE_DNS_BOUNDARY '+case+' SAFE=0\n')
            r=subprocess.run([PACKAGE/'dns-host',case],capture_output=True,text=True,timeout=10)
            self.assertEqual((r.returncode,r.stdout,r.stderr),(0,'APPLE_DNS_BOUNDARY '+case+' SAFE=1\n',''))
        r=subprocess.run([PACKAGE/'dns-host'],capture_output=True,text=True,timeout=20)
        self.assertEqual((r.returncode,r.stdout,r.stderr),(0,self.m['native_stdout'],''))
        r=subprocess.run([PACKAGE/'dns-host','bad-expectation'],capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,37)

if __name__=='__main__':unittest.main()
