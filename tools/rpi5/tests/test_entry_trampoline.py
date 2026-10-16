# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compare_native_macho import entry_trampoline


class EntryTrampolineTests(unittest.TestCase):
    def test_direct_branch_contract(self):
        entry = 0xfffffe0007004000
        host = {"entry": entry, "segments": [dict(initprot=5, vmaddr=entry, fileoff=0, filesize=4)]}
        for displacement in (0x100, -0x100):
            symbols = {"__start": entry, "_start_first_cpu": entry+displacement}
            data = struct.pack("<I", 0x14000000 | ((displacement//4) & 0x03ffffff))
            self.assertEqual(entry_trampoline(data, host, symbols), entry+displacement)
            symbols["_start_first_cpu"] += 4
            with self.assertRaisesRegex(ValueError, "target changed"):
                entry_trampoline(data, host, symbols)
        symbols = {"__start": entry, "_start_first_cpu": entry+0x100}
        for instruction in (0x94000040, 0xd503201f, 0xd61f0200):
            with self.assertRaisesRegex(ValueError, "direct B"):
                entry_trampoline(struct.pack("<I", instruction), host, symbols)
        with self.assertRaises(ValueError):
            entry_trampoline(bytes(4), host, {})
        host["segments"][0]["filesize"] = 3
        with self.assertRaisesRegex(ValueError, "file-backed"):
            entry_trampoline(bytes(4), host, symbols)
