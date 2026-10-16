# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from tools.rpi5 import repeat_display_xnu_trial_v2 as repeat


class RepeatDisplayXNUTests(unittest.TestCase):
    def test_only_typed_predecessor_and_source_closure_change(self):
        s=repeat.stage
        self.assertIs(repeat.prepare_install.__code__,s.prepare_install.__code__)
        self.assertIs(repeat.prepare_install.__globals__['baseline'],s.restoration)
        self.assertIs(repeat.prepare_install.__globals__['source_pins'],repeat.source_pins)
        self.assertIs(repeat.main.__code__,s.main.__code__)
        for name in ('dispatch','launch','prepare_restore'):
            self.assertIs(repeat.main.__globals__[name],getattr(s,name))
        pins=repeat.source_pins()
        for p in (Path(repeat.__file__).resolve(),Path(__file__).resolve()):
            self.assertEqual(pins[str(p)],s.sha(p))
        self.assertEqual({k:pins[k] for k in s.source_pins()},s.source_pins())

    def test_actual_completed394_restore_is_byte_only_and_pin_bound(self):
        s=repeat.stage
        p=s.ROOT/'build/rpi5/display-xnu-v2-restored-20261014'
        seal='505e983ea03c6c5d90ddff2951be5cb668c2de6f0353e5529f96331c45f8cb30'
        plan='e356a27c94253ac7c88046a29e344ddde82ca01e43e8029852bfc06285b71b4e'
        self.assertEqual(s.sha(p/'result.json'),'d1ceef296c7dac94a4b4318c1eee8ac6d6b7d8fd7142d6eca489e171bddaca79')
        with patch.object(subprocess,'run',side_effect=AssertionError('No compiler/history/hardware')):
            v=repeat.prepare_install.__globals__['baseline'](p,seal,plan)
            with self.assertRaises(ValueError):s.restoration(p,'0'*64,plan)
            with self.assertRaises(ValueError):s.restoration(p,seal,'0'*64)
        self.assertEqual(len(v['result']['next_catalog']),394)
        self.assertEqual(v['result']['publication']['identity']['boot_id'],'8f1e79b1-12c6-4f74-b233-f3aa60d71990')


if __name__=='__main__':unittest.main()
