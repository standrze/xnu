# SPDX-License-Identifier: BSD-2-Clause
"""Narrow host checks for the read-only Pi 5 PCIe/RP1 FDT contract."""

import copy
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
PINNED = ROOT / "build/rpi5/bcm2712-rpi-5-b-2768f610.dtb"
PINNED_SHA256 = "399caff4dcf03c55e20b6a4a7907dd8bd1c0cc42a9fc79e0b3b2ad4f7511585a"


def _cells(*values):
    return struct.pack(">" + "I" * len(values), *values)


def _node(name, properties, *children):
    return {"name": name, "properties": properties, "children": list(children)}


def _synthetic_tree():
    """Textual subset of the pinned binding; no ignored download is needed."""
    gic, mip, rp1, clock, rescal, reset, phy = range(1, 8)
    axi_map = _cells(0, 0, 0, 0, 0x10, 0,
                     0x10, 0, 0x10, 0, 0x10, 0)
    pci_ranges = _cells(
        0x02000000, 0, 0, 0x1f, 0, 0, 0xfffffffc,
        0x43000000, 4, 0, 0x1c, 0, 3, 0)
    pci_dma = _cells(
        0x02000000, 0, 0, 0x1f, 0, 0, 0x400000,
        0x43000000, 0x10, 0, 0, 0, 0x10, 0,
        0x03000000, 0xff, 0xfffff000, 0x10, 0x00130000, 0, 0x1000)
    rp1_dma = _cells(
        0x10, 0, 0x43000000, 0x10, 0, 0x10, 0,
        0xc0, 0x40000000, 0x02000000, 0, 0, 0, 0x410000,
        0, 0, 0x02000000, 0x10, 0, 0x10, 0)
    intx = b"".join(_cells(0, 0, 0, pin, gic, 0, 228 + pin, 4)
                    for pin in range(1, 5))
    gem = _node("ethernet@100000", {
        "compatible": b"raspberrypi,rp1-gem\0cdns,macb\0",
        "status": b"okay\0", "reg": _cells(0xc0, 0x40100000, 0, 0x4000),
        "#address-cells": _cells(1), "#size-cells": _cells(0),
        "interrupts": _cells(6, 4), "phy-mode": b"rgmii-id\0",
        "phy-handle": _cells(phy),
        "clock-names": b"pclk\0hclk\0tsu_clk\0tx_clk\0",
        "clocks": _cells(clock, 12, clock, 12, clock, 29, clock, 16),
    }, _node("ethernet-phy@1", {"reg": _cells(1), "phandle": _cells(phy)}))
    rp1_node = _node("rp1", {
        "compatible": b"simple-bus\0", "phandle": _cells(rp1),
        "#address-cells": _cells(2), "#size-cells": _cells(2),
        "#interrupt-cells": _cells(2), "interrupt-controller": b"",
        "interrupt-parent": _cells(rp1),
        "ranges": _cells(0xc0, 0x40000000, 0x02000000, 0, 0, 0, 0x410000),
        "dma-ranges": rp1_dma,
    }, _node("clocks@18000", {
        "compatible": b"raspberrypi,rp1-clocks\0", "phandle": _cells(clock),
        "#clock-cells": _cells(1), "reg": _cells(0xc0, 0x40018000, 0, 0x10038),
    }), gem)
    bridge = _node("pcie@1000120000", {
        "compatible": b"brcm,bcm2712-pcie\0", "status": b"okay\0",
        "reg": _cells(0x10, 0x00120000, 0, 0x9310), "device_type": b"pci\0",
        "linux,pci-domain": _cells(2), "num-lanes": _cells(4),
        "max-link-speed": _cells(2),
        "#address-cells": _cells(3), "#size-cells": _cells(2),
        "#interrupt-cells": _cells(1), "interrupt-parent": _cells(gic),
        "interrupts": _cells(0, 233, 4, 0, 234, 4),
        "interrupt-names": b"pcie\0msi\0",
        "interrupt-map-mask": _cells(0, 0, 0, 7), "interrupt-map": intx,
        "msi-controller": b"", "msi-parent": _cells(mip),
        "ranges": pci_ranges, "dma-ranges": pci_dma,
        "reset-names": b"rescal\0bridge\0", "resets": _cells(rescal, reset, 44),
    }, rp1_node)
    mip_node = _node("msi-controller@1000130000", {
        "compatible": b"brcm,bcm2712-mip\0", "phandle": _cells(mip),
        "reg": _cells(0x10, 0x00130000, 0, 0xc0, 0xff, 0xfffff000, 0, 0x1000),
        "msi-controller": b"", "msi-ranges": _cells(gic, 0, 128, 1, 64),
        "brcm,msi-offset": _cells(0),
    })
    soc = _node("soc@107c000000", {
        "compatible": b"simple-bus\0", "#address-cells": _cells(1),
        "#size-cells": _cells(1),
        "ranges": _cells(0, 0x10, 0, 0x80000000),
    }, _node("interrupt-controller@7fff9000", {
        "compatible": b"arm,gic-400\0", "phandle": _cells(gic),
        "#address-cells": _cells(0),
        "#interrupt-cells": _cells(3), "interrupt-controller": b"",
    }), _node("reset-controller@119500", {
        "compatible": b"brcm,bcm7216-pcie-sata-rescal\0",
        "reg": _cells(0x00119500, 0x10), "phandle": _cells(rescal),
        "#reset-cells": _cells(0),
    }), _node("reset-controller@1504318", {
        "compatible": b"brcm,brcmstb-reset\0",
        "reg": _cells(0x01504318, 0x30), "phandle": _cells(reset),
        "#reset-cells": _cells(1),
    }))
    axi = _node("axi", {
        "compatible": b"simple-bus\0", "#address-cells": _cells(2),
        "#size-cells": _cells(2), "ranges": axi_map,
        "dma-ranges": axi_map,
    }, bridge, mip_node)
    return _node("", {
        "compatible": b"raspberrypi,5-model-b\0brcm,bcm2712\0",
        "#address-cells": _cells(2), "#size-cells": _cells(2),
        "interrupt-parent": _cells(gic),
    }, soc, axi)


def _encode_fdt(root):
    names = bytearray()
    offsets = {}

    def name_offset(name):
        if name not in offsets:
            offsets[name] = len(names)
            names.extend(name.encode("ascii") + b"\0")
        return offsets[name]

    def padded(data):
        return data + bytes(-len(data) % 4)

    def encode_node(node):
        body = _cells(1) + padded(node["name"].encode("ascii") + b"\0")
        for key, value in node["properties"].items():
            body += _cells(3, len(value), name_offset(key)) + padded(value)
        for child in node["children"]:
            body += encode_node(child)
        return body + _cells(2)

    structure = encode_node(root) + _cells(9)
    structure_offset = 56  # 40-byte header plus one terminating reservation tuple.
    strings_offset = structure_offset + len(structure)
    header = _cells(0xd00dfeed, strings_offset + len(names), structure_offset,
                    strings_offset, 40, 17, 16, 0, len(names), len(structure))
    return header + bytes(16) + structure + names


class PCIeFDTTests(unittest.TestCase):
    def test_self_contained_binding_and_rejections(self):
        root = _synthetic_tree()

        def changed(path, name, value):
            altered = copy.deepcopy(root)
            node = altered
            for part in path.strip("/").split("/"):
                node = next(child for child in node["children"] if child["name"] == part)
            node["properties"][name] = value
            return _encode_fdt(altered)

        host = "/axi/pcie@1000120000"
        gem = host + "/rp1/ethernet@100000"
        cases = [
            ("valid", _encode_fdt(root), "valid"),
            ("host_irq_override", changed(host, "interrupts-extended",
                                           _cells(1, 0, 233, 4, 1, 0, 234, 4)), "reject"),
            ("gem_irq_override", changed(gem, "interrupts-extended",
                                          _cells(3, 6, 4)), "reject"),
            ("bad_reset_width", changed("/soc@107c000000/reset-controller@119500",
                                        "#reset-cells", _cells(1)), "reject"),
            ("bad_gic_address_width", changed(
                "/soc@107c000000/interrupt-controller@7fff9000",
                "#address-cells", _cells(1)), "reject"),
            ("wrong_domain", changed(host, "linux,pci-domain", _cells(1)), "reject"),
            ("unmapped_outbound", changed(host, "ranges", _cells(
                0x02000000, 0, 0, 0x20, 0, 0, 0xfffffffc,
                0x43000000, 4, 0, 0x1c, 0, 3, 0)), "reject"),
            ("bad_phy", changed(gem, "phy-handle", _cells(6)), "reject"),
            ("disabled_bridge", changed(host, "status", b"disabled\0"), "reject"),
        ]
        source = r'''
#include "pcie_fdt.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv) {
    assert(argc == 3);
    FILE *f = fopen(argv[1], "rb"); assert(f);
    assert(!fseek(f, 0, SEEK_END)); long length = ftell(f); assert(length > 40);
    rewind(f); unsigned char *b = malloc((size_t)length); assert(b);
    assert(fread(b, 1, (size_t)length, f) == (size_t)length); assert(!fclose(f));
    struct rpi5_pcie_fdt output, prior; memset(&prior, 0xa5, sizeof prior);
    output = prior;
    int rc = rpi5_fdt_pcie_rp1(b, (size_t)length, &output);
    if (argv[2][0] == 'v') {
        assert(rc == 0);
        assert(output.bridge_regs.start == 0x1000120000ull);
        assert(output.mip_regs.start == 0x1000130000ull);
        assert(output.gem_bar_offset == 0x100000ull);
        assert(output.rp1_irq == 6 && output.phy_address == 1);
    } else assert(rc == -1 && !memcmp(&output, &prior, sizeof output));
    free(b); return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source_path, binary = work / "binding.c", work / "binding"
            source_path.write_text(source)
            subprocess.run([
                "xcrun", "clang", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-I", str(ROOT / "loader/rpi5"),
                str(source_path), str(ROOT / "loader/rpi5/fdt.c"),
                str(ROOT / "loader/rpi5/fdt_reg.c"),
                str(ROOT / "loader/rpi5/pcie_fdt.c"), "-o", str(binary),
            ], check=True)
            for label, blob, expected in cases:
                path = work / f"{label}.dtb"
                path.write_bytes(blob)
                subprocess.run([str(binary), str(path), expected], check=True)

    def test_freestanding_target_compile(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "pcie_fdt.o"
            subprocess.run([
                "xcrun", "clang", "--target=aarch64-none-elf", "-mcpu=cortex-a76",
                "-mstrict-align", "-mgeneral-regs-only", "-ffreestanding",
                "-fno-stack-protector", "-Wall", "-Wextra", "-Werror", "-O2",
                "-I", str(ROOT / "loader/rpi5"), "-c",
                str(ROOT / "loader/rpi5/pcie_fdt.c"), "-o", str(target),
            ], check=True)
            self.assertGreater(target.stat().st_size, 0)

    def test_pinned_profile_and_atomic_rejection(self):
        if not PINNED.exists():
            self.skipTest("optional pinned firmware DTB has not been downloaded")
        self.assertEqual(hashlib.sha256(PINNED.read_bytes()).hexdigest(), PINNED_SHA256)
        source = r'''
#include "pcie_fdt.h"
#include "fdt.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void rejected(unsigned char *b, size_t n)
{
    struct rpi5_pcie_fdt output, prior;
    memset(&prior, 0xa5, sizeof prior);
    output = prior;
    assert(rpi5_fdt_pcie_rp1(b, n, &output) == -1);
    assert(!memcmp(&output, &prior, sizeof output));
}

static void broken_property(unsigned char *b, size_t n,
    const char *path, const char *name, unsigned byte, unsigned char xor_mask)
{
    struct rpi5_fdt_property p;
    assert(!rpi5_fdt_property(b, n, path, name, &p));
    assert(byte < p.length);
    b[p.offset + byte] ^= xor_mask;
    rejected(b, n);
    b[p.offset + byte] ^= xor_mask;
}

static void shortened_property(unsigned char *b, size_t n,
    const char *path, const char *name)
{
    struct rpi5_fdt_property p;
    assert(!rpi5_fdt_property(b, n, path, name, &p));
    assert(p.length > 0 && p.length % 4 == 0 && p.offset >= 8);
    uint32_t shorter = p.length - 1;
    unsigned char saved[4];
    memcpy(saved, b + p.offset - 8, sizeof saved);
    b[p.offset - 8] = (unsigned char)(shorter >> 24);
    b[p.offset - 7] = (unsigned char)(shorter >> 16);
    b[p.offset - 6] = (unsigned char)(shorter >> 8);
    b[p.offset - 5] = (unsigned char)shorter;
    rejected(b, n);
    memcpy(b + p.offset - 8, saved, sizeof saved);
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    FILE *f = fopen(argv[1], "rb");
    assert(f);
    assert(!fseek(f, 0, SEEK_END));
    long length = ftell(f);
    assert(length > 40);
    rewind(f);
    size_t n = (size_t)length;
    unsigned char *b = malloc(n);
    assert(b && fread(b, 1, n, f) == n);
    assert(!fclose(f));

    struct rpi5_pcie_fdt out;
    assert(!rpi5_fdt_pcie_rp1(b, n, &out));
    assert(out.bridge_regs.start == 0x1000120000ull);
    assert(out.bridge_regs.end == 0x1000129310ull);
    assert(out.mip_regs.start == 0x1000130000ull);
    assert(out.mip_regs.end == 0x10001300c0ull);
    assert(out.mip_target.start == 0xfffffff000ull);
    assert(out.mip_target.end == 0x10000000000ull);
    assert(out.rescal_regs.start == 0x1000119500ull);
    assert(out.bridge_reset_regs.start == 0x1001504318ull);
    assert(out.bridge_reset_id == 44);
    assert(out.outbound_count == 2 && out.dma_count == 3 && out.rp1_dma_count == 3);
    assert(out.outbound[0].space == 0x02000000 && out.outbound[0].pci_base == 0);
    assert(out.outbound[0].cpu_base == 0x1f00000000ull);
    assert(out.outbound[0].size == 0xfffffffcull);
    assert(out.outbound[1].space == 0x43000000);
    assert(out.outbound[1].pci_base == 0x400000000ull);
    assert(out.outbound[1].cpu_base == 0x1c00000000ull);
    assert(out.outbound[1].size == 0x300000000ull);
    assert(out.dma[2].pci_base == 0xfffffff000ull);
    assert(out.dma[2].cpu_base == 0x1000130000ull && out.dma[2].size == 0x1000);
    assert(out.bridge_intid[0] == 265 && out.bridge_intid[1] == 266);
    for (unsigned i = 0; i < 4; ++i) assert(out.intx_intid[i] == 261 + i);
    assert(out.mip_intid_base == 160 && out.mip_intid_count == 64);
    assert(out.rp1_local_base == 0xc040000000ull);
    assert(out.rp1_pci_base == 0 && out.rp1_aperture_size == 0x410000);
    assert(out.clock_bar_offset == 0x18000 && out.clock_size == 0x10038);
    assert(out.gem_bar_offset == 0x100000 && out.gem_size == 0x4000);
    assert(out.rp1_irq == 6 && out.rp1_irq_flags == 4);
    assert(out.phy_phandle == 0x3f && out.phy_address == 1);
    assert(out.gem_clock_id[0] == 12 && out.gem_clock_id[1] == 12);
    assert(out.gem_clock_id[2] == 29 && out.gem_clock_id[3] == 16);

    const char *host = "/axi/pcie@1000120000";
    const char *mip = "/axi/msi-controller@1000130000";
    const char *rp1 = "/axi/pcie@1000120000/rp1";
    const char *gem = "/axi/pcie@1000120000/rp1/ethernet@100000";
    const char *phy = "/axi/pcie@1000120000/rp1/ethernet@100000/ethernet-phy@1";
    const char *root = "/";
    broken_property(b, n, host, "status", 0, 0x0b); /* okay -> disabled spelling */
    broken_property(b, n, host, "msi-parent", 3, 1);
    broken_property(b, n, host, "#address-cells", 3, 1);
    broken_property(b, n, host, "ranges", 0, 1);
    broken_property(b, n, host, "dma-ranges", 0, 1);
    broken_property(b, n, host, "interrupts", 11, 1);
    broken_property(b, n, mip, "msi-ranges", 3, 1);
    broken_property(b, n, mip, "msi-ranges", 11, 0x69); /* SPI 128 -> 233, overlaps bridge */
    broken_property(b, n, mip, "reg", 7, 1);
    broken_property(b, n, rp1, "ranges", 0, 1);
    broken_property(b, n, rp1, "interrupt-parent", 3, 1);
    broken_property(b, n, gem, "reg", 7, 1);
    broken_property(b, n, gem, "interrupts", 7, 1);
    broken_property(b, n, gem, "clocks", 3, 1);
    broken_property(b, n, gem, "phy-handle", 3, 1);
    broken_property(b, n, phy, "reg", 3, 1);
    broken_property(b, n, phy, "phandle", 3, 1);
    broken_property(b, n, root, "interrupt-parent", 3, 1);
    shortened_property(b, n, host, "reg");
    shortened_property(b, n, host, "ranges");
    shortened_property(b, n, host, "dma-ranges");
    shortened_property(b, n, mip, "msi-ranges");
    shortened_property(b, n, rp1, "ranges");
    shortened_property(b, n, gem, "reg");
    rejected(b, n - 1);
    rejected(b, 40);
    rejected(b, 0);
    assert(rpi5_fdt_pcie_rp1(b, n, NULL) == -1);
    assert(rpi5_fdt_pcie_rp1(NULL, n, &out) == -1);
    free(b);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source_path, binary = work / "test.c", work / "test"
            source_path.write_text(source)
            subprocess.run([
                "xcrun", "clang", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-I", str(ROOT / "loader/rpi5"),
                str(source_path), str(ROOT / "loader/rpi5/fdt.c"),
                str(ROOT / "loader/rpi5/fdt_reg.c"),
                str(ROOT / "loader/rpi5/pcie_fdt.c"), "-o", str(binary),
            ], check=True)
            subprocess.run([str(binary), str(PINNED)], check=True)


if __name__ == "__main__":
    unittest.main()
