# SPDX-License-Identifier: BSD-2-Clause
"""Actual Apple encoder bodies with all52 generated diagnostic formats."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import gem_dma_batch_trial_profile as profile
from tools.rpi5.tests import test_pcie_bounded_log as encoder

class BatchLoggingTests(unittest.TestCase):
    def test_actual_apple_encoder_all52rows_all_location_subsystem_modes(self):
        text=profile.derive()['BCM2712PCIeIDTrialProgress.inc'].decode()
        formats=re.findall(r'kprintf\("([^"\n]+)"',text)
        self.assertEqual(len(formats),52)
        lines=['int main(void){for(unsigned loc=4;loc<=8;loc+=4)for(unsigned sid=0;sid<2;sid++){location_size=loc;subsystem=sid;']
        for fmt in formats:
            values=encoder.values(fmt)
            lines.append('assert(encode('+encoder.c_string(fmt)+(','+values if values else '')+'));')
        lines+=['}assert(encoded_calls==208);printf("BATCH_LOG_PASS CALLS=%u MAX_BYTES=%zu\\n",encoded_calls,max_bytes);return 0;}']
        with tempfile.TemporaryDirectory(prefix='batch-actual-log-') as directory:
            folder=Path(directory);source=folder/'encoder.c';source.write_text(encoder.encoder_source()+'\n'.join(lines));exe=folder/'encoder'
            p=subprocess.run(['xcrun','clang','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(source),'-o',str(exe)],capture_output=True,text=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stderr)
            p=subprocess.run([exe],capture_output=True,text=True,timeout=15)
            self.assertEqual(p.returncode,0,p.stderr);print(p.stdout,end='')

if __name__=='__main__':unittest.main()
