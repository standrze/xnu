# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from probe_crypto_table import dependency_closure

class DependencyClosureTests(unittest.TestCase):
    def test_transitive_cycle_external_and_unused(self):
        records=[({'table'},{'a'}),({'a'},{'b','external'}),
                 ({'b'},{'a'}),({'unused'},set())]
        self.assertEqual(dependency_closure(records,'table'),[0,1,2])

    def test_missing_root_and_duplicate_definitions(self):
        with self.assertRaises(RuntimeError):
            dependency_closure([({'a'},set())],'table')
        with self.assertRaises(RuntimeError):
            dependency_closure([({'table'},set()),({'table'},set())],'table')
