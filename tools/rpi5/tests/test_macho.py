# SPDX-License-Identifier: BSD-2-Clause
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location("audit_macho", Path(__file__).parents[1] / "audit_macho.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def fixture():
    data = bytearray(512)
    struct.pack_into("<8I", data, 0, 0xfeedfacf, 0x100000c, 0, 2, 4, 464, 0, 0)
    struct.pack_into("<2I16s4Q4I", data, 32, 0x19, 72, b"__TEXT", 0x1004000,
                     0x4000, 0, 512, 5, 5, 0, 0)
    struct.pack_into("<6I", data, 104, 2, 24, 511, 0, 511, 1)
    struct.pack_into("<2I", data, 128, 0xb, 80)
    struct.pack_into("<4I", data, 208, 5, 288, 6, 68)
    struct.pack_into("<Q", data, 480, 0x1004000 + 496)
    return data


class MachOTests(unittest.TestCase):
    def test_relocation_sites_and_pointer_inventory(self):
        data = fixture() + bytearray(16)
        struct.pack_into("<2I", data, 200, 512, 1)
        struct.pack_into("<2I", data, 512, 496, 6 << 24)
        struct.pack_into("<Q", data, 496, 0x1004000)
        self.assertEqual(audit.inspect(data)["relocation_pointer_destinations"], {"__TEXT": 1})
        for address, bits in [(508, 6 << 24), (0x80000000, 6 << 24),
                              (496, 7 << 24), (496, 14 << 24), (496, 22 << 24)]:
            bad = data.copy()
            struct.pack_into("<2I", bad, 512, address, bits)
            with self.subTest(address=address, bits=bits), self.assertRaises(ValueError):
                audit.inspect(bad)
        struct.pack_into("<I", data, 204, 2)
        struct.pack_into("<2I", data, 520, 496, 6 << 24)
        with self.assertRaisesRegex(ValueError, "duplicate relocation"):
            audit.inspect(data)

    def test_valid_inventory(self):
        result = audit.inspect(fixture())
        self.assertEqual(result["physical_base_mod_32MiB"], 0x1004000)
        self.assertEqual(result["segments"][0]["zero_fill"], 0x4000 - 512)

    def test_truncation(self):
        data = fixture()
        for length in range(len(data)):
            with self.subTest(length=length), self.assertRaises(ValueError):
                audit.inspect(data[:length])

    def test_malformed_contract(self):
        for offset, fmt, value in [
            (8, "I", 2), (20, "I", 8), (36, "I", 0),
            (32, "I", 0x80000028), (64, "Q", 1),
            (80, "Q", 513), (92, "I", 7), (96, "I", 1),
            (124, "I", 2), (156, "I", 1), (188, "I", 1),
            (204, "I", 1), (220, "I", 67), (480, "Q", 0),
        ]:
            data = fixture()
            struct.pack_into("<" + fmt, data, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                audit.inspect(data)


if __name__ == "__main__":
    unittest.main()
