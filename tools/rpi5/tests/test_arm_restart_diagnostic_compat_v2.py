# SPDX-License-Identifier: BSD-2-Clause
"""Run actual arm_once recognition and unchanged launch/armed.json validation.

Children are local Python fixture processes, never the target/UART recorder.
The SSH callback is an explicit double; there are no hardware operations.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

from tools.rpi5 import arm_restart_diagnostic_compat_v2 as adapter

stage = adapter.stage
recorder = adapter.recorder
ROOT = stage.ROOT
INSTALLATION = ROOT/'build/rpi5/restart-diagnostic-installed-20261014'
SEAL = 'c60850eccfb96d7427da7e481489e9648ba8dfe0ec4752d706555d09a0ad2ef2'
PLAN = '7f36b928660d34773e65de43b3034e56df59d52400073fe46ddb7e4adcbb0ab5'
RESULT = '4015f4b51210e02ea60030c930b26b39bc0c08b9dca70ffdf04e341e04bd51e8'
DEVICE = '/dev/cu.usbmodemFixture'


class RestartLauncherCompatibilityTests(unittest.TestCase):
    def line(self):
        return recorder.armed_line(json.loads(stage.REPORT.read_text()))

    def case(self, lines=None, implementation=None, invalid=False, ambiguous=False):
        temporary = tempfile.TemporaryDirectory(prefix='restart-arm-')
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name)/'run'
        calls = []
        children = []
        real_popen = subprocess.Popen
        def popen(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            return child
        def cleanup():
            for child in children:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=3)
        self.addCleanup(cleanup)
        def validate(pid):
            calls.append(('validate', pid))
            if invalid:
                raise ValueError('Invalid armed receipt double')
            return {'pid': pid}
        def reboot():
            calls.append(('reboot',))
            if ambiguous:
                raise TimeoutError('Unknown SSH outcome double')
            return {'verification_marker_observed': True, 'no_retry': True}
        script = 'import time\n'
        if lines is not None:
            script += 'print('+repr('\n'.join(lines))+',flush=True)\n'
        script += 'time.sleep(3)\n'
        invoke = implementation or adapter.arm_once
        def run():
            return invoke(output, [sys.executable, '-u', '-c', script], self.line(),
                validate, reboot, timeout=0.4, popen=popen)
        return output, calls, run

    def test_original_negative_then_exact_live_line_and_single_intent(self):
        self.assertNotIn('CAPTURE_ARMED', self.line())
        output, calls, run = self.case([self.line()], adapter.original_arm.arm_once)
        with self.assertRaises(TimeoutError):
            run()
        self.assertEqual(calls, [])
        self.assertFalse((output/'reboot-intent.json').exists())
        output, calls, run = self.case([self.line()])
        self.assertTrue(run()['reboot_attempted'])
        self.assertEqual([c[0] for c in calls], ['validate', 'reboot'])
        self.assertTrue((output/'reboot-intent.json').exists())
        with self.assertRaises(FileExistsError):
            run()
        self.assertEqual(sum(c[0] == 'reboot' for c in calls), 1)

    def test_wrong_duplicate_missing_and_invalid_receipt_never_reboot(self):
        for lines, invalid in (([self.line()+' wrong'], False),
                ([self.line(), self.line()], False), (None, False),
                (['OTHER_CAPTURE_ARMED'], False), ([self.line()], True)):
            with self.subTest(lines=lines, invalid=invalid):
                output, calls, run = self.case(lines, invalid=invalid)
                with self.assertRaises((ValueError, TimeoutError)):
                    run()
                self.assertNotIn(('reboot',), calls)
                self.assertFalse((output/'reboot-intent.json').exists())

    def test_dead_child_and_expired_or_dead_during_validation(self):
        for mode in ('dead', 'expires', 'dies'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as name:
                calls = []
                alive = [mode != 'dead']
                def spawn(*args, **kwargs):
                    kwargs['stdout'].write((self.line()+'\n').encode())
                    return types.SimpleNamespace(pid=17, poll=lambda: None if alive[0] else 0)
                def validate(pid):
                    if mode == 'expires':
                        time.sleep(0.04)
                    if mode == 'dies':
                        alive[0] = False
                    return {'pid': pid}
                with self.assertRaises(ValueError):
                    adapter.arm_once(Path(name)/'run', ['fixture-only'], self.line(),
                        validate, lambda: calls.append('reboot'), timeout=0.02, popen=spawn)
                self.assertEqual(calls, [])

    def test_ambiguous_callback_is_durable_no_retry(self):
        output, calls, run = self.case([self.line()], ambiguous=True)
        with self.assertRaises(TimeoutError):
            run()
        self.assertEqual(sum(c[0] == 'reboot' for c in calls), 1)
        self.assertTrue((output/'reboot-intent.json').exists())
        self.assertTrue(json.loads((output/'launcher-failure.json').read_text())['reboot_attempted'])
        with self.assertRaises(FileExistsError):
            run()

    def context(self):
        with patch.object(subprocess, 'run', side_effect=AssertionError('No compiler/history/transport')), \
                patch.object(stage.checker, 'inspect', side_effect=AssertionError('No package replay')):
            return adapter.load_context(INSTALLATION, SEAL, PLAN, RESULT,
                stage.sha(adapter.SELF), stage.sha(adapter.TEST))

    def test_actual_installed_byte_intake_and_separate_pin_negatives(self):
        context = self.context()
        self.assertEqual(context['installed']['result_sha256'], RESULT)
        self.assertEqual(context['installed']['original_linux_boot_id'], '5893543b-80df-4594-bef7-9e6c4833a8b4')
        self.assertNotIn(str(adapter.SELF), context['checkpoint']['evidence_sha256'])
        self.assertNotIn(str(adapter.TEST), context['checkpoint']['evidence_sha256'])
        actual = (SEAL, PLAN, RESULT, stage.sha(adapter.SELF), stage.sha(adapter.TEST))
        for index in range(len(actual)):
            with self.subTest(index=index):
                bad = list(actual)
                bad[index] = '0'*64
                with patch.object(subprocess, 'run', side_effect=AssertionError('No external call')), \
                        self.assertRaises(ValueError):
                    adapter.load_context(INSTALLATION, *bad)

    def test_actual_original_launch_body_and_real_child_armed_schema(self):
        context = self.context()
        with tempfile.TemporaryDirectory(prefix='restart-launch-', dir=ROOT/'build/rpi5') as name:
            temporary = Path(name)
            # Canonical launcher paths must be direct build/rpi5 children.
            capture = ROOT/'build/rpi5'/(temporary.name+'-capture')
            output = ROOT/'build/rpi5'/(temporary.name+'-launch')
            self.addCleanup(lambda: __import__('shutil').rmtree(capture, ignore_errors=True))
            self.addCleanup(lambda: __import__('shutil').rmtree(output, ignore_errors=True))
            template = recorder.initial(context, DEVICE, 17, '2026-10-14T04:50:00+00:00')
            template.update(armed_utc='2026-10-14T04:50:00+00:00', armed_monotonic=1.0)
            stage.save(temporary/'armed-template.json', template)
            real_popen = subprocess.Popen
            children = []
            calls = []
            def spawn(command, **kwargs):
                self.assertEqual(command[1], str(Path(recorder.__file__).resolve()))
                self.assertEqual(command[2:4], [DEVICE, str(capture)])
                supplement = json.loads((output/'launcher-supplement.json').read_text())
                self.assertFalse(supplement['supplemental_was_in_original_installation_seal'])
                self.assertEqual(supplement['installation'], context['installed'])
                script = ('import json,os,time\nfrom pathlib import Path\n'
                    'p=Path('+repr(str(capture))+');p.mkdir()\n'
                    'a=json.loads(Path('+repr(str(temporary/'armed-template.json'))+').read_text())\n'
                    'a["pid"]=os.getpid()\n(p/"armed.json").write_text(json.dumps(a))\n'
                    'print('+repr(self.line())+',flush=True)\ntime.sleep(30)\n')
                child = real_popen([sys.executable, '-u', '-c', script], **kwargs)
                children.append(child)
                return child
            def cleanup():
                for child in children:
                    if child.poll() is None:
                        child.terminate()
                    child.wait(timeout=3)
            self.addCleanup(cleanup)
            def ssh(command, **kwargs):
                self.assertEqual(command, stage.SSH+['sudo -n python3 -'])
                self.assertIn(context['installed']['original_linux_boot_id'], kwargs['input'])
                self.assertEqual(kwargs['timeout'], 30)
                self.assertTrue((output/'reboot-intent.json').exists())
                self.assertEqual(json.loads((output/'reboot-intent.json').read_text())['armed']['launcher_supplement_sha256'],
                    stage.sha(output/'launcher-supplement.json'))
                calls.append('ssh')
                return subprocess.CompletedProcess(command, 0, 'VERIFIED_SSD_LINUX_REBOOT_ONCE {}\n', '')
            with patch.object(subprocess, 'Popen', side_effect=spawn), patch.object(subprocess, 'run', side_effect=ssh):
                result = adapter.launch(context, DEVICE, capture, output,
                    context['installed']['original_linux_boot_id'], stage.sha(adapter.SELF), stage.sha(adapter.TEST))
            self.assertTrue(result['reboot_attempted'])
            self.assertEqual(calls, ['ssh'])
            self.assertTrue(result['result']['verification_marker_observed'])
            self.assertEqual(json.loads((capture/'armed.json').read_text())['source_sha256'], recorder.bound_sources(context))


if __name__ == '__main__':
    unittest.main()
