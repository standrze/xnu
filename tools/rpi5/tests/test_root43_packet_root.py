# SPDX-License-Identifier: BSD-2-Clause
import copy
import os
import subprocess
import unittest
from unittest.mock import patch
from tools.rpi5 import check_root43_packet_root as check
from tools.rpi5 import socket_identity_evidence as evidence
from tools.rpi5.tests import test_root_capacity_package as inherited


class PacketRootTests(inherited.ExpandedPackageTests):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ,{'RPI5_CAPACITY_ROOT':str(check.PACKAGE)}):super().setUpClass()

    def test_actual_complete_expanded_catalogue(self):
        r=subprocess.run([str(self.program),str(self.tree),'none','0'],capture_output=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stdout.decode()+r.stderr.decode());self.assertEqual(r.stderr,b'')
        parsed=evidence.validate(r.stdout,self.report)
        self.assertEqual((parsed['nodes'],parsed['file_hashes']),(43,31))
        self.assertRegex(r.stdout,rb'NATIVE:CALLS=\d+:LEAKS=0:VIOLATIONS=0\n$')

    def test_exact_file_change_scope_and_command_set(self):
        report=check.inspect(check.PACKAGE)
        before=check.old.profile.files_from((check.builder.BASE/'ramdisk.bin').read_bytes())
        self.assertEqual(len(before),30)
        self.assertEqual(set(self.files)-set(before),{check.builder.ENTRY})
        self.assertEqual({p for p in before if before[p]!=self.files[p]},{check.builder.IDENTITY})
        self.assertEqual(check.old.profile.sha(self.files[check.builder.ENTRY][0]),check.builder.PACKET_SHA)
        self.assertEqual(len(report['required_future_trial_commands']),10)
        self.assertIn('/usr/local/libexec/xnu/pthreadprobe',report['required_future_trial_commands'])
        for key in ('installed','pi_executed','ssh_daemon','networking'):self.assertFalse(report[key])

    def test_complete_closure_omissions_reject(self):
        for key in ('inputs_sha256','generated_sha256'):
            altered=copy.deepcopy(self.report);altered[key].pop(next(iter(altered[key])))
            with self.assertRaises(ValueError):check.inspect_record(check.PACKAGE,altered)
        altered=copy.deepcopy(self.report);altered['identity_catalog'].pop()
        with self.assertRaises(ValueError):check.inspect_record(check.PACKAGE,altered)


if __name__=='__main__':unittest.main()
