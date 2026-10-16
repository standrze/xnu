# SPDX-License-Identifier: BSD-2-Clause
"""Focused host checks for planning RP1 BAR1 CPU resource spans."""

from pathlib import Path
import hashlib
import json
import struct
import subprocess
import tempfile
import unittest

from tools.rpi5.fdt import parse
from tools.rpi5.tests.test_pcie_fdt import (
    PINNED, PINNED_SHA256, _encode_fdt, _synthetic_tree,
)


ROOT = Path(__file__).resolve().parents[3]
LOADER = ROOT / "loader/rpi5"
REFERENCE = ROOT / "build/rpi5/rp1-linux-reference-20261012/reference.json"
REFERENCE_SHA256 = "ece8b18da3d1b863800e4973cbb5f544c7ef3896a64b12742a0903cd8bda27bf"
REVALIDATION = REFERENCE.with_name("revalidation.json")
REVALIDATION_SHA256 = "070f53f4eb40851f1274e3a6b8621d26456910567188aab3ff89a5bd81bc931b"


class PCIeResourcePlanTests(unittest.TestCase):
    def test_synthetic_binding_and_observed_bar_contract(self):
        # The FDT is synthetic; BAR1 size/base and translated CPU range match
        # the read-only 2026-10-12 Linux RP1 reference observation.
        source = r'''
#include "pcie_fdt.h"
#include "pcie_resource_plan.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void reject(const struct rpi5_pcie_fdt *binding,
    const struct rpi5_rp1_bar_observation *bar)
{
    struct rpi5_pcie_resource_plan result, before;
    memset(&before, 0xa5, sizeof before);
    result = before;
    assert(rpi5_pcie_resource_plan(binding, bar, &result) == -1);
    assert(!memcmp(&result, &before, sizeof result));
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    FILE *f = fopen(argv[1], "rb"); assert(f);
    assert(!fseek(f, 0, SEEK_END));
    long length = ftell(f); assert(length > 40);
    rewind(f);
    unsigned char *blob = malloc((size_t)length); assert(blob);
    assert(fread(blob, 1, (size_t)length, f) == (size_t)length);
    assert(!fclose(f));
    struct rpi5_pcie_fdt binding;
    assert(!rpi5_fdt_pcie_rp1(blob, (size_t)length, &binding));
    free(blob);

    struct rpi5_rp1_bar_observation bar = {
        .vendor_id = 0x1de4, .device_id = 0x0001,
        .bar_index = 1, .assigned = 1, .memory_decode_enabled = 1,
        .space = 0x02000000, .pci_base = 0, .size = 0x400000
    };
    struct rpi5_pcie_resource_plan plan;
    assert(!rpi5_pcie_resource_plan(&binding, &bar, &plan));
    assert(plan.bar_cpu.start == 0x1f00000000ull);
    assert(plan.bar_cpu.end == 0x1f00400000ull);
    assert(plan.gem_cpu.start == 0x1f00100000ull);
    assert(plan.gem_cpu.end == 0x1f00104000ull);
    assert(plan.gem_pages.start == plan.gem_cpu.start);
    assert(plan.gem_pages.end == plan.gem_cpu.end);
    assert(plan.clock_cpu.start == 0x1f00018000ull);
    assert(plan.clock_cpu.end == 0x1f00028038ull);
    assert(plan.clock_pages.start == plan.clock_cpu.start);
    assert(plan.clock_pages.end == 0x1f0002c000ull);

    /* Base zero is legal when assignment and decode are independently proven. */
    bar.pci_base = 0x10000000;
    assert(!rpi5_pcie_resource_plan(&binding, &bar, &plan));
    assert(plan.bar_cpu.start == 0x1f10000000ull);
    assert(plan.gem_cpu.start == 0x1f10100000ull);

    struct rpi5_rp1_bar_observation bad = bar;
    bad.vendor_id = 0xffff; reject(&binding, &bad);
    bad = bar; bad.device_id = 2; reject(&binding, &bad);
    bad = bar; bad.bar_index = 0; reject(&binding, &bad);
    bad = bar; bad.assigned = 0; reject(&binding, &bad);
    bad = bar; bad.memory_decode_enabled = 0; reject(&binding, &bad);
    bad = bar; bad.space = 0x43000000; reject(&binding, &bad);
    bad = bar; bad.size = 0; reject(&binding, &bad);
    bad = bar; bad.size = 0x80000; reject(&binding, &bad);
    bad = bar; bad.size = 0x600000; reject(&binding, &bad);
    bad = bar; bad.pci_base = 0x1000; reject(&binding, &bad);
    bad = bar; bad.pci_base = 0xffc00000; reject(&binding, &bad);
    bad = bar; bad.pci_base = UINT64_MAX; reject(&binding, &bad);

    struct rpi5_pcie_fdt changed = binding;
    changed.outbound[1] = changed.outbound[0];
    reject(&changed, &bar); /* Ambiguous host translation. */
    changed = binding; changed.outbound[0].size = 0x200000;
    reject(&changed, &bar); /* No full BAR containment. */
    changed = binding; changed.outbound[0].cpu_base = (1ull << 40) - 0x4000;
    reject(&changed, &bar); /* CPU physical width exceeded. */
    changed = binding; changed.gem_bar_offset = changed.rp1_aperture_size;
    reject(&changed, &bar); /* Peripheral lies beyond RP1 aperture. */
    changed = binding; changed.rp1_pci_base = 0x10000000;
    reject(&changed, &bar); /* No invented relocation for another profile. */
    changed = binding; changed.clock_size = 0x10000000;
    reject(&changed, &bar);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            dtb = work / "synthetic.dtb"
            dtb.write_bytes(_encode_fdt(_synthetic_tree()))
            harness = work / "resource_plan.c"
            harness.write_text(source)
            binary = work / "resource_plan"
            subprocess.run([
                "xcrun", "clang", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-I", str(LOADER),
                str(harness), str(LOADER / "fdt.c"),
                str(LOADER / "fdt_reg.c"), str(LOADER / "pcie_fdt.c"),
                str(LOADER / "pcie_resource_plan.c"), "-o", str(binary),
            ], check=True)
            subprocess.run([str(binary), str(dtb)], check=True)
            if PINNED.exists():
                self.assertEqual(hashlib.sha256(PINNED.read_bytes()).hexdigest(),
                                 PINNED_SHA256)
                subprocess.run([str(binary), str(PINNED)], check=True)

    def test_optional_read_only_linux_reference(self):
        if not all(path.exists() for path in (REFERENCE, REVALIDATION, PINNED)):
            self.skipTest("optional local Linux RP1 reference is unavailable")
        self.assertEqual(hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),
                         REFERENCE_SHA256)
        self.assertEqual(hashlib.sha256(REVALIDATION.read_bytes()).hexdigest(),
                         REVALIDATION_SHA256)
        self.assertEqual(hashlib.sha256(PINNED.read_bytes()).hexdigest(),
                         PINNED_SHA256)
        observed = json.loads(REFERENCE.read_text())
        checked_again = json.loads(REVALIDATION.read_text())
        self.assertEqual(checked_again["reference_sha256"], REFERENCE_SHA256)
        self.assertTrue(checked_again["pci_header_resource_and_selected_of_unchanged"])
        self.assertEqual(checked_again["boot_id_before"], checked_again["boot_id_after"])
        self.assertEqual(checked_again["pci_config_first64_hex"],
                         observed["pci_config_first64_hex"])
        self.assertEqual(checked_again["resource"], observed["pci"]["resource"])
        self.assertEqual(observed["pci_bdf"], "0002:01:00.0")

        config = bytes.fromhex(observed["pci_config_first64_hex"])
        self.assertEqual(len(config), 64)
        self.assertEqual(struct.unpack_from("<HH", config), (0x1de4, 0x0001))
        command, = struct.unpack_from("<H", config, 4)
        bar1, = struct.unpack_from("<I", config, 0x14)
        self.assertTrue(command & 0x2)  # PCI memory decode enabled.
        self.assertEqual(bar1 & 0xf, 0)  # 32-bit, nonprefetchable memory BAR.
        self.assertEqual(bar1 & ~0xf, 0)  # Bus base zero is assigned here.
        row = observed["pci"]["resource"].splitlines()[1].split()
        cpu_start, cpu_last, flags = (int(value, 16) for value in row)
        self.assertEqual((cpu_start, cpu_last + 1, flags),
                         (0x1f00000000, 0x1f00400000, 0x40200))
        self.assertEqual(len(observed["pci"]["msi_irqs"]), 61)

        pinned = parse(PINNED.read_bytes())["root"]

        def node(path):
            current = pinned
            for component in path.strip("/").split("/"):
                current = next(child for child in current["children"]
                               if child["name"] == component)
            return current

        safe_properties = {
            "/axi/pcie@1000120000": (
                "compatible", "reg", "ranges", "dma-ranges", "interrupts",
                "interrupt-parent", "msi-parent", "linux,pci-domain",
            ),
            "/axi/pcie@1000120000/rp1": (
                "compatible", "ranges", "dma-ranges", "interrupt-parent",
                "#address-cells", "#size-cells",
            ),
            "/axi/pcie@1000120000/rp1/ethernet@100000": (
                "compatible", "reg", "interrupts", "clocks", "clock-names",
                "phy-mode", "phy-handle",
            ),
            "/axi/pcie@1000120000/rp1/clocks@18000": (
                "compatible", "reg", "phandle",
            ),
            "/axi/msi-controller@1000130000": (
                "compatible", "reg", "phandle",
            ),
        }
        self.assertEqual(sum(map(len, safe_properties.values())), 27)
        for path, names in safe_properties.items():
            live = observed["of_properties_hex"][path]
            saved = node(path)["properties"]
            for name in names:
                self.assertEqual(bytes.fromhex(live[name]), saved[name],
                                 (path, name))

    def test_freestanding_target_compile(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "pcie_resource_plan.o"
            subprocess.run([
                "xcrun", "clang", "--target=aarch64-none-elf", "-mcpu=cortex-a76",
                "-mstrict-align", "-mgeneral-regs-only", "-ffreestanding",
                "-fno-stack-protector", "-Wall", "-Wextra", "-Werror", "-O2",
                "-I", str(LOADER), "-c", str(LOADER / "pcie_resource_plan.c"),
                "-o", str(target),
            ], check=True)
            self.assertGreater(target.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
