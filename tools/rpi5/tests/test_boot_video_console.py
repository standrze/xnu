# SPDX-License-Identifier: BSD-2-Clause
"""Checked boot ABI and actual Apple dispatch/glyph functions, no physical I/O."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import apple_console_native as native
from tools.rpi5 import console_mirror_overlay as overlay

ROOT=native.ROOT


class BootVideoConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name)
        native.prepare(cls.work)
        for command in native.commands(cls.work).values():
            result=subprocess.run(command,capture_output=True,text=True,timeout=30)
            if result.returncode:raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def run_native(self,name,*args,expected=0):
        result=subprocess.run([str(self.work/name),*args],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,expected,result.stderr)
        if expected==0:self.assertEqual(result.stderr,'')
        return result.stdout

    def test_actual_boot_video_abi_and_ownership_atomic_rejections(self):
        self.assertIn('ACTUAL_ABI=1 SIX_FIELDS_ONLY=1 ATOMIC=1 NO_MAPPING=1',self.run_native('boot-video'))

    def test_original_dispatch_exact_uart_newlines_polls_and_video_gate(self):
        self.assertIn('UART_EXACT=1 ORIGINAL_DISPATCH=1 ORIGINAL_VIDEO_GATE=1 POLL_UART_ONLY=1',self.run_native('console-mirror'))
        self.run_native('console-mirror','invalid-index',expected=91)

    def test_original_renderer_font_attributes_cached_path_padding_and_clear(self):
        self.assertIn('CASES=12288 ORIGINAL_FONT=1 ATTRS=8 GUARDED_ROWS=1 ORIGINAL_CLEAR=1 NO_SCANOUT=1',self.run_native('apple-glyph'))
        self.run_native('apple-glyph','bad-expectation',expected=74)

    def test_overlay_is_exact_single_dispatch_replacement_default_off(self):
        source=overlay.SOURCE.read_text();changed=overlay.overlay(source)
        recovered=changed.replace(overlay.WRAPPER,'').replace(
            '.putc = rpi5_console_mirror_putc, .getc = _serial_getc,',
            '.putc = serial_putc_options, .getc = _serial_getc,')
        self.assertEqual(recovered,source)
        self.assertEqual(overlay.WRAPPER.count('serial_putc_options(c, poll);'),1)
        self.assertNotIn('rpi5_console_mirror_publish();',changed)
        for broken in (source.replace(overlay.ANCHOR,''), source+source):
            with self.assertRaises(ValueError):overlay.overlay(broken)

    def test_actual_boot_helper_a76_freestanding_compile(self):
        for name in ('boot_video.c','boot_args.c','framebuffer_descriptor.c','fdt.c','ranges.c'):
            dep=self.work/(name+'.d');obj=self.work/(name+'.o')
            result=subprocess.run(['xcrun','clang','-target','aarch64-none-elf','-mcpu=cortex-a76',
                '-std=c11','-O2','-ffreestanding','-fno-builtin','-Wall','-Wextra','-Werror',
                '-I',str(ROOT/'loader/rpi5'),'-MD','-MF',str(dep),'-c',str(ROOT/'loader/rpi5'/name),
                '-o',str(obj)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn(name,dep.read_text());self.assertTrue(obj.stat().st_size)


if __name__=='__main__':unittest.main()
