# SPDX-License-Identifier: BSD-2-Clause
"""Exact fixed adapter, actual recorder API, and typed root43 rollback intake."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import guard_composition_trial_v1 as stage
from tools.rpi5 import serial_guard_composition_trial_v1 as recorder
from tools.rpi5 import guard_composition_evidence_v1 as evidence
from tools.rpi5.tests import test_root_route_trial_v1 as old


class GuardControllerTests(unittest.TestCase):
    def test_fixed_adapter_original_bodies_complete_sources(self):
        self.assertEqual(set(stage.get_descriptor.__globals__['ADAPTERS']),{'pcie-guard-composition'})
        self.assertIs(stage._prepare_install.__code__,stage.prior.prepare_install.__code__)
        for name in ('load_installation','prepare_restore','launch','replay','dispatch'):
            self.assertIs(getattr(stage,name).__code__,getattr(stage.prior,name).__code__)
        self.assertIs(evidence.captured.__code__,evidence.original.captured.__code__)
        self.assertIs(recorder.bindings.__code__,recorder.original.bindings.__code__)
        pins=stage.source_pins()
        for name in ('guard_composition_trial_v1.py','serial_guard_composition_trial_v1.py','guard_composition_evidence_v1.py',
            'tests/test_guard_composition_trial_v1.py','stage_root43_packet_trial.py','root43_packet_trial_core.py'):
            path=stage.ROOT/'tools/rpi5'/name;self.assertEqual(pins[str(path)],stage.sha(path))

    def test_typed_root43_intake_rejects_bad_pair_seal_and_type(self):
        with tempfile.TemporaryDirectory(prefix='guard-intake-fixture-',dir=stage.ROOT/'build/rpi5') as name:
            path=Path(name);plan={'media':{'profile':stage.ready.engine.RESTORE,'controller':stage.ready.CONTROLLER}}
            (path/'plan.json').write_text(json.dumps(plan))
            context={'result':{'publication':{'protected_files_sha256':{n:v[1] for n,v in stage.GOOD.items()}}}}
            with patch.object(stage.ready,'restoration',return_value=context) as called:
                self.assertIs(stage.baseline(path,'a'*64,'b'*64),context);called.assert_called_once_with(path,'a'*64,'b'*64)
            for key in stage.GOOD:
                altered=copy.deepcopy(context);altered['result']['publication']['protected_files_sha256'][key]='0'*64
                with patch.object(stage.ready,'restoration',return_value=altered),self.assertRaises(ValueError):stage.baseline(path,'a'*64,'b'*64)
            with patch.object(stage.ready,'restoration',side_effect=ValueError('bad seal')),self.assertRaisesRegex(ValueError,'seal'):stage.baseline(path,'a'*64,'b'*64)
            for field in ('profile','controller'):
                changed=copy.deepcopy(plan);changed['media'][field]='unknown';(path/'plan.json').write_text(json.dumps(changed))
                with patch.object(stage.ready,'restoration') as wrong,self.assertRaises(Exception):stage.baseline(path,'a'*64,'b'*64)
                wrong.assert_not_called()

    def test_complete_protocol_api_required_before_descriptor_admission(self):
        names=('inspect','inventory','return_positions','PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX')
        values={n:object() for n in names};values.update(PREFIX=b'prefix:',PREPARED_PREFIX=b'prefix:PREPARED ')
        for missing in names:
            protocol=types.SimpleNamespace(**{k:v for k,v in values.items() if k!=missing})
            with patch.object(stage,'get_descriptor',return_value={'protocol':protocol}),self.assertRaises(ValueError):
                stage.load_descriptor({})
        protocol=types.SimpleNamespace(**values);selected={'protocol':protocol}
        with patch.object(stage,'get_descriptor',return_value=selected):self.assertIs(stage.load_descriptor({}),selected)
        protocol.PREPARED_PREFIX=b'wrong'
        with patch.object(stage,'get_descriptor',return_value=selected),self.assertRaises(ValueError):stage.load_descriptor({})

    def test_prepublication_admission_binds_actual_recorder_without_uart(self):
        from tools.rpi5.tests import test_pcie_guard_composition_serial as fixture
        from tools.rpi5 import pcie_guard_composition_serial_core as protocol
        _,report=fixture.GuardCompositionSerialTests().fixture()
        case=json.loads((stage.ROOT/'build/rpi5/pcie-guard-composition-case-20261013/descriptor.json').read_text())
        report['firmware_sha256']=case['firmware_sha256']
        record=dict(marker=report['marker'],firmware_sha256=report['firmware_sha256'])
        selected=dict(protocol=protocol,record=record)
        pins=stage.source_pins()|{str(Path(protocol.__file__).resolve()):stage.sha(protocol.__file__),
            str(Path(recorder.__file__).resolve()):stage.sha(recorder.__file__)}
        checkpoint=dict(payload=dict(media_plan=dict(descriptor={},preflight=report)),evidence_sha256=pins)
        with patch.object(stage,'load_descriptor',return_value=selected):
            admitted=stage.admit(checkpoint)
            self.assertTrue(admitted['actual_package_report_bound']);self.assertFalse(admitted['hardware_executed'])
            altered=copy.deepcopy(checkpoint);altered['payload']['media_plan']['preflight']['marker']='wrong'
            with self.assertRaises(ValueError):stage.admit(altered)
            altered=copy.deepcopy(checkpoint);altered['evidence_sha256'].pop(str(Path(protocol.__file__).resolve()))
            with self.assertRaises(ValueError):stage.admit(altered)

    def test_real_recorder_body_capture_return_replay(self):
        text=Path(old.__file__).read_text()
        replacements=(('serial_root_route_trial_v1','serial_guard_composition_trial_v1'),
            ('root_route_trial_v1','guard_composition_trial_v1'),
            ('root_route_evidence_v1','guard_composition_evidence_v1'),
            ('test_pcie_root_route_serial','test_pcie_guard_composition_serial'),
            ('pcie_root_route_serial_core','pcie_guard_composition_serial_core'),
            ('fixture.RootRouteSerialTests()','fixture.GuardCompositionSerialTests()'),
            ('stage.prior.base.loaded_sources()','stage.prior.prior.prior.base.loaded_sources()'))
        for before,after in replacements:
            self.assertIn(before,text);text=text.replace(before,after)
        text=text.replace("        raw = raw.replace(b'OK=1 PHASE=5 LAST=5', b'OK=0 PHASE=6 LAST=14')\n",'')
        text=text.replace("self.assertFalse(observed['diagnostic']['rp1_id_trial_pass'])","self.assertTrue(observed['diagnostic']['bars_trial_pass'])")
        text=text.replace("self.assertFalse(returned['diagnostic']['rp1_id_trial_pass'])","self.assertTrue(returned['diagnostic']['bars_trial_pass'])")
        module=types.ModuleType('_guard_actual_recorder_fixture');module.__file__=old.__file__
        exec(compile(text,old.__file__,'exec'),module.__dict__)
        module.RootRouteTests('test_actual_recorder_full_capture_independent_return_and_failure_guards').test_actual_recorder_full_capture_independent_return_and_failure_guards()


if __name__=='__main__':unittest.main()
