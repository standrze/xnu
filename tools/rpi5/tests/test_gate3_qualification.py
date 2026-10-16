# SPDX-License-Identifier: BSD-2-Clause
"""The combined run must be one ordered, independently checked capture."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "check_gate3_qualification.py"
SPEC = importlib.util.spec_from_file_location("gate3_qualification", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


RAW = (
    b"RPi: BOOTSYS release VERSION:6219bf00\r\n"
    b"RPI5XNU:CPU_ON:ONLINE_MASK=0xf\r\n"
    b"XNU-RPI5 USERSPACE PID1 OK\r\n"
    b"[KTEST]\tSTART\t1\r\n"
    b"[KTEST]\tTESTBEGIN\t100\t1\txnu/test.c\t10\txnu.ipi_test\r\n"
    b"[KTEST]\tPASS\t110\t1\txnu/test.c\t11\tIPI delivered\r\n"
    b"[KTEST]\tTESTEND\t120\t1\txnu/test.c\t12\txnu.ipi_test\r\n"
    b"[KTEST]\tFINISH\r\n"
    b"RPI5XNU:XNUPOST:PASS SELECTED=1 PASSED=1\r\n"
    b"RPI5XNU:XNUPOST:TIMING TICKS=900 FREQ=100\r\n"
    b"RPI5XNU:QUALIFICATION:START STAGE=SMP_CONCURRENCY\r\n"
    b"RPI5XNU:SMP_CONCURRENCY:DETAIL CPUS=0,1,2,3 COUNT=4000000 OVERLAP=1\r\n"
    b"RPI5XNU:SMP_CONCURRENCY:TIMING TICKS=500 FREQ=100\r\n"
    b"RPI5XNU:SMP_CONCURRENCY:PASS\r\n"
    b"RPI5XNU:QUALIFICATION:START STAGE=TLB\r\n"
    b"RPI5XNU:TLB:DETAIL REMAP_ROUNDS=16 PERMISSION_ROUNDS=8 STRESS_ROUNDS=64 STRESS_PERMISSION_ROUNDS=32 CPUS=1-3\r\n"
    b"RPI5XNU:TLB:TIMING TICKS=250 FREQ=100\r\n"
    b"RPI5XNU:TLB:PASS\r\n"
    b"RPI5XNU:QUALIFICATION:START STAGE=USER_TLB\r\n"
    b"RPI5XNU:USER_TLB:DETAIL REMAP_ROUNDS=64 CPUS=1-3\r\n"
    b"RPI5XNU:USER_TLB:TIMING TICKS=300 FREQ=100\r\n"
    b"RPI5XNU:USER_TLB:PASS\r\n"
    b"RPI5XNU:CROSS_CORE_INVALIDATION:PASS\r\n"
    b"RPI5XNU:SOAK:ARM SECONDS=300\r\n"
    b"RPI5XNU:QUALIFICATION:PRE_SOAK_PASS\r\n"
    b"RPI5XNU:SOAK:HEARTBEAT ACKS=1,1,1\r\n"
    b"RPI5XNU:SOAK:HEARTBEAT ACKS=80,80,80\r\n"
    b"RPI5XNU:IPI_STRESS:PASS CPUS=1-3 ACKS=80,80,80\r\n"
    b"RPI5XNU:CACHE_VIS:PASS ROUNDS=64 ERRORS=0\r\n"
    b"RPI5XNU:SOAK:HEARTBEAT ACKS=160,160,160\r\n"
    b"RPI5XNU:SOAK:HEARTBEAT ACKS=240,240,240\r\n"
    b"RPI5XNU:SOAK:PASS SECONDS=300\r\n"
    b"RPi: BOOTSYS Linux fallback\r\n"
    b"Debian GNU/Linux 13 kamidana\r\n"
)


class Gate3QualificationTests(unittest.TestCase):
    def test_selected_case_file_is_exactly_34_unique_names(self):
        selection = SCRIPT.with_name("gate3_selected_cases.txt")
        names = [line.strip() for line in selection.read_text().splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual(len(names), 34)
        self.assertEqual(len(set(names)), 34)
        self.assertEqual(names[22], "xnu.vfp_state_test")
        self.assertEqual(names[23], "xnu.vm_tests")

    def check(self, raw, pre_soak_only=False):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "serial.bin").write_bytes(raw)
            (directory / "state.json").write_text(json.dumps({
                "status": "finished", "requested_seconds": 480,
                "started_utc": "2026-09-26T00:00:00+00:00",
                "ended_utc": "2026-09-26T00:08:00+00:00",
                "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            }))
            return MODULE.inspect(directory, ["xnu.ipi_test"], 300,
                                  pre_soak_only=pre_soak_only)

    def test_ordered_complete_capture_passes(self):
        report = self.check(RAW)
        self.assertTrue(report["qualification_check_pass"])
        self.assertEqual(report["trial_duration_seconds"]["USER_TLB"], 3)

    def test_pre_soak_can_be_checked_before_eight_hour_result(self):
        first_boot = RAW.split(b"RPI5XNU:SOAK:HEARTBEAT", 1)[0]
        self.assertTrue(self.check(first_boot, pre_soak_only=True)
                        ["qualification_check_pass"])
        self.assertFalse(self.check(first_boot)["qualification_check_pass"])
        self.assertFalse(self.check(RAW, pre_soak_only=True)
                         ["qualification_check_pass"])
        missing = first_boot.replace(
            b"RPI5XNU:QUALIFICATION:PRE_SOAK_PASS\r\n", b"")
        self.assertFalse(self.check(missing, pre_soak_only=True)
                         ["qualification_check_pass"])

    def test_pre_soak_rejects_failed_or_later_boot_evidence(self):
        first_boot = RAW.split(b"RPI5XNU:SOAK:HEARTBEAT", 1)[0]
        self.assertFalse(self.check(first_boot + b"RPI5XNU:TLB:FAIL\r\n",
                                    pre_soak_only=True)["qualification_check_pass"])
        moved = first_boot.replace(
            b"RPI5XNU:QUALIFICATION:PRE_SOAK_PASS\r\n",
            b"RPi: BOOTSYS again\r\n"
            b"RPI5XNU:QUALIFICATION:PRE_SOAK_PASS\r\n")
        self.assertFalse(self.check(moved, pre_soak_only=True)
                         ["qualification_check_pass"])

    def test_one_uart_interleave_before_arm_duration_is_accepted(self):
        interleaved = RAW.replace(b"SOAK:ARM SECONDS=300",
                                  b"SOAK:ARM SECONDS=x300")
        self.assertTrue(self.check(interleaved)["qualification_check_pass"])
        doubled = RAW.replace(b"SOAK:ARM SECONDS=300",
                              b"SOAK:ARM SECONDS=xy300")
        self.assertFalse(self.check(doubled)["qualification_check_pass"])

    def test_reordered_or_cross_boot_evidence_rejected(self):
        moved = RAW.replace(
            b"RPI5XNU:CROSS_CORE_INVALIDATION:PASS\r\n", b"")
        moved = moved.replace(
            b"RPI5XNU:USER_TLB:PASS\r\n",
            b"RPI5XNU:CROSS_CORE_INVALIDATION:PASS\r\n"
            b"RPI5XNU:USER_TLB:PASS\r\n")
        self.assertFalse(self.check(moved)["qualification_check_pass"])
        moved = RAW.replace(
            b"RPI5XNU:SOAK:PASS SECONDS=300\r\n",
            b"RPi: BOOTSYS premature reset\r\n"
            b"RPI5XNU:SOAK:PASS SECONDS=300\r\n")
        self.assertFalse(self.check(moved)["qualification_check_pass"])

    def test_failure_and_missing_named_case_rejected(self):
        self.assertFalse(self.check(RAW + b"RPI5XNU:TLB:FAIL\r\n")
                         ["qualification_check_pass"])
        self.assertFalse(self.check(RAW.replace(b"xnu.ipi_test", b"xnu.other_test"))
                         ["qualification_check_pass"])

    def test_named_subtest_skip_requires_exact_exception(self):
        raw = RAW.replace(
            b"[KTEST]\tPASS\t110\t1\txnu/test.c\t11\tIPI delivered\r\n",
            b"[KTEST]\tPASS\t110\t1\txnu/test.c\t11\tIPI delivered\r\n"
            b"[KTEST]\tTESTSKIP\t115\txnu/test.c\t12\tUnsupported feature\r\n")
        self.assertFalse(self.check(raw)["qualification_check_pass"])
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "serial.bin").write_bytes(raw)
            (directory / "state.json").write_text(json.dumps({
                "status": "finished", "requested_seconds": 480,
                "started_utc": "2026-09-26T00:00:00+00:00",
                "ended_utc": "2026-09-26T00:08:00+00:00",
                "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            }))
            report = MODULE.inspect(directory, ["xnu.ipi_test"], 300,
                                    {"xnu.ipi_test": ["Unsupported feature"]})
            self.assertTrue(report["qualification_check_pass"])

    def test_trial_detail_and_xnupost_records_must_be_in_stage(self):
        detail = b"RPI5XNU:USER_TLB:DETAIL REMAP_ROUNDS=64 CPUS=1-3\r\n"
        moved = RAW.replace(detail, b"").replace(
            b"RPI5XNU:QUALIFICATION:START STAGE=USER_TLB\r\n",
            detail + b"RPI5XNU:QUALIFICATION:START STAGE=USER_TLB\r\n")
        self.assertFalse(self.check(moved)["qualification_check_pass"])
        timing = b"RPI5XNU:XNUPOST:TIMING TICKS=900 FREQ=100\r\n"
        moved = RAW.replace(timing, b"").replace(
            b"RPI5XNU:XNUPOST:PASS SELECTED=1 PASSED=1\r\n",
            timing + b"RPI5XNU:XNUPOST:PASS SELECTED=1 PASSED=1\r\n")
        self.assertFalse(self.check(moved)["qualification_check_pass"])
        late_case = RAW.replace(b"[KTEST]\tFINISH\r\n", b"").replace(
            b"RPI5XNU:XNUPOST:PASS SELECTED=1 PASSED=1\r\n",
            b"RPI5XNU:XNUPOST:PASS SELECTED=1 PASSED=1\r\n"
            b"[KTEST]\tFINISH\r\n")
        self.assertFalse(self.check(late_case)["qualification_check_pass"])


if __name__ == "__main__":
    unittest.main()
