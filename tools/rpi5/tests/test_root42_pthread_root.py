# SPDX-License-Identifier: BSD-2-Clause
"""Actual root bytes/identity plus independent omission rejection, no Pi runs."""
import copy
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from tools.rpi5 import check_root42_pthread_root as check
from tools.rpi5 import socket_identity_evidence as evidence
from tools.rpi5.tests import test_root_capacity_package as inherited


class PthreadRootTests(inherited.ExpandedPackageTests):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ,{'RPI5_CAPACITY_ROOT':str(check.PACKAGE)}):super().setUpClass()

    def test_actual_complete_expanded_catalogue(self):
        result=subprocess.run([str(self.program),str(self.tree),'none','0'],capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout.decode()+result.stderr.decode())
        self.assertEqual(result.stderr,b'')
        parsed=evidence.validate(result.stdout,self.report)
        self.assertEqual((parsed['nodes'],parsed['file_hashes']),(42,30))
        self.assertRegex(result.stdout,rb'NATIVE:CALLS=\d+:LEAKS=0:VIOLATIONS=0\n$')

    def test_frozen_root_checker_and_exact_member_scope(self):
        result=check.inspect(check.PACKAGE)
        self.assertEqual(result['root_manifest_sha256'],check.MANIFEST_SHA)
        before=check.old.profile.files_from((check.builder.BASE/'ramdisk.bin').read_bytes())
        self.assertEqual(set(self.files)-set(before),{check.builder.ENTRY})
        self.assertEqual({p for p in before if before[p]!=self.files[p]},{check.builder.IDENTITY})
        self.assertEqual(check.old.profile.sha(self.files[check.builder.ENTRY][0]),check.builder.PTHREAD_SHA)
        self.assertEqual(len(result['required_future_trial_commands']),9)
        for key in ('installed','pi_executed','ssh_daemon','networking'):self.assertIs(result[key],False)

    def test_independent_input_generated_catalog_omissions_rejected(self):
        for key in ('inputs_sha256','generated_sha256'):
            record=copy.deepcopy(self.report);record[key].pop(next(iter(record[key])))
            with self.subTest(key=key),self.assertRaises(ValueError):check.inspect_record(check.PACKAGE,record)
        record=copy.deepcopy(self.report);record['identity_catalog'].pop()
        with self.assertRaises(ValueError):check.inspect_record(check.PACKAGE,record)


if __name__=='__main__':unittest.main()
