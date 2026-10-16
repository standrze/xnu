# SPDX-License-Identifier: BSD-2-Clause
"""Offline assignment/restore core with actual size-probe/config transactions."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]


class RP1BarsAssignmentTests(unittest.TestCase):
    def test_actual_probe_assignment_restore_and_fail_closed_boundaries(self):
        with tempfile.TemporaryDirectory(prefix='rp1-bars-assign-') as directory:
            program=Path(directory)/'host'
            prior=Path(__file__).with_name('rp1_bars_probe_host.c').read_text()
            self.assertEqual(prior.count('\nint main(void)\n'),1)
            (Path(directory)/'prior_bars_probe_host.c').write_text(prior.replace(
                '\nint main(void)\n','\nvoid prior_bars_test_main(void)\n'))
            sources=['pcie_config','pcie_windows','rp1_bars_probe','rp1_bars_plan','rp1_bars_assign']
            result=subprocess.run(['xcrun','clang','-std=c11','-D_DARWIN_C_SOURCE',
                '-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),
                '-I',directory,'-I',str(Path(__file__).parent),
                str(Path(__file__).with_name('rp1_bars_assign_host.c')),
                *[str(ROOT/'loader/rpi5'/(name+'.c')) for name in sources],'-o',str(program)],
                text=True,capture_output=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([program],text=True,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            print(result.stdout,end='')
            self.assertRegex(result.stdout,r'^RP1_ASSIGN_PASS MAX_TRANSFERS=76 MAX_WRITES=12 CALLBACK_FAILURES=1760 SOURCE_FAILURES=\d+ REAL_PROBE_CONFIG=1 NO_MEM_ENABLE=1 NO_HARDWARE=1\n$')

    def test_a76_freestanding_object(self):
        with tempfile.TemporaryDirectory(prefix='rp1-bars-assign-target-') as directory:
            result=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin','-fno-stack-protector',
                '-O2','-Wall','-Wextra','-Werror','-c',str(ROOT/'loader/rpi5/rp1_bars_assign.c'),
                '-o',str(Path(directory)/'assign.o')],text=True,capture_output=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
