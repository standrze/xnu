# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import build_pcie_gem_mdio_kernel as b
from tools.rpi5.tests import test_pcie_bounded_log as encoder


class GEMMDIOKernelTests(unittest.TestCase):
    def test_exact_object_delta_and_actual_bounded_encoder(self):
        with tempfile.TemporaryDirectory(prefix='gem-mdio-log-') as name:
            folder=Path(name);overlay=folder/'overlay';sources=b.profile.emit(overlay)
            self.assertEqual([p.name for p in sources],['BCM2712PCIePHYTransport.cpp','rp1_gem_mdio.c'])
            original,current,changes=b.objects(folder);self.assertEqual(len(changes),1);self.assertEqual(len(current),len(original)+1)
            formats=re.findall(r'kprintf\("([^"\n]+)"',(overlay/'BCM2712PCIeIDTrialProgress.inc').read_text())
            self.assertEqual(len(formats),53)
            new=re.findall(r'kprintf\("([^"\n]+)"',b.profile.records());self.assertEqual(len(new),6)
            lines=['int main(void){for(unsigned loc=4;loc<=8;loc+=4)for(unsigned sid=0;sid<2;sid++){','location_size=loc;subsystem=sid;']
            for fmt in new:lines.append('assert(encode('+encoder.c_string(fmt)+','+encoder.values(fmt)+'));')
            lines+=['}assert(encoded_calls==24);printf("MDIO_LOG_PASS CALLS=%u MAX_BYTES=%zu\\n",encoded_calls,max_bytes);return 0;}']
            src=folder/'encoder.c';src.write_text(encoder.encoder_source()+'\n'.join(lines));exe=folder/'encoder'
            result=subprocess.run(['xcrun','clang','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(src),'-o',str(exe)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([exe],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr);print(result.stdout,end='')
            self.assertLess(int(re.search(r'MAX_BYTES=(\d+)',result.stdout)[1]),100)

    def test_actual_link_new_core_and_transport_only(self):
        folder=b.ROOT/'build/rpi5/pcie-gem-mdio-kernel-20261014-v1'
        if not (folder/'manifest.json').exists():self.skipTest('Distinct kernel not yet built')
        m=json.loads((folder/'manifest.json').read_text());b.engine.verify(m['inputs_sha256']|m['generated_sha256'])
        self.assertEqual(m['mdio_contract'],b.contract());self.assertEqual(m['profile'],b.PROFILE)
        self.assertEqual(len(m['compiles']),2);self.assertEqual(len(m['mdio_object_replacements']),1)
        self.assertEqual(m['kernel_sha256'],b.audit.sha(folder/'kernel.rp1-config'))
        self.assertEqual(m['logging_calls'],53);self.assertEqual(m['transport_class_layout']['other_class_imports'],0)
        self.assertTrue(m['owner_client_core_secure_objects_unchanged']);self.assertFalse(m['physical_trial_admitted'])


if __name__=='__main__':unittest.main()
