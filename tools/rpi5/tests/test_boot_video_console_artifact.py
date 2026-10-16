# SPDX-License-Identifier: BSD-2-Clause
"""Freshly built offline target closure; no target execution or extra compilation."""
import copy
import json
import os
from pathlib import Path
import unittest
from tools.rpi5 import check_boot_video_console as check


@unittest.skipUnless(os.environ.get('RPI5_BOOT_VIDEO_PACKAGE'), 'select an actual distinct offline artifact')
class BootVideoArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=Path(os.environ['RPI5_BOOT_VIDEO_PACKAGE']).resolve()
        cls.report=json.loads((cls.directory/'manifest.json').read_text())
        cls.pin=check.build.sha(cls.directory/'manifest.json')

    def test_actual_target_and_all_consumed_source_headers(self):
        result=check.inspect(self.directory,self.pin)
        self.assertTrue(result['one_kernel_object_replaced']);self.assertFalse(result['mirror_enabled'])
        self.assertFalse(result['mapping_or_scanout_proven']);self.assertEqual(result['native_renderer_cases'],12288)
        with self.assertRaises(ValueError):check.inspect(self.directory,'0'*64)

    def test_omitted_current_header_original_source_and_artifact_rejected(self):
        for table,key in [('inputs_sha256',str(check.overlay.HEADER)),
                          ('inputs_sha256',str(check.build.native.VIDEO)),
                          ('actual_headers_sha256',str(check.overlay.HEADER)),
                          ('generated_sha256',str(self.directory/'NOT_RUN_boot_video.elf'))]:
            report=copy.deepcopy(self.report);del report[table][key]
            with self.subTest(table=table,key=key),self.assertRaises(ValueError):check.validate(report,self.directory)

    def test_forged_scope_object_or_byte_digest_rejected(self):
        for key,value in [('mirror_has_enable_callsite',True),('pi_executed',True),
                          ('original_kprintf_object_unchanged',1),('replaced_objects',{}),
                          ('kernel_sha256','0'*64)]:
            report=copy.deepcopy(self.report);report[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):check.validate(report,self.directory)
        data=bytearray((self.directory/'NOT_RUN_boot_video.elf').read_bytes());data[18]=0
        with self.assertRaises(ValueError):check.build.elf_symbols(data)


if __name__=='__main__':unittest.main()
