# SPDX-License-Identifier: BSD-2-Clause
"""The long-soak evidence checker rejects incomplete or contradictory logs."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "check_gate3_soak.py"
SPEC = importlib.util.spec_from_file_location("gate3_soak", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture(directory: Path, raw: bytes, *, status="finished", seconds=480):
    (directory / "serial.bin").write_bytes(raw)
    (directory / "state.json").write_text(json.dumps({
        "status": status,
        "requested_seconds": seconds,
        "started_utc": "2026-09-26T00:00:00+00:00",
        "ended_utc": "2026-09-26T00:08:00+00:00",
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }))


GOOD = (b"RPi: BOOTSYS XNU first boot\r\n"
        b"RPI5XNU:SOAK:ARM SECONDS=300\r\n"
        b"RPI5XNU:SOAK:HEARTBEAT ACKS=1,1,1\r\n"
        b"RPI5XNU:SOAK:HEARTBEAT ACKS=80,80,80\r\n"
        b"RPI5XNU:IPI_STRESS:PASS CPUS=1-3 ACKS=80,80,80\r\n"
        b"RPI5XNU:CACHE_VIS:PASS ROUNDS=64 ERRORS=0\r\n"
        b"RPI5XNU:SOAK:HEARTBEAT ACKS=160,160,160\r\n"
        b"RPI5XNU:SOAK:HEARTBEAT ACKS=240,240,240\r\n"
        b"RPI5XNU:SOAK:PASS SECONDS=300\r\n"
        b"RPi: BOOTSYS Linux fallback\r\n"
        b"Debian GNU/Linux 13 kamidana\r\n")


class Gate3SoakTests(unittest.TestCase):
    def test_late_start_tail_support_never_claims_formal_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            raw = b"".join(
                f"RPI5XNU:SOAK:HEARTBEAT ACKS={ack},{ack},{ack}\r\n".encode()
                for ack in range(150, 571, 60)) + b"RPI5XNU:SOAK:PASS SECONDS=600\r\n"
            fixture(directory, raw, seconds=600)
            state = json.loads((directory / "state.json").read_text())
            state["ended_utc"] = "2026-09-26T00:10:00+00:00"
            (directory / "state.json").write_text(json.dumps(state))
            report = MODULE.inspect_tail(directory, 600)
            self.assertTrue(report["tail_support_pass"])
            self.assertFalse(report["formal_soak_exit_proven"])
            self.assertFalse(MODULE.inspect(directory, 600)["marker_check_pass"])
            fixture(directory, b"RPi: BOOTSYS reset\r\n" + raw, seconds=600)
            state = json.loads((directory / "state.json").read_text())
            state["ended_utc"] = "2026-09-26T00:10:00+00:00"
            (directory / "state.json").write_text(json.dumps(state))
            self.assertFalse(MODULE.inspect_tail(directory, 600)["tail_support_pass"])

    def test_complete_capture_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture(directory, GOOD)
            report = MODULE.inspect(directory, 300)
            self.assertTrue(report["marker_check_pass"])
            self.assertEqual(report["heartbeat_count"], 4)
            self.assertEqual(report["last_acks"], (240, 240, 240))

    def test_early_reset_and_failure_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture(directory, GOOD.replace(b"SOAK:PASS SECONDS=300",
                                            b"SOAK:FAIL STAGE=HEARTBEAT"))
            report = MODULE.inspect(directory, 300)
            self.assertFalse(report["marker_check_pass"])
            self.assertFalse(report["checks"]["soak_pass"])
            self.assertFalse(report["checks"]["no_failure_marker"])

    def test_second_boot_cannot_supply_soak_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            raw = GOOD.replace(
                b"RPI5XNU:SOAK:PASS SECONDS=300\r\n",
                b"RPi: BOOTSYS premature warm reset\r\n"
                b"RPI5XNU:SOAK:PASS SECONDS=300\r\n")
            fixture(directory, raw)
            report = MODULE.inspect(directory, 300)
            self.assertFalse(report["marker_check_pass"])
            self.assertFalse(report["checks"]["soak_pass"])

    def test_linux_message_without_recovery_boot_banner_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            raw = GOOD.replace(b"RPi: BOOTSYS Linux fallback\r\n", b"")
            fixture(directory, raw)
            report = MODULE.inspect(directory, 300)
            self.assertFalse(report["checks"]["linux_serial_after_pass"])

    def test_hash_and_progress_regression_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture(directory, GOOD.replace(b"ACKS=160,160,160", b"ACKS=79,79,79"))
            state = json.loads((directory / "state.json").read_text())
            state["sha256"] = "0" * 64
            (directory / "state.json").write_text(json.dumps(state))
            report = MODULE.inspect(directory, 300)
            self.assertFalse(report["marker_check_pass"])
            self.assertFalse(report["checks"]["heartbeats_monotonic"])
            self.assertFalse(report["checks"]["raw_sha256_matches"])

    def test_any_gate3_failure_overrides_later_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture(directory, GOOD.replace(
                b"RPI5XNU:SOAK:PASS SECONDS=300",
                b"RPI5XNU:IPI_STRESS:FAIL ACKS=0,0,0\r\n"
                b"RPI5XNU:SOAK:PASS SECONDS=300"))
            report = MODULE.inspect(directory, 300)
            self.assertFalse(report["marker_check_pass"])
            self.assertFalse(report["checks"]["no_failure_marker"])

    def test_missing_start_and_heartbeat_gap_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            raw = GOOD.replace(b"RPI5XNU:SOAK:ARM SECONDS=300\r\n", b"")
            fixture(directory, raw)
            checks = MODULE.inspect(directory, 300)["checks"]
            self.assertFalse(checks["soak_arm"])
            raw = GOOD
            raw = raw.replace(b"ACKS=80,80,80\r\n", b"ACKS=200,200,200\r\n")
            raw = raw.replace(b"ACKS=160,160,160\r\n", b"ACKS=220,220,220\r\n")
            raw = raw.replace(b"ACKS=240,240,240\r\n", b"ACKS=260,260,260\r\n")
            fixture(directory, raw)
            checks = MODULE.inspect(directory, 300)["checks"]
            self.assertFalse(checks["heartbeat_gaps_bounded"])

    def test_single_interleaved_arm_character_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture(directory, GOOD.replace(b"ARM SECONDS=300", b"ARM SECONDS=k300"))
            self.assertTrue(MODULE.inspect(directory, 300)["marker_check_pass"])

    def test_short_capture_or_pass_before_arm_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture(directory, GOOD.replace(
                b"RPI5XNU:SOAK:ARM SECONDS=300\r\n", b""))
            state = json.loads((directory / "state.json").read_text())
            state["ended_utc"] = "2026-09-26T00:02:00+00:00"
            (directory / "state.json").write_text(json.dumps(state))
            checks = MODULE.inspect(directory, 300)["checks"]
            self.assertFalse(checks["actual_capture_duration"])
            self.assertFalse(checks["soak_pass"])


if __name__ == "__main__":
    unittest.main()
