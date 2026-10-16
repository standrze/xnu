# SPDX-License-Identifier: BSD-2-Clause
"""Run the real corrected observer, preserving every prior fixture check."""
import subprocess
import tempfile
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[3]
TESTS=Path(__file__).resolve().parent

class CheckedRP1Tests(unittest.TestCase):
    def test_bar0_width_cannot_reinterpret_bar1_and_all_prior_failures(self):
        source=(TESTS/'rp1_config_host.c').read_text()
        self.assertEqual(source.count('int main(void)'),1)
        source=source.replace('int main(void)','int original_snapshot_tests(void)')
        source+='''
int main(void) {
    assert(!original_snapshot_tests());
    for(unsigned bits=1;bits<16;bits++) {
        struct fixture f; snapshot_setup(&f);f.m.bytes[1][16]=(unsigned char)bits;
        struct rpi5_rp1_config_snapshot out;memset(&out,0xa5,sizeof out);
        struct rpi5_rp1_config_snapshot saved=out;
        assert(rpi5_rp1_config_snapshot(&f.config,&out)==-4);
        assert(!memcmp(&out,&saved,sizeof out) && !f.m.writes);finish(&f);
    }
    puts("RP1_CHECKED_PASS BAR0_SHAPES=15 NO_HARDWARE=1");return 0;
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            src=Path(temporary)/'checked.c';src.write_text(source)
            program=Path(temporary)/'checked'
            result=subprocess.run(['xcrun','clang','-std=c11','-D_DARWIN_C_SOURCE','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(ROOT),'-I',str(ROOT/'loader/rpi5'),'-I',str(TESTS),
                str(src),str(ROOT/'loader/rpi5/pcie_config.c'),str(ROOT/'loader/rpi5/rp1_config_snapshot_checked.c'),
                '-o',str(program)],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([program],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('FAILURES=416 MUTATIONS=16',result.stdout)
            self.assertIn('RP1_CHECKED_PASS BAR0_SHAPES=15',result.stdout)

if __name__=='__main__':unittest.main()
