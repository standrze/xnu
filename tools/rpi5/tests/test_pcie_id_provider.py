# SPDX-License-Identifier: BSD-2-Clause
import subprocess
import tempfile
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[3]


class PCIeIDProviderTests(unittest.TestCase):
    def test_actual_provider_rp1_transport_and_released_window_phases(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            # Exclude only the separately full-kernel-compiled IOKit boot entry;
            # all six production provider methods are compiled verbatim.
            source=(ROOT/'iokit/Kernel/BCM2712PCIeIDTrial.inc').read_text()
            boundary='/* Distinct IOStartIOKit caller invokes this BEFORE any driver matching'
            self.assertEqual(source.count(boundary),1)
            (directory/'actual-id-provider.inc').write_text(source.split(boundary)[0])
            objects=[]
            for name in ('pcie_config','rp1_config_snapshot_checked','pcie_released_windows'):
                obj=directory/(name+'.o')
                result=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined','-c',str(ROOT/'loader/rpi5'/(name+'.c')),'-o',str(obj)],
                    capture_output=True,text=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stderr);objects.append(obj)
            program=directory/'provider'
            result=subprocess.run(['xcrun','clang++','-std=c++17','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(ROOT),'-I',str(directory),
                str(Path(__file__).with_name('pcie_id_provider_host.cpp')),*map(str,objects),'-o',str(program)],
                capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([program],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertRegex(result.stdout,r'^PCIE_ID_PROVIDER_PASS ACTUAL_METHODS=13 GUARD_FAILURES=\d+ NO_HARDWARE=1\n$')


if __name__=='__main__':unittest.main()
