# SPDX-License-Identifier: BSD-2-Clause
"""XNUPOST gate evidence must reject failing or incomplete named cases."""

import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "check_gate3_xnupost.py"
SPEC = importlib.util.spec_from_file_location("gate3_xnupost", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def capture(directory: Path, extra=b""):
    path = directory / "serial.bin"
    path.write_bytes(
        b"RPi: BOOTSYS release VERSION:6219bf00\r\n"
        b"[KTEST]\tSTART\t1\r\n"
        b"[KTEST]\tTESTBEGIN\t100\t1\txnu/test.c\t10\txnu.ipi_test\r\n"
        b"[KTEST]\tPASS\t110\t1\txnu/test.c\t11\tIPI delivered\r\n"
        b"[KTEST]\tTESTEND\t120\t1\txnu/test.c\t12\txnu.ipi_test\r\n"
        + extra + b"[KTEST]\tFINISH\r\n")
    return path


class Gate3XnupostTests(unittest.TestCase):
    def test_named_case_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = capture(Path(temporary))
            report = MODULE.inspect(path, ["xnu.ipi_test"])
            self.assertTrue(report["suite_check_pass"])
            self.assertEqual(report["cases"]["xnu.ipi_test"]["pass_assertions"], 1)

    def test_unrelated_assertion_failure_blocks_suite(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = capture(Path(temporary), b"[KTEST]\tFAIL\t130\t2\txnu/test.c\t13\tVFP broke\r\n")
            report = MODULE.inspect(path, ["xnu.ipi_test"])
            self.assertFalse(report["suite_check_pass"])
            self.assertTrue(report["failures"])

    def test_missing_or_incomplete_case_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = capture(Path(temporary))
            self.assertFalse(MODULE.inspect(path, ["xnu.pmap_test"])["suite_check_pass"])
            path.write_bytes(path.read_bytes().replace(b"TESTEND", b"TESTXXX"))
            self.assertFalse(MODULE.inspect(path, ["xnu.ipi_test"])["suite_check_pass"])

    def test_runtime_failure_after_test_blocks_suite(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = capture(Path(temporary), b"RPI5XNU:CPU_ON:FAIL\r\n")
            self.assertFalse(MODULE.inspect(path, ["xnu.ipi_test"])["suite_check_pass"])

    def test_required_case_allows_only_exact_documented_skip(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = capture(Path(temporary))
            raw = path.read_bytes().replace(
                b"[KTEST]\tPASS\t110\t1\txnu/test.c\t11\tIPI delivered\r\n",
                b"[KTEST]\tPASS\t110\t1\txnu/test.c\t11\tIPI delivered\r\n"
                b"[KTEST]\tTESTSKIP\t115\txnu/test.c\t12\tUnsupported feature\r\n")
            path.write_bytes(raw)
            self.assertFalse(MODULE.inspect(path, ["xnu.ipi_test"])
                             ["suite_check_pass"])
            allowed = {"xnu.ipi_test": ["Unsupported feature"]}
            report = MODULE.inspect(path, ["xnu.ipi_test"],
                                    allowed_skips=allowed)
            self.assertTrue(report["suite_check_pass"])
            self.assertEqual(report["cases"]["xnu.ipi_test"]["skips"], 1)
            self.assertFalse(MODULE.inspect(
                path, ["xnu.ipi_test"],
                allowed_skips={"xnu.ipi_test": ["Different reason"]})
                ["suite_check_pass"])
            self.assertFalse(MODULE.inspect(
                path, ["xnu.ipi_test"],
                allowed_skips={"xnu.other_test": ["Unsupported feature"]})
                ["suite_check_pass"])

    def test_qualification_summary_must_match_named_suite(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = capture(directory)
            self.assertFalse(MODULE.inspect(path, ["xnu.ipi_test"], True)["suite_check_pass"])
            path = capture(directory, b"RPI5XNU:XNUPOST:PASS SELECTED=2 PASSED=2\r\n")
            self.assertFalse(MODULE.inspect(path, ["xnu.ipi_test"], True)["suite_check_pass"])
            path = capture(directory, b"RPI5XNU:XNUPOST:PASS SELECTED=1 PASSED=1\r\n")
            self.assertTrue(MODULE.inspect(path, ["xnu.ipi_test"], True)["suite_check_pass"])

    def test_timing_reports_duration_and_rejects_invalid_required_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = capture(directory, b"RPI5XNU:XNUPOST:TIMING TICKS=900 FREQ=100\r\n")
            report = MODULE.inspect(path, ["xnu.ipi_test"], require_timing=True)
            self.assertTrue(report["suite_check_pass"])
            self.assertEqual(report["duration_seconds"], 9)
            path = capture(directory, b"RPI5XNU:XNUPOST:TIMING TICKS=900 FREQ=0\r\n")
            self.assertFalse(MODULE.inspect(path, ["xnu.ipi_test"],
                                            require_timing=True)["suite_check_pass"])
            path = capture(directory, b"RPI5XNU:XNUPOST:TIMING TICKS=900 FREQ=100\r\n"
                                      b"RPI5XNU:XNUPOST:TIMING TICKS=901 FREQ=100\r\n")
            self.assertFalse(MODULE.inspect(path, ["xnu.ipi_test"],
                                            require_timing=True)["suite_check_pass"])

    def test_strict_suite_rejects_records_recycled_from_later_boot(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = capture(Path(temporary),
                           b"RPI5XNU:XNUPOST:PASS SELECTED=1 PASSED=1\r\n"
                           b"RPI5XNU:XNUPOST:TIMING TICKS=900 FREQ=100\r\n")
            self.assertTrue(MODULE.inspect(path, ["xnu.ipi_test"], True, True)
                            ["suite_check_pass"])
            raw = path.read_bytes()
            raw = raw.replace(b"[KTEST]\tSTART\t1\r\n",
                              b"RPi: BOOTSYS recovery\r\n"
                              b"[KTEST]\tSTART\t1\r\n")
            path.write_bytes(raw)
            report = MODULE.inspect(path, ["xnu.ipi_test"], True, True)
            self.assertFalse(report["suite_check_pass"])
            self.assertFalse(report["first_boot_records"])


if __name__ == "__main__":
    unittest.main()
