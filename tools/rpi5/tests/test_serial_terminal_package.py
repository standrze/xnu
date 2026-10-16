# SPDX-License-Identifier: BSD-2-Clause
"""Terminal preflight must reject mistaken or altered board packages."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import check_serial_terminal_package as package


def fixture(directory: Path):
    image_dir = directory / "package"
    image_dir.mkdir()
    image = image_dir / "probe.bin"
    image.write_bytes(package.TERMINAL_COMMAND + b"\0XNU-RPI5 TERMINAL PID1 OK\0"
                      b"xnu-rpi5> \0TICKS=0x\0 FREQ=0x\0"
                      b"UART_IRQ_BINDING SPI=121 INTID=153 NOT_ENABLED")
    kernel = directory / "kernel"
    kernel.write_bytes(b"kernel")
    init = directory / "init"
    init.write_bytes(b"terminal pid1")
    baseline = directory / "baseline"
    baseline.write_bytes(b"gate3 baseline")
    manifest = {
        "sha256": {str(image): package.sha256(image)},
        "embedded_kernel": {"sha256": package.sha256(kernel)},
        "embedded_init": {"sha256": package.sha256(init)},
        "serial_terminal": True, "xnu_transfer_enabled": True,
        "gate3_cpu_on_all": True,
        "commands": [["clang", "-DRPI5_SERIAL_TERMINAL=1", "-c", "probe_main.c"]],
    }
    for key in ("gate3_register_cpus", "gate3_register_boot_cpu", "gate3_cpu_on_1",
                "gate3_tlb_trial", "gate3_user_tlb_trial", "gate3_concurrency_trial",
                "gate3_xnupost_inventory", "gate3_xnupost_index", "gate3_xnupost_config",
                "gate3_qualification_config", "gate3_soak_seconds"):
        manifest[key] = False
    (image_dir / "manifest.json").write_text(json.dumps(manifest))
    return image_dir, kernel, init, baseline


class SerialTerminalPackageTests(unittest.TestCase):
    def test_process_preflight_rejects_original_console(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = fixture(Path(temporary))
            with patch.object(package, "GATE3_BASELINE_SHA256", package.sha256(args[3])):
                report = package.inspect(*args, process_trial=True)
            self.assertFalse(report["preflight_pass"])
            self.assertFalse(report["checks"]["distinct_process_payload_embedded"])

    def test_matching_separate_package_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = fixture(Path(temporary))
            with patch.object(package, "GATE3_BASELINE_SHA256", package.sha256(args[3])):
                report = package.inspect(*args)
            self.assertTrue(report["preflight_pass"])
            self.assertTrue(all(report["checks"].values()))

    def test_mutations_are_rejected(self):
        for mutation in ("image", "init", "qualify", "compile_switch", "baseline"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                image_dir, kernel, init, baseline = fixture(Path(temporary))
                expected_baseline = package.sha256(baseline)
                manifest_path = image_dir / "manifest.json"
                manifest = json.loads(manifest_path.read_text())
                if mutation == "image":
                    with (image_dir / "probe.bin").open("ab") as stream:
                        stream.write(b"changed")
                elif mutation == "init":
                    init.write_bytes(b"wrong pid1")
                elif mutation == "qualify":
                    manifest["gate3_qualification_config"] = "1_34"
                elif mutation == "compile_switch":
                    manifest["commands"][0][1] = "-DRPI5_SERIAL_TERMINAL=0"
                elif mutation == "baseline":
                    baseline.write_bytes(b"wrong baseline")
                manifest_path.write_text(json.dumps(manifest))
                with patch.object(package, "GATE3_BASELINE_SHA256", expected_baseline):
                    self.assertFalse(package.inspect(image_dir, kernel, init, baseline)["preflight_pass"])


if __name__ == "__main__":
    unittest.main()
