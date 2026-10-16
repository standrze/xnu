# SPDX-License-Identifier: BSD-2-Clause
"""Unchanged recorder/return/dispatch bodies with new real protocol and typed intake."""
import copy
import importlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import bars_root_trial_v1 as stage
from tools.rpi5 import serial_bars_root_trial_v1 as recorder
from tools.rpi5 import bars_root_evidence_v1 as evidence
from tools.rpi5.tests import test_root_route_trial_v1 as old


class BarsControllerTests(unittest.TestCase):
    def test_only_fixed_adapter_original_guard_bodies_and_all_sources(self):
        self.assertEqual(set(stage.get_descriptor.__globals__['ADAPTERS']),{'rp1-contained-bars'})
        for name in ('prepare_install','load_installation','prepare_restore','launch','replay','dispatch'):
            self.assertIs(getattr(stage,name).__code__,getattr(stage.prior,name).__code__)
        self.assertIs(evidence.captured.__code__,evidence.original.captured.__code__)
        self.assertIs(recorder.bindings.__code__,recorder.original.bindings.__code__)
        pins=stage.source_pins()
        for name in ('bars_root_trial_v1.py','serial_bars_root_trial_v1.py','bars_root_evidence_v1.py','tests/test_bars_root_trial_v1.py'):
            path=stage.ROOT/'tools/rpi5'/name;self.assertEqual(pins[str(path)],stage.sha(path))

    def test_exact_typed_loader_intake_no_fabricated_pair_receipt(self):
        with tempfile.TemporaryDirectory(prefix='bars-intake-fixture-',dir=stage.ROOT/'build/rpi5') as name:
            path=Path(name);(path/'plan.json').write_text(json.dumps({'media':{'profile':stage.loader.engine.RESTORE}}))
            context={'result':{'publication':{'protected_files_sha256':{n:v[1] for n,v in stage.GOOD.items()}}}}
            with patch.object(stage.loader,'restoration',return_value=context) as called:
                self.assertIs(stage.baseline(path,'a'*64,'b'*64),context)
                called.assert_called_once_with(path,'a'*64,'b'*64)
            changed=copy.deepcopy(context);changed['result']['publication']['protected_files_sha256']['bl31.bin']='0'*64
            with patch.object(stage.loader,'restoration',return_value=changed),self.assertRaises(ValueError):stage.baseline(path,'a'*64,'b'*64)
            with patch.object(stage.loader,'restoration',side_effect=ValueError('invalid retained seal')),self.assertRaisesRegex(ValueError,'seal'):
                stage.baseline(path,'a'*64,'b'*64)
            (path/'plan.json').write_text(json.dumps({'media':{'profile':'unknown'}}))
            with self.assertRaises(Exception):stage.baseline(path,'a'*64,'b'*64)

    def test_actual_bound_recorder_to_independent_return_and_replay(self):
        # The frozen whole-path test runs its actual recorder body with UART,
        # clocks and SSH doubled. Adapt only the named protocol fixture and
        # expectation: this synthetic BAR completion is not board evidence.
        text=Path(old.__file__).read_text()
        text=text.replace('root_route_trial_v1','bars_root_trial_v1').replace('serial_root_route_trial_v1','serial_bars_root_trial_v1')
        text=text.replace('root_route_evidence_v1','bars_root_evidence_v1')
        text=text.replace('test_pcie_root_route_serial','test_rp1_bars_root_serial').replace('pcie_root_route_serial_core','rp1_bars_root_serial_core')
        text=text.replace('fixture.RootRouteSerialTests()','fixture.BarsSerialTests()')
        text=text.replace("        raw = raw.replace(b'OK=1 PHASE=5 LAST=5', b'OK=0 PHASE=6 LAST=14')\n",'')
        text=text.replace("self.assertFalse(observed['diagnostic']['rp1_id_trial_pass'])","self.assertTrue(observed['diagnostic']['bars_trial_pass'])")
        text=text.replace("self.assertFalse(returned['diagnostic']['rp1_id_trial_pass'])","self.assertTrue(returned['diagnostic']['bars_trial_pass'])")
        module=types.ModuleType('_bars_actual_recorder_fixture');module.__file__=old.__file__
        exec(compile(text,old.__file__,'exec'),module.__dict__)
        module.RootRouteTests('test_actual_recorder_full_capture_independent_return_and_failure_guards').test_actual_recorder_full_capture_independent_return_and_failure_guards()


if __name__=='__main__':unittest.main()
