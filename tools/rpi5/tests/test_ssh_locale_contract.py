#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Actual source/header/startup/thread contract, never run target Mach-O."""
import copy
import json
from pathlib import Path
import re
import struct
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_locale_slice as build
from tools.rpi5 import check_apple_pthread_kernel_contract as macho
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE=build.ROOT/'build/rpi5/apple-ssh-locale-slice-lu4cw5xx'
PACKAGE_SHA='061bb7cd2d98e9e0ef23814250b29a7e8c661347fd26d465df823985b039af36'
CONTRACT=build.ROOT/'build/rpi5/apple-ssh-locale-contract-z_bni486'
CONTRACT_SHA='56843a4a270a8f2ec0a1ed8ddf2afb42efac98bb873d3835e347810c2085b8ec'


class LocaleContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE/'manifest.json')!=PACKAGE_SHA or build.sha(CONTRACT/'manifest.json')!=CONTRACT_SHA:
            raise ValueError('Locale evidence changed')
        cls.report=json.loads((PACKAGE/'manifest.json').read_text())
        cls.contract=json.loads((CONTRACT/'manifest.json').read_text())

    def test_source_and_actual_consumed_header_closure(self):
        for report in (self.report,self.contract):
            for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
                for name,digest in report[key].items():self.assertEqual(build.sha(name),digest,name)
            actual_dependencies(report)
            omitted=copy.deepcopy(report);omitted['headers_sha256'].pop(next(iter(omitted['headers_sha256'])))
            with self.assertRaises(ValueError):actual_dependencies(omitted)
        self.assertEqual(self.report['compile_failures'],{})
        self.assertEqual(self.report['original_units'],list(build.UNITS))
        for name in build.UNITS:
            self.assertEqual((build.LIBC/name).read_bytes(),subprocess.check_output(['git','-C',build.LIBC,'show','HEAD:'+name]))
        flags=next(c['command'] for c in self.report['commands'] if c['stdout'].endswith('/target-strtoll-compile.stdout'))
        self.assertIn('-D__LIBC__=1',flags)
        self.assertFalse(any('SIMULATOR' in a or '_LIBC_NO_FEATURE_VERIFICATION' in a for a in flags))

    def test_actual_startup_key_and_provider_bindings(self):
        original=(build.ROOT/'tools/rpi5/user/pthread_static_start.c').read_text()
        generated=Path(self.report['startup_replacement_source']).read_text()
        self.assertEqual(generated,build.startup_source(original))
        with self.assertRaises(ValueError):build.startup_source(generated)
        image=macho.MachO(self.contract['target'])
        self.assertEqual(image.at(image.names['___locale_key']['address'],8),b'\xff'*8)
        dis=(CONTRACT/'target-disassembly.stdout').read_text()
        start=dis.split('<_darwin_static_start>:',1)[1].split('\n000000',1)[0]
        ordered=['<___libkernel_init>','<___pthread_init>','<___xlocale_init>',
                 '<_malloc>','<___pthread_late_init>','<_rpi5_run_initializers>','<_rpi5_pthread_smoke_main>']
        positions=[start.index(token) for token in ordered]
        self.assertEqual(positions,sorted(positions))
        init=dis.split('<___xlocale_init>:',1)[1].split('\n000000',1)[0]
        self.assertIn('<_pthread_key_init_np>',init)
        self.assertIn('#0xa',init)
        strtoll=dis.split('<_strtoll>:',1)[1].split('\n000000',1)[0]
        self.assertIn('TPIDRRO_EL0',strtoll)
        self.assertNotIn('_fixture_',strtoll)
        table=(CONTRACT/'target.map').read_text()
        owners={int(n):p for n,p in re.findall(r'^\[\s*(\d+)\]\s+(.+)$',table,re.M)}
        for symbol,object_name in {'_strtoll':'target-strtoll.o','___xlocale_init':'target-xlocale.o',
                                  '___global_locale':'target-xlocale.o','_pthread_key_init_np':'pthread-pthread_tsd.o'}.items():
            match=re.search(r'^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+'+re.escape(symbol)+r'$',table,re.M)
            self.assertIsNotNone(match,symbol);self.assertTrue(owners[int(match[1])].endswith('('+object_name+')'),symbol)
        self.assertEqual((CONTRACT/'target-undefined.stdout').read_text(),'')
        # This initial slice still contains legacy archive entries. Successor
        # group admission must replace their owners, never infer that here.
        self.assertIn('locale-table.o',table)

    def test_native_vectors_real_threads_refcounts_destructors_and_negative(self):
        for args,code in (([],0),(['bad-expected'],11)):
            run=subprocess.run([CONTRACT/'locale-host',*args],capture_output=True,text=True,timeout=15)
            self.assertEqual(run.returncode,code,run.stderr);self.assertEqual(run.stderr,'')
            self.assertEqual(run.stdout,self.contract['host_stdout'] if not args else '')
        self.assertTrue(self.contract['native_asan_ubsan_pass'])
        self.assertFalse(self.contract['target_executed'])
        self.assertFalse(self.contract['target_locale_runtime_executed'])
        self.assertIn('reserved key',self.contract['explicit_host_boundary'])

    def test_real_full_client_delta_not_complete_ssh(self):
        self.assertEqual(self.report['closed_symbols'],['_strtoll'])
        self.assertEqual(self.report['newly_reachable_dependencies'],[])
        self.assertEqual(len(self.report['target_missing_symbols']),101)
        self.assertFalse(self.report['target_link_complete'])
        self.assertFalse(self.report['full_current_libc_initialized'])
        self.assertFalse(self.report['provider_stubs'])


if __name__=='__main__':unittest.main()
