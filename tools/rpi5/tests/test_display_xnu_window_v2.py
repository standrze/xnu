# SPDX-License-Identifier: BSD-2-Clause
"""Actual V2 receiver, truthful failed V1 trace, finite host-only timing seam."""
import copy
from datetime import datetime
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import tempfile
import textwrap
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import stage_display_xnu_trial_v2 as stage
from tools.rpi5 import serial_display_xnu_trial_v2 as recorder
from tools.rpi5 import display_xnu_evidence_v2 as evidence
from tools.rpi5 import arm_display_xnu_reboot_v2 as launcher
from tools.rpi5.tests import test_display_xnu_transport as old_tests

ROOT = stage.ROOT
_scope = dict(vars(old_tests), stage=stage, recorder=recorder, evidence=evidence, launcher=launcher)


def bind(fn):
    return types.FunctionType(fn.__code__, _scope, argdefs=fn.__defaults__)


# Reuse the explicit device/clock doubles, not a stand-in recorder. The two
# test-only changes allow loader delay and RX return at exact host boundaries.
_runtime_text = textwrap.dedent(inspect.getsource(old_tests.DisplayXNUTransportTests.runtime))
for _old, _new in (
    ('chunks=[(101.0,initial)]',
     "chunks=[(101.0,p.SD+b'\\r\\n'),(101.0+getattr(self,'boot_delay',0),initial[len(p.SD)+2:])]"),
    ('chunks.append((296.0,tail))', "chunks.append((getattr(self,'tail_at',296.0),tail))"),
):
    if _runtime_text.count(_old) != 1:
        raise ValueError('Exact prior host-double seam changed')
    _runtime_text = _runtime_text.replace(_old, _new)
exec(compile(_runtime_text, __file__, 'exec'), _scope)


class DisplayXNUWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = old_tests.report()
        cls.package = json.loads((stage.PACKAGE/'manifest.json').read_text())

    context = bind(old_tests.DisplayXNUTransportTests.context)
    media = bind(old_tests.DisplayXNUTransportTests.media)
    runtime = _scope['runtime']

    def test_exact_derivation_changes_no_kernel_tx_protocol_or_publisher(self):
        self.assertEqual(recorder.HOST_RETURN_SECONDS, 60+180+15+45)
        self.assertEqual(stage.CONTROLLER, 'display-xnu-config-loader-controller-v2')
        self.assertIs(stage.engine, stage.original.engine)
        self.assertIs(stage.valid_report, stage.original.valid_report)
        self.assertIs(stage._dispatch.__code__, stage.original._dispatch.__code__)
        self.assertIs(stage.prepare_restore.__code__, stage.original.prepare_restore.__code__)
        self.assertIs(stage.main.__code__, stage.original.main.__code__)
        self.assertEqual(recorder.protocol.__file__, old_tests.recorder.protocol.__file__)
        self.assertIn('deadline=sd_time+HOST_RETURN_SECONDS', recorder._text)
        for unchanged in ("deadline=state['admitted_monotonic']+120", 'time.monotonic()>=deadline-45',
                          'Absolute pending-RX TX deadline exhausted'):
            self.assertIn(unchanged, recorder._text)
        self.assertIn('not 0<reset_delta<220', evidence._text)
        context = self.context()
        checkpoint = dict(payload={'media_plan': self.media()}, evidence_sha256=context['evidence'])
        with patch.object(stage.checker, 'inspect', side_effect=AssertionError('No semantic replay')):
            admitted = stage.admit(checkpoint)
        self.assertEqual(admitted['host_sd_to_nvme_seconds'], 300)
        self.assertEqual(admitted['tx_seconds'], 120)
        for change in ({'terminal_watchdog_seconds': 181}, {'watchdog_hardware_timeout_seconds': 16}, {'tag': '0'*32}):
            bad = copy.deepcopy(checkpoint)
            bad['payload']['media_plan']['preflight'].update(change)
            with self.assertRaises(ValueError):
                stage.admit(bad)
        bad = copy.deepcopy(checkpoint)
        bad['evidence_sha256'].pop(str(ROOT/'tools/rpi5/serial_display_xnu_trial_v2.py'))
        with self.assertRaises(ValueError):
            stage.admit(bad)

    def test_actual_failed_capture_is_immutable_and_loader_consumed_budget(self):
        directory = ROOT/'build/rpi5/display-xnu-capture-20261014'
        data = (directory/'serial.bin').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), 'eeda023c6bcd3a50d3948d908ae687b412f1c9cbdd466255481f2ee868fe56bd')
        state = json.loads((directory/'state.json').read_text())
        rows = [json.loads(line) for line in (directory/'receive-events.jsonl').read_text().splitlines()]
        returned = json.loads((directory/'return.json').read_text())
        self.assertEqual(state['status'], 'failed')
        self.assertTrue(state['command_tests_passed'])
        self.assertEqual(state['transmitted_bytes'], 442)
        self.assertFalse(returned['capture_valid'])
        self.assertTrue(returned['independent_normal_nvme_linux_return_verified'])
        self.assertIsNone(recorder.protocol.return_positions(data))
        def when(marker):
            offset = data.index(marker)
            return next(r['monotonic'] for r in rows if r['offset'] <= offset < r['offset']+r['bytes'])
        sd = when(recorder.SD)
        watchdog = when(recorder.protocol.WATCHDOG)
        self.assertGreater(watchdog-sd, 59)
        self.assertLess(watchdog-sd, 60)
        ended = datetime.fromisoformat(state['ended_utc'])
        sd_utc = datetime.fromisoformat(next(r['utc'] for r in rows if r['monotonic'] == sd))
        self.assertGreaterEqual((ended-sd_utc).total_seconds(), 240)
        self.assertLess((ended-sd_utc).total_seconds(), 241)
        # Neither V2 nor a new allowance can certify a raw trace with no tail.
        with self.assertRaises(ValueError):
            evidence.inspect_capture(data, rows, state, state['installation'], state['source_sha256'])

    def test_delayed_loader_return_after_old240_is_captured_without_extending_tx(self):
        self.boot_delay = 50.0
        self.tail_at = 361.0  #260s from SD;210s from fresh watchdog/readiness.
        context = self.context()
        with tempfile.TemporaryDirectory(prefix='display-xnu-v2-late-', dir=ROOT/'build/rpi5') as name:
            directory = Path(name); directory.rmdir()
            rc, sent = self.runtime(context, directory)
            state, observed, _ = evidence.captured(context, directory)
            self.assertEqual(rc, 0, state.get('diagnostic_error'))
            self.assertTrue(observed['capture_valid'])
            self.assertEqual(observed['diagnostic']['sd_to_nvme_seconds'], 260)
            self.assertEqual(observed['diagnostic']['watchdog_ready_to_bootsys_seconds'], 210)
            self.assertEqual(len(sent), 442)
            self.assertLess(state['exchanges'][-1]['response_monotonic'], state['admitted_monotonic']+120)
            self.assertFalse(state['host_return_window']['kernel_deadline_extended'])
            raw = (directory/'serial.bin').read_bytes()
            rows = [json.loads(line) for line in (directory/'receive-events.jsonl').read_text().splitlines()]
            for change in ({'sd_to_nvme_seconds': 301}, {'sd_to_nvme_seconds': 300.0},
                           {'terminal_service_seconds': 181}, {'hardware_countdown_seconds': 16},
                           {'kernel_deadline_extended': True}, {'tx_deadline_extended': 0}):
                bad = copy.deepcopy(state)
                bad['host_return_window'].update(change)
                with self.subTest(window=change), self.assertRaisesRegex(ValueError, 'host-only return window'):
                    evidence.inspect_capture(raw, rows, bad, context['installed'], recorder.bound_sources(context))

    def test_host300_strict_boundary_and_independent_ready220_stay_finite(self):
        context = self.context()
        #80s deliberately exceeds the nominal loader allocation: the final
        #300s cap still does not move. This fixture isolates its exact boundary.
        self.boot_delay = 80.0
        for at, passed in ((400.999, True), (401.0, False), (401.001, False)):
            self.tail_at = at
            with self.subTest(at=at), tempfile.TemporaryDirectory(prefix='display-xnu-v2-bound-', dir=ROOT/'build/rpi5') as name:
                directory = Path(name); directory.rmdir()
                rc, _ = self.runtime(context, directory)
                state, observed, _ = evidence.captured(context, directory)
                self.assertEqual(observed['capture_valid'], passed)
                self.assertEqual(rc, 0 if passed else 1)
                if at > 401:
                    self.assertNotIn(recorder.NVME, (directory/'serial.bin').read_bytes())
        #A return inside300 must still fail when fresh-ready→BOOTSYS exceeds220.
        self.boot_delay = 50.0; self.tail_at = 372.0
        with tempfile.TemporaryDirectory(prefix='display-xnu-v2-ready-', dir=ROOT/'build/rpi5') as name:
            directory = Path(name); directory.rmdir()
            rc, _ = self.runtime(context, directory)
            self.assertEqual(rc, 1)
            self.assertIn('watchdog return exceeded', json.loads((directory/'state.json').read_text())['diagnostic_error'])

    def test_actual_completed384_typed_baseline_no_semantic_replay(self):
        directory = ROOT/'build/rpi5/display-xnu-restored-20261014'
        seal = '67f3a94e6d9df8726bbdaccd69363057d5d2c969bc04a7ab85d031ff12fbe5ba'
        plan = 'eb779553d2bfd71fc353254c01a4496d411ef5690bc810a08a8dfa67225a293c'
        self.assertEqual(stage.sha(directory/'result.json'), 'b657b3f6d51a4b5f0a1210ad5115e8d8bb2b0938459564ae9a1b2bfcd0235044')
        with patch.object(stage.checker, 'inspect', side_effect=AssertionError('No package replay')), \
                patch.object(stage.previous_compact, 'restoration', side_effect=AssertionError('No historical replay')), \
                patch.object(subprocess, 'run', side_effect=AssertionError('No transport/compiler')):
            context = stage.baseline(directory, seal, plan)
            with self.assertRaises(ValueError):
                stage.baseline(directory, '0'*64, plan)
            with self.assertRaises(ValueError):
                stage.baseline(directory, seal, '0'*64)
        self.assertEqual(len(context['result']['next_catalog']), 384)
        self.assertEqual(context['result']['publication']['identity']['boot_id'], '35f6ae79-87c2-48d4-ba11-14a75b1ebf00')


for _name in (
    'test_actual_recorder_four_exchanges_and_independent_return',
    'test_incomplete_admission_is_zero_tx_and_full_recovery_rx',
    'test_echo_only_nonzero_exit_reset_and_full_tail_faults',
    'test_modem_low_read_error_never_arm_receive_or_reboot',
    'test_continuously_readable_rx_stops_tx_at_absolute_deadline',
    'test_one_shot_launcher_exact_actual_armed_schema',
    'test_actual_dispatch_upload_and_unknown_failures_never_retry',
):
    setattr(DisplayXNUWindowTests, _name, bind(getattr(old_tests.DisplayXNUTransportTests, _name)))

if __name__ == '__main__':
    unittest.main()
