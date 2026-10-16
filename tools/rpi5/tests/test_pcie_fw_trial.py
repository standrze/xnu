# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import copy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/rpi5'))
import build_pcie_fw_trial as builder
import check_pcie_fw_trial_package as checker
import pcie_fw_trial_serial_core as serial


class FirmwareTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=builder.build();cls.package=Path(cls.report['image']).parent

    def test_actual_protocol_cores_and_producer_under_leaf_doubles(self):
        with tempfile.TemporaryDirectory() as name:
            program=Path(name)/'trial'
            sources=[ROOT/'tools/rpi5/tests/pcie_fw_trial_host.c',*(ROOT/'loader/rpi5'/n for n in
                ('pcie_fw_client.c','pcie_irq_mask.c','pcie_watchdog_lease.c'))]
            subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror','-O1','-g',
                '-fsanitize=address,undefined','-I',str(ROOT),'-I',str(ROOT/'loader/rpi5'),
                '-I',str(ROOT/'tools/rpi5/tests/fw_verifier_stubs'),*map(str,sources),'-o',str(program)],
                check=True,timeout=60)
            r=subprocess.run([str(program)],capture_output=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr.decode());self.assertIn(b'ACTUAL_PROTOCOL_CORES_PRODUCER_SERVICE=1',r.stdout)
            self.assertIn(b'RECORD_FAILURES=15 ABI_MUTATIONS=20',r.stdout)
            trace=subprocess.check_output([str(program),'--trace'],timeout=30)
            model=serial.inspect(trace,'0123456789abcdef0123456789abcdef','1'*64,'2'*64)
            self.assertEqual(model['pm_checks'],485)
            self.assertFalse(model['physical_reset_return_proven'])

    def test_actual_emitted_image_firmware_pair_and_no_activation(self):
        r=checker.inspect(self.package)
        self.assertTrue(r['preflight_pass']);self.assertTrue(all(r['leaf_checks'].values()))
        self.assertEqual(len(r['checks']),17)
        self.assertFalse(r['installation_admitted']);self.assertFalse(r['physical_execution'])
        self.assertEqual(r['firmware_sha256'],builder.FIRMWARE_SHA)
        self.assertEqual(subprocess.check_output(['xcrun','llvm-nm','--undefined-only',str(self.package/'probe.elf')],text=True).strip(),'')

    def test_clean_package_import_without_prior_cli_path_setup(self):
        r=subprocess.run(['python3','-c',
            'from tools.rpi5 import build_pcie_fw_trial, check_pcie_fw_trial_package; '
            'assert build_pcie_fw_trial.PROFILE == "pcie-firmware-abi-trial-v1"'],
            cwd=ROOT,capture_output=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr.decode())

    def test_manifest_mutations_refused_without_foreign_path_access(self):
        m=checker.read_manifest(self.package)
        changes={
            'profile':'other','trial_tag':'not-a-tag','firmware_sha256':'0'*64,
            'firmware_manifest_sha256':'0'*64,'firmware_image':'/dev/mmcblk0',
            'physical_execution':True,'firmware_installed':True,'dma':True,'pcie_writes':True,
            'selective_gic_disable_writes':4,'firmware_checks':1,'watchdog_reload_once_seconds':60,
            'image_bytes':1,'sources_stable':False,'commands':[],
            'generated_sha256':{'/dev/mmcblk0':'0'*64},'inputs_sha256':{'/dev/nvme0n1':'0'*64},
            'stack_budget':{},'tool_identity':{},'loads':[],
        }
        for field,value in changes.items():
            bad=copy.deepcopy(m);bad[field]=value
            with self.subTest(field=field),patch.object(checker,'read_manifest',return_value=bad),self.assertRaises(ValueError):
                checker.inspect(self.package)
        with self.assertRaises(ValueError):checker.inspect(ROOT/'build/rpi5/pcie-access-vo0exx93')


if __name__=='__main__':unittest.main()
