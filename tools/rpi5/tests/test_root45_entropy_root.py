# SPDX-License-Identifier: BSD-2-Clause
import copy
import os
import subprocess
import unittest
from unittest.mock import patch
from tools.rpi5 import check_root45_entropy_root as check
from tools.rpi5 import socket_identity_evidence as evidence
from tools.rpi5.tests import test_root_capacity_package as inherited


class EntropyRootTests(inherited.ExpandedPackageTests):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ,{'RPI5_CAPACITY_ROOT':str(check.PACKAGE)}):super().setUpClass()

    def test_actual_complete_expanded_catalogue(self):
        r=subprocess.run([str(self.program),str(self.tree),'none','0'],capture_output=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stdout.decode()+r.stderr.decode());self.assertEqual(r.stderr,b'')
        parsed=evidence.validate(r.stdout,self.report)
        self.assertEqual((parsed['nodes'],parsed['file_hashes']),(45,33))
        self.assertRegex(r.stdout,rb'NATIVE:CALLS=\d+:LEAKS=0:VIOLATIONS=0\n$')

    def test_exact_two_added_files_all_old_executables_unchanged(self):
        report=check.inspect(check.PACKAGE)
        before=check.old.profile.files_from((check.builder.BASE/'ramdisk.bin').read_bytes())
        self.assertEqual(len(before),31)
        self.assertEqual(set(self.files)-set(before),set(check.builder.PROBES))
        self.assertEqual({p for p in before if before[p]!=self.files[p]},{check.builder.IDENTITY})
        for name,row in check.builder.PROBES.items():self.assertEqual(check.old.profile.sha(self.files[name][0]),row[2])
        self.assertEqual(len(report['required_future_trial_commands']),12)
        for key in ('installed','pi_executed','ssh_daemon','networking'):self.assertFalse(report[key])
        self.assertTrue(report['limits']['entropy_not_qualified'])
        self.assertTrue(report['limits']['health_startup_zero_is_observation_not_qualification'])

    def test_actual_closure_scope_and_geometry_tampering_rejected(self):
        for key in ('inputs_sha256','generated_sha256'):
            altered=copy.deepcopy(self.report);altered[key].pop(next(iter(altered[key])))
            with self.assertRaises(ValueError):check.inspect_record(check.PACKAGE,altered)
        for field,value in (('output_nodes',43),('output_files',31),('probe_manifests',{}),
                            ('required_trial_commands',self.report['required_trial_commands'][:-1])):
            altered=copy.deepcopy(self.report);altered[field]=value
            with self.assertRaises(ValueError):check.inspect_record(check.PACKAGE,altered)
        altered=copy.deepcopy(self.report);altered['limits']['entropy_not_qualified']=1
        with self.assertRaises(ValueError):check.inspect_record(check.PACKAGE,altered)


if __name__=='__main__':unittest.main()
