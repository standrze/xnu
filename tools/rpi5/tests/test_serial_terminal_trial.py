# SPDX-License-Identifier: BSD-2-Clause
"""The trial must prove responses and never type into the Gate 3 baseline."""

import io
import socket
import threading
import time
import unittest
from unittest.mock import patch

from tools.rpi5.serial_terminal_trial import (BANNER, KEYBOARD_START, PROMPT,
                                             TERMINAL_LOADER, WAKE_NONCE,
                                             check_late_terminal, parse_ticks,
                                             run_trial, trial, valid_probe_device)


class SerialTerminalTrialTests(unittest.TestCase):
    def test_late_wait_starts_after_initial_acceptance_not_capture_setup(self):
        events = []
        progress = {"checks": [], "transmitted_bytes": 0}
        output = io.BytesIO()

        def initial_acceptance(*args, **kwargs):
            events.append("accepted")

        def acceptance_time():
            events.append("clock")
            return 1000.0

        module = "tools.rpi5.serial_terminal_trial"
        with patch(module + ".trial", side_effect=initial_acceptance) as initial, \
                patch(module + ".time.monotonic", side_effect=acceptance_time), \
                patch(module + ".check_late_terminal") as late:
            run_trial(42, output, 300, 180, progress)
        self.assertEqual(events, ["accepted", "clock"])
        initial.assert_called_once_with(42, output, 300, progress=progress,
                                        boot_wait_seconds=None)
        late.assert_called_once_with(42, output, 1180.0, progress)

    def test_initial_acceptance_failure_cannot_start_late_input(self):
        module = "tools.rpi5.serial_terminal_trial"
        with patch(module + ".trial", side_effect=TimeoutError("no boot markers")), \
                patch(module + ".check_late_terminal") as late:
            with self.assertRaises(TimeoutError):
                run_trial(42, io.BytesIO(), 300, 180,
                          {"checks": [], "transmitted_bytes": 0})
        late.assert_not_called()

    def test_wait_for_operator_does_not_consume_command_timeout(self):
        module = "tools.rpi5.serial_terminal_trial"
        output = io.BytesIO()
        with patch(module + ".time.monotonic", side_effect=[100.0, 3600.0]), \
                patch(module + ".time.sleep"), \
                patch(module + ".wait_for_boot_markers", return_value=True) as boot, \
                patch(module + ".transmit"), \
                patch(module + ".read_until", side_effect=TimeoutError("command")) as read:
            with self.assertRaises(TimeoutError):
                trial(42, output, 180, boot_wait_seconds=3600)
        boot.assert_called_once_with(42, output, 3700.0)
        self.assertEqual(read.call_args.args[-1], 3780.0)

    def test_orchestrator_preserves_separate_boot_wait(self):
        module = "tools.rpi5.serial_terminal_trial"
        output = io.BytesIO()
        progress = {"checks": [], "transmitted_bytes": 0}
        with patch(module + ".trial") as initial, \
                patch(module + ".check_late_terminal") as late:
            run_trial(42, output, 180, 0, progress, boot_wait_seconds=3600)
        initial.assert_called_once_with(42, output, 180, progress=progress,
                                        boot_wait_seconds=3600)
        late.assert_not_called()

    def test_late_check_echoes_only_after_target(self):
        host, board = socket.socketpair()
        progress = {"checks": [], "transmitted_bytes": 0}
        commands = []

        def simulate_board():
            data = b""
            while not data.endswith(b"\n"):
                data += board.recv(128)
            commands.append(data)
            board.sendall(b"ECHO: RPI5_TERMINAL_LATE_CHECK\r\n" + PROMPT)
            board.close()

        worker = threading.Thread(target=simulate_board)
        worker.start()
        target = time.monotonic() + 0.05
        try:
            check_late_terminal(host.fileno(), io.BytesIO(), target, progress)
        finally:
            host.close()
            worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(commands, [b"echo RPI5_TERMINAL_LATE_CHECK\n"])
        self.assertIn("late_echo_after_old_watchdog_window", progress["checks"])

    def test_late_check_reboot_marker_prevents_transmission(self):
        host, board = socket.socketpair()
        try:
            board.sendall(b"Debian GNU/Linux 13\r\n")
            progress = {"checks": [], "transmitted_bytes": 0}
            with self.assertRaisesRegex(RuntimeError, "reboot detected"):
                check_late_terminal(host.fileno(), io.BytesIO(),
                                    time.monotonic() + 0.05, progress)
            board.settimeout(0.05)
            with self.assertRaises(socket.timeout):
                board.recv(1)
            self.assertEqual(progress["transmitted_bytes"], 0)
        finally:
            host.close()
            board.close()

    def test_probe_device_paths_are_host_specific(self):
        linux = ("/dev/serial/by-id/"
                 "usb-Raspberry_Pi_Debug_Probe__CMSIS-DAP__E66480454F719939-if01")
        mac = "/dev/cu.usbmodem1102"
        self.assertTrue(valid_probe_device(linux, "linux"))
        self.assertTrue(valid_probe_device(mac, "darwin"))
        self.assertFalse(valid_probe_device(mac, "linux"))
        self.assertFalse(valid_probe_device(linux, "darwin"))
        self.assertFalse(valid_probe_device("/dev/cu.usbserial-110", "darwin"))

    def test_marker_guard_prevents_transmission_to_old_image(self):
        host, board = socket.socketpair()
        try:
            board.sendall(b"XNU-RPI5 USERSPACE PID1 TICK\n")
            with self.assertRaises(TimeoutError):
                trial(host.fileno(), io.BytesIO(), 0.05)
            board.settimeout(0.05)
            with self.assertRaises(socket.timeout):
                board.recv(1)
        finally:
            host.close()
            board.close()

    def test_prompt_without_keyboard_start_does_not_transmit(self):
        host, board = socket.socketpair()
        try:
            board.sendall(BANNER + b"\r\n" + PROMPT)
            with self.assertRaises(TimeoutError):
                trial(host.fileno(), io.BytesIO(), 0.05)
            board.settimeout(0.05)
            with self.assertRaises(socket.timeout):
                board.recv(1)
        finally:
            host.close()
            board.close()

    def test_full_command_and_recovery_sequence(self):
        host, board = socket.socketpair()
        commands = []

        def simulate_board():
            try:
                board.sendall(TERMINAL_LOADER + b"\r\n" + KEYBOARD_START + b"\r\n" +
                              BANNER + b"\r\n" + PROMPT)
                responses = [b"help, status, ticks, echo TEXT", b"PID 1 alive; serial console active.",
                             b"TICKS=0x0000000000000001 FREQ=0x000000000337f980",
                             b"TICKS=0x0000000000000002 FREQ=0x000000000337f980",
                             b"ECHO: RPI5_TERMINAL_PROBE", b"PID 1 alive; serial console active.",
                             b"Unknown command. Type help.", b"PID 1 alive; serial console active."]
                for response in responses:
                    data = b""
                    while not data.endswith(b"\n"):
                        data += board.recv(128)
                    commands.append(data)
                    board.sendall(data + b"\r\n" + response + b"\r\n" + PROMPT)
            finally:
                board.close()

        worker = threading.Thread(target=simulate_board)
        worker.start()
        try:
            result = trial(host.fileno(), io.BytesIO(), 2)
        finally:
            host.close()
            worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(result["checks"]), 10)
        self.assertEqual(commands[5], b"statuz\x7fs\n")
        self.assertEqual(result["transmitted_bytes"], sum(map(len, commands)))

    def test_partial_failure_preserves_completed_checks_and_transmission(self):
        host, board = socket.socketpair()

        def simulate_board():
            try:
                board.sendall(TERMINAL_LOADER + b"\r\n" + BANNER + b"\r\n" +
                              PROMPT + KEYBOARD_START + b"\r\n")
                data = b""
                while not data.endswith(b"\n"):
                    data += board.recv(128)
                board.sendall(b"help, status, ticks, echo TEXT\r\n" + PROMPT)
                data = b""
                while not data.endswith(b"\n"):
                    data += board.recv(128)
            finally:
                board.close()

        worker = threading.Thread(target=simulate_board)
        worker.start()
        progress = {"checks": [], "transmitted_bytes": 0}
        try:
            with self.assertRaises((TimeoutError, RuntimeError)):
                trial(host.fileno(), io.BytesIO(), 0.5, progress=progress)
        finally:
            host.close()
            worker.join(timeout=2)
        self.assertEqual(progress["checks"],
                         ["terminal_loader_and_keyboard", "terminal_banner_prompt", "help"])
        self.assertEqual(progress["transmitted_bytes"], len(b"help\nstatus\n"))

    def test_interleaved_banner_recovers_only_after_terminal_loader_marker(self):
        host, board = socket.socketpair()
        commands = []

        def simulate_board():
            try:
                board.sendall(TERMINAL_LOADER + b"\r\n" + KEYBOARD_START + b"\r\n" +
                              b"XNU-RPI5 TkernelERMINAL PID1 OK\r\nxnu-rpikernel5> ")
                data = b""
                while not data.endswith(b"\n"):
                    data += board.recv(128)
                commands.append(data)
                board.sendall(b"ECHO: " + WAKE_NONCE + b"\r\n" + PROMPT)
                data = b""
                while not data.endswith(b"\n"):
                    data += board.recv(128)
                commands.append(data)
            finally:
                board.close()

        worker = threading.Thread(target=simulate_board)
        worker.start()
        progress = {"checks": [], "transmitted_bytes": 0}
        try:
            with self.assertRaises(RuntimeError):
                trial(host.fileno(), io.BytesIO(), 3, progress=progress)
        finally:
            host.close()
            worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(commands, [b"echo " + WAKE_NONCE + b"\n", b"help\n"])
        self.assertEqual(progress["checks"],
                         ["terminal_loader_and_keyboard", "terminal_wake_echo"])

    def test_ticks_parser_rejects_missing_or_zero_frequency(self):
        self.assertEqual(parse_ticks(b"TICKS=0x0000000000000002 FREQ=0x000000000337f980"),
                         (2, 54000000))
        for response in (b"TICKS=2 FREQ=54000000",
                         b"TICKS=0x0000000000000002 FREQ=0x0000000000000000"):
            with self.subTest(response=response), self.assertRaises(RuntimeError):
                parse_ticks(response)


if __name__ == "__main__":
    unittest.main()
