# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import build_pcie_fw_client_kernel as builder


class FirmwareClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory();cls.output=(Path(cls.temporary.name)/'fw-client-kernel').resolve()
        cls.report=builder.build(cls.output)

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    def test_actual_client_pe_and_firmware_producer_service_under_doubles(self):
        with tempfile.TemporaryDirectory() as name:
            output=Path(name)/'client'
            subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined',
                '-I',str(builder.ROOT),'-I',str(builder.ROOT/'firmware/rpi5'),
                '-I',str(builder.ROOT/'tools/rpi5/tests/fw_verifier_stubs'),
                '-I',str(builder.ROOT/'tools/rpi5/tests/pcie_irq_stubs'),
                str(builder.ROOT/'tools/rpi5/tests/pcie_fw_client_host.c'),str(builder.CORE),'-o',str(output)],check=True,timeout=60)
            r=subprocess.run([str(output)],capture_output=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr.decode());self.assertIn(b'REAL_PRODUCER_SERVICE_CLIENT_PE=1',r.stdout)

    def test_actual_initial_transport_guard_and_pe_clients_under_doubles(self):
        with tempfile.TemporaryDirectory() as name:
            out=Path(name)
            source=(self.output/'overlay/BCM2712PCIePHYTransport.cpp').read_text()
            body=source.split('bool BCM2712PCIePHYTransport::runInitialPHY(',1)[1].split('#include "BCM2712PCIeFWTransport.inc"',1)[0]
            (out/'actual-irq-initial.inc').write_text('bool BCM2712PCIePHYTransport::runInitialPHY('+body)
            header=(self.output/'overlay/BCM2712PCIePHYTransport.h').read_text()
            observation=header.split('struct bcm2712_phy_observation {',1)[1].split('};',1)[0]
            (out/'actual-irq-observation.inc').write_text('struct bcm2712_phy_observation {'+observation+'};\n')
            (out/'actual-fw-transport.inc').write_text((self.output/'overlay/BCM2712PCIeFWTransport.inc').read_text())
            common=['-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined','-I',str(builder.ROOT)]
            objects=[]
            for i,p in enumerate((builder.CORE,builder.previous.previous.CORE)):
                obj=out/(str(i)+'.o');subprocess.run(['xcrun','clang','-std=c11',*common,'-c',str(p),'-o',str(obj)],check=True,timeout=60);objects.append(obj)
            output=out/'transport'
            subprocess.run(['xcrun','clang++','-std=c++17',*common,'-I',str(builder.ROOT/'tools/rpi5/tests/pcie_irq_stubs'),
                '-I',str(out),str(builder.ROOT/'tools/rpi5/tests/pcie_fw_transport_host.cpp'),*map(str,objects),'-o',str(output)],check=True,timeout=60)
            r=subprocess.run([str(output)],capture_output=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr.decode());self.assertIn(b'ACTUAL_INITIAL_PE_CORE=1',r.stdout)
            self.assertIn(b'GUARD_PM=14',r.stdout)

    def test_real_complete_kernel_smccc_bytes_entries_and_preserved_inputs(self):
        r=self.report
        self.assertTrue(r['complete_kernel_link_proven']);self.assertTrue(r['actual_smccc_argument_and_frame_bytes'])
        self.assertEqual(len(r['link']['controller_firmware_implementations']),25)
        self.assertEqual(len(r['link']['added_initializers']),7);self.assertEqual(r['new_linker_warnings'],[])
        for p,pin in {**r['inputs_sha256'],**r['generated_sha256']}.items():self.assertEqual(builder.audit.sha(Path(p)),pin)
        for k in ('installed','pi_executed','firmware_installed','ethernet_proven','controller_writes_admitted',
                  'power_domain_ownership_proven','dma_authorized','boot_caller_added','concrete_full_lifecycle_provider_added'):
            self.assertFalse(r[k],k)
        source=(self.output/'overlay/BCM2712PCIePHYTransport.cpp').read_text()
        initial=source.split('bool BCM2712PCIePHYTransport::runInitialPHY(',1)[1]
        steps=('pe_rpi5_watchdog_claim_pcie','claimControllerIRQ','claimControllerFirmware','rpi5_pcie_reset_init')
        positions=[initial.index(s) for s in steps];self.assertEqual(positions,sorted(positions))


if __name__=='__main__':unittest.main()
