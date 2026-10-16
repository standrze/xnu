# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import tempfile
import unittest
from tools.rpi5 import prepare_root42_pthread_trial_v3 as prepare


class AliasTests(unittest.TestCase):
    def test_literal_alias_and_target_both_retained_and_revalidated(self):
        with tempfile.TemporaryDirectory() as name:
            d=Path(name).resolve();target=d/'versioned.h';target.write_text('int original;');alias=d/'current.h';alias.symlink_to(target)
            h=prepare.stage.sha(target);manifest=d/'manifest.json';manifest.write_text(json.dumps(dict(
                inputs_sha256={str(alias):h},headers_sha256={},generated_sha256={})))
            pins=prepare.retain_literal_pins(manifest,{str(target):h})
            self.assertEqual(pins,{str(alias):h,str(target):h});prepare.stage.seals.check_pins(pins)
            changed=d/'changed.h';changed.write_text('int different;');alias.unlink();alias.symlink_to(changed)
            with self.assertRaises(ValueError):prepare.stage.seals.check_pins(pins)
            with self.assertRaisesRegex(ValueError,'resolved target'):prepare.retain_literal_pins(manifest,{str(target):h})

    def test_missing_resolved_or_conflicting_literal_members_fail_closed(self):
        with tempfile.TemporaryDirectory() as name:
            d=Path(name).resolve();target=d/'input';target.write_text('real');alias=d/'alias';alias.symlink_to(target)
            h=prepare.stage.sha(target);manifest=d/'manifest.json';manifest.write_text(json.dumps(dict(
                inputs_sha256={str(alias):h},headers_sha256={},generated_sha256={})))
            for pins in ({},{str(target):'0'*64},{str(target):h,str(alias):'0'*64}):
                with self.assertRaises(ValueError):prepare.retain_literal_pins(manifest,pins)
