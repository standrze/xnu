# SPDX-License-Identifier: BSD-2-Clause
"""Fixed-case adapters, actual recorder body, full return path; no hardware."""
import contextlib
import copy
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import root_route_trial_v1 as stage
from tools.rpi5 import serial_root_route_trial_v1 as recorder
from tools.rpi5 import root_route_evidence_v1 as evidence

ROOT = stage.ROOT
BASELINE = ROOT/'build/rpi5/rp1-config-v3-restored-20261013'
SEAL = '3f61edfb23248147a2758b295b44865065c39a7040b6f80b20377a2f881adaa0'
PLAN = '2af00537d406b32033aa435610bd82e8c657449afad1a2201c8227dfcc58a184'
BOOT = '804c0ee2-a4a2-4db8-acc5-08857c983181'


class RootRouteTests(unittest.TestCase):
    def test_only_fixed_adapter_and_original_guard_bodies(self):
        self.assertEqual(set(stage.get_descriptor.__globals__['ADAPTERS']), {'root-bridge-route'})
        self.assertEqual(stage.ADAPTER[:2], ('tools.rpi5.check_pcie_root_route_package',
                                          'tools.rpi5.pcie_root_route_serial_core'))
        for name in ('prepare_install', 'load_installation', 'prepare_restore', 'launch', 'replay', 'dispatch'):
            self.assertIs(getattr(stage, name).__code__, getattr(stage.prior, name).__code__)
        self.assertIs(evidence.captured.__code__, evidence.original.captured.__code__)
        self.assertIs(recorder.bindings.__code__, recorder.original.bindings.__code__)

    def test_complete_protocol_api_required_before_sealing(self):
        fields = {n: object() for n in ('inspect', 'inventory', 'return_positions', 'BEGIN',
                                      'TRANSFER', 'ENTRY', 'COMMIT', 'PREPARED')}
        fields.update(PREFIX=b'RPI5XNU:PCIEID:', PREPARED_PREFIX=b'RPI5XNU:PCIEID:PREPARED ')
        with patch.object(stage, 'get_descriptor', return_value={'protocol': types.SimpleNamespace(**fields)}):
            stage.load_descriptor({})
        for name in fields:
            changed = dict(fields); changed.pop(name)
            with self.subTest(name=name), patch.object(stage, 'get_descriptor',
                    return_value={'protocol': types.SimpleNamespace(**changed)}), self.assertRaises(ValueError):
                stage.load_descriptor({})

    def test_descriptor_digest_and_module_authority_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix='route-case-negative-', dir=ROOT/'build/rpi5') as name:
            path = Path(name).resolve()/'descriptor.json'
            record = dict(format=stage.prior.descriptors.FORMAT, name='root-route-negative-fixture',
                adapter='root-bridge-route', package=str(ROOT/'build/rpi5/offline-route-package'),
                package_manifest_sha256='1'*64, checker=stage.ADAPTER[0], protocol=stage.ADAPTER[1],
                source_sha256={}, marker=stage.ADAPTER[2]+'1'*32+' CPUS=1 NO_CPU_ON NO_INIT ZERO_SERIAL_INPUT',
                firmware_sha256=stage.prior.descriptors.FIRMWARE_SHA, hardware_allowed=True)
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, 'digest differs'):
                stage.get_descriptor({'path': str(path), 'sha256': '0'*64})
            for change in ({'adapter': 'rp1-config-trace'}, {'hardware_allowed': False},
                           {'protocol': 'tools.rpi5.stage_pcie_trial_v3'},
                           {'checker': 'tools.rpi5.stage_pcie_trial_v3'},
                           {'marker': record['marker'].replace('CPUS=1', 'CPUS=4')}):
                path.write_text(json.dumps(record | change))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    stage.get_descriptor({'path': str(path), 'sha256': stage.sha(path)})

    def test_declared_sources_cover_all_new_bindings(self):
        pins = stage.source_pins()
        for name in ('root_route_trial_v1.py', 'serial_root_route_trial_v1.py',
                     'root_route_evidence_v1.py', 'tests/test_root_route_trial_v1.py'):
            path = ROOT/'tools/rpi5'/name
            self.assertEqual(pins[str(path)], stage.sha(path))

    def test_actual148_restore_intake_keeps_supplemental_provenance(self):
        with patch.object(stage.prior.base.prior, 'validate_result', side_effect=AssertionError('No old semantic replay')):
            prior = stage.baseline(BASELINE, SEAL, PLAN)
        self.assertEqual(len(prior['result']['next_catalog']), 148)
        self.assertEqual(prior['result']['publication']['identity']['boot_id'], BOOT)
        self.assertEqual(prior['result']['publication']['pair_sha256'], {n: r[1] for n, r in stage.GOOD.items()})
        for path in (ROOT/'tools/rpi5/rp1_config_return_compat_v1.py',
                     ROOT/'build/rpi5/rp1-config-v3-serial-20261013/protocol-compatibility.json'):
            self.assertEqual(prior['evidence'][str(path)], stage.sha(path))
        with self.assertRaises(ValueError):
            stage.baseline(BASELINE, '0'*64, PLAN)

    def test_launcher_uses_distinct_recorder_and_exact_staged_boot(self):
        actual_recorder = importlib.import_module('serial_root_route_trial_v1')
        arm = importlib.import_module('arm_pcie_trace_reboot')
        context = dict(descriptor={'hardware_allowed': True}, installed=dict(
            directory=str(ROOT/'build/rpi5/offline-route-install'), original_linux_boot_id=BOOT,
            pair_sha256={'probe.bin': '1'*64, 'bl31.bin': '2'*64}),
            plan={'media': {'identity_binding': {'expected': {'root': '/dev/nvme0n1p2 ext4 fixture'}}}}, evidence={})
        with tempfile.TemporaryDirectory(prefix='route-launch-fixture-', dir=ROOT/'build/rpi5') as name:
            capture = Path(name); capture.rmdir(); calls = []
            def once(output, command, expected, validate, reboot):
                calls.append(command); capture.mkdir()
                stage.save(capture/'armed.json', dict(pid=123, installation=context['installed'],
                    transmitted_bytes=0, device='/dev/cu.usbmodemTEST', baud=115200,
                    source_sha256={}, receipt_evidence_sha256={}))
                validate(123)
                return {'synthetic_no_reboot': True}
            with patch.dict(stage.launch.__globals__, load_installation=lambda *_: context), \
                 patch.object(arm, 'arm_once', side_effect=once), \
                 patch.object(actual_recorder, 'revalidate'), patch.object(actual_recorder, 'bound_sources', return_value={}):
                with self.assertRaisesRegex(ValueError, 'staged Linux boot'):
                    stage.launch('', '', '', '/dev/cu.usbmodemTEST', capture, capture, 'wrong')
                stage.launch('', '', '', '/dev/cu.usbmodemTEST', capture, capture, BOOT)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1], str(ROOT/'tools/rpi5/serial_root_route_trial_v1.py'))

    def test_actual_recorder_full_capture_independent_return_and_failure_guards(self):
        fixture_module = ROOT/'tools/rpi5/tests/test_pcie_root_route_serial.py'
        if not fixture_module.exists(): self.skipTest('Final route protocol fixture is not available yet')
        from tools.rpi5 import pcie_root_route_serial_core as protocol
        fixture = importlib.import_module('tools.rpi5.tests.test_pcie_root_route_serial')
        raw, report = fixture.RootRouteSerialTests().fixture()
        # This fixture is a captured DIAGNOSTIC FAILURE, never actual board proof.
        raw = raw.replace(b'OK=1 PHASE=5 LAST=5', b'OK=0 PHASE=6 LAST=14')
        report.update(image_sha256='1'*64, firmware_sha256='2'*64)
        descriptor = {'protocol': protocol, 'hardware_allowed': True}
        installed = dict(directory=str(ROOT/'build/rpi5/offline-route-install'),
            checkpoint_sha256='1'*64, plan_sha256='2'*64, result_sha256='3'*64,
            preflight=report, pair_sha256={'probe.bin': '1'*64, 'bl31.bin': '2'*64},
            original_linux_boot_id=BOOT)
        identity = json.loads((BASELINE/'plan.json').read_text())['media']['identity_binding']
        context = dict(descriptor=descriptor, installed=installed,
            plan={'media': {'linux_boot_id': BOOT, 'host': stage.HOST, 'identity_binding': identity}},
            evidence=stage.source_pins() | stage.prior.base.loaded_sources())
        with tempfile.TemporaryDirectory(prefix='route-serial-fixture-', dir=ROOT/'build/rpi5') as name, tempfile.TemporaryFile() as uart:
            out = Path(name); out.rmdir()
            chunks = iter(raw.splitlines(keepends=True)); real_open = os.open
            ticks = iter(i/100 for i in range(100000)); captured = io.StringIO()
            fn = recorder.bindings(context); g = fn.__globals__
            def open_(path, *args, **kwargs):
                return os.dup(uart.fileno()) if path == '/dev/cu.usbmodemTEST' else real_open(path, *args, **kwargs)
            with patch.object(g['lease'], 'hold', return_value=contextlib.nullcontext()), \
                 patch.object(g['subprocess'], 'run', return_value=subprocess.CompletedProcess([], 1, '', '')), \
                 patch.object(g['os'], 'open', side_effect=open_), patch.object(g['os'], 'read', side_effect=lambda *_: next(chunks)), \
                 patch.object(g['fcntl'], 'ioctl'), patch.object(g['termios'], 'tcgetattr', side_effect=lambda _: [0,0,0,0,0,0,[0]*32]), \
                 patch.object(g['termios'], 'tcsetattr'), patch.object(g['termios'], 'tcflush'), \
                 patch.object(g['select'], 'select', side_effect=lambda fd, *args: (fd, [], [])), \
                 patch.object(g['time'], 'monotonic', side_effect=lambda: next(ticks)), contextlib.redirect_stdout(captured):
                self.assertEqual(fn(['/dev/cu.usbmodemTEST', str(out), '--installation', installed['directory'], '--seconds', '600']), 0)
            self.assertIn('RP1_TRACE_CAPTURE_ARMED ZERO_SERIAL_TX', captured.getvalue())
            state, observed, _ = evidence.captured(context, out)
            self.assertTrue(observed['trace_capture_valid'])
            self.assertFalse(observed['diagnostic']['rp1_id_trial_pass'])
            def ssh(command, **kwargs):
                self.assertEqual(command, stage.SSH + ['sudo -n python3 -'])
                boot = '11111111-1111-4111-8111-111111111111'
                value = dict(host=stage.HOST, boot_id=boot,
                    identity=dict(identity=identity['expected'], boot_id=boot, hostname='kamidana'),
                    root=identity['expected']['root'].split(), bootloader={'boot-mode':6, 'partition':1, 'tryboot':0},
                    read_only=True, sd_partitions_unmounted=True, observed_utc='2099-01-01T00:00:00+00:00',
                    installation=installed, serial_sha256=state['serial_sha256'], return_source_sha256=evidence.return_source_pins())
                return subprocess.CompletedProcess(command, 0, json.dumps(value), '')
            with patch.object(evidence.collect_return.__globals__['subprocess'], 'run', side_effect=ssh) as called:
                returned = evidence.collect_return(context, out)
            self.assertEqual(called.call_count, 1)
            self.assertTrue(returned['capture_valid']); self.assertFalse(returned['diagnostic']['rp1_id_trial_pass'])
            self.assertEqual(evidence.load_return(context, out)[0], returned)
            wrong = copy.deepcopy(returned); wrong['observation']['root'] = ['/dev/mmcblk0p2', 'ext4', 'wrong']
            (out/'return.json').write_text(json.dumps(wrong))
            with self.assertRaises(ValueError): evidence.load_return(context, out)
            state.update(status='failed', continuous_capture=False, error='explicit fixture downgrade')
            (out/'state.json').write_text(json.dumps(state))
            self.assertFalse(evidence.captured(context, out)[1]['trace_capture_valid'])
            state['transmitted_bytes'] = 1; (out/'state.json').write_text(json.dumps(state))
            with self.assertRaisesRegex(ValueError, 'zero-TX capture'): evidence.captured(context, out)

    def test_final_once_audit_and_prepared_seal(self):
        path = os.environ.get('RPI5_ROUTE_DESCRIPTOR')
        if not path: self.skipTest('Final immutable package and retained descriptor digest required')
        reference = {'path': str(Path(path).resolve()), 'sha256': os.environ['RPI5_ROUTE_DESCRIPTOR_SHA']}
        selected = stage.load_descriptor(reference)
        with patch.object(selected['checker'], 'inspect', wraps=selected['checker'].inspect) as checker, \
             patch.object(stage.prior.base.prior, 'validate_result', side_effect=AssertionError('No historical audit')), \
             patch.object(stage.prior.base, 'full_install_audit', side_effect=AssertionError('No old full audit')):
            checkpoint, pin, metrics = stage.prepare_install(BASELINE, SEAL, PLAN, reference, BOOT)
        self.assertEqual(checker.call_count, 1)
        self.assertEqual(len(checkpoint['payload']['history_catalog']), 148)
        self.assertEqual(metrics['historical_semantic_audit_calls'], 0)
        self.assertIn(str(ROOT/'tools/rpi5/rp1_config_return_compat_v1.py'), checkpoint['evidence_sha256'])
        self.assertEqual(checkpoint['payload']['media_plan']['preflight']['marker'], selected['record']['marker'])
        if output := os.environ.get('RPI5_ROUTE_TEST_OUTPUT'):
            out = stage.local(output); out.mkdir(exist_ok=False)
            stage.seals.save_new(out/'checkpoint.json', checkpoint, pin)
            stage.save(out/'metrics.json', metrics)
            stage.save(out/'validation.json', dict(offline_only=True, hardware_executed=False,
                checkpoint_sha256=pin, metrics=metrics))


if __name__ == '__main__':
    unittest.main()
