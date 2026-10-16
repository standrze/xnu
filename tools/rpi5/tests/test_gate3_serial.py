# SPDX-License-Identifier: BSD-2-Clause
"""Marker extraction must reject contradictory hardware evidence."""

import importlib.util
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "check_gate3_serial.py"
SPEC = importlib.util.spec_from_file_location("gate3_serial", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Gate3SerialTests(unittest.TestCase):
    def test_exact_markers_and_raw_hash(self):
        raw = (b"noise RPI5XNU:SMP:FAIL\nRPI5XNU:SMP:PASS\r\n"
               b"RPI5XNU:TLB:PASS\nRPI5XNU:SMP:PASS extra\n")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "serial.bin"
            path.write_bytes(raw)
            with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("not streaming")):
                capture = MODULE.inspect(path)
            self.assertEqual([(m["stage"], m["result"]) for m in capture["markers"]],
                             [("SMP", "PASS"), ("TLB", "PASS")])
            self.assertEqual(capture["bytes"], len(raw))
            self.assertEqual(capture["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertTrue(MODULE.evaluate([capture], ["SMP", "TLB"])["marker_check_pass"])

    def test_fail_overrides_pass_and_missing_fails(self):
        captures = [{"markers": [{"stage": "SMP", "result": "PASS"}]},
                    {"markers": [{"stage": "SMP", "result": "FAIL"}]}]
        report = MODULE.evaluate(captures, ["SMP", "TLB"])
        self.assertFalse(report["marker_check_pass"])
        self.assertEqual(report["failed_stages"], ["SMP"])
        self.assertEqual(report["missing_required_stages"], ["SMP", "TLB"])


if __name__ == "__main__":
    unittest.main()
