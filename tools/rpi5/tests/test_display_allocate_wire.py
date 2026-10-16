# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]
class DisplayAllocateWireTests(unittest.TestCase):
    def test_actual_wire_schema_mutations_sanitized(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/'wire';r=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),str(ROOT/'tools/rpi5/tests/display_allocate_wire_host.c'),str(ROOT/'loader/rpi5/display_allocate_wire.c'),'-o',str(exe)],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run([exe],capture_output=True,text=True,timeout=10);self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');self.assertIn('framing_faults=2400',r.stdout)
    def test_exact_transport_callback_guards_unchanged(self):
        old=(ROOT/'loader/rpi5/display_mailbox_transaction.c').read_text();new=(ROOT/'loader/rpi5/display_allocate_transaction.c').read_text()
        start='static int intact(';end='static int transaction('
        self.assertEqual(old[old.index(start):old.index(end)],new[new.index(start):new.index(end)])
        for macro in ('RPI5_DISPLAY_MBOX_MAX_POLLS','RPI5_DISPLAY_MBOX_MAX_CALLBACKS','RPI5_DISPLAY_MBOX_MAX_DURATION_US'):
            self.assertEqual(old.count(macro),new.count(macro))
if __name__=='__main__':unittest.main()
