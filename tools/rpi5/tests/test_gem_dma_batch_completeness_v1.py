# SPDX-License-Identifier: BSD-2-Clause
"""Actual recipe mutation tests, byte-only; no compiler or device access."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import gem_dma_batch_completeness_v1 as c
PACKAGE=c.b.ROOT/'build/rpi5/gem-dma-batch-trial-20261014-v2'
PIN='dfbbb521f31083158b690c43a08891c7bbe947a44ac5bdd459ea7e402bfca6a6'
class BatchCompletenessTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(c.sha(PACKAGE/'manifest.json'),PIN)
        self.m=json.loads((PACKAGE/'manifest.json').read_bytes())
        self.block=patch('subprocess.run',side_effect=AssertionError('No subprocess'))
        self.block.start();self.addCleanup(self.block.stop)
    def test_actual_complete_recipe_and_dependency_union(self):
        scans=c.command_bindings(PACKAGE,self.m)
        self.assertEqual(c.dependencies(PACKAGE,self.m,scans),len(self.m['actual_headers_sha256']))
        self.assertGreater(len(scans),20)
        c.payload(PACKAGE)
    def test_actual_command_label_flags_link_cwd_and_strict_status(self):
        mutations=[]
        m=deepcopy(self.m);m['commands'].pop();mutations.append(m)
        m=deepcopy(self.m);m['commands'].append(deepcopy(m['commands'][0]));mutations.append(m)
        m=deepcopy(self.m);m['commands'][0]['command'].append('-O0');mutations.append(m)
        m=deepcopy(self.m);m['commands'][0]['cwd']=str(PACKAGE);mutations.append(m)
        m=deepcopy(self.m);m['commands'][0]['returncode']=False;mutations.append(m)
        m=deepcopy(self.m);next(r for r in m['commands'] if r['log'].endswith('/kernel-link.log'))['command'].append('/tmp/extra.o');mutations.append(m)
        m=deepcopy(self.m);m['compiler_scans'].pop(next(iter(m['compiler_scans'])));mutations.append(m)
        m=deepcopy(self.m);m['profile']='bcm2712-gem-owned-rings-resolved-reservations-default-off-v1';mutations.append(m)
        for m in mutations:
            with self.assertRaises(ValueError):c.command_bindings(PACKAGE,m)
    def test_omitted_actual_header_or_source_pin(self):
        scans=c.command_bindings(PACKAGE,self.m)
        for key in ('inputs_sha256','actual_headers_sha256'):
            m=deepcopy(self.m);name=next(iter(m['actual_headers_sha256']));m[key].pop(name)
            with self.assertRaises(ValueError):c.dependencies(PACKAGE,m,scans)
        # v2 predates this helper; no synthetic retroactive artifact admission.
        with self.assertRaises(ValueError):c.source_outputs(PACKAGE,self.m)
    def test_actual_canonical_source_and_object_delta_negative(self):
        # Source-only comparison excludes closure admission. The saved prototype
        # may predate later builder checker-input additions, not code recipes.
        c.source_outputs(PACKAGE,self.m,require_pins=False)
        m=deepcopy(self.m);m['added_objects'].append('/tmp/injected.o')
        with self.assertRaises(ValueError):c.source_outputs(PACKAGE,m,require_pins=False)
        actual=c.b.derived_sources()
        for name in ('arm_init.c','probe_main.c','overlay/BCM2712GEMDMABatch.cpp'):
            changed=dict(actual);changed[name]+=b'\n'
            with patch.object(c.b,'derived_sources',return_value=changed):
                with self.assertRaises(ValueError):c.source_outputs(PACKAGE,self.m,require_pins=False)
        with patch.object(c.b.old.payload_container,'encode',return_value=b'not a payload'):
            with self.assertRaises(ValueError):c.payload(PACKAGE)
if __name__=='__main__':unittest.main()
