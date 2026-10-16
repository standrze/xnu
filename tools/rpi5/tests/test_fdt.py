# SPDX-License-Identifier: BSD-2-Clause
import sys
from pathlib import Path
import struct
import unittest
import hashlib

sys.path.insert(0, str(Path(__file__).parents[1]))
from fdt import parse, memory_ranges, available_memory
from fdt_address import reg_ranges
from fdt_clock import fixed_clock_rates


def fixture():
    structure = struct.pack(">I", 1) + bytes(4)
    structure += struct.pack(">III", 3, 4, 0) + b"test"
    structure += struct.pack(">II", 2, 9)
    names = b"model\0"
    header = struct.pack(">10I", 0xd00dfeed, 72 + len(structure) + len(names),
                         72, 72 + len(structure), 40, 17, 16, 0x100, len(names), len(structure))
    return header + struct.pack(">4Q", 0x100000, 4096, 0, 0) + structure + names


class FDTTests(unittest.TestCase):
    def test_static_reservation_reg_takes_precedence_over_size(self):
        cells = {"#address-cells": struct.pack(">I", 1), "#size-cells": struct.pack(">I", 1)}
        tree = {"reservations": [], "root": {"properties": cells, "children": [
            {"name": "memory@0", "properties": {"device_type": b"memory\0", "reg": struct.pack(">II", 0, 4096)}},
            {"name": "reserved-memory", "properties": {**cells, "ranges": b""}, "children": [
                {"name": "pool@400", "children": [], "properties": {
                    "reg": struct.pack(">II", 1024, 1024), "size": b"ignored"}}]}]}}
        self.assertEqual(available_memory(tree, additional_reserved=[])["available"], [(0, 1024), (2048, 4096)])

    def test_fixed_clock_references_fail_closed(self):
        provider = {"name": "clock", "children": [], "properties": {
            "phandle": struct.pack(">I", 1), "#clock-cells": bytes(4),
            "compatible": b"fixed-clock\0", "clock-frequency": struct.pack(">I", 9216000)}}
        consumer = {"name": "uart", "children": [], "properties": {
            "clock-names": b"uartclk\0", "clocks": struct.pack(">I", 1)}}
        tree = {"root": {"properties": {}, "children": [provider, consumer]}}
        self.assertEqual(fixed_clock_rates(tree, "/uart"), {"uartclk": 9216000})
        for raw in [b"", struct.pack(">I", 2), struct.pack(">II", 1, 1)]:
            consumer["properties"]["clocks"] = raw
            with self.assertRaises(ValueError):
                fixed_clock_rates(tree, "/uart")
        consumer["properties"]["clocks"] = struct.pack(">I", 1)
        provider["properties"]["#clock-cells"] = struct.pack(">I", 1)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            fixed_clock_rates(tree, "/uart")

    def test_bus_translation_rejects_missing_and_crossing_ranges(self):
        cells = {"#address-cells": struct.pack(">I", 1), "#size-cells": struct.pack(">I", 1)}
        device = {"name": "uart", "properties": {"reg": struct.pack(">II", 0x100, 0x20)}, "children": []}
        bus = {"name": "bus", "properties": {**cells, "ranges": struct.pack(">III", 0, 0x1000, 0x200)}, "children": [device]}
        tree = {"root": {"properties": cells, "children": [bus]}}
        self.assertEqual(reg_ranges(tree, "/bus/uart"), [(0x1100, 0x1120)])
        for raw in [None, bytes(3), struct.pack(">III", 0, 0x1000, 0x110),
                    struct.pack(">III", 0, 0x1000, 0x200) * 2]:
            bus["properties"]["ranges"] = raw
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                reg_ranges(tree, "/bus/uart")

    def test_pinned_official_pi5_blob_when_available(self):
        path = Path(__file__).parents[3] / "build/rpi5/bcm2712-rpi-5-b-2768f610.dtb"
        if not path.exists():
            self.skipTest("optional pinned firmware DTB has not been downloaded")
        blob = path.read_bytes()
        self.assertEqual(hashlib.sha256(blob).hexdigest(),
                         "399caff4dcf03c55e20b6a4a7907dd8bd1c0cc42a9fc79e0b3b2ad4f7511585a")
        tree = parse(blob)
        self.assertEqual(memory_ranges(tree), [(0, 0x28000000)])
        cpus = next(n for n in tree["root"]["children"] if n["name"] == "cpus")
        identities = [int.from_bytes(n["properties"]["reg"], "big") for n in cpus["children"]
                      if n["properties"].get("device_type") == b"cpu\0"]
        self.assertEqual(identities, [0, 0x100, 0x200, 0x300])
        self.assertEqual(reg_ranges(tree, "/soc@107c000000/serial@7d001000"),
                         [(0x107d001000, 0x107d001200)])
        self.assertEqual(fixed_clock_rates(tree, "/soc@107c000000/serial@7d001000"),
                         {"uartclk": 9216000, "apb_pclk": 750000000})
        with self.assertRaisesRegex(ValueError, "dynamic"):
            available_memory(tree, additional_reserved=[])

    def test_reserved_nodes_and_live_ranges_are_subtracted(self):
        cells = {"#address-cells": struct.pack(">I", 2), "#size-cells": struct.pack(">I", 2)}
        child = {"name": "pool@4000", "properties": {"reg": struct.pack(">QQ", 0x4000, 0x2000), "reusable": b""}, "children": []}
        container = {"name": "reserved-memory", "properties": {**cells, "ranges": b""}, "children": [child]}
        tree = {"reservations": [(0, 0x2000)], "root": {"properties": cells, "children": [
            {"name": "memory@0", "properties": {"device_type": b"memory\0", "reg": struct.pack(">QQ", 0, 0x10000)}}, container]}}
        result = available_memory(tree, additional_reserved=[(0x1000, 0x3000), (0xf000, 0x10000)])
        self.assertEqual(result["available"], [(0x3000, 0x4000), (0x6000, 0xf000)])
        child["properties"] = {"size": struct.pack(">Q", 4096)}
        with self.assertRaisesRegex(ValueError, "dynamic"):
            available_memory(tree, additional_reserved=[])

    def test_memory_cells_preserve_64bit_addresses_and_holes(self):
        def tree(raw):
            return {"root": {"properties": {"#address-cells": struct.pack(">I", 2),
                    "#size-cells": struct.pack(">I", 2)}, "children": [{"name": "memory@0",
                    "properties": {"device_type": b"memory\0", "reg": raw}}]}}
        self.assertEqual(memory_ranges(tree(struct.pack(">4Q", 0, 1 << 30, 1 << 32, 1 << 30))),
                         [(0, 1 << 30), (1 << 32, (1 << 32) + (1 << 30))])
        for raw in [b"", bytes(15), struct.pack(">2Q", 1 << 40, 1),
                    struct.pack(">4Q", 0, 4096, 2048, 4096)]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                memory_ranges(tree(raw))

    def test_reads_big_endian_header_and_reservations(self):
        result = parse(fixture())
        self.assertEqual(result["reservations"], [(0x100000, 0x101000)])
        self.assertEqual(result["boot_cpuid_phys"], 0x100)
        self.assertEqual(result["root"]["properties"], {"model": b"test"})

    def test_every_truncation_fails(self):
        data = fixture()
        for length in range(len(data)):
            with self.subTest(length=length), self.assertRaises(ValueError):
                parse(data[:length])

    def test_bad_offsets_tokens_and_lengths(self):
        for offset, value in [(8, 40), (16, 41), (20, 16), (72, 9),
                              (84, 0xffffffff), (88, 1000), (96, 9), (100, 4)]:
            data = bytearray(fixture())
            struct.pack_into(">I", data, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                parse(bytes(data))
