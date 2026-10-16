# SPDX-License-Identifier: BSD-2-Clause
"""Loader opt-in, sanitized logging faults and reviewed stack bounds."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.rpi5.pcie_reference_core import encode_properties
from tools.rpi5.pcie_stack import check as check_stack
from tools.rpi5.tests.test_pcie_reference import properties

ROOT = Path(__file__).resolve().parents[3]


class PCIeTopologyTests(unittest.TestCase):
    def test_actual_preprocessor_default_off_and_storage_exclusion(self):
        base = ["xcrun", "clang", "--target=aarch64-none-elf", "-E", "-P",
                "-I" + str(ROOT / "loader/rpi5/freestanding")]
        source = str(ROOT / "loader/rpi5/probe_main.c")
        default = subprocess.run([*base, source], capture_output=True, text=True, timeout=30)
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertNotIn("rpi5_pcie_topology_log", default.stdout)
        enabled = subprocess.run([*base, "-DRPI5_GATE5_PCIE_TOPOLOGY=1", source],
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(enabled.returncode, 0, enabled.stderr)
        self.assertIn("rpi5_pcie_topology_log((const void *)fdt_pa", enabled.stdout)
        body = enabled.stdout[enabled.stdout.index("void probe_el1_main(uintptr_t fdt_pa)\n{"):]
        self.assertLess(body.index("runtime_cpus(fdt_pa"), body.index("rpi5_pcie_topology_log"))
        self.assertLess(body.index("rpi5_pcie_topology_log"), body.index("psci_secondary_probe(&cpus)"))
        rejected = subprocess.run([*base, "-DRPI5_GATE5_PCIE_TOPOLOGY=1",
                                   "-DRPI5_GATE4_STORAGE=1", source],
                                  capture_output=True, text=True, timeout=30)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("must remain separate from storage trials", rejected.stderr)
        for storage in ("--gate4-storage", "--gate4-sd-readonly", "--gate4-hfs-readonly", "--gate4-hfs-write-trial"):
            rejected = subprocess.run([
                "python3", str(ROOT / "tools/rpi5/build_probe.py"), "--load-address", "0x9000000",
                "--gate5-pcie-topology", storage,
            ], capture_output=True, text=True, timeout=30)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("must remain separate from storage trials", rejected.stderr)

    def test_native_declaration_log_and_each_output_failure(self):
        source = r'''
#include "pcie_topology.h"
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
static unsigned calls, fail_at, printing;
static int text(const char *value) {
    if (++calls == fail_at) return 0;
    if (printing) fputs(value, stdout);
    return 1;
}
static int hex(uint64_t value) {
    if (++calls == fail_at) return 0;
    if (printing) printf("0x%" PRIx64, value);
    return 1;
}
int main(int argc, char **argv) {
    assert(argc == 2); unsigned char blob[65536];
    FILE *file = fopen(argv[1], "rb"); assert(file);
    size_t size = fread(blob, 1, sizeof blob, file); assert(!ferror(file));
    assert(!fclose(file)); printing = 1;
    assert(!rpi5_pcie_topology_log(blob, size, text, hex));
    unsigned total = calls; printing = 0;
    for (unsigned i = 1; i <= total; i++) {
        calls = 0; fail_at = i;
        assert(rpi5_pcie_topology_log(blob, size, text, hex) == -2);
        assert(calls == i);
    }
    fail_at = calls = 0;
    assert(rpi5_pcie_topology_log(0, 0, text, hex) == -1);
    assert(calls == 2);
    assert(rpi5_pcie_topology_log(blob, size, 0, hex) == -2);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            harness = work / "log.c"; harness.write_text(source)
            binary = work / "log"
            subprocess.run([
                "xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-I", str(ROOT / "loader/rpi5"), str(harness),
                *[str(ROOT / "loader/rpi5" / name) for name in
                  ("fdt.c", "fdt_reg.c", "pcie_fdt.c", "pcie_topology.c")],
                "-o", str(binary),
            ], check=True, timeout=60)
            dtb = work / "filtered.dtb"; dtb.write_bytes(encode_properties(properties()))
            result = subprocess.run([str(binary), str(dtb)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("CPU_START=0x1000120000", result.stdout)
            self.assertIn("GEM BAR_OFFSET=0x100000 BYTES=0x4000 RP1_IRQ=0x6 PHY_ADDRESS=0x1", result.stdout)
            self.assertEqual(result.stdout.count("PCIE_TOPOLOGY:PASS"), 1)
            self.assertIn("PASS PCIE_MMIO=0 CONFIG_ACCESS=0 DMA=0 NIC_READY=0", result.stdout)

    def test_stack_budget_rejects_missing_ambiguous_or_excess_frames(self):
        functions = {
            "probe_main": ["probe_el1_main"], "pcie_topology": ["rpi5_pcie_topology_log"],
            "pcie_fdt": ["rpi5_fdt_pcie_rp1"], "fdt_reg": ["rpi5_fdt_reg"],
            "fdt": ["rpi5_fdt_structure", "rpi5_fdt_layout", "rpi5_fdt_property", "rpi5_fdt_phandles"],
        }
        frames = [{"location": f"loader/rpi5/{unit}.c:1:{name}", "bytes": 16}
                  for unit, names in functions.items() for name in names]
        result = check_stack(frames)
        self.assertEqual(result["conservative_bytes"], len(frames) * 16)
        for i in range(len(frames)):
            with self.assertRaises(ValueError):
                check_stack(frames[:i] + frames[i + 1:])
        with self.assertRaises(ValueError):
            check_stack(frames + [frames[0]])
        with self.assertRaises(ValueError):
            check_stack(frames, len(frames) * 16 + 512)
        # runtime_cpus is deliberately no longer on this call chain.
        extra = frames + [{"location": "loader/rpi5/probe_main.c:1:runtime_cpus", "bytes": 15000}]
        self.assertEqual(check_stack(extra)["conservative_bytes"], result["conservative_bytes"])


if __name__ == "__main__":
    unittest.main()
