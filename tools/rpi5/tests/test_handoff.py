# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1]))
from prepare_handoff import prepare, prepare_with_tree
from bootstrap_layout import LINK_BASE
from test_macho import fixture


def image():
    data = fixture()
    struct.pack_into("<Q", data, 56, LINK_BASE)
    struct.pack_into("<Q", data, 480, LINK_BASE + 496)
    return bytes(data)


def placement():
    return dict(header_pa=0x1004000, phys_base=0, mem_size=1 << 30,
                mem_size_actual=1 << 30, ram=(0, 1 << 30), reserved=[],
                boot_args_pa=0x2000000, device_tree_pa=0x2004000,
                device_tree_length=4096, live_allocations={"stack": (0x2100000, 0x2104000)},
                command_line="-v")


class HandoffTests(unittest.TestCase):
    def test_low_probe_cannot_share_firmware_free_bootstrap_extent(self):
        # Diagnostic link address is not a handoff placement. Mapping its
        # first 32 MiB block would include the fixed low firmware exclusion.
        args = placement()
        args.update(ram=(0x80000, 1 << 30), phys_base=0x80000,
                    mem_size=(1 << 30)-0x80000,
                    reserved=[(0,0x80000)],
                    live_allocations={"probe": (0x200000,0x240000)})
        with self.assertRaises(ValueError):
            prepare(image(), **args)
        # Moving the kernel to the next block alone cannot rescue a live
        # probe that is still below the selected contiguous extent.
        args.update(ram=(0x2000000,1 << 30), phys_base=0x2000000,
                    mem_size=(1 << 30)-0x2000000, header_pa=0x3004000,
                    boot_args_pa=0x4000000, device_tree_pa=0x4004000)
        with self.assertRaises(ValueError):
            prepare(image(), **args)
        # A synthetic co-located layout is feasible; not board ownership proof.
        args['live_allocations']={"probe": (0x2100000,0x2140000)}
        plan=prepare(image(), **args)
        self.assertEqual(plan['entry_pa'],0x3004000+496)

    def test_tree_bytes_drive_length_and_allocation(self):
        args = placement()
        del args["device_tree_length"]
        tree = {"name": "device-tree", "properties": {}, "children": []}
        plan = prepare_with_tree(image(), device_tree=tree, **args)
        size = len(plan["device_tree"])
        self.assertEqual(struct.unpack_from("<I", plan["boot_args"], 104)[0], size)
        self.assertIn((args["device_tree_pa"], args["device_tree_pa"] + size, "device_tree"), plan["allocations"])
        self.assertEqual(plan["boot_data_writes"][0]["data"], plan["device_tree"])
        with self.assertRaisesRegex(ValueError, "derived"):
            prepare_with_tree(image(), device_tree=tree, **placement())
        tree["properties"]["oversized"] = bytes(0x110000)
        with self.assertRaisesRegex(ValueError, "overlap"):
            prepare_with_tree(image(), device_tree=tree, **args)

    def test_composed_plan(self):
        plan = prepare(image(), **placement())
        self.assertEqual(plan["entry_x0_pa"], 0x2000000)
        self.assertEqual(plan["entry_pa"], 0x1004000 + 496)
        self.assertEqual(plan["copy_operations"], [{"file_offset": 0, "physical_address": 0x1004000, "length": 512}])
        self.assertEqual(plan["zero_operations"][0]["length"], 16384 - 512)
        self.assertEqual(struct.unpack_from("<Q", plan["boot_args"], 96)[0], LINK_BASE + 0x2004000 - 0x1004000)
        self.assertEqual(plan["top_of_kernel_data"], 0x2104000)

    def test_conflicts_and_unmapped_allocations(self):
        for changes in [dict(boot_args_pa=0x1004000), dict(device_tree_pa=0x2000000),
                        dict(live_allocations={}), dict(mem_size_actual=1024),
                        dict(reserved=[(0x2000000, 0x2004000)]),
                        dict(live_allocations={"tail": ((1 << 30) - 4096, 1 << 30)})]:
            args = placement()
            args.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                prepare(image(), **args)
