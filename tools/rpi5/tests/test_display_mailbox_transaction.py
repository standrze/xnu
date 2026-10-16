# SPDX-License-Identifier: BSD-2-Clause
"""Native pure mailbox state machine; all device/cache/time callbacks are doubles."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]


class DisplayMailboxTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='display-mailbox-transaction-')
        cls.work=Path(cls.temp.name);cls.native=cls.work/'transaction'
        result=subprocess.run(['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
            '-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),
            str(ROOT/'loader/rpi5/display_mailbox_get.c'),
            str(ROOT/'loader/rpi5/display_mailbox_transaction.c'),
            str(Path(__file__).with_name('display_mailbox_transaction_host.c')),
            '-o',str(cls.native)],capture_output=True,text=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def native_case(self,case,text):
        result=subprocess.run([self.native,case],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,'')
        self.assertEqual(result.stdout,text+'\n')

    def test_count_then_zero_one_or_two_raw_settings_distinct_buffers(self):
        self.native_case('success','DISPLAY_MBOX_SUCCESS PASS COUNT=0,1,2 DISTINCT_BUFFERS=3 RAW_ONLY=1')

    def test_every_callback_owner_revocation_reentrancy_and_input_mutation(self):
        self.native_case('faults','DISPLAY_MBOX_FAULTS PASS CALLBACKS=107 OWNERS=227 NO_RETRY=1 OUTPUT_ATOMIC=1')

    def test_no_unrelated_pop_timeouts_stuck_backward_time_and_corrupt_response(self):
        self.native_case('bounds','DISPLAY_MBOX_BOUNDS PASS MISMATCH_PEEK_POP=0 POLL_CAP=512 CLOCK_FAIL_CLOSED=1')

    def test_pre_admission_bounds_aliases_explicit_address_no_conversion(self):
        self.native_case('admission','DISPLAY_MBOX_ADMISSION PASS NO_ADDRESS_GUESS NO_BUFFER_REUSE NO_HARDWARE')

    def test_a76_freestanding_no_architecture_adapter(self):
        assembly=self.work/'transaction.s';obj=self.work/'transaction.o'
        flags=['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76','-std=c11','-O2',
            '-ffreestanding','-fno-builtin','-fno-stack-protector','-Wall','-Wextra','-Werror',
            '-I',str(ROOT/'loader/rpi5')]
        for option,output in (('-c',obj),('-S',assembly)):
            result=subprocess.run([*flags,option,str(ROOT/'loader/rpi5/display_mailbox_transaction.c'),
                '-o',str(output)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,'')
        self.assertGreater(obj.stat().st_size,0)
        self.assertNotRegex(assembly.read_text(),r'(?m)^\s+(smc|hvc|mrs|msr|dc|ic|sys|dsb|dmb)\s')

    def test_exact_preserved_primary_non_pop_and_current_compatible(self):
        refs=json.loads((ROOT/'tools/rpi5/display_mailbox_transaction_sources.json').read_text())
        self.assertEqual(len(refs['sources']),3)
        for source in refs['sources']:
            raw=(ROOT/source['path']).read_bytes()
            self.assertEqual(len(raw),source['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),source['sha256'])
            self.assertIn('/'+source['commit']+'/',source['url'])
        header=(ROOT/refs['sources'][0]['path']).read_text()
        self.assertRegex(header,r'ARM_0_MAIL0_POL\s+HW_REGISTER_RW\(ARM_SBM_OWN0\+0x90\)\s+/\* none-pop read \*/')
        driver=(ROOT/refs['sources'][1]['path']).read_text()
        self.assertIn('#define MAIL0_POL\t(ARM_0_MAIL0 + 0x10)',driver)
        self.assertIn('.compatible = "brcm,bcm2835-mbox"',driver)
        dts=(ROOT/refs['sources'][2]['path']).read_text()
        self.assertIn('compatible = "brcm,bcm2835-mbox"',dts)
        self.assertIs(refs['hardware_observed'],False);self.assertIs(refs['source_code_imported'],False)


if __name__=='__main__':unittest.main()
