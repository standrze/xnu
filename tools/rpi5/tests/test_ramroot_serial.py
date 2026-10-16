# SPDX-License-Identifier: BSD-2-Clause
"""RAM-root command/guard protocol fixtures, not hardware evidence."""
import io
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest

from tools.rpi5.serial_terminal_trial import (
    KEYBOARD_START, PROCESS_READY, RAMROOT_READY, RAMROOT_PASS, PROMPT,
    TERMINAL_LOADER, process_trial, ramroot_recovery_evidence, recover_ramroot_prompt, utc_now,
)
from tools.rpi5.tests.test_serial_process_trial import RESULT


class RamrootSerialTests(unittest.TestCase):
    def test_result_recovery_rejects_bad_evidence(self):
        raw = (TERMINAL_LOADER + b"RPI5XNU:RAMROOT:MOUNT NODES=10 BYTES=131072 READONLY" +
               RAMROOT_READY + PROCESS_READY + RAMROOT_PASS +
               b"RPI5XNU:PROC:EXEC_CHILD\ncorrupted wait result\n" + PROMPT)
        state = {"ramroot_trial": True, "transmitted_bytes": 8, "device": "/dev/cu.usbmodem102",
                 "ended_utc": utc_now(), "sha256": hashlib.sha256(raw).hexdigest()}
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "serial.bin").write_bytes(raw)
            (directory / "state.json").write_text(json.dumps(state))
            self.assertIn("reason", ramroot_recovery_evidence(directory, state["device"]))
            for change in ({"transmitted_bytes": 15}, {"ramroot_trial": False},
                           {"ramroot_recovery": {"previous": True}}, {"sha256": "wrong"},
                           {"ended_utc": "2020-01-01T00:00:00+00:00"}):
                (directory / "state.json").write_text(json.dumps(state | change))
                with self.assertRaises(ValueError):
                    ramroot_recovery_evidence(directory, state["device"])
            for bad in (raw + b"RPi: BOOTSYS", raw + b"RPI5XNU:PROC:FAIL",
                        raw.replace(RAMROOT_PASS, b"missing"), raw.replace(PROMPT, b"missing")):
                (directory / "serial.bin").write_bytes(bad)
                (directory / "state.json").write_text(json.dumps(state | {"sha256": hashlib.sha256(bad).hexdigest()}))
                with self.assertRaises(ValueError):
                    ramroot_recovery_evidence(directory, state["device"])

    def test_result_recovery_requires_fresh_echo(self):
        host, board = socket.socketpair()
        errors = []
        progress = {"checks": [], "transmitted_bytes": 0}
        def simulate():
            try:
                board.settimeout(1)
                command = b""
                while not command.endswith(b"\n"):
                    command += board.recv(128)
                self.assertTrue(command.startswith(b"\x15echo R"))
                self.assertEqual(len(command), 16)
                board.sendall(b"ECHO: " + command[6:].strip() + b"\n" + PROMPT)
            except Exception as error:
                errors.append(error)
            finally:
                board.close()
        worker = threading.Thread(target=simulate)
        worker.start()
        try:
            recover_ramroot_prompt(host.fileno(), io.BytesIO(), progress, quiet_seconds=0.01)
        finally:
            host.close()
            worker.join(2)
        self.assertEqual(errors, [])
        self.assertGreater(progress["transmitted_bytes"], 0)

    def test_old_process_payload_receives_no_commands(self):
        host, board = socket.socketpair()
        progress = {"ramroot_trial": True, "checks": [], "transmitted_bytes": 0}
        try:
            board.sendall(TERMINAL_LOADER + KEYBOARD_START + PROCESS_READY + PROMPT)
            with self.assertRaises(TimeoutError):
                process_trial(host.fileno(), io.BytesIO(), 1, 0.03, progress)
            self.assertEqual(progress["transmitted_bytes"], 0)
        finally:
            host.close()
            board.close()

    def test_specific_ready_and_file_checks_required(self):
        for include_files in (True, False):
            host, board = socket.socketpair()
            progress = {"ramroot_trial": True, "checks": [], "transmitted_bytes": 0}
            errors = []

            def simulate():
                try:
                    board.settimeout(2)
                    # No generic keyboard marker: process-specific readiness
                    # is the guard, while actual replies prove input delivery.
                    board.sendall(TERMINAL_LOADER + RAMROOT_READY + PROCESS_READY + PROMPT)
                    self.assertEqual(board.recv(128), b"process\n")
                    board.sendall((RAMROOT_PASS + b"\n" if include_files else b"") + RESULT + PROMPT)
                    if include_files:
                        self.assertEqual(board.recv(128), b"status\n")
                        board.sendall(b"PID 1 alive; serial console active." + PROMPT)
                except Exception as exc:
                    errors.append(exc)
                finally:
                    board.close()

            worker = threading.Thread(target=simulate)
            worker.start()
            try:
                if include_files:
                    process_trial(host.fileno(), io.BytesIO(), 1, 1, progress)
                    self.assertEqual(len(progress["checks"]), 7)
                else:
                    with self.assertRaisesRegex(RuntimeError, "file checks missing"):
                        process_trial(host.fileno(), io.BytesIO(), 1, 1, progress)
            finally:
                host.close()
                worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
