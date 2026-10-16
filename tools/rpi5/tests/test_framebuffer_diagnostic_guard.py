# SPDX-License-Identifier: BSD-2-Clause
"""Actual early precheck body with explicit register/UART/FDT-result doubles."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from .test_framebuffer_observation_guard import FramebufferObservationGuardTests
ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/'loader/rpi5/probe_framebuffer_diagnostic_main.c'
class DiagnosticGuardTests(unittest.TestCase):
    def test_original_watchdog_byte_path_unchanged(self):
        old=(ROOT/'loader/rpi5/probe_framebuffer_observe_main.c').read_text();new=SOURCE.read_text()
        self.assertEqual(old[:old.index('void probe_main(')],new[:new.index('/* The early UART')])
        self.assertLess(new.index('rpi5_uart_snapshot(UART,&uart)'),new.index('rpi5_fdt_structure(fdt,size)'))
        self.assertLess(new.index('RPI5XNU:FBOBS:ENTRY TAG='),new.index('rpi5_fdt_structure(fdt,size)'))
    def test_actual_each_precheck_failure_has_ordered_early_evidence(self):
        s=SOURCE.read_text();body=s[s.index('static void check('):s.index('void probe_el1_main(')]
        body,n=re.subn(r'__asm__ volatile\("mrs %0,([a-zA-Z0-9_]+)":"=r"\(([a-z]+)\)\);',lambda m:m[2]+'=reg("'+m[1]+'");',body)
        self.assertEqual(n,5);self.assertNotIn('__asm__',body)
        template=Path(__file__).with_name('framebuffer_diagnostic_precheck_host.c').read_text()
        self.assertEqual(template.count('/* ACTUAL_SOURCE */'),1)
        with tempfile.TemporaryDirectory() as work:
            p=Path(work);(p/'test.c').write_text(template.replace('/* ACTUAL_SOURCE */',body))
            r=subprocess.run(['xcrun','clang','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                '-I',str(ROOT/'loader/rpi5'),str(p/'test.c'),'-o',str(p/'test')],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
            for stage in range(18):
                r=subprocess.run([str(p/'test'),str(stage)],capture_output=True,text=True,timeout=10)
                self.assertEqual((r.returncode,r.stderr),(0,''),r.stderr)
                expected=range(1,(stage or 17)+1)
                self.assertEqual(re.findall(r'CHECK STAGE=0x([0-9A-F]+)',r.stdout),[f'{n:016X}' for n in expected])
                if stage:
                    self.assertIn(f'REJECT STAGE=0x{stage:016X} RC=0xFFFFFFFFFFFFFFFF',r.stdout)
                    from tools.rpi5 import framebuffer_diagnostic_serial as protocol
                    report=dict(profile=protocol.PROFILE,tag='0123456789abcdef0123456789abcdef')
                    result=protocol.inspect(r.stdout.encode(),report)
                    self.assertEqual(result['failed_stage'],stage);self.assertFalse(result['complete_observation'])
if __name__=='__main__':unittest.main()
