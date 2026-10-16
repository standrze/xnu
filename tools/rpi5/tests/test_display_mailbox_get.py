# SPDX-License-Identifier: BSD-2-Clause
"""Actual pure C framing/validator, no firmware model or hardware claim."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]


class DisplayMailboxGetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name)
        cls.native=cls.work/'display-get'
        command=['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
            '-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),
            str(ROOT/'loader/rpi5/display_mailbox_get.c'),
            str(Path(__file__).with_name('display_mailbox_get_host.c')),'-o',str(cls.native)]
        result=subprocess.run(command,capture_output=True,text=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def run_native(self,case,expected):
        result=subprocess.run([self.native,case],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stderr,'')
        self.assertEqual(result.stdout,expected+'\n')

    def test_exact_requests_whitelist_cap_alignment_and_atomic_capacity(self):
        self.run_native('request','DISPLAY_GET_REQUEST PASS MAX_INDEX=1 EXACT_LENGTHS=28,88 NO_TRANSPORT=1')

    def test_raw_response_only_and_matching_request_identity(self):
        self.run_native('response','DISPLAY_GET_RESPONSE PASS RAW_WORDS=16 NO_FORMAT_OR_ADDRESS_AUTHORITY=1')

    def test_all_framing_bits_truncation_extra_bytes_and_atomic_rejection(self):
        self.run_native('negative','DISPLAY_GET_NEGATIVE PASS FRAMING_TRUNCATION_ALIGN_CASES=670 OUTPUT_ATOMIC=1')

    def test_target_a76_and_exact_source_reference_pins(self):
        obj=self.work/'display-get.o';assembly=self.work/'display-get.s'
        flags=['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
            '-std=c11','-O2','-ffreestanding','-fno-builtin','-fno-stack-protector',
            '-Wall','-Wextra','-Werror','-I',str(ROOT/'loader/rpi5')]
        for option,output in (('-c',obj),('-S',assembly)):
            result=subprocess.run([*flags,option,str(ROOT/'loader/rpi5/display_mailbox_get.c'),
                '-o',str(output)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stderr,'')
        self.assertGreater(obj.stat().st_size,0)
        self.assertNotRegex(assembly.read_text(),r'(?m)^\s+(smc|hvc|mrs|msr|dc|ic|sys)\s')
        refs=json.loads((ROOT/'tools/rpi5/display_mailbox_get_sources.json').read_text())
        self.assertEqual(refs['commit'],'80d4218cb877ccb07d09a9f21f0678e78d8b36f5')
        expected={
            'include/soc/bcm2835/raspberrypi-firmware.h':'4eef64f4ba698648299ea30978df83cc211728d6b7aba9fd1a04df627208e07e',
            'drivers/video/fbdev/bcm2708_fb.c':'ecdfa03f27085b49b5abdb6dcb6c13127613bb443d82819b1a0f1ae781c372c7',
            'drivers/firmware/raspberrypi.c':'df915d2a2c74ac24c684b108930e4fcc37ae0daeac858c50c9961a278d5463cb'}
        self.assertEqual({s['path']:s['sha256'] for s in refs['sources']},expected)
        self.assertEqual(len(refs['sources']),3)
        self.assertEqual(refs['preserved_source_directory'],
            'build/rpi5/display-get-primary-80d4218-20261013')
        preserved=ROOT/refs['preserved_source_directory']
        receipt_bytes=(preserved/'receipt.json').read_bytes()
        self.assertEqual(refs['preserved_receipt_sha256'],
            '6f17e951adc97265c6d0c2515fb62e731c7c708fbe32a2bbdaf8624812888ff4')
        self.assertEqual(hashlib.sha256(receipt_bytes).hexdigest(),
            refs['preserved_receipt_sha256'])
        receipt=json.loads(receipt_bytes)
        self.assertEqual(receipt['commit'],refs['commit'])
        self.assertEqual(receipt['repository'],refs['repository'])
        self.assertEqual({s['path']:s['sha256'] for s in receipt['sources']},expected)
        self.assertEqual(len(receipt['sources']),3)
        for source in receipt['sources']:
            saved_bytes=(preserved/source['path']).read_bytes()
            self.assertEqual(hashlib.sha256(saved_bytes).hexdigest(),source['sha256'])
            self.assertEqual(len(saved_bytes),source['bytes'])
            self.assertEqual(source['url'],'https://raw.githubusercontent.com/raspberrypi/linux/'+
                refs['commit']+'/'+source['path'])
        self.assertIs(receipt['code_imported_into_project'],False)
        self.assertIs(receipt['hardware_queries_performed'],False)
        for source in refs['sources']:
            self.assertEqual(source['url'],refs['repository']+'/blob/'+refs['commit']+'/'+source['path'])
        self.assertIs(refs['hardware_support_observed'],False)
        self.assertIs(refs['raw_response_is_allocation_or_mapping_authority'],False)


if __name__=='__main__':unittest.main()
