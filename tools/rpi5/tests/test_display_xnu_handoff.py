# SPDX-License-Identifier: BSD-2-Clause
"""Smallest same-boot ownership/type/Boot_Video/map-policy slice; software only."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]
class DisplayXNUHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name)
        cls.sources=[ROOT/'tools/rpi5/tests/display_xnu_handoff_host.c',*[ROOT/'loader/rpi5'/p for p in ('display_xnu_handoff.c','memory_type.c','boot_args.c')]]
        r=subprocess.run(['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
            '-I',str(ROOT/'loader/rpi5'),*map(str,cls.sources),'-o',str(cls.work/'native')],capture_output=True,text=True,timeout=30)
        if r.returncode:raise AssertionError(r.stderr)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_exact_owned_types_handoff_record_and_cache_policy(self):
        r=subprocess.run([self.work/'native'],capture_output=True,text=True,timeout=15)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');self.assertIn('MANAGED_UNCHANGED',r.stdout)
    def test_real_a76_helpers_link_without_undefined_symbols(self):
        objects=[]
        for source in self.sources[1:]:
            obj=self.work/(source.stem+'.o');objects.append(obj)
            r=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align','-ffreestanding','-fno-builtin',
                '-mgeneral-regs-only','-O2','-Wall','-Wextra','-Werror','-c',str(source),'-o',str(obj)],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
        elf=self.work/'NOT_RUN_handoff.elf'
        memory=self.work/'memory.o'
        r=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76','-c',str(ROOT/'loader/rpi5/memory.S'),'-o',str(memory)],capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr);objects.append(memory)
        r=subprocess.run([ROOT/'tools/rpi5/tfa-lld','--no-undefined','-e','rpi5_display_xnu_handoff',*objects,'-o',elf],capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(subprocess.check_output(['xcrun','llvm-nm','--undefined-only',elf],text=True),'')
if __name__=='__main__':unittest.main()
