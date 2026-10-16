# SPDX-License-Identifier: BSD-2-Clause
"""Explicit Linux-reference models, not interrupt/power/clock hardware tests."""
import contextlib
import copy
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

from tools.rpi5 import capture_pcie_lifecycle_reference as controller
from tools.rpi5 import pcie_lifecycle_reference_core as core
from tools.rpi5 import pcie_reference_core as reference
from tools.rpi5.tests.test_pcie_reference import reference as base_report

CLOCKS = """enable prepare protect duty hardware connection
clock count count count rate accuracy phase cycle enable consumer id
-------------------------------------------------------------------
xosc 7 7 0 50000000 0 0 50000 Y deviceless no_connection_id
 pll_sys_core 3 3 0 1000000000 0 0 50000 Y deviceless no_connection_id
  clk_sys 4 4 0 200000000 0 0 50000 Y 1f00100000.ethernet hclk
                                              1f00100000.ethernet pclk
  clk_eth 1 1 0 125000000 0 0 50000 Y 1f00100000.ethernet tx_clk
 clk_eth_tsu 1 1 0 50000000 0 0 50000 Y 1f00100000.ethernet tsu_clk
unrelated 1 1 0 123 0 0 50000 Y deviceless no_connection_id
"""
IRQS = """           CPU0 CPU1 CPU2 CPU3
38: 0 0 0 0 GICv2 251 Level PCIe PME, aerdrv, PCIe bwctrl
39: 14 0 0 0 MIP-MSI-PCI-MSIX-0001:01:00.0 0 Edge nvme0q0
44: 0 0 0 0 GICv2 261 Level PCIe PME, aerdrv, PCIe bwctrl
112: 0 0 0 0 rp1_irq_chip 6 Level eth0
167: 3 0 0 0 GICv2 305 Level mmc0
IPI0: 0 0 0 0 Rescheduling interrupts
Err: 0
"""


def cells(*values):
    return struct.pack(">" + "I" * len(values), *values).hex()


def fixture():
    old = base_report()
    for which in ("first", "second"):
        old[which]["of_properties_hex"][reference.RP1 + "/clocks@18000"]["clocks"] = cells(41)
    props = core.collect_extra(lambda node, name: (_ for _ in ()).throw(FileNotFoundError()))
    props[core.PCIE1].update({"compatible": b"brcm,bcm2712-pcie\0".hex(),
                            "status": b"okay\0".hex(), "reg": cells(0x10, 0x110000, 0, 0x9310),
                            "resets": cells(5, 6, 43), "reset-names": b"rescal\0bridge\0".hex(),
                            "msi-parent": cells(38), "interrupt-parent": cells(1),
                            "interrupts": cells(0, 223, 4, 0, 224, 4)})
    props[core.MIP1].update({"compatible": b"brcm,bcm2712-mip\0".hex(),
                            "phandle": cells(38), "msi-controller": "",
                            "msi-ranges": cells(1, 0, 247, 1, 8)})
    props[core.XOSC].update({"compatible": b"fixed-clock\0".hex(), "phandle": cells(41),
                            "#clock-cells": cells(0), "clock-frequency": cells(50000000)})
    snapshot = {"of_properties_hex": props,
                "power": {name: {"runtime_status": "active", "control": "auto"} for name in core.POWER_PATHS},
                "links": {bdf: {"current_link_speed": "5.0 GT/s PCIe", "current_link_width": "4"}
                          for bdf in ("0001:01:00.0", "0002:01:00.0")},
                "clocks": core.clock_rows(CLOCKS), "interrupts": core.interrupt_rows(IRQS),
                "msi_allocations": {"0001:01:00.0": {"39": "msix"}, "0002:01:00.0": {"45": "msix"}}}
    return {"schema_version": 1, "status": "linux_reference_only", "reference": old,
            "identity_after": copy.deepcopy(old["identity_after"]), "first": snapshot,
            "second": copy.deepcopy(snapshot), "operations": dict(core.OPERATIONS),
            "limitations": dict(core.LIMITATIONS)}


class PCIeLifecycleReferenceTests(unittest.TestCase):
    def test_allowlist_precedes_property_reads(self):
        requested = []
        def read(node, name):
            requested.append((node, name))
            raise FileNotFoundError
        fields = core.collect_extra(read)
        self.assertEqual(requested, [(n, p) for n, props in core.EXTRA_PROPERTIES.items() for p in props])
        self.assertFalse(any("chosen" in n or "seed" in p for n, p in requested))
        core.validate_extra(fields)
        for value in (b"x" * 4097, "not-bytes"):
            with self.assertRaises(ValueError): core.collect_extra(lambda n, p: value)
        with self.assertRaises(PermissionError):
            core.collect_extra(lambda n, p: (_ for _ in ()).throw(PermissionError()))

    def test_clock_format_and_missing_status_not_fabricated(self):
        rows = core.clock_rows(CLOCKS)
        self.assertEqual(rows["framework_clock_rows"], 6)
        self.assertEqual(rows["selected"]["clk_sys"]["rate_hz"], 200000000)
        self.assertNotIn("unrelated", rows["selected"])
        self.assertFalse(any("pcie" in name for name in rows["selected"]))
        optional = core.clock_rows(CLOCKS + "sw_pcie 1 1 0 100000000 0 0 50000 Y deviceless none\n")
        self.assertIn("sw_pcie", optional["selected"])
        for text in ("", CLOCKS.replace("rate accuracy", "new rate accuracy"),
                     CLOCKS + "xosc 7 7 0 50000000 0 0 50000 Y deviceless none\n"):
            with self.assertRaises(ValueError): core.clock_rows(text)
        report = fixture()
        for key in ("first", "second"):
            report[key]["clocks"] = {"status": "unavailable", "selected": {}}
        core.validate_lifecycle(report, reference)
        self.assertFalse(report["limitations"]["power_clock_ownership_proven"])

    def test_live_interrupt_counters_are_not_required_idle(self):
        rows = core.interrupt_rows(IRQS)
        self.assertEqual([r["linux_irq"] for r in rows], [38, 39, 44, 112])
        report = fixture()
        report["second"]["interrupts"][1]["cpu_counts"][0] += 99
        core.validate_lifecycle(report, reference)
        report["second"]["interrupts"][1]["hwirq"] += 1
        with self.assertRaisesRegex(ValueError, "changed between snapshots"):
            core.validate_lifecycle(report, reference)
        for raw in (IRQS.replace("CPU0", "CPU8"), IRQS.replace("44: 0", "44: bad")):
            with self.assertRaises(ValueError): core.interrupt_rows(raw)

    def test_decode_gic_masks_excludes_nvme_adjacent_bank_bits(self):
        decoded = core.validate_lifecycle(fixture(), reference)
        self.assertEqual(decoded["pcie2_direct_gic_intids"], [265, 266])
        self.assertEqual(decoded["pcie2_intx_gic_intids"], [261, 262, 263, 264])
        self.assertEqual(decoded["pcie2_mip_gic_intids"], [160, 223])
        self.assertEqual(decoded["pcie2_gic_bank_masks"], {"5": "0xffffffff", "6": "0xffffffff", "8": "0x000007e0"})
        # NVMe controller INTID256 shares bank8 but is excluded.
        self.assertFalse(int(decoded["pcie2_gic_bank_masks"]["8"], 16) & 1)
        self.assertEqual(decoded["pcie1_direct_gic_intids"], [255, 256])
        self.assertEqual(decoded["pcie1_mip_gic_intids"], [279, 286])
        self.assertEqual(int(decoded["pcie2_gic_bank_masks"]["8"], 16) & (0xff << 23), 0)
        self.assertEqual(decoded["gem_clock_ids"], {"pclk": 12, "hclk": 12, "tsu_clk": 29, "tx_clk": 16})
        self.assertEqual(decoded["rp1_oscillator_hz"], 50000000)
        self.assertEqual(decoded["bridge_reset_ids"], [43, 44])

    def test_binding_mutations_refused_not_inferred(self):
        changes = [(core.PCIE1, "resets", cells(5, 6, 44)),
                   (core.PCIE1, "interrupt-parent", cells(99)),
                   (core.PCIE1, "status", b"disabled\0".hex()),
                   (core.PCIE1, "interrupts-extended", cells(1, 0, 223, 4)),
                   (core.XOSC, "clock-frequency", ""),
                   (core.XOSC, "phandle", cells(99)),
                   (core.XOSC, "#clock-cells", cells(1)),
                   (core.MIP1, "msi-ranges", cells(1, 0, 128, 1, 8))]
        for node, name, value in changes:
            report = fixture()
            for which in ("first", "second"):
                report[which]["of_properties_hex"][node][name] = value
            with self.assertRaises(ValueError, msg=(node, name)):
                core.validate_lifecycle(report, reference)
        for name, value in (("interrupts", cells(1, 233, 4, 0, 234, 4)),
                            ("interrupt-map", ""), ("msi-parent", cells(99))):
            report = fixture()
            for which in ("first", "second"):
                report["reference"][which]["of_properties_hex"][core.PCIE2][name] = value
            with self.assertRaises(ValueError): core.validate_lifecycle(report, reference)

    def test_changed_boot_power_or_claims_rejected(self):
        for mutation in (lambda r: r["identity_after"].update(boot_id="other"),
                         lambda r: r["second"]["power"]["pcie1-host"].update(runtime_status="suspended"),
                         lambda r: r["operations"].update(reboots=1),
                         lambda r: r["operations"].update(reboots=False),
                         lambda r: r["limitations"].update(xnu_admission=True)):
            report = fixture(); mutation(report)
            with self.assertRaises(ValueError): core.validate_lifecycle(report, reference)
        for mutate in (lambda s: s["power"].pop("pcie1-host"),
                       lambda s: s["clocks"]["selected"]["clk_sys"].update(rate_hz=True),
                       lambda s: s["interrupts"][0].update(cpu_counts=[True]),
                       lambda s: s["msi_allocations"]["0002:01:00.0"].update({"45": "bogus"})):
            report = fixture()
            for which in ("first", "second"): mutate(report[which])
            with self.assertRaises(ValueError): core.validate_lifecycle(report, reference)

    def test_remote_program_uses_original_reference_namespace(self):
        source = controller.remote_source()
        source = source.rsplit("print(json.dumps(capture_lifecycle(reference), sort_keys=True))", 1)[0]
        namespace = {}
        exec(compile(source, "embedded-reference", "exec"), namespace)
        self.assertEqual(namespace["reference"].PROPERTIES, reference.PROPERTIES)
        self.assertEqual(namespace["EXTRA_PROPERTIES"], core.EXTRA_PROPERTIES)
        namespace["capture_lifecycle"] = lambda module: {"namespace": module.__name__}
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            exec("print(json.dumps(capture_lifecycle(reference), sort_keys=True))", namespace)
        self.assertEqual(json.loads(stream.getvalue()), {"namespace": "pcie_reference_core"})

    def test_capture_bounds_identity_after_both_extra_snapshots(self):
        report = fixture()
        fake = mock.Mock()
        fake.capture_linux.return_value = report["reference"]
        fake.linux_identity.return_value = report["identity_after"]
        fake.validate_capture.side_effect = reference.validate_capture
        with mock.patch.object(core, "linux_extra", side_effect=[report["first"], report["second"]]) as read:
            actual = core.capture_lifecycle(fake)
        self.assertEqual(read.call_count, 2)
        self.assertEqual(actual["status"], "linux_reference_only")
        fake.linux_identity.assert_called_once_with()

    def test_plan_only_no_ssh_overwrite_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "plan"
            with mock.patch("sys.argv", ["capture", "--output-dir", str(out)]), \
                    mock.patch.object(controller.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(controller.main(), 0)
                run.assert_not_called()
                with self.assertRaises(FileExistsError): controller.main()
            self.assertEqual([p.name for p in out.iterdir()], ["plan.json"])

    def test_source_drift_stops_before_ssh_timeout_never_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "drift"
            with mock.patch("sys.argv", ["capture", "--execute", "--output-dir", str(out)]), \
                    mock.patch.object(controller, "hashes", side_effect=[{"a": "before"}, {"a": "after"}]), \
                    mock.patch.object(controller.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "source changed before SSH"): controller.main()
                run.assert_not_called()
            out = Path(directory) / "timeout"
            error = subprocess.TimeoutExpired("ssh", 45, output=b"partial")
            with mock.patch("sys.argv", ["capture", "--execute", "--output-dir", str(out)]), \
                    mock.patch.object(controller.subprocess, "run", side_effect=error) as run:
                with self.assertRaises(subprocess.TimeoutExpired): controller.main()
                self.assertEqual(run.call_count, 1)
                self.assertIn("StrictHostKeyChecking=yes", run.call_args.args[0])
            self.assertEqual((out / "partial.stdout").read_bytes(), b"partial")
            self.assertEqual(json.loads((out / "result.json").read_text())["remote_outcome"], "unknown")


if __name__ == "__main__":
    unittest.main()
