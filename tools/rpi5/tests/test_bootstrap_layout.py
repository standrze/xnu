# SPDX-License-Identifier: BSD-2-Clause
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("bootstrap_layout", Path(__file__).parents[1] / "bootstrap_layout.py")
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


def fixture():
    return dict(phys_base=0, virt_base=layout.LINK_BASE - 0x1004000,
                mem_size=1 << 30, header_pa=0x1004000, ram=(0, 1 << 30),
                reserved=[], required=[(0x1004000, 0x2000000)])


class BootstrapTests(unittest.TestCase):
    def test_mapping_and_truncated_tail(self):
        result = layout.validate(**fixture())
        self.assertEqual(result["table_pages"], 4)
        self.assertEqual(result["l2_entries_per_mapping"], 31)
        self.assertEqual(result["physical_mapping"], [0, 31 * layout.BLOCK])
        self.assertEqual(result["unmapped_advertised_tail"], [31 * layout.BLOCK, 1 << 30])

    def test_rejects_unsafe_inputs(self):
        for changes in [dict(mem_size=layout.BLOCK), dict(virt_base=0),
                        dict(header_pa=1), dict(required=[]),
                        dict(required=[((1 << 30) - 1, 1 << 30)]),
                        dict(reserved=[(0, 4096)]), dict(ram=(4096, 1 << 30)),
                        dict(mem_size=1 << 41), dict(reserved=[(100, 1)]),
                        dict(mem_size=1 << 37, ram=(0, 1 << 37))]:
            args = fixture()
            args.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                layout.validate(**args)

    def test_prefix_is_checked_even_before_advertised_base(self):
        args = fixture()
        args.update(phys_base=0x1004000, virt_base=layout.LINK_BASE,
                    mem_size=(1 << 30) - 0x1004000, reserved=[(0, 4096)])
        with self.assertRaisesRegex(ValueError, "rounded mapping"):
            layout.validate(**args)
