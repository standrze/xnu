# SPDX-License-Identifier: BSD-2-Clause
"""Exact fixed adapter, actual recorder API, and typed root45 rollback intake."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import bars_assignment_trial_v1 as stage
from tools.rpi5 import serial_bars_assignment_trial_v1 as recorder
from tools.rpi5 import bars_assignment_evidence_v1 as evidence
from tools.rpi5.tests import test_root_route_trial_v1 as old


class AssignmentControllerTests(unittest.TestCase):
    def test_actual_completed_root45_baseline_without_semantic_replay(self):
        directory=stage.ROOT/'build/rpi5/root45-entropy-restored-20261013'
        seal='d9b79d1f693994bde6a07fbba05747aefd10ad2a57c227a97e7c1562f51e7403'
        plan='a47bf310153c40ad9b1ceb0c2ecc839c02876c7a6fc4ac3190389f0f65853efe'
        with patch.object(stage.ready.checker,'inspect',side_effect=AssertionError('No package compiler replay')),\
            patch.object(stage.prior,'baseline',side_effect=AssertionError('Must use exact root45 typed reader')):
            context=stage.baseline(directory,seal,plan)
        self.assertEqual(len(context['result']['next_catalog']),220)
        self.assertEqual(context['result']['publication']['identity']['boot_id'],'b4facb5d-241b-411f-82a3-5990b2a455ac')
        self.assertEqual(stage.sha(directory/'result.json'),'bf508a933256ac255566e4e3c00ab1374852bc40db0ab20d5713a9202248c3dd')
        for name,value in stage.GOOD.items():
            self.assertEqual(context['result']['publication']['protected_files_sha256'][name],value[1])

    def test_descriptor_digest_and_fixed_execution_authority(self):
        with tempfile.TemporaryDirectory(prefix='assignment-descriptor-negative-',dir=stage.ROOT/'build/rpi5') as name:
            path=Path(name).resolve()/'descriptor.json'
            record=dict(format='rpi5-zero-tx-pcie-case-v3',name='assignment-negative-fixture',
                adapter='pcie-bars-assignment',package=str(stage.ROOT/'build/rpi5/offline-assignment-package'),
                package_manifest_sha256='1'*64,checker=stage.ADAPTER[0],protocol=stage.ADAPTER[1],
                source_sha256={},marker=stage.ADAPTER[2]+'1'*32+' CPUS=1 NO_CPU_ON NO_INIT ZERO_SERIAL_INPUT',
                firmware_sha256='dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b',hardware_allowed=True)
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,'digest differs'):
                stage.get_descriptor({'path':str(path),'sha256':'0'*64})
            for change in ({'adapter':'pcie-guard-composition'},{'hardware_allowed':False},
                {'protocol':'tools.rpi5.stage_pcie_trial_v3'},{'checker':'tools.rpi5.stage_pcie_trial_v3'},
                {'marker':record['marker'].replace('CPUS=1','CPUS=4')},{'firmware_sha256':'0'*64}):
                path.write_text(json.dumps(record|change))
                with self.subTest(change=change),self.assertRaises(ValueError):
                    stage.get_descriptor({'path':str(path),'sha256':stage.sha(path)})

    def test_fixed_adapter_original_bodies_complete_sources(self):
        self.assertEqual(set(stage.get_descriptor.__globals__['ADAPTERS']),{'pcie-bars-assignment'})
        self.assertIs(stage._prepare_install.__code__,stage.prior.prepare_install.__code__)
        for name in ('load_installation','prepare_restore','launch','replay','dispatch'):
            self.assertIs(getattr(stage,name).__code__,getattr(stage.prior,name).__code__)
        self.assertIs(evidence.captured.__code__,evidence.original.captured.__code__)
        self.assertIs(recorder.bindings.__code__,recorder.original.bindings.__code__)
        pins=stage.source_pins()
        for name in ('bars_assignment_trial_v1.py','serial_bars_assignment_trial_v1.py','bars_assignment_evidence_v1.py',
            'tests/test_bars_assignment_trial_v1.py','stage_root45_entropy_trial.py','root45_entropy_trial_core.py'):
            path=stage.ROOT/'tools/rpi5'/name;self.assertEqual(pins[str(path)],stage.sha(path))

    def test_typed_root45_intake_rejects_bad_pair_seal_and_type(self):
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
        from tools.rpi5.tests import test_pcie_bars_assignment_serial as fixture
        from tools.rpi5 import pcie_bars_assignment_serial_core as protocol
        _,report=fixture.BarsAssignmentSerialTests().fixture()
        report['firmware_sha256']='dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b'
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
        replacements=(('serial_root_route_trial_v1','serial_bars_assignment_trial_v1'),
            ('root_route_trial_v1','bars_assignment_trial_v1'),
            ('root_route_evidence_v1','bars_assignment_evidence_v1'),
            ('test_pcie_root_route_serial','test_pcie_bars_assignment_serial'),
            ('pcie_root_route_serial_core','pcie_bars_assignment_serial_core'),
            ('fixture.RootRouteSerialTests()','fixture.BarsAssignmentSerialTests()'),
            ('stage.prior.base.loaded_sources()','stage.prior.prior.prior.base.loaded_sources()'))
        for before,after in replacements:
            self.assertIn(before,text);text=text.replace(before,after)
        text=text.replace("        raw = raw.replace(b'OK=1 PHASE=5 LAST=5', b'OK=0 PHASE=6 LAST=14')\n",'')
        text=text.replace("self.assertFalse(observed['diagnostic']['rp1_id_trial_pass'])","self.assertTrue(observed['diagnostic']['assignment_trial_pass'])")
        text=text.replace("self.assertFalse(returned['diagnostic']['rp1_id_trial_pass'])","self.assertTrue(returned['diagnostic']['assignment_trial_pass'])")
        module=types.ModuleType('_assignment_actual_recorder_fixture');module.__file__=old.__file__
        exec(compile(text,old.__file__,'exec'),module.__dict__)
        module.RootRouteTests('test_actual_recorder_full_capture_independent_return_and_failure_guards').test_actual_recorder_full_capture_independent_return_and_failure_guards()
        module.RootRouteTests('test_launcher_uses_distinct_recorder_and_exact_staged_boot').test_launcher_uses_distinct_recorder_and_exact_staged_boot()
        # Execute the same real receive-only body with a fault after END. The
        # independent return may still occur, but cannot rehabilitate the trial.
        start=text.index('    def test_actual_recorder_full_capture_independent_return_and_failure_guards(self):')
        end=text.index('    def test_final_once_audit_and_prepared_seal(self):',start)
        body=text[start:end]
        before="        report.update(image_sha256='1'*64, firmware_sha256='2'*64)"
        self.assertEqual(body.count(before),1)
        body=body.replace(before,"        self.assertIn(b'RPi: BOOTSYS',raw)\n"
            "        raw=raw.replace(b'RPi: BOOTSYS',b'panic(cpu 0): post-END fixture\\nRPi: BOOTSYS',1)\n"+before)
        before="'--seconds', '600']), 0)"
        self.assertEqual(body.count(before),1);body=body.replace(before,"'--seconds', '600']), 1)")
        body=body[:body.index("            self.assertTrue(observed['trace_capture_valid'])")]
        body+="            self.assertFalse(observed['trace_capture_valid'])\n            self.assertEqual(state['transmitted_bytes'],0)\n"
        scope=dict(module.__dict__);exec(compile('class AssignmentPanicTests(unittest.TestCase):\n'+body,__file__,'exec'),scope)
        scope['AssignmentPanicTests']('test_actual_recorder_full_capture_independent_return_and_failure_guards').test_actual_recorder_full_capture_independent_return_and_failure_guards()


if __name__=='__main__':unittest.main()
