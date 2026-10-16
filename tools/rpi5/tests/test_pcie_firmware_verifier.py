# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import build_pcie_firmware_verifier as builder


class FirmwareVerifierTests(unittest.TestCase):
    def test_real_core_service_under_sanitizers_with_explicit_hardware_and_abi_doubles(self):
        with tempfile.TemporaryDirectory() as name:
            output=Path(name)/'verifier'
            subprocess.run(['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(builder.ROOT/'firmware/rpi5'),
                '-I',str(builder.ROOT/'tools/rpi5/tests/fw_verifier_stubs'),
                str(builder.ROOT/'tools/rpi5/tests/pcie_firmware_verifier_host.c'),'-o',str(output)],check=True,timeout=60)
            r=subprocess.run([str(output)],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr);self.assertIn('FW_VERIFIER_HOST_PASS',r.stdout)

    def test_original_firmware_and_checkout_preserved(self):
        self.assertEqual(builder.sha(builder.UPSTREAM/'build/rpi5/debug/bl31.bin'),builder.ORIGINAL_SHA)
        self.assertEqual(subprocess.check_output(['git','-C',str(builder.UPSTREAM),'status','--porcelain'],text=True),'')

    def test_actual_distinct_firmware_build_and_runtime_descriptor(self):
        with tempfile.TemporaryDirectory(prefix='fw-verifier-test-',dir=builder.ROOT/'build/rpi5') as name:
            # builder requires a fresh direct child, so use the allocated name
            # only as a uniqueness witness; do not overwrite its directory.
            output=Path(name+'-build')
            r=builder.build(output)
            self.assertTrue(r['actual_service_registered']);self.assertTrue(r['one_attempt_lock'])
            self.assertFalse(r['installed']);self.assertFalse(r['controller_writes']);self.assertFalse(r['dma_authorized'])
            for p,pin in {**r['inputs_sha256'],**r['generated_sha256']}.items():self.assertEqual(builder.sha(Path(p)),pin)
            with self.assertRaises(FileExistsError):builder.build(output)


if __name__=='__main__':unittest.main()
