# SPDX-License-Identifier: BSD-2-Clause
"""Actual distinct XNU allocator overlay, inherited exhaustive host doubles."""
from pathlib import Path
import re
import subprocess
import tempfile
from .test_display_allocate_zero_adapter import DisplayAllocateZeroAdapterTests
from .. import display_xnu_overlays as overlays
ROOT=overlays.ROOT
class DisplayXNUAllocatorTests(DisplayAllocateZeroAdapterTests):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name)
        cls.sources=('display_allocate_transaction.c','display_allocate_wire.c','display_mailbox_fdt.c','fdt.c','fdt_reg.c','ranges.c')
        adapter=cls.work/'display_xnu_allocate.c';adapter.write_text(overlays.allocator(overlays.ALLOCATOR.read_text()))
        harness=cls.work/'host.c';harness.write_text((Path(__file__).with_name('display_allocate_zero_adapter_host.c')).read_text()
            .replace('#include "display_allocate_adapter.h"','#include "display_xnu_allocate.h"')
            .replace('rpi5_display_allocate_run(', 'rpi5_display_xnu_allocate_run('))
        command=['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),
            str(harness),str(adapter),*[str(ROOT/'loader/rpi5'/n) for n in cls.sources],'-o',str(cls.work/'native')]
        result=subprocess.run(command,capture_output=True,text=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)
    def test_only_candidate_prefix_admission_differs_from_frozen_adapter(self):
        old=overlays.ALLOCATOR.read_text();new=overlays.allocator(old)
        strip=lambda text:re.sub(r'/\*.*?\*/','',text,flags=re.S).strip()
        self.assertEqual(strip(new),strip(old.replace('#include "display_allocate_adapter.h"','#include "display_xnu_allocate.h"')
            .replace('rpi5_display_allocate_run(', 'rpi5_display_xnu_allocate_run(')))
    def test_a76_actual_sources(self):
        sources=[self.work/'display_xnu_allocate.c',*[ROOT/'loader/rpi5'/n for n in self.sources]]
        for source in sources:
            result=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align','-ffreestanding','-fno-builtin',
                '-mgeneral-regs-only','-O2','-Wall','-Wextra','-Werror','-I',str(ROOT/'loader/rpi5'),'-c',str(source),'-o',str(self.work/(source.name+'.o'))],
                capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
del DisplayAllocateZeroAdapterTests
