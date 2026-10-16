#!/usr/bin/env python3
"""Offline original full-client compilation and leaf-delta evidence only."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import unittest
from tools.rpi5 import audit_apple_ssh_full_client as full
from tools.rpi5 import build_apple_ssh_client_leaves as leaves

PACKAGE=full.ROOT/'build/rpi5/apple-ssh-client-leaves-8svd9i48'
MANIFEST_SHA='ef270aebee087a072eed44dfd2c15183b8a3ce3de36e1c897b380699687f6b08'


def actual_dependencies(report):
    expected={}
    for row in report['commands']:
        args=row['command']
        if '-MF' not in args:continue
        if row['returncode']:raise ValueError('Failed original compilation')
        path=Path(args[args.index('-MF')+1])
        for name in shlex.split(path.read_text().replace('\\\n',' ').partition(':')[2]):
            p=Path(name).resolve();expected[str(p)]=full.sha(p)
    if expected!=report['headers_sha256']:raise ValueError('Actual full header membership differs')
    return expected


class FullClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if full.sha(PACKAGE/'manifest.json')!=MANIFEST_SHA:raise ValueError('Leaf receipt changed')
        cls.leaf=json.loads((PACKAGE/'manifest.json').read_text())
        if full.sha(leaves.BASE/'manifest.json')!=leaves.BASE_SHA:raise ValueError('Full client receipt changed')
        cls.base=json.loads((leaves.BASE/'manifest.json').read_text())

    def test_upstream_membership_and_exact_header_closure(self):
        b=self.base
        self.assertEqual(b['requested_groups'],full.object_lists((full.SOURCE/'Makefile.in').read_text(),('LIBSSH_OBJS','SSHOBJS')))
        self.assertEqual(len(b['requested_translation_units']),176)
        self.assertTrue(b['all_original_client_units_compiled'])
        self.assertEqual(b['compile_failures'],[])
        self.assertEqual(set(b['compiled_objects']),set(b['requested_translation_units'])|{str(full.ROOT/'tools/rpi5/user/ssh_full_client_entry.c')})
        actual_dependencies(b);actual_dependencies(self.leaf)
        bad=dict(b,headers_sha256=dict(b['headers_sha256']))
        bad['headers_sha256'].pop(next(iter(bad['headers_sha256'])))
        with self.assertRaises(ValueError):actual_dependencies(bad)
        with self.assertRaises(ValueError):full.object_lists('A=$(B)\nB=$(A)\n',('A',))
        with self.assertRaises(ValueError):full.object_lists('A=shell-command\n',('A',))

    def test_preserved_inputs_and_actual_linker_delta(self):
        for r in (self.base,self.leaf):
            for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
                for n,h in r[key].items():self.assertEqual(full.sha(n),h,n)
            command=next(c for c in r['commands'] if c['stdout'].endswith('/target-link.stdout'))
            stderr=Path(command['stderr']).read_text()
            missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',stderr,re.M)))
            self.assertEqual(missing,r['target_missing_symbols'])
            self.assertFalse(r['target_link_complete'])
            self.assertEqual(r['target_duplicate_symbols'],[])
        self.assertEqual(len(self.base['target_missing_symbols']),108)
        self.assertEqual(len(self.leaf['target_missing_symbols']),102)
        self.assertEqual(set(self.base['target_missing_symbols'])-set(self.leaf['target_missing_symbols']),leaves.CLOSED)
        self.assertEqual(self.leaf['newly_reachable_dependencies'],['_strtoll'])
        grouped=self.leaf['remaining_provider_groups']
        self.assertEqual(sum(map(len,grouped.values())),102)
        self.assertEqual(set().union(*map(set,grouped.values())),set(self.leaf['target_missing_symbols']))

    def test_real_leaf_archive_and_native_original_sources(self):
        symbols=subprocess.check_output(['xcrun','nm','-g',self.leaf['target_archive']],text=True)
        for n in leaves.CLOSED:
            self.assertRegex(symbols,r'(?m)^[0-9a-f]+ [TDC] '+re.escape(n)+r'$')
        run=subprocess.run([str(PACKAGE/'original-leaves-host')],capture_output=True,text=True,timeout=10)
        self.assertEqual((run.returncode,run.stdout,run.stderr),(0,leaves.EXPECTED,''))
        self.assertTrue(self.leaf['native_asan_ubsan_pass'])
        self.assertFalse(self.leaf['target_executed'])
        self.assertFalse(self.leaf['provider_stubs'])
        self.assertFalse(self.leaf['entropy_qualified'])


if __name__=='__main__':unittest.main()
