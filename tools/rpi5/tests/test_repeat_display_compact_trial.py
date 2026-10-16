# SPDX-License-Identifier: BSD-2-Clause
import unittest
from pathlib import Path
import subprocess
from unittest.mock import patch
from tools.rpi5 import repeat_display_compact_trial as repeat


class RepeatCompactTests(unittest.TestCase):
    def test_only_typed_predecessor_and_source_closure_change(self):
        s=repeat.stage
        self.assertIs(repeat.prepare_install.__code__,s.prepare_install.__code__)
        self.assertIs(repeat.prepare_install.__globals__['baseline'],s.restoration)
        self.assertIs(repeat.prepare_install.__globals__['source_pins'],repeat.source_pins)
        self.assertIs(repeat.main.__code__,s.main.__code__)
        self.assertIs(repeat.main.__globals__['dispatch'],s.dispatch)
        self.assertIs(repeat.main.__globals__['launch'],s.launch)
        self.assertIs(repeat.main.__globals__['prepare_restore'],s.prepare_restore)
        pins=repeat.source_pins()
        for p in (Path(repeat.__file__).resolve(),Path(__file__).resolve()):
            self.assertEqual(pins[str(p)],s.sha(p))
        self.assertEqual({k:pins[k] for k in s.source_pins()},s.source_pins())

    def test_actual_completed364_restore_is_byte_only_and_pin_bound(self):
        s=repeat.stage
        p=s.ROOT/'build/rpi5/display-compact-restored-20261014'
        seal='daef6c477fd6a11587a177b9326a7a1c001380dac2507bc67a42fa2468d4e1b8'
        plan='1fb0033c1212f0fb1222113ce53f6275bf3bdbf90879abf33d9be88b212968d6'
        self.assertEqual(s.sha(p/'result.json'),'6106212952c8fd0a1b201de19196a69585569a67b273fe137f16563d81c4dea1')
        with patch.object(subprocess,'run',side_effect=AssertionError('No compiler/history/hardware')):
            v=repeat.prepare_install.__globals__['baseline'](p,seal,plan)
            with self.assertRaises(ValueError):s.restoration(p,'0'*64,plan)
            with self.assertRaises(ValueError):s.restoration(p,seal,'0'*64)
        self.assertEqual(len(v['result']['next_catalog']),364)
        self.assertEqual(v['result']['publication']['identity']['boot_id'],'93738a7e-3f36-4fd9-bf60-e587a1281b2f')


if __name__=='__main__':unittest.main()
