# SPDX-License-Identifier: BSD-2-Clause
import struct
import unittest

from tools.rpi5.audit_zsh_pi_binary import immediate_x16, inventory, source_tables, text_section
from tools.rpi5.tests.test_prepare_pid1 import fixture


class ZshPiBinaryTests(unittest.TestCase):
    def macho(self):
        data = fixture()
        thread = bytes(data[104:392])
        struct.pack_into("<I", data, 20, 440)
        struct.pack_into("<I", data, 36, 152)
        struct.pack_into("<I", data, 32 + 64, 1)
        data[184:472] = thread
        struct.pack_into("<Q", data, 184 + 16 + 256, 0x1000001e0)
        struct.pack_into("<16s16sQQ8I", data, 104, b"__text", b"__TEXT",
                         0x1000001e0, 16, 480, 2, 0, 0, 0x80000400, 0, 0, 0)
        data[480:496] = self.fixture()[0]
        return data

    def test_instruction_section_bounds_and_mapping(self):
        data = self.macho()
        self.assertEqual(text_section(data), (0x1000001e0, self.fixture()[0]))
        for offset, value, fmt in ((104 + 32, 0x1000001e4, "Q"),
                                   (104 + 40, 17, "Q"), (104 + 48, 508, "I"),
                                   (104 + 64, 0, "I"), (32 + 64, 2, "I")):
            bad = self.macho()
            struct.pack_into("<" + fmt, bad, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                text_section(bad)

    def fixture(self):
        # MOVZ x16,3; SVC 0x80; MOVN x16,27; SVC 0x80.
        code = struct.pack("<IIII", 0xd2800070, 0xd4001001, 0x92800370, 0xd4001001)
        listing = ("1000 <_read>:\n1000: mov x16, #3\n1004: svc #0x80\n"
                   "1008 <_task>:\n1008: mov x16, #-28\n100c: svc #0x80\n")
        return code, listing

    def test_complete_raw_bound_inventory_is_not_runtime_proof(self):
        code, listing = self.fixture()
        report = inventory(code, 0x1000, listing, {3: {"read"}}, {28: {"task_self_trap"}})
        self.assertEqual(report["instruction_words"], 4)
        self.assertEqual(report["trap_count"], 2)
        self.assertEqual(report["unresolved_immediate_sites"], 0)
        a, b = report["trap_sites"]
        self.assertEqual((a["kind"], a["immediately_preceding_x16"]), ("bsd", 3))
        self.assertEqual((b["kind"], b["immediately_preceding_x16"]), ("mach", -28))
        self.assertFalse(a["runtime_argument_and_result_contract_proven"])

    def test_gaps_duplicates_incomplete_and_raw_svc_mismatch_rejected(self):
        code, listing = self.fixture()
        for bad in (listing.replace("1004:", "1000:"), listing.replace("1004:", "1005:"),
                    listing.replace("1004: svc #0x80\n", ""),
                    listing.replace("1004: svc", "1004: nop")):
            with self.subTest(listing=bad), self.assertRaises(ValueError):
                inventory(code, 0x1000, bad, {}, {})

    def test_no_cross_symbol_or_register_derived_resolution(self):
        code, listing = self.fixture()
        listing = listing.replace("1004: svc", "1004 <_other>:\n1004: svc")
        result = inventory(code, 0x1000, listing, {}, {})
        self.assertIsNone(result["trap_sites"][0]["immediately_preceding_x16"])
        self.assertIsNone(immediate_x16(0xaa0003f0))  # MOV x16,x0.
        self.assertIsNone(immediate_x16(0xf2800070))  # MOVK is not a complete value.
        self.assertEqual(immediate_x16(0xd2b00010), 0x80000000)

    def test_conditional_source_variants_remain_visible(self):
        bsd = "#if FEATURE\n3 AUE_NULL ALL { long read(int fd); }\n#else\n3 AUE_NULL ALL { int nosys(void); }\n#endif"
        mach = "/* 28 */ MACH_TRAP(task_self_trap, 0, 0, NULL),"
        calls, traps = source_tables(bsd, mach)
        self.assertEqual(calls[3], {"read", "nosys"})
        self.assertEqual(traps[28], {"task_self_trap"})


if __name__ == "__main__":
    unittest.main()
