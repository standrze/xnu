# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]


class RP1DecodeCycleTests(unittest.TestCase):
    def test_actual_config_assignment_decode_restore_and_all_failures(self):
        with tempfile.TemporaryDirectory(prefix='rp1-decode-core-') as directory:
            root=Path(directory);program=root/'host'
            for source,target,name in (('rp1_bars_probe_host.c','prior_bars_probe_host.c','prior_bars_test_main'),
                ('rp1_bars_assign_host.c','prior_assign_host.c','prior_assignment_test_main')):
                text=Path(__file__).with_name(source).read_text()
                self.assertEqual(text.count('\nint main(void)\n'),1)
                (root/target).write_text(text.replace('\nint main(void)\n','\nvoid '+name+'(void)\n'))
            sources=('pcie_config','pcie_windows','rp1_bars_probe','rp1_bars_plan','rp1_bars_assign','rp1_decode_cycle')
            compiled=subprocess.run(['xcrun','clang','-std=c11','-D_DARWIN_C_SOURCE','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),'-I',directory,'-I',str(Path(__file__).parent),
                str(Path(__file__).with_name('rp1_decode_cycle_host.c')),
                *[str(ROOT/'loader/rpi5'/(n+'.c')) for n in sources],'-o',str(program)],capture_output=True,text=True,timeout=60)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            result=subprocess.run([program],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr);print(result.stdout,end='')
            self.assertRegex(result.stdout,r'^RP1_DECODE_PASS TRANSACTIONS=34 HALFWORD_COMMAND_WRITES=2 MAPS=2 UNMAPS=2 FAULTS=\d+ NO_NIC_ACCESS=1 NO_HARDWARE=1\n$')

    def test_a76_freestanding_object(self):
        with tempfile.TemporaryDirectory(prefix='rp1-decode-target-') as directory:
            result=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin','-fno-stack-protector',
                '-O2','-Wall','-Wextra','-Werror','-c',str(ROOT/'loader/rpi5/rp1_decode_cycle.c'),
                '-o',str(Path(directory)/'decode.o')],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
