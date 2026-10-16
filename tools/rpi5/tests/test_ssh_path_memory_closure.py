#!/usr/bin/env python3
"""Original small leaves and actual alias to a genuine existing Apple body."""
import json
from pathlib import Path
import struct
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_path_memory as build
from tools.rpi5 import check_apple_pthread_kernel_contract as macho
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE=build.ROOT/'build/rpi5/apple-ssh-path-memory-p6awfv2m'
SHA='14798734ab0c6af05342b41e7557676eb3dffe41fc1aead96fed0acc4ceea38c'


class PathMemory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE/'manifest.json')!=SHA:raise ValueError('Frozen path/memory receipt changed')
        cls.report=json.loads((PACKAGE/'manifest.json').read_text())

    def test_exact_inputs_header_closure_and_actual_native_boundaries(self):
        r=self.report
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for n,h in r[key].items():self.assertEqual(build.sha(n),h,n)
        actual_dependencies(r)
        bad=dict(r,headers_sha256=dict(r['headers_sha256']))
        bad['headers_sha256'].pop(next(iter(bad['headers_sha256'])))
        with self.assertRaises(ValueError):actual_dependencies(bad)
        good=subprocess.run([str(PACKAGE/'original-path-memory-host')],capture_output=True,text=True,timeout=10)
        self.assertEqual((good.returncode,good.stdout,good.stderr),(0,build.EXPECTED,''))
        failure=subprocess.run([str(PACKAGE/'original-path-memory-host'),'alloc-fail'],capture_output=True,text=True,timeout=10)
        self.assertEqual((failure.returncode,failure.stdout,failure.stderr),(0,'APPLE_SSH_PATH_MEMORY ALLOC_FAILURE PASS\n',''))

    def test_actual_alias_address_and_original_body_branch(self):
        r=self.report;image=macho.MachO(Path(r['forced_contract']))
        at=image.names['_bzero']['address']
        self.assertEqual(at,image.names['_rpi5_pthread_private_bzero']['address'])
        word=struct.unpack('<I',image.at(at,4))[0];self.assertEqual(word>>26,0b000101)
        offset=word&0x3ffffff
        if offset&(1<<25):offset-=1<<26
        self.assertEqual(at+offset*4,image.names['__platform_bzero']['address'])
        self.assertEqual((PACKAGE/'forced-undefined.stdout').read_text(),'')
        self.assertIn('_dirname',image.names);self.assertIn('_memmem',image.names)
        self.assertTrue(r['forced_contract_is_not_full_ssh'])

    def test_full_link_and_execution_limits(self):
        r=self.report
        self.assertEqual(r['closed_symbols'],['_bzero','_dirname','_memmem'])
        self.assertEqual(r['newly_reachable_symbols'],[]);self.assertEqual(r['target_duplicate_symbols'],[])
        self.assertEqual(len(r['target_missing_symbols']),77)
        self.assertFalse(r['target_link_complete']);self.assertFalse(r['target_executed'])
        self.assertTrue(r['dirname_original_static_storage']);self.assertFalse(r['provider_stubs'])


if __name__=='__main__':unittest.main()
