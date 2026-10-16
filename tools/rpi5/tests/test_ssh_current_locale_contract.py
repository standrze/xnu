#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Whole current locale providers, explicit owners and honest runtime limits."""
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_locale_slice as base
from tools.rpi5 import check_apple_pthread_kernel_contract as macho
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

GROUP=base.ROOT/'build/rpi5/apple-ssh-locale-slice-p7_8ertv'
OWNER=base.ROOT/'build/rpi5/apple-ssh-current-locale-ebd652yw'
CONTRACT=base.ROOT/'build/rpi5/apple-ssh-current-locale-contract-ni1pfpjw'
PINS={GROUP:'a6411a2990ba6abea004cd17363bb57a7d89559c4703a00d6d923d5facc43fc6',
      OWNER:'4c722fcbab48d012865d2071953cf3994d27e1220a8eacddac7adf23c0fd0395',
      CONTRACT:'c45e4a7c3f672003dfa1b6afdb97b6c370153902a487ac0230457251b5da5c6b'}


def owner_of(text,symbol):
    owners={int(n):p for n,p in re.findall(r'^\[\s*(\d+)\]\s+(.+)$',text,re.M)}
    found=re.findall(r'^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+'+
                     re.escape(symbol)+r'$',text,re.M)
    if len(found)!=1:raise ValueError('Missing/duplicate live owner: '+symbol)
    return owners[int(found[0])]


def validate_members(report):
    expected={'locale-'+n+'.o' for n in
              ('table','tolower','toupper','none','nomacros','lconv','localeconv','runetype')}
    if set(report['removed_legacy_locale_members'])!=expected:raise ValueError('Wrong replaced owner set')
    before,after=report['before_members_sha256'],report['after_members_sha256']
    if set(before)-set(after)!=expected or set(after)-set(before):raise ValueError('Wrong archive membership')
    if any(before[n]!=h for n,h in after.items()):raise ValueError('Unrelated object changed')


class CurrentLocaleContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reports={}
        for path,digest in PINS.items():
            if base.sha(path/'manifest.json')!=digest:raise ValueError('Frozen locale evidence changed')
            reports[path]=json.loads((path/'manifest.json').read_text())
        cls.group,cls.owner,cls.contract=reports[GROUP],reports[OWNER],reports[CONTRACT]

    def test_original_38_units_actual_headers_generated_and_negative(self):
        for report in (self.group,self.owner,self.contract):
            for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
                for name,digest in report[key].items():self.assertEqual(base.sha(name),digest,name)
        for report in (self.group,self.contract):
            actual_dependencies(report)
            omitted=copy.deepcopy(report)
            omitted['headers_sha256'].pop(next(iter(omitted['headers_sha256'])))
            with self.assertRaises(ValueError):actual_dependencies(omitted)
        self.assertEqual(len(self.group['original_units']),38)
        self.assertEqual(self.group['compile_failures'],{})
        for name in self.group['original_units']:
            self.assertEqual((base.LIBC/name).read_bytes(),subprocess.check_output(
                ['git','-C',base.LIBC,'show','71bbe350ab79eef58113991d817ccc6165061a64:'+name]))
        self.assertEqual(len(self.group['dependency_records']),39)
        self.assertEqual(len(self.contract['dependency_records']),39)
        self.assertFalse(self.group['provider_stubs'])

    def test_exact_eight_archive_replacements_preserve_all_other_bytes(self):
        validate_members(self.owner)
        for mutate in ('missing','restored-old','changed-unrelated'):
            bad=copy.deepcopy(self.owner)
            if mutate=='missing':bad['removed_legacy_locale_members'].pop()
            elif mutate=='restored-old':bad['after_members_sha256']['locale-runetype.o']=bad['before_members_sha256']['locale-runetype.o']
            else:bad['after_members_sha256'][next(iter(bad['after_members_sha256']))]='0'*64
            with self.assertRaises(ValueError):validate_members(bad)
        archive=self.owner['runtime_archive']
        actual=subprocess.check_output(['xcrun','ar','t',archive],text=True).splitlines()
        self.assertEqual(actual.count('__.SYMDEF SORTED'),1)
        self.assertEqual(set(actual)-{'__.SYMDEF SORTED'},set(self.owner['after_members_sha256']))
        # Actual bytes, not just declared before/after hashes, for every kept member.
        for name,digest in self.owner['after_members_sha256'].items():
            self.assertEqual(hashlib.sha256(subprocess.check_output(['xcrun','ar','p',archive,name])).hexdigest(),digest,name)
        self.assertNotEqual(archive,self.owner['original_runtime_archive'])

    def test_real_static_target_live_current_owners_and_tsd_startup(self):
        self.assertTrue(self.contract['target_link_complete'])
        self.assertEqual(self.contract['target_missing_symbols'],[])
        self.assertEqual(self.contract['target_duplicate_symbols'],[])
        self.assertEqual((CONTRACT/'target-undefined.stdout').read_text(),'')
        table=(CONTRACT/'target.map').read_text()
        for symbol,unit in {'_strtoll':'strtoll','_uselocale':'xlocale','___xlocale_init':'xlocale',
                            '__DefaultRuneLocale':'table','__DefaultRuneXLocale':'table',
                            '____runetype':'runetype','_mbtowc':'mbtowc','_wcwidth':'wcwidth',
                            '_tolower':'isctype','_toupper':'isctype'}.items():
            self.assertTrue(owner_of(table,symbol).endswith('(target-'+unit+'.o)'),symbol)
        for name in ('isalnum','isalpha','isblank','iscntrl','isdigit','isgraph','islower',
                     'isprint','ispunct','isspace','isupper','isxdigit'):
            self.assertTrue(owner_of(table,'_'+name).endswith('(target-isctype.o)'),name)
        for member in self.owner['removed_legacy_locale_members']:
            self.assertNotIn('('+member+')',table)
        generated=Path(self.group['startup_replacement_source']).read_text()
        self.assertEqual(generated,base.startup_source((base.ROOT/'tools/rpi5/user/pthread_static_start.c').read_text()))
        dis=(CONTRACT/'target-disassembly.stdout').read_text()
        start=dis.split('<_darwin_static_start>:',1)[1].split('\n000000',1)[0]
        calls=['<___libkernel_init>','<___pthread_init>','<___xlocale_init>','<_malloc>',
               '<___pthread_late_init>','<_rpi5_run_initializers>','<_rpi5_pthread_smoke_main>']
        positions=[start.index(call) for call in calls]
        self.assertEqual(positions,sorted(positions))
        image=macho.MachO(self.contract['target'])
        self.assertEqual(image.at(image.names['___locale_key']['address'],8),b'\xff'*8)
        init=dis.split('<___xlocale_init>:',1)[1].split('\n000000',1)[0]
        self.assertIn('#0xa',init);self.assertIn('<_pthread_key_init_np>',init)
        self.assertTrue(owner_of(table,'_pthread_key_init_np').endswith('(pthread-pthread_tsd.o)'))

    def test_native_all_current_providers_and_real_thread_contract(self):
        table=(CONTRACT/'native.map').read_text()
        for name,unit in {'_fixture_isalpha':'isctype','_wcwidth':'wcwidth',
                          '_fixture_mbtowc':'mbtowc','_fixture_setlocale':'setlocale',
                          '_fixture_nl_langinfo':'nl_langinfo','_fixture_localeconv':'localeconv'}.items():
            self.assertTrue(owner_of(table,name).endswith('/native-'+unit+'.o'),name)
        for args,expected in (([],0),(['bad-expected'],11),(['bad-api'],31)):
            result=subprocess.run([CONTRACT/'current-locale-host',*args],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,expected,result.stderr);self.assertEqual(result.stderr,'')
            if not args:self.assertEqual(result.stdout,self.contract['host_stdout'])
            if args==['bad-expected']:self.assertEqual(result.stdout,'')
        self.assertEqual(self.contract['original_unit_count'],38)
        self.assertTrue(self.contract['native_asan_ubsan_pass'])
        self.assertFalse(self.contract['target_executed'])
        self.assertFalse(self.contract['target_locale_runtime_executed'])
        self.assertFalse(self.contract['non_c_locale_files_tested'])

    def test_full_client_actual_delta_and_remaining_gaps_not_fake_success(self):
        self.assertEqual(len(self.group['closed_symbols']),17)
        self.assertEqual(self.group['newly_reachable_dependencies'],
                         ['__os_crash','_open$NOCANCEL','_read$NOCANCEL','_reallocf'])
        self.assertEqual(len(self.owner['target_missing_symbols']),89)
        self.assertEqual(self.owner['newly_reachable_dependencies'],[])
        self.assertFalse(self.owner['target_link_complete'])
        self.assertFalse(self.owner['target_executed'])
        self.assertFalse(self.group['full_current_libc_initialized'])
        link=next(c['command'] for c in self.owner['commands'] if c['stdout'].endswith('/target-link.stdout'))
        for path in (self.owner['runtime_archive'],self.owner['startup_replacement_object'],self.owner['target_archive']):
            self.assertEqual(link.count(path),1)
        self.assertNotIn(self.owner['original_runtime_archive'],link)
        self.assertNotIn(str(base.START/'startup.o'),link)


if __name__=='__main__':unittest.main()
