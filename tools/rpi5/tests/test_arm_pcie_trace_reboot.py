# SPDX-License-Identifier: BSD-2-Clause
"""Simulated child outputs: never runs SSH, reboots, or opens a serial port."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from tools.rpi5 import arm_pcie_trace_reboot as launcher


class ArmTests(unittest.TestCase):
    def run_case(self,script,armed=True,raise_reboot=False):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        output=Path(temporary.name)/'run';calls=[];children=[]
        def popen(*a,**kw):
            child=subprocess.Popen(*a,**kw);children.append(child);return child
        def cleanup():
            for child in children:
                if child.poll() is None:child.terminate()
                child.wait(timeout=3)
        self.addCleanup(cleanup)
        def validate(pid):
            calls.append(('armed',pid))
            if not armed:raise ValueError('Invalid actual armed snapshot')
            return {'pid':pid}
        def reboot():
            calls.append(('reboot',))
            if raise_reboot:raise TimeoutError('Ambiguous SSH result')
            return {'no_retry':True}
        return output,calls,lambda:launcher.arm_once(output,[sys.executable,'-u','-c',script],
            'TRACE_CAPTURE_ARMED exact',validate,reboot,timeout=0.3,popen=popen)

    def test_exact_live_armed_before_single_reboot_and_fresh_output_guard(self):
        output,calls,run=self.run_case('import time; print("TRACE_CAPTURE_ARMED exact",flush=True); time.sleep(2)')
        self.assertTrue(run()['reboot_attempted']);self.assertEqual([c[0] for c in calls],['armed','reboot'])
        self.assertTrue((output/'reboot-intent.json').exists());self.assertTrue((output/'reboot-result.json').exists())
        with self.assertRaises(FileExistsError):run()
        self.assertEqual(sum(c[0]=='reboot' for c in calls),1)

    def test_missing_wrong_dead_or_invalid_armed_never_reboots(self):
        for script,armed in (
            ('import time; time.sleep(2)',True),
            ('import time; print("TRACE_CAPTURE_ARMED wrong",flush=True); time.sleep(2)',True),
            ('import time; print("TRACE_CAPTURE_ARMED exact\\nTRACE_CAPTURE_ARMED exact",flush=True); time.sleep(2)',True),
            ('print("not armed")',True),
            ('import time; print("TRACE_CAPTURE_ARMED exact",flush=True); time.sleep(2)',False)):
            with self.subTest(script=script):
                output,calls,run=self.run_case(script,armed)
                with self.assertRaises((ValueError,TimeoutError)):run()
                self.assertNotIn(('reboot',),calls);self.assertFalse((output/'reboot-intent.json').exists())

    def test_exact_armed_from_already_exited_child_never_reboots(self):
        import types
        with tempfile.TemporaryDirectory() as temporary:
            calls=[]
            def popen(*args,**kwargs):
                kwargs['stdout'].write(b'TRACE_CAPTURE_ARMED exact\n')
                return types.SimpleNamespace(pid=17,poll=lambda:0)
            with self.assertRaisesRegex(ValueError,'alive'):
                launcher.arm_once(Path(temporary)/'run',['fixture-only'],'TRACE_CAPTURE_ARMED exact',
                    lambda _:calls.append('validate'),lambda:calls.append('reboot'),timeout=0.2,popen=popen)
            self.assertEqual(calls,[])

    def test_ambiguous_ssh_has_durable_single_intent_and_no_retry(self):
        output,calls,run=self.run_case('import time; print("TRACE_CAPTURE_ARMED exact",flush=True); time.sleep(2)',raise_reboot=True)
        with self.assertRaises(TimeoutError):run()
        self.assertEqual(sum(c[0]=='reboot' for c in calls),1)
        self.assertTrue((output/'reboot-intent.json').exists());self.assertTrue((output/'launcher-failure.json').exists())

    def test_actual_remote_script_wrong_boot_or_root_never_execs_reboot(self):
        from unittest.mock import patch
        import os
        source=launcher.reboot_source('exact-boot',['/dev/nvme0n1p2','ext4','root-uuid'])
        for boot,root in (('wrong-boot','/dev/nvme0n1p2 ext4 root-uuid'),('exact-boot','/dev/mmcblk0p2 ext4 root-uuid')):
            with self.subTest(boot=boot),patch.object(Path,'read_text',return_value=boot),\
                patch.object(subprocess,'check_output',return_value=root),patch.object(os,'execv') as reboot:
                with self.assertRaises(SystemExit):exec(compile(source,'<remote-guard>','exec'),{})
                reboot.assert_not_called()


if __name__=='__main__':unittest.main()
