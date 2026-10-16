# SPDX-License-Identifier: BSD-2-Clause
"""Standalone Gate 3 trial evidence must include workload and timing."""

import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "check_gate3_trials.py"
SPEC = importlib.util.spec_from_file_location("gate3_trials", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


BASE = (b"  1.07 RPi: BOOTSYS release VERSION:6219bf00\r\n"
        b"RPI5XNU:CPU_ON:ONLINE_MASK=0xf\r\n"
        b"XNU-RPI5 USERSPACE PID1 OK\r\n")


class Gate3TrialTests(unittest.TestCase):
    def check(self, raw, stage):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "serial.bin"
            path.write_bytes(raw)
            return MODULE.inspect(path, stage)

    def test_concurrency_requires_all_four_cpus_shared_count_and_overlap(self):
        raw = (BASE + b"RPI5XNU:SMP_CONCURRENCY:DETAIL CPUS=0,1,2,3 "
               b"COUNT=4000000 OVERLAP=1\r\n"
               b"RPI5XNU:SMP_CONCURRENCY:TIMING TICKS=500 FREQ=100\r\n"
               b"RPI5XNU:SMP_CONCURRENCY:PASS\r\n")
        report = self.check(raw, "SMP_CONCURRENCY")
        self.assertTrue(report["trial_check_pass"])
        self.assertEqual(report["duration_seconds"], 5)
        self.assertFalse(self.check(raw.replace(b"OVERLAP=1", b"OVERLAP=0"),
                                    "SMP_CONCURRENCY")["trial_check_pass"])
        self.assertFalse(self.check(raw + b"RPI5XNU:TLB:FAIL\r\n",
                                    "SMP_CONCURRENCY")["trial_check_pass"])
        late_pid1 = raw.replace(b"XNU-RPI5 USERSPACE PID1 OK\r\n", b"")
        late_pid1 += b"XNU-RPI5 USERSPACE PID1 TICK\r\n"
        self.assertTrue(self.check(late_pid1, "SMP_CONCURRENCY")
                        ["trial_check_pass"])

    def test_tlb_requires_all_three_subtests_and_exact_pass(self):
        raw = (BASE + b"RPI5XNU:TLB:DETAIL REMAP_ROUNDS=16 "
               b"PERMISSION_ROUNDS=8 STRESS_ROUNDS=64 STRESS_PERMISSION_ROUNDS=32 CPUS=1-3\r\n"
               b"RPI5XNU:TLB:TIMING TICKS=250 FREQ=100\r\n"
               b"RPI5XNU:TLB:PASS\r\n")
        self.assertTrue(self.check(raw, "TLB")["trial_check_pass"])
        self.assertTrue(self.check(raw.replace(b"PID1 OK", b"PID1 TICK"),
                                   "TLB")["trial_check_pass"])
        self.assertFalse(self.check(raw.replace(b"STRESS_ROUNDS=64",
                                                b"STRESS_ROUNDS=0"), "TLB")["trial_check_pass"])
        self.assertFalse(self.check(raw.replace(b"STRESS_PERMISSION_ROUNDS=32",
                                                b"STRESS_PERMISSION_ROUNDS=0"), "TLB")["trial_check_pass"])
        self.assertFalse(self.check(raw.replace(b"RPI5XNU:TLB:PASS\r\n",
                                                b"RPI5XNU:TLB:PASS EXTRA\r\n"),
                                    "TLB")["trial_check_pass"])

    def test_user_tlb_requires_64_rounds_timing_and_same_boot_pid1(self):
        raw = (BASE + b"RPI5XNU:USER_TLB:DETAIL REMAP_ROUNDS=64 CPUS=1-3\r\n"
               b"RPI5XNU:USER_TLB:TIMING TICKS=300 FREQ=100\r\n"
               b"RPI5XNU:USER_TLB:PASS\r\n")
        self.assertTrue(self.check(raw, "USER_TLB")["trial_check_pass"])
        self.assertFalse(self.check(raw.replace(b"REMAP_ROUNDS=64", b"REMAP_ROUNDS=63"),
                                    "USER_TLB")["trial_check_pass"])
        self.assertFalse(self.check(raw.replace(b"FREQ=100", b"FREQ=0"),
                                    "USER_TLB")["trial_check_pass"])
        self.assertTrue(self.check(raw.replace(b"XNU-RPI5 USERSPACE PID1 OK\r\n", b"") +
                                   b"XNU-RPI5 USERSPACE PID1 TICK\r\n",
                                   "USER_TLB")["trial_check_pass"])
        self.assertFalse(self.check(raw + b"RPI5XNU:USER_TLB:FAIL\r\n",
                                    "USER_TLB")["trial_check_pass"])

    def test_missing_boot_or_ambiguous_timing_rejected(self):
        raw = (BASE + b"RPI5XNU:TLB:DETAIL REMAP_ROUNDS=16 "
               b"PERMISSION_ROUNDS=8 STRESS_ROUNDS=64 STRESS_PERMISSION_ROUNDS=32 CPUS=1-3\r\n"
               b"RPI5XNU:TLB:TIMING TICKS=250 FREQ=100\r\n"
               b"RPI5XNU:TLB:PASS\r\n")
        self.assertFalse(self.check(raw.replace(b"ONLINE_MASK=0xf", b"ONLINE_MASK=0x7"),
                                    "TLB")["trial_check_pass"])
        self.assertFalse(self.check(raw + b"RPI5XNU:TLB:TIMING TICKS=251 FREQ=100\r\n",
                                    "TLB")["trial_check_pass"])
        self.assertTrue(self.check(raw + b"RPi: BOOTSYS 2026\r\n",
                                   "TLB")["trial_check_pass"])
        self.assertFalse(self.check(BASE + raw,
                                    "TLB")["trial_check_pass"])
        second_boot_pid1 = raw.replace(b"XNU-RPI5 USERSPACE PID1 OK\r\n", b"")
        second_boot_pid1 += (b"RPi: BOOTSYS 2026\r\n"
                             b"XNU-RPI5 USERSPACE PID1 TICK\r\n")
        self.assertFalse(self.check(second_boot_pid1, "TLB")["trial_check_pass"])
        late_details = raw.replace(b"RPI5XNU:TLB:DETAIL REMAP_ROUNDS=16 "
                                   b"PERMISSION_ROUNDS=8 STRESS_ROUNDS=64 STRESS_PERMISSION_ROUNDS=32 CPUS=1-3\r\n", b"")
        late_details += (b"RPi: BOOTSYS 2026\r\n"
                         b"RPI5XNU:TLB:DETAIL REMAP_ROUNDS=16 "
                         b"PERMISSION_ROUNDS=8 STRESS_ROUNDS=64 STRESS_PERMISSION_ROUNDS=32 CPUS=1-3\r\n")
        self.assertFalse(self.check(late_details, "TLB")["trial_check_pass"])


if __name__ == "__main__":
    unittest.main()
