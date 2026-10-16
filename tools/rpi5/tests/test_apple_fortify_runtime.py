#!/usr/bin/env python3
"""Target provider recursion regression and original checked API contracts."""
import json
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5 import build_apple_fortify_runtime_v2 as build
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE=build.ROOT/'build/rpi5/apple-fortify-runtime-punnvr0c'
SHA='adcab45b4082c864520a6101d4fc5efa8e2ada095aa1a23b4dbc01aaeb3cc365'


class Fortify(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE/'manifest.json')!=SHA:raise ValueError('Fortify receipt changed')
        cls.r=json.loads((PACKAGE/'manifest.json').read_text())

    def test_frozen_original_sources_and_actual_dependency_membership(self):
        r=self.r
        for k in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for n,h in r[k].items():self.assertEqual(build.sha(n),h,n)
        actual_dependencies(r)
        for d in r['dependency_records'].values():self.assertEqual(d['scanned_sha256'],d['consumed_sha256'])
        expected={prefix+n for prefix in ('target-','native-') for n in build.original.UNITS}
        expected|={'native-crash','native-caller','native-original-strcpy'}
        self.assertEqual(set(r['dependency_records']),expected)
        bad=dict(r,headers_sha256=dict(r['headers_sha256']));bad['headers_sha256'].pop(next(iter(bad['headers_sha256'])))
        with self.assertRaises(ValueError):actual_dependencies(bad)
        original=(build.original.LIBC/'secure/strcpy_chk.c').read_text()
        self.assertEqual((PACKAGE/'overlay/strcpy_chk.c').read_text(),build.original.strcpy_overlay(original))
        with self.assertRaises(ValueError):build.original.strcpy_overlay(original.replace('  return dest;','  return other;'))
        self.assertEqual(r['modified_original_units'],['strcpy_chk'])
        self.assertEqual(build.CONFIG.read_text().splitlines().count(build.POLICY),1)
        for row in r['commands']:
            if '-MF' not in row['command']:continue
            self.assertIn('-D_FORTIFY_SOURCE=0',row['command'])
            self.assertIn('-DPR_13085474_CHECK=0',row['command'])
        self.assertTrue(r['consumer_flags_unchanged'])

    def test_native_valid_fatal_and_original_heap_failure(self):
        result=subprocess.run([PACKAGE/'host-fortify'],capture_output=True,text=True,timeout=20)
        self.assertEqual((result.returncode,result.stdout,result.stderr),(0,build.original.EXPECTED,''))
        original=subprocess.run([PACKAGE/'host-original-negative','original-overflow'],capture_output=True,text=True,timeout=20)
        self.assertNotEqual(original.returncode,0)
        self.assertIn('AddressSanitizer: heap-buffer-overflow',original.stderr)
        self.assertTrue(self.r['original_os_crash_callback_and_caller_trap'])
        self.assertFalse(self.r['target_executed'])

    def test_actual_target_calls_not_namespace_hidden_recursion(self):
        expected={'memcpy_chk':('_memcpy',),'memmove_chk':('_memmove',),'memset_chk':('_memset',),
                  'strcpy_chk':('_strlen','_stpcpy'),'strlcpy_chk':('_strlcpy',),
                  'strlcat_chk':('_memcpy','_strlen','_strnlen'),
                  'snprintf_chk':('_vsnprintf',),'sprintf_chk':('_vsnprintf','_vsprintf')}
        for unit,providers in expected.items():
            names=subprocess.check_output(['xcrun','nm','-g',PACKAGE/('target-'+unit+'.o')],text=True)
            for p in providers:self.assertRegex(names,r'(?m)^\s+U '+re.escape(p)+r'$')
            self.assertRegex(names,r'(?m)^[0-9a-f]+ T ___'+unit+r'$')
        disassembly=(PACKAGE/'disassembly.stdout').read_text()
        self.assertEqual(len(re.findall(r'\bbrk\s+#0x1',disassembly)),2)
        self.assertIn('ARM64_RELOC_BRANCH26\t__os_crash',disassembly)
        strcpy=disassembly.split('/target-strcpy_chk.o:',1)[1].split('/target-strlcpy_chk.o:',1)[0]
        self.assertLess(strcpy.index('ARM64_RELOC_BRANCH26\t_strlen'),strcpy.index('ARM64_RELOC_BRANCH26\t___chk_overlap'))
        self.assertLess(strcpy.index('ARM64_RELOC_BRANCH26\t___chk_overlap'),strcpy.index('ARM64_RELOC_BRANCH26\t_stpcpy'))
        # The earlier namespace-native fixture passed, but its actual unrenamed
        # target memory providers had no leaf relocation and looped. Keep that
        # negative evidence explicit rather than declaring both artifacts good.
        for unit,leaf in (('memcpy_chk','_memcpy'),('memmove_chk','_memmove'),('memset_chk','_memset')):
            names=subprocess.check_output(['xcrun','nm','-g',build.PREVIOUS/('target-'+unit+'.o')],text=True)
            self.assertNotRegex(names,r'(?m)^\s+U '+leaf+r'$')
        self.assertTrue(self.r['preserved_prototype_target_recursion_not_admitted'])

    def test_full_original_client_composition_and_honest_delta(self):
        r=self.r;base=json.loads((build.original.BASE/'manifest.json').read_text())
        stderr=(PACKAGE/'target-link.stderr').read_text()
        missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',stderr,re.M)))
        self.assertEqual(missing,r['target_missing_symbols']);self.assertEqual(len(missing),56)
        self.assertEqual(r['previous_missing_count'],67);self.assertEqual(len(r['closed_symbols']),12)
        self.assertEqual(r['newly_reachable_symbols'],['_stpcpy']);self.assertEqual(r['target_duplicate_symbols'],[])
        old=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
        new=list(next(c['command'] for c in r['commands'] if c['stdout'].endswith('/target-link.stdout')))
        for flag in ('-o','-map'):old[old.index(flag)+1]=new[new.index(flag)+1]
        self.assertEqual(new,old+r['added_archives'])
        self.assertEqual(r['added_archives'],[str(PACKAGE/'libapple-fortify.a'),
            str(build.original.APIS/'libapple-selected-runtime-apis.a'),str(build.original.BLOCKS/'libapple-blocks-runtime.a')])
        for name in ('_dispatch_once','_si_destination_compare','_gss_init_sec_context','_dlopen','_notify_check'):
            self.assertIn(name,missing)
        self.assertFalse(r['target_link_complete']);self.assertFalse(r['accepted_runtime_modified'])
        self.assertTrue(r['original_openssh_config_unchanged'])


if __name__=='__main__':unittest.main()
