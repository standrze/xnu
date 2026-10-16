# SPDX-License-Identifier: BSD-2-Clause
"""Actual bound recorder/return functions and exact new single-loader intake."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import owner_trace_trial_v1 as stage
from tools.rpi5 import serial_owner_trace_trial_v1 as recorder
from tools.rpi5 import owner_trace_evidence_v1 as evidence
from tools.rpi5.tests import test_root_route_trial_v1 as old


class OwnerControllerTests(unittest.TestCase):
    def test_fixed_adapter_original_bodies_complete_sources(self):
        self.assertEqual(set(stage.get_descriptor.__globals__['ADAPTERS']),{'pcie-owner-trace'})
        for name in ('prepare_install','load_installation','prepare_restore','launch','replay','dispatch'):
            self.assertIs(getattr(stage,name).__code__,getattr(stage.prior,name).__code__)
        self.assertIs(evidence.captured.__code__,evidence.original.captured.__code__)
        self.assertIs(recorder.bindings.__code__,recorder.original.bindings.__code__)
        pins=stage.source_pins()
        for name in ('owner_trace_trial_v1.py','serial_owner_trace_trial_v1.py','owner_trace_evidence_v1.py','tests/test_owner_trace_trial_v1.py','stage_root42_ready_trial.py'):
            path=stage.ROOT/'tools/rpi5'/name;self.assertEqual(pins[str(path)],stage.sha(path))

    def test_new_typed_ready_root_intake_and_no_forged_pair_receipt(self):
        with tempfile.TemporaryDirectory(prefix='owner-intake-fixture-',dir=stage.ROOT/'build/rpi5') as name:
            path=Path(name);plan={'media':{'profile':stage.ready.engine.RESTORE,'controller':stage.ready.CONTROLLER}}
            (path/'plan.json').write_text(json.dumps(plan))
            context={'result':{'publication':{'protected_files_sha256':{n:v[1] for n,v in stage.GOOD.items()}}}}
            with patch.object(stage.ready,'restoration',return_value=context) as called:
                self.assertIs(stage.baseline(path,'a'*64,'b'*64),context);called.assert_called_once_with(path,'a'*64,'b'*64)
            altered=copy.deepcopy(context);altered['result']['publication']['protected_files_sha256']['bl31.bin']='0'*64
            with patch.object(stage.ready,'restoration',return_value=altered),self.assertRaises(ValueError):stage.baseline(path,'a'*64,'b'*64)
            with patch.object(stage.ready,'restoration',side_effect=ValueError('bad seal')),self.assertRaisesRegex(ValueError,'seal'):stage.baseline(path,'a'*64,'b'*64)
            for field in ('profile','controller'):
                changed=copy.deepcopy(plan);changed['media'][field]='unknown';(path/'plan.json').write_text(json.dumps(changed))
                with patch.object(stage.ready,'restoration') as wrong,self.assertRaises(Exception):stage.baseline(path,'a'*64,'b'*64)
                wrong.assert_not_called()

    def test_real_recorder_body_capture_return_replay(self):
        text=Path(old.__file__).read_text()
        text=text.replace('root_route_trial_v1','owner_trace_trial_v1').replace('serial_root_route_trial_v1','serial_owner_trace_trial_v1')
        text=text.replace('root_route_evidence_v1','owner_trace_evidence_v1')
        text=text.replace('test_pcie_root_route_serial','test_pcie_owner_trace_serial').replace('pcie_root_route_serial_core','pcie_owner_trace_serial_core')
        text=text.replace('fixture.RootRouteSerialTests()','fixture.OwnerSerialTests()')
        # Use the actual frozen engine at owner -> BAR -> v3 -> base. Do not
        # manufacture a compatibility API on the production adapter.
        text=text.replace('stage.prior.base.loaded_sources()', 'stage.prior.prior.base.loaded_sources()')
        text=text.replace("        raw = raw.replace(b'OK=1 PHASE=5 LAST=5', b'OK=0 PHASE=6 LAST=14')\n",'')
        text=text.replace("self.assertFalse(observed['diagnostic']['rp1_id_trial_pass'])","self.assertTrue(observed['diagnostic']['bars_trial_pass'])")
        text=text.replace("self.assertFalse(returned['diagnostic']['rp1_id_trial_pass'])","self.assertTrue(returned['diagnostic']['bars_trial_pass'])")
        module=types.ModuleType('_owner_actual_recorder_fixture');module.__file__=old.__file__
        exec(compile(text,old.__file__,'exec'),module.__dict__)
        module.RootRouteTests('test_actual_recorder_full_capture_independent_return_and_failure_guards').test_actual_recorder_full_capture_independent_return_and_failure_guards()


if __name__=='__main__':unittest.main()
