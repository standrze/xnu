# SPDX-License-Identifier: BSD-2-Clause
"""Twenty true cold boots require a complete, unbroken evidence ledger."""

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "check_gate3_cold_boots.py"
SPEC = importlib.util.spec_from_file_location("gate3_cold_boots", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

IMAGE = "a" * 64
KERNEL = "b" * 64
def synthetic_pre_soak():
    lines = [b"  1.17 RPi: BOOTSYS release VERSION:6219bf00",
             b"RPI5XNU:CPU_ON:ONLINE_MASK=0xf",
             b"XNU-RPI5 USERSPACE PID1 TICK",
             b"[KTEST]\tSTART\t1"]
    for index, name in enumerate(MODULE.REQUIRED_CASES, 1):
        encoded = name.encode()
        lines.extend((b"[KTEST]\tTESTBEGIN\t100\t1\txnu/test.c\t10\t" + encoded,
                      b"[KTEST]\tPASS\t110\t1\txnu/test.c\t11\tAssertion passed"))
        if name == "xnu.vm_tests":
            lines.append(b"[KTEST]\tTESTSKIP\t115\txnu/test.c\t12\t"
                         b"System not designed to support this test, skipping...")
        lines.append(b"[KTEST]\tTESTEND\t120\t1\txnu/test.c\t12\t" + encoded)
    lines.extend((b"[KTEST]\tFINISH",
                  b"RPI5XNU:XNUPOST:PASS SELECTED=34 PASSED=34",
                  b"RPI5XNU:XNUPOST:TIMING TICKS=900 FREQ=100",
                  b"RPI5XNU:QUALIFICATION:START STAGE=SMP_CONCURRENCY",
                  b"RPI5XNU:SMP_CONCURRENCY:DETAIL CPUS=0,1,2,3 COUNT=4000000 OVERLAP=1",
                  b"RPI5XNU:SMP_CONCURRENCY:TIMING TICKS=500 FREQ=100",
                  b"RPI5XNU:SMP_CONCURRENCY:PASS",
                  b"RPI5XNU:QUALIFICATION:START STAGE=TLB",
                  b"RPI5XNU:TLB:DETAIL REMAP_ROUNDS=16 PERMISSION_ROUNDS=8 "
                  b"STRESS_ROUNDS=64 STRESS_PERMISSION_ROUNDS=32 CPUS=1-3",
                  b"RPI5XNU:TLB:TIMING TICKS=250 FREQ=100",
                  b"RPI5XNU:TLB:PASS",
                  b"RPI5XNU:QUALIFICATION:START STAGE=USER_TLB",
                  b"RPI5XNU:USER_TLB:DETAIL REMAP_ROUNDS=64 CPUS=1-3",
                  b"RPI5XNU:USER_TLB:TIMING TICKS=300 FREQ=100",
                  b"RPI5XNU:USER_TLB:PASS",
                  b"RPI5XNU:CROSS_CORE_INVALIDATION:PASS",
                  b"RPI5XNU:SOAK:ARM SECONDS=28800",
                  b"RPI5XNU:QUALIFICATION:PRE_SOAK_PASS"))
    return b"\r\n".join(lines) + b"\r\n"


RAW = synthetic_pre_soak()


def stamp(value):
    return value.isoformat()


def make_ledger(root: Path, count=20):
    origin = datetime(2026, 9, 26, tzinfo=timezone.utc)
    attempts = []
    for index in range(count):
        removed = origin + timedelta(minutes=index * 3)
        restored = removed + timedelta(seconds=12)
        directory = root / f"boot-{index + 1:02d}"
        directory.mkdir()
        raw = RAW + f"RPI5XNU:COLD_BOOT:ID={index + 1}\r\n".encode()
        (directory / "serial.bin").write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        (directory / "manifest.json").write_text(json.dumps({
            "status": "finished", "bytes": len(raw), "sha256": digest,
            "started_utc": stamp(removed - timedelta(seconds=2)),
            "ended_utc": stamp(restored + timedelta(seconds=30)),
        }))
        attempts.append({
            "number": index + 1,
            "image_sha256": IMAGE,
            "kernel_sha256": KERNEL,
            "power_method": "manual 5 V disconnect",
            "power_off_evidence": "operator watched power LED go dark",
            "power_removed_utc": stamp(removed),
            "power_restored_utc": stamp(restored),
            "capture_dir": directory.name,
            "serial_sha256": digest,
            "result": "PASS",
        })
    ledger = root / "ledger.json"
    ledger.write_text(json.dumps({
        "candidate_image_sha256": IMAGE,
        "kernel_sha256": KERNEL,
        "sd_image_sha256_before": IMAGE,
        "sd_image_sha256_after": IMAGE,
        "attempts": attempts,
    }))
    return ledger


class Gate3ColdBootTests(unittest.TestCase):
    def test_receive_only_state_json_is_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = make_ledger(Path(temporary))
            directory = Path(temporary) / "boot-20"
            metadata = json.loads((directory / "manifest.json").read_text())
            metadata["transmitted_bytes"] = 0
            (directory / "state.json").write_text(json.dumps(metadata))
            (directory / "manifest.json").unlink()
            report = MODULE.evaluate(ledger)
            self.assertTrue(report["checks_pass"])
            self.assertEqual(MODULE.inspect_capture(directory)["metadata"],
                             str(directory / "state.json"))

    def test_twenty_complete_attempts_pass_machine_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = MODULE.evaluate(make_ledger(Path(temporary)))
            self.assertTrue(report["checks_pass"])
            self.assertEqual(report["ending_streak"], 20)
            self.assertTrue(report["physical_power_evidence_requires_human_review"])
            self.assertTrue(MODULE.inspect_capture(Path(temporary) / "boot-01")
                            ["ordered_boot_chain"])

    def test_linux_watchdog_boot_after_first_xnu_boot_is_allowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = make_ledger(Path(temporary))
            directory = Path(temporary) / "boot-20"
            raw = RAW + b"RPi: BOOTSYS Linux fallback\r\n"
            (directory / "serial.bin").write_bytes(raw)
            metadata = json.loads((directory / "manifest.json").read_text())
            metadata["bytes"] = len(raw)
            metadata["sha256"] = hashlib.sha256(raw).hexdigest()
            (directory / "manifest.json").write_text(json.dumps(metadata))
            data = json.loads(ledger.read_text())
            data["attempts"][-1]["serial_sha256"] = metadata["sha256"]
            ledger.write_text(json.dumps(data))
            self.assertTrue(MODULE.evaluate(ledger)["checks_pass"])

    def test_one_failure_breaks_streak(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = make_ledger(Path(temporary))
            data = json.loads(ledger.read_text())
            data["attempts"][10]["result"] = "FAIL"
            ledger.write_text(json.dumps(data))
            report = MODULE.evaluate(ledger)
            self.assertFalse(report["checks_pass"])
            self.assertEqual(report["ending_streak"], 9)

    def test_changed_image_or_missing_power_evidence_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = make_ledger(Path(temporary))
            data = json.loads(ledger.read_text())
            data["attempts"][19]["image_sha256"] = "c" * 64
            data["attempts"][19]["power_off_evidence"] = ""
            ledger.write_text(json.dumps(data))
            report = MODULE.evaluate(ledger)
            self.assertFalse(report["checks_pass"])
            self.assertEqual(report["ending_streak"], 0)

    def test_recycled_or_out_of_order_runtime_lines_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = make_ledger(Path(temporary))
            directory = Path(temporary) / "boot-20"
            raw = (b"RPI5XNU:CPU_ON:ONLINE_MASK=0xf\r\n"
                   b"XNU-RPI5 USERSPACE PID1 TICK\r\n"
                   b"  1.17 RPi: BOOTSYS release VERSION:6219bf00\r\n")
            (directory / "serial.bin").write_bytes(raw)
            metadata = json.loads((directory / "manifest.json").read_text())
            metadata["bytes"] = len(raw)
            metadata["sha256"] = hashlib.sha256(raw).hexdigest()
            (directory / "manifest.json").write_text(json.dumps(metadata))
            data = json.loads(ledger.read_text())
            data["attempts"][-1]["serial_sha256"] = metadata["sha256"]
            ledger.write_text(json.dumps(data))
            report = MODULE.evaluate(ledger)
            self.assertFalse(report["checks_pass"])
            self.assertEqual(report["ending_streak"], 0)

    def test_later_warm_boot_cannot_replace_failed_first_boot(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = make_ledger(Path(temporary))
            directory = Path(temporary) / "boot-20"
            raw = (b"RPi: BOOTSYS first boot\r\n"
                   b"RPi: BOOTSYS later warm boot\r\n"
                   b"RPI5XNU:CPU_ON:ONLINE_MASK=0xf\r\n"
                   b"XNU-RPI5 USERSPACE PID1 TICK\r\n")
            (directory / "serial.bin").write_bytes(raw)
            metadata = json.loads((directory / "manifest.json").read_text())
            metadata["bytes"] = len(raw)
            metadata["sha256"] = hashlib.sha256(raw).hexdigest()
            (directory / "manifest.json").write_text(json.dumps(metadata))
            data = json.loads(ledger.read_text())
            data["attempts"][-1]["serial_sha256"] = metadata["sha256"]
            ledger.write_text(json.dumps(data))
            report = MODULE.evaluate(ledger)
            self.assertFalse(report["checks_pass"])
            self.assertEqual(report["ending_streak"], 0)

    def test_copied_raw_serial_in_new_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = make_ledger(Path(temporary))
            raw = (Path(temporary) / "boot-19" / "serial.bin").read_bytes()
            directory = Path(temporary) / "boot-20"
            (directory / "serial.bin").write_bytes(raw)
            metadata = json.loads((directory / "manifest.json").read_text())
            metadata["bytes"] = len(raw)
            metadata["sha256"] = hashlib.sha256(raw).hexdigest()
            (directory / "manifest.json").write_text(json.dumps(metadata))
            data = json.loads(ledger.read_text())
            data["attempts"][-1]["serial_sha256"] = metadata["sha256"]
            ledger.write_text(json.dumps(data))
            report = MODULE.evaluate(ledger)
            self.assertFalse(report["checks_pass"])
            self.assertIn("raw serial capture reused by another attempt",
                          report["attempts"][-1]["reasons"])

    def test_boot_reaching_pid1_without_pre_soak_qualification_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = make_ledger(Path(temporary))
            directory = Path(temporary) / "boot-20"
            raw = (directory / "serial.bin").read_bytes().replace(
                b"RPI5XNU:QUALIFICATION:PRE_SOAK_PASS\r\n", b"")
            (directory / "serial.bin").write_bytes(raw)
            metadata = json.loads((directory / "manifest.json").read_text())
            metadata["bytes"] = len(raw)
            metadata["sha256"] = hashlib.sha256(raw).hexdigest()
            (directory / "manifest.json").write_text(json.dumps(metadata))
            data = json.loads(ledger.read_text())
            data["attempts"][-1]["serial_sha256"] = metadata["sha256"]
            ledger.write_text(json.dumps(data))
            report = MODULE.evaluate(ledger)
            self.assertFalse(report["checks_pass"])
            self.assertFalse(MODULE.inspect_capture(directory)["qualified_pre_soak"])

    def test_xnupost_summary_must_be_nonempty_and_all_passed(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = make_ledger(Path(temporary))
            directory = Path(temporary) / "boot-20"
            raw = (directory / "serial.bin").read_bytes().replace(
                b"SELECTED=34 PASSED=34", b"SELECTED=34 PASSED=33")
            (directory / "serial.bin").write_bytes(raw)
            metadata = json.loads((directory / "manifest.json").read_text())
            metadata["bytes"] = len(raw)
            metadata["sha256"] = hashlib.sha256(raw).hexdigest()
            (directory / "manifest.json").write_text(json.dumps(metadata))
            data = json.loads(ledger.read_text())
            data["attempts"][-1]["serial_sha256"] = metadata["sha256"]
            ledger.write_text(json.dumps(data))
            self.assertFalse(MODULE.evaluate(ledger)["checks_pass"])

    def test_aggregate_pass_cannot_hide_missing_named_case(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = make_ledger(Path(temporary))
            directory = Path(temporary) / "boot-20"
            raw = (directory / "serial.bin").read_bytes().replace(
                b"xnu.vfp_state_test", b"xnu.missing_vfp__")
            (directory / "serial.bin").write_bytes(raw)
            metadata = json.loads((directory / "manifest.json").read_text())
            metadata["bytes"] = len(raw)
            metadata["sha256"] = hashlib.sha256(raw).hexdigest()
            (directory / "manifest.json").write_text(json.dumps(metadata))
            data = json.loads(ledger.read_text())
            data["attempts"][-1]["serial_sha256"] = metadata["sha256"]
            ledger.write_text(json.dumps(data))
            report = MODULE.evaluate(ledger)
            self.assertFalse(report["checks_pass"])
            self.assertFalse(MODULE.inspect_capture(directory)["qualified_named_pre_soak"])

    def test_changed_sd_image_after_streak_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = make_ledger(Path(temporary))
            data = json.loads(ledger.read_text())
            data["sd_image_sha256_after"] = "c" * 64
            ledger.write_text(json.dumps(data))
            report = MODULE.evaluate(ledger)
            self.assertEqual(report["ending_streak"], 20)
            self.assertFalse(report["sd_image_hashes_match"])
            self.assertFalse(report["checks_pass"])


if __name__ == "__main__":
    unittest.main()
