# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import build_pcie_phy_reset_kernel as b
from tools.rpi5.tests import test_pcie_bounded_log as encoder


class PHYResetKernelTests(unittest.TestCase):
    def test_actual_encoder_and_two_replacements_two_new_cores(self):
        with tempfile.TemporaryDirectory(prefix='reset-log-') as name:
            folder=Path(name);sources=b.profile.emit(folder/'overlay')
            self.assertEqual(len(sources),4);old,new,delta=b.objects(folder)
            self.assertEqual(len(delta),2);self.assertEqual(len(new),len(old)+2)
            formats=re.findall(r'kprintf\("([^"\n]+)"',b.profile.records());self.assertEqual(len(formats),12)
            lines=['int main(void){for(unsigned loc=4;loc<=8;loc+=4)for(unsigned sid=0;sid<2;sid++){location_size=loc;subsystem=sid;']
            for fmt in formats:lines.append('assert(encode('+encoder.c_string(fmt)+','+encoder.values(fmt)+'));')
            lines+=['}assert(encoded_calls==48);printf("RESET_LOG_PASS CALLS=%u MAX_BYTES=%zu\\n",encoded_calls,max_bytes);return 0;}']
            src=folder/'encoder.c';src.write_text(encoder.encoder_source()+'\n'.join(lines));exe=folder/'encoder'
            r=subprocess.run(['xcrun','clang','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(src),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr);r=subprocess.run([exe],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr);print(r.stdout,end='')

    def test_actual_link(self):
        folder=b.ROOT/'build/rpi5/pcie-phy-reset-kernel-20261014-v2'
        if not (folder/'manifest.json').exists():self.skipTest('Distinct reset kernel not yet built')
        m=json.loads((folder/'manifest.json').read_text());b.engine.verify(m['inputs_sha256']|m['generated_sha256'])
        self.assertEqual(m['reset_contract'],b.contract());self.assertEqual(m['profile'],b.PROFILE)
        self.assertEqual(len(m['compiles']),4);self.assertEqual(len(m['reset_object_replacements']),2)
        self.assertEqual(len(m['reset_added_objects']),2);self.assertEqual(m['kernel_sha256'],b.audit.sha(folder/'kernel.rp1-config'))
        self.assertEqual(m['transport_class_layout']['other_class_imports'],0);self.assertEqual(m['logging_calls'],59)


if __name__=='__main__':unittest.main()
