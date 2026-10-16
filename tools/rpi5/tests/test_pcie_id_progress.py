# SPDX-License-Identifier: BSD-2-Clause
import subprocess
import tempfile
from pathlib import Path
import unittest
from tools.rpi5 import build_pcie_id_progress_kernel as builder


class PCIeIDProgressTests(unittest.TestCase):
    def test_last_phase_survives_repeated_failure_without_extra_access(self):
        header=(builder.BASE/'overlay/BCM2712PCIePHYTransport.h').read_text()
        transformed=builder.transform_header(header)
        self.assertIn(builder.SET_PHASE,transformed)
        self.assertEqual(transformed.count('unsigned trialLastPhase ='),1)
        source='''
#include <cassert>
enum {BCM2712_PHY_EMPTY=0,BCM2712_PHY_PREPARED=1,BCM2712_PHY_FAILED=6};
struct State {
 unsigned trialLastPhase=0,phase=0;
'''+builder.SET_PHASE+'''
};
int main(){State s; s.setPhase(1);assert(s.phase==1&&s.trialLastPhase==1);
s.setPhase(11);assert(s.phase==11&&s.trialLastPhase==11);
s.setPhase(6);s.setPhase(6);assert(s.phase==6&&s.trialLastPhase==11);
State fresh;fresh.setPhase(6);assert(fresh.phase==6&&fresh.trialLastPhase==0);}
'''
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);(path/'state.cpp').write_text(source)
            subprocess.run(['xcrun','clang++','-std=c++17','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined',str(path/'state.cpp'),'-o',str(path/'state')],check=True)
            subprocess.run([path/'state'],check=True)

    def test_only_terminal_report_changes_in_provider_source(self):
        body=builder.previous.BODY.read_text();new=builder.transform_body(body)
        boundary='/* Distinct IOStartIOKit caller invokes this BEFORE any driver matching'
        self.assertEqual(body.split(boundary)[0],new.split(boundary)[0])
        self.assertIn('END OK=%u PHASE=%u LAST=%u LIFE=%u FLAGS=%02x ID=%08x',new)
        self.assertEqual(body.count('kprintf('),new.count('kprintf('))
        for token in ('reinterpret_cast','trialAdmission','trialDisableMSI','wfi'):
            self.assertEqual(body.count(token),new.count(token))


if __name__=='__main__':unittest.main()
