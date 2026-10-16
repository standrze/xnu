# SPDX-License-Identifier: BSD-2-Clause
"""Mock transport checks only; not board or UART evidence."""
import io
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import serial_shell_trial as shell

class SerialShellTests(unittest.TestCase):
    def test_invalid_capture_limit_rejected_before_transmission(self):
        for limit in (0, -1, 262145, True, '262144'):
            with self.subTest(limit=limit), patch.object(shell.os, 'write') as write:
                progress = {'transmitted_bytes': 0}
                with self.assertRaises(ValueError):
                    shell.command(1, io.BytesIO(), 'pwd', [], progress, max_bytes=limit)
                write.assert_not_called()
                self.assertEqual(progress['transmitted_bytes'], 0)

    def test_large_capture_requires_explicit_bounded_opt_in(self):
        data = b'00 ' * 33034 + b'\nDONE\nxnu:/# '
        for limit in (65536, 262144):
            chunks = [data[i:i+4096] for i in range(0, len(data), 4096)]
            with patch.object(shell.select, 'select', return_value=([], [1], [])), \
                    patch.object(shell.os, 'write', return_value=1), \
                    patch.object(shell.time, 'sleep', return_value=None), \
                    patch.object(shell, 'receive', side_effect=chunks):
                if limit == 65536:
                    with self.assertRaisesRegex(RuntimeError, 'output limit exceeded'):
                        shell.command(1, io.BytesIO(), 'x', [b'DONE'], {'transmitted_bytes': 0})
                else:
                    actual = shell.command(1, io.BytesIO(), 'x', [b'DONE'],
                                           {'transmitted_bytes': 0}, max_bytes=limit)
                    self.assertEqual(actual, data)

    def exchange(self, response, expected):
        host, peer = socket.socketpair()
        output = io.BytesIO()
        def device():
            command = b""
            while not command.endswith(b"\n"):
                command += peer.recv(128)
            peer.sendall(response)
        worker = threading.Thread(target=device)
        worker.start()
        try:
            with patch.object(shell.time, "sleep", return_value=None):
                shell.command(host.fileno(), output, "pwd", expected,
                              {"transmitted_bytes": 0}, seconds=0.1)
        finally:
            worker.join(timeout=1)
            host.close(); peer.close()
        return output.getvalue()

    def test_exact_line_and_dynamic_prompt(self):
        self.exchange(b"pwd\r\n/etc\r\nxnu:/etc# ", [b"/etc"])

    def test_expected_text_split_before_line_ending(self):
        for chunks in ([b'END\r\r\nNONCE', b'\r\r\nxnu:/# '],
                       [b'END\r\r\nNONCE\r', b'\r', b'\nxnu:/# '],
                       [b'NONCE', b'X\nxnu:/# ', b'\nNONCE\nxnu:/# ']):
            with self.subTest(chunks=chunks), \
                    patch.object(shell.select, 'select', return_value=([], [1], [])), \
                    patch.object(shell.os, 'write', return_value=1), \
                    patch.object(shell.time, 'sleep', return_value=None), \
                    patch.object(shell, 'receive', side_effect=chunks):
                actual = shell.command(1, io.BytesIO(), 'echo NONCE', [b'NONCE'],
                                       {'transmitted_bytes': 0})
                self.assertEqual(actual, b''.join(chunks))

    def test_echoed_input_does_not_prove_output(self):
        with self.assertRaises(TimeoutError):
            self.exchange(b"echo NONCE\r\nxnu:/# ", [b"NONCE"])

    def test_empty_result_still_requires_recovered_prompt(self):
        self.exchange(b"pwd\r\nxnu:/# ", [])

    def test_diagnostic_image_never_receives_input(self):
        host, peer = socket.socketpair()
        peer.sendall(shell.TERMINAL_LOADER + b"\nSerial keyboard started\nRPI5XNU:RAMROOT:READY\nxnu-rpi5> ")
        peer.setblocking(False)
        try:
            with self.assertRaises(TimeoutError):
                shell.trial(host.fileno(), io.BytesIO(), 0.05, {"checks": [], "transmitted_bytes": 0})
            with self.assertRaises(BlockingIOError):
                peer.recv(1)
        finally:
            host.close(); peer.close()

if __name__ == "__main__":
    unittest.main()
