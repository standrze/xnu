# SPDX-License-Identifier: BSD-2-Clause
"""Focused host protocol checks, not fork/exec or physical Pi execution."""
import io
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

from tools.rpi5.serial_terminal_trial import (
    KEYBOARD_START, PROCESS_PASS, PROCESS_READY, PROMPT, TERMINAL_LOADER,
    parse_process_result, process_trial, process_resume_evidence,
    utc_now, wait_for_process_resume,
)


RESULT = (b"RPI5XNU:PROC:FORK_CHILD\r\n"
          b"RPI5XNU:PROC:EXEC_CHILD PID=0x0000000000000002 "
          b"ARG=RPI5_EXEC_ARG BSS_ZERO=1\r\n"
          b"RPI5XNU:PROC:WAIT_CHILD PID=0x0000000000000002 "
          b"STATUS=0x00002a00 COW=1\r\n" + PROCESS_PASS + b"\r\n")


class SerialProcessTrialTests(unittest.TestCase):
    def test_resume_evidence_rejects_stale_changed_or_transmitted_capture(self):
        raw = TERMINAL_LOADER + b"\n" + (PROCESS_READY + b"\n" + PROMPT) * 2
        state = {"process_trial": True, "transmitted_bytes": 0,
                 "device": "/dev/cu.usbmodem102", "ended_utc": utc_now(),
                 "sha256": hashlib.sha256(raw).hexdigest()}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "serial.bin").write_bytes(raw)
            (directory / "state.json").write_text(json.dumps(state))
            result = process_resume_evidence(directory, state["device"])
            self.assertFalse(result["keyboard_marker_seen"])
            for change in ({"transmitted_bytes": 8}, {"device": "/dev/cu.other"},
                           {"sha256": "wrong"}, {"process_trial": False},
                           {"ended_utc": "2020-01-01T00:00:00+00:00"}):
                (directory / "state.json").write_text(json.dumps(state | change))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    process_resume_evidence(directory, state["device"])
            for invalid in (raw.replace(PROCESS_READY, b"old image"),
                            raw + b"RPi: BOOTSYS", raw + TERMINAL_LOADER):
                (directory / "serial.bin").write_bytes(invalid)
                (directory / "state.json").write_text(json.dumps(
                    state | {"sha256": hashlib.sha256(invalid).hexdigest()}))
                with self.assertRaises(ValueError):
                    process_resume_evidence(directory, state["device"])

    def test_resume_requires_two_fresh_pairs_and_rejects_reset(self):
        for raw, error in ((PROCESS_READY + PROMPT, TimeoutError),
                           (KEYBOARD_START + PROMPT, TimeoutError),
                           ((PROCESS_READY + PROMPT) * 2 + b"RPi: BOOTSYS", RuntimeError),
                           ((PROCESS_READY + PROMPT) * 2, None)):
            host, board = socket.socketpair()
            try:
                board.sendall(raw)
                if error:
                    with self.assertRaises(error):
                        wait_for_process_resume(host.fileno(), io.BytesIO(), time.monotonic() + 0.03)
                else:
                    wait_for_process_resume(host.fileno(), io.BytesIO(), time.monotonic() + 0.03)
                board.settimeout(0.01)
                with self.assertRaises(socket.timeout):
                    board.recv(1)
            finally:
                host.close()
                board.close()

    def test_exact_process_evidence(self):
        self.assertEqual(parse_process_result(RESULT), 2)
        mutations = [
            RESULT.replace(b"WAIT_CHILD PID=0x0000000000000002",
                           b"WAIT_CHILD PID=0x0000000000000003"),
            RESULT.replace(b"0000000000000002", b"0000000000000001"),
            RESULT.replace(b"00002a00", b"00000009"),
            RESULT.replace(b"BSS_ZERO=1", b"BSS_ZERO=0"),
            RESULT.replace(b"COW=1", b"COW=0"),
            RESULT.replace(b"RPI5_EXEC_ARG", b"WRONG_ARGUMENT"),
            RESULT.replace(PROCESS_PASS, b"RPI5XNU:PROC:FAIL STAGE=RESULT"),
            RESULT + RESULT,
            RESULT.replace(b"RPI5XNU:PROC:FORK_CHILD\r\n", b"") +
            b"RPI5XNU:PROC:FORK_CHILD\r\n",
        ]
        for data in mutations:
            with self.subTest(data=data), self.assertRaises(RuntimeError):
                parse_process_result(data)

    def test_old_terminal_gets_no_input(self):
        host, board = socket.socketpair()
        progress = {"checks": [], "transmitted_bytes": 0}
        try:
            board.sendall(TERMINAL_LOADER + b"\n" + KEYBOARD_START + b"\n" + PROMPT)
            with self.assertRaises(TimeoutError):
                process_trial(host.fileno(), io.BytesIO(), 1, 0.03, progress)
            self.assertEqual(progress["transmitted_bytes"], 0)
            board.settimeout(0.03)
            with self.assertRaises(socket.timeout):
                board.recv(1)
        finally:
            host.close()
            board.close()

    def test_one_process_launch_then_prompt_recovery(self):
        host, board = socket.socketpair()
        commands = []
        errors = []
        progress = {"checks": [], "transmitted_bytes": 0}

        def simulate_board():
            try:
                board.settimeout(2)
                board.sendall(TERMINAL_LOADER + b"\n" + KEYBOARD_START + b"\n" +
                              b"RPI5XNU:PRcpu2OC:TRIAL_READY\n" + PROMPT)
                # The physical first banner was torn by concurrent SMP logs.
                # No input is allowed until the payload repeats a clean marker.
                board.settimeout(0.03)
                try:
                    unexpected = board.recv(128)
                except socket.timeout:
                    pass
                else:
                    raise RuntimeError(f"input before clean marker: {unexpected!r}")
                board.settimeout(2)
                board.sendall(PROCESS_READY + b"\n" + PROMPT)
                for response in (RESULT, b"PID 1 alive; serial console active.\r\n"):
                    command = b""
                    while not command.endswith(b"\n"):
                        chunk = board.recv(128)
                        if not chunk:
                            raise RuntimeError("host closed early")
                        command += chunk
                    commands.append(command)
                    board.sendall(response + PROMPT)
            except Exception as error:
                errors.append(error)
            finally:
                board.close()

        worker = threading.Thread(target=simulate_board)
        worker.start()
        try:
            process_trial(host.fileno(), io.BytesIO(), 1, 1, progress)
        finally:
            host.close()
            worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(commands, [b"process\n", b"status\n"])
        self.assertEqual(progress["child_pid"], 2)
        self.assertEqual(len(progress["checks"]), 6)

    def test_actionable_failure_stops_without_more_commands(self):
        host, board = socket.socketpair()
        progress = {"checks": [], "transmitted_bytes": 0}
        try:
            board.sendall(TERMINAL_LOADER + b"\n" + KEYBOARD_START + b"\n" +
                          PROCESS_READY + b"\n")
            board.sendall(b"RPI5XNU:PROC:FAIL STAGE=EXEC\r\n" + PROMPT)
            # Keep failure separate from the receive-only boot-marker read.
            from unittest.mock import patch
            with patch("tools.rpi5.serial_terminal_trial.wait_for_boot_markers"):
                with self.assertRaisesRegex(RuntimeError, "process launch failed"):
                    process_trial(host.fileno(), io.BytesIO(), 1, 1, progress)
            self.assertEqual(board.recv(128), b"process\n")
        finally:
            host.close()
            board.close()

    def test_unknown_process_command_stops_immediately(self):
        host, board = socket.socketpair()
        progress = {"checks": [], "transmitted_bytes": 0}
        try:
            board.sendall(b"Unknown command. Type help.\r\n" + PROMPT)
            from unittest.mock import patch
            with patch("tools.rpi5.serial_terminal_trial.wait_for_boot_markers"):
                with self.assertRaisesRegex(RuntimeError, "not recognized"):
                    process_trial(host.fileno(), io.BytesIO(), 1, 1, progress)
            self.assertEqual(board.recv(128), b"process\n")
            self.assertEqual(progress["transmitted_bytes"], 8)
        finally:
            host.close()
            board.close()


if __name__ == "__main__":
    unittest.main()
