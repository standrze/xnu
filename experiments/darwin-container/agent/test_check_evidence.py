# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic auditor controls, deliberately not VM qualification evidence."""
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from check_evidence import audit


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.session = "00112233445566778899aabbccddeeff"
        self.data = bytes(range(256))
        frames = [(0, "HELLO", b"exec,streams,cancel,shutdown"), (1, "STARTED", b"\0\0\0\3"),
                  (1, "OUT", self.data), (1, "OUT_EOF", b""), (1, "ERR_EOF", b""),
                  (1, "EXIT", b"\0\0\0\1\0"), (0, "SHUTDOWN", b"")]
        lines = [b"DARWIN:AGENT:READY:1\r\n"]
        for sequence, (command, kind, payload) in enumerate(frames, 1):
            body = f"DGA1|G|{self.session}|{command:08x}|{sequence:08x}|{kind}|{len(payload):04x}|{payload.hex()}".encode()
            lines.append(body + f"|{zlib.crc32(body):08x}\r\r\n".encode())
        (self.directory / "serial.bin").write_bytes(b"".join(lines))
        (self.directory / "command-1-stdout.bin").write_bytes(self.data)
        (self.directory / "command-1-stderr.bin").write_bytes(b"")
        self.result = {"sessionID": self.session, "started": True, "guestStopped": True, "termination": "guestStopped",
                       "commandSucceeded": True, "agent": {"readyObserved": True, "protocolValid": True, "handshakeCompleted": True,
                       "shutdownAcknowledged": True, "commands": [{"commandID": 1, "terminalObserved": True,
                       "processID": 3, "exitStatus": 0, "cancelled": False, "cleanupVerified": True,
                       "outputLimit": False, "cancellationRequested": False, "cancellationAcknowledged": False,
                       "stdoutPath": "command-1-stdout.bin", "stderrPath": "command-1-stderr.bin",
                       "stdoutByteCount": 256, "stderrByteCount": 0, "stdoutEOF": True, "stderrEOF": True}]}}
        self.save_result()

    def save_result(self):
        (self.directory / "result.json").write_text(json.dumps(self.result))

    def test_exact_binary_stream(self):
        self.assertEqual(audit(self.directory)["commands"][0]["stdout"]["bytes"], 256)

    def test_corrupted_stream_fails(self):
        (self.directory / "command-1-stdout.bin").write_bytes(self.data[:-1])
        with self.assertRaises(AssertionError):
            audit(self.directory)

    def test_corrupted_wire_fails(self):
        path = self.directory / "serial.bin"
        path.write_bytes(path.read_bytes().replace(b"|OUT|0100|00", b"|OUT|0100|ff"))
        with self.assertRaises(AssertionError):
            audit(self.directory)

    def test_shutdown_ack_is_not_actual_stop(self):
        self.result["guestStopped"] = False
        self.save_result()
        with self.assertRaises(AssertionError):
            audit(self.directory)


if __name__ == "__main__":
    unittest.main()
