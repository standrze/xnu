# SPDX-License-Identifier: BSD-2-Clause
"""Restored baseline240, fixed GEM authority and actual recorder body."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.rpi5 import gem_identify_trial_v1 as stage
from tools.rpi5 import serial_gem_identify_trial_v1 as recorder
from tools.rpi5 import gem_identify_evidence_v1 as evidence
from tools.rpi5.tests import test_decode_cycle_trial_v1 as previous


class GEMControllerTests(unittest.TestCase):
    def test_actual_completed_decode_baseline_without_compiler_replay(self):
        directory = stage.ROOT / 'build/rpi5/pcie-decode-cycle-restored-20261013'
        seal = 'ed2219ca68a21d0aeffd4415bd0c493f8b67073c5951a0f11d6cb40c2322f15b'
        plan = '44fb310aeb42bff2fcbccf264bacbe262843de8ace59962d269e0186c9cd8ecf'
        with patch.object(stage.prior.prior.prior.prior.prior.descriptors, 'get',
                side_effect=AssertionError('No historical case/compiler replay')):
            context = stage.baseline(directory, seal, plan)
        self.assertEqual(len(context['result']['next_catalog']), 240)
        self.assertEqual(context['result']['publication']['identity']['boot_id'],
            '8f2b1d32-7ea5-4a6c-8856-13126de4f14b')
        self.assertEqual(stage.sha(directory / 'result.json'),
            '7dc7187242609b43689d060901c04aed8d51c7f2598909449a5781d80d52f970')
        for name, value in stage.GOOD.items():
            self.assertEqual(context['result']['publication']['protected_files_sha256'][name], value[1])

    def test_fixed_adapter_original_bodies_and_closed_sources(self):
        self.assertEqual(set(stage.get_descriptor.__globals__['ADAPTERS']), {'pcie-gem-identify'})
        self.assertIs(stage._prepare_install.__code__, stage.prior._prepare_install.__code__)
        for name in ('load_installation', 'prepare_restore', 'launch', 'replay', 'dispatch'):
            self.assertIs(getattr(stage, name).__code__, getattr(stage.prior, name).__code__)
        self.assertIs(evidence.captured.__code__, evidence.original.captured.__code__)
        self.assertIs(recorder.bindings.__code__, recorder.original.bindings.__code__)
        pins = stage.source_pins()
        for name in ('gem_identify_trial_v1.py', 'serial_gem_identify_trial_v1.py',
                'gem_identify_evidence_v1.py', 'tests/test_gem_identify_trial_v1.py'):
            path = stage.ROOT / 'tools/rpi5' / name
            self.assertEqual(pins[str(path)], stage.sha(path))

    def test_fixed_descriptor_rejects_wrong_authority(self):
        with tempfile.TemporaryDirectory(prefix='gem-descriptor-', dir=stage.ROOT / 'build/rpi5') as directory:
            path = Path(directory) / 'descriptor.json'
            record = dict(format='rpi5-zero-tx-pcie-case-v3', name='gem-negative-fixture',
                adapter='pcie-gem-identify', package=str(stage.ROOT / 'build/rpi5/offline-gem-package'),
                package_manifest_sha256='1' * 64, checker=stage.ADAPTER[0], protocol=stage.ADAPTER[1],
                source_sha256={}, marker=stage.ADAPTER[2] + '1' * 32 + ' CPUS=1 NO_CPU_ON NO_INIT ZERO_SERIAL_INPUT',
                firmware_sha256='dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b',
                hardware_allowed=True)
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, 'digest differs'):
                stage.get_descriptor(dict(path=str(path), sha256='0' * 64))
            for change in ({'adapter': 'pcie-decode-cycle'}, {'hardware_allowed': False},
                    {'protocol': 'tools.rpi5.stage_pcie_trial_v3'}, {'checker': 'tools.rpi5.stage_pcie_trial_v3'},
                    {'marker': record['marker'].replace('CPUS=1', 'CPUS=4')}, {'firmware_sha256': '0' * 64}):
                path.write_text(json.dumps(record | change))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    stage.get_descriptor(dict(path=str(path), sha256=stage.sha(path)))

    def test_prepublication_actual_recorder_namespace_and_report(self):
        from tools.rpi5.tests import test_pcie_gem_identify_serial as fixture
        from tools.rpi5 import pcie_gem_identify_serial_core as protocol
        _, report = fixture.GEMIdentifySerialTests().fixture()
        report['firmware_sha256'] = 'dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b'
        selected = dict(protocol=protocol, record=dict(marker=report['marker'],
            firmware_sha256=report['firmware_sha256']))
        pins = stage.source_pins() | {
            str(Path(protocol.__file__).resolve()): stage.sha(protocol.__file__),
            str(Path(recorder.__file__).resolve()): stage.sha(recorder.__file__)}
        checkpoint = dict(payload=dict(media_plan=dict(descriptor={}, preflight=report)), evidence_sha256=pins)
        with patch.object(stage, 'load_descriptor', return_value=selected):
            result = stage.admit(checkpoint)
            self.assertTrue(result['actual_package_report_bound'])
            self.assertFalse(result['hardware_executed'])
            bad = copy.deepcopy(checkpoint); bad['payload']['media_plan']['preflight']['marker'] = 'wrong'
            with self.assertRaises(ValueError): stage.admit(bad)
            bad = copy.deepcopy(checkpoint); bad['evidence_sha256'].pop(str(Path(protocol.__file__).resolve()))
            with self.assertRaises(ValueError): stage.admit(bad)

    def test_real_recorder_capture_return_launcher_and_post_end_fault(self):
        # Reuse the actual complete receive-only fixture, changing only its
        # fixed protocol/controller namespace and exact expected result field.
        text = Path(previous.previous.__file__).read_text()
        start = text.index('    def test_real_recorder_body_capture_return_replay(self):')
        end = text.index("\n\nif __name__", start)
        method = text[start:end]
        replacements = (
            ('serial_bars_assignment_trial_v1', 'serial_gem_identify_trial_v1'),
            ('bars_assignment_trial_v1', 'gem_identify_trial_v1'),
            ('bars_assignment_evidence_v1', 'gem_identify_evidence_v1'),
            ('test_pcie_bars_assignment_serial', 'test_pcie_gem_identify_serial'),
            ('pcie_bars_assignment_serial_core', 'pcie_gem_identify_serial_core'),
            ('fixture.BarsAssignmentSerialTests()', 'fixture.GEMIdentifySerialTests()'),
            ('assignment_trial_pass', 'gem_identify_trial_pass'),
            ('stage.prior.prior.prior.base.loaded_sources()', 'stage.prior.prior.prior.prior.prior.base.loaded_sources()'),
        )
        for old, new in replacements:
            if old not in method: raise ValueError('Actual recorder fixture seam changed: ' + old)
            method = method.replace(old, new)
        scope = dict(previous.previous.__dict__, stage=stage, recorder=recorder, evidence=evidence)
        exec(compile('class ActualGEMRecorderTests(unittest.TestCase):\n' + method,
            __file__, 'exec'), scope)
        scope['ActualGEMRecorderTests']('test_real_recorder_body_capture_return_replay').test_real_recorder_body_capture_return_replay()


if __name__ == '__main__':
    unittest.main()
