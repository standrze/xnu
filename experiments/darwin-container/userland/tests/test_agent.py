# SPDX-License-Identifier: BSD-2-Clause
"""Native agent/control tests. No VM, target kernel, host broadcast or reboot."""
import errno
import json
import os
from pathlib import Path
import select
import subprocess
import tempfile
import time
import unittest
import zlib

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "src"
SESSION = "00112233445566778899aabbccddeeff"


def frame(kind, command=0, sequence=1, payload=b"", session=SESSION, direction="H"):
    body = f"DGA1|{direction}|{session}|{command:08x}|{sequence:08x}|{kind}|{len(payload):04x}|{payload.hex()}".encode()
    return body + f"|{zlib.crc32(body):08x}\n".encode()


class Session:
    def __init__(self, test, executable, **settings):
        self.test = test
        self.process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, env={**os.environ, **settings}, bufsize=0)
        self.buffer = bytearray()
        self.events = []
        self.incoming = 1
        self.outgoing = 1
        self.read_until_banner()

    def line(self, timeout=10):
        deadline = time.monotonic() + timeout
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            self.test.assertGreater(remaining, 0, "native agent output timeout")
            readable, _, _ = select.select([self.process.stdout], [], [], remaining)
            self.test.assertTrue(readable, "native agent output timeout")
            data = os.read(self.process.stdout.fileno(), 65536)
            self.test.assertTrue(data, f"native agent ended early: {self.process.poll()}")
            self.buffer.extend(data)
        line, _, rest = self.buffer.partition(b"\n")
        self.buffer = bytearray(rest)
        return bytes(line).rstrip(b"\r")

    def read_until_banner(self):
        while self.line() != b"DARWIN:AGENT:READY:1":
            pass

    def send(self, kind, command=0, payload=b""):
        self.process.stdin.write(frame(kind, command, self.outgoing, payload))
        self.outgoing += 1

    def event(self, timeout=10):
        line = self.line(timeout)
        fields = line.split(b"|")
        self.test.assertEqual(len(fields), 9, line)
        self.test.assertEqual(fields[:3], [b"DGA1", b"G", SESSION.encode()])
        self.test.assertEqual(int(fields[4], 16), self.incoming, line)
        self.incoming += 1
        self.test.assertEqual(int(fields[8], 16), zlib.crc32(line.rsplit(b"|", 1)[0]))
        payload = bytes.fromhex(fields[7].decode())
        self.test.assertEqual(len(payload), int(fields[6], 16))
        event = (fields[5].decode(), int(fields[3], 16), payload)
        self.events.append(event)
        return event

    def hello(self):
        self.send("HELLO")
        self.test.assertEqual(self.event(), ("HELLO", 0, b"exec,streams,cancel,shutdown"))

    def execute(self, command, *argv):
        self.send("EXEC", command, b"\0".join(a.encode() for a in argv) + b"\0")
        event = self.event()
        self.test.assertEqual(event[:2], ("STARTED", command))
        self.test.assertEqual(len(event[2]), 4)
        self.test.assertGreater(int.from_bytes(event[2], "big"), 1)

    def finish(self, command):
        output, error = bytearray(), bytearray()
        ended = set()
        while True:
            kind, identity, payload = self.event()
            self.test.assertEqual(identity, command)
            if kind in ("OUT", "ERR"):
                self.test.assertNotIn(kind + "_EOF", ended)
                self.test.assertTrue(payload)
                (output if kind == "OUT" else error).extend(payload)
            elif kind in ("OUT_EOF", "ERR_EOF"):
                self.test.assertNotIn(kind, ended)
                self.test.assertEqual(payload, b"")
                ended.add(kind)
            elif kind == "EXIT":
                self.test.assertEqual(ended, {"OUT_EOF", "ERR_EOF"})
                self.test.assertEqual(len(payload), 5)
                return bytes(output), bytes(error), payload
            elif kind != "CANCELLED":
                self.test.fail(f"unexpected record {kind}: {payload!r}")

    def shutdown(self):
        self.send("SHUTDOWN")
        self.test.assertEqual(self.event(), ("SHUTDOWN", 0, b""))
        self.test.assertEqual(self.process.wait(timeout=5), 0)
        self.test.assertEqual(self.process.stderr.read(), b"")

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()


class AgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="darwin-agent-native-")
        cls.executable = Path(cls.tmp.name) / "agent-native"
        subprocess.run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", str(HERE / "agent_host.c"),
                        *(str(SOURCE / n) for n in ("agent_protocol.c", "agent.c", "agent_fixtures.c",
                                                   "utilities.c", "poweroff.c")),
                        "-o", str(cls.executable)], check=True, capture_output=True, timeout=60)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def session(self, **settings):
        session = Session(self, self.executable, **settings)
        self.addCleanup(session.close)
        return session

    def codec(self, data):
        result = subprocess.run([str(self.executable), "--codec"], input=data, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b"")
        return result.stdout

    def test_independent_golden_vectors_and_all_byte_values(self):
        vectors = json.loads((HERE.parents[1] / "agent" / "wire-vectors.json").read_text())["vectors"]
        for vector in vectors:
            with self.subTest(vector["name"]):
                wire = vector["wire"].encode()
                self.assertEqual(wire, frame(vector["type"], vector["commandID"], vector["sequence"],
                                             bytes.fromhex(vector["payloadHex"]), vector["session"], vector["direction"]))
                self.assertEqual(self.codec(wire), wire)

    def test_codec_rejects_corruption_version_length_type_and_noncanonical_fields(self):
        hello = frame("HELLO")
        invalid = [hello.replace(b"DGA1", b"DGA2"), hello.replace(b"|0000|", b"|0001|"),
                   hello.replace(b"|HELLO|", b"|BOGUS|"), hello.replace(b"001122", b"A01122"),
                   hello.replace(b"|00000001|", b"|00000000|"), hello.replace(b"|H|", b"|X|"),
                   hello.replace(b"|HELLO|", b"|HEL\rLO|"), hello[:-10] + b"|00000000\n",
                   frame("OUT", 1, payload=bytes(257)), b"DGA1|" + bytes(1100) + b"\n"]
        for wire in invalid:
            with self.subTest(wire=wire[:90]):
                self.assertTrue(self.codec(wire).startswith(b"ERROR:"))

    def test_every_hello_fragmentation_boundary_and_crlf(self):
        wire = frame("HELLO")
        for split in range(1, len(wire)):
            with self.subTest(split=split):
                session = self.session()
                session.process.stdin.write(wire[:split])
                session.process.stdin.write(wire[split:-1] + b"\r\r\n")
                session.outgoing = 2
                self.assertEqual(session.event(), ("HELLO", 0, b"exec,streams,cancel,shutdown"))
                session.shutdown()
                session.close()

    def test_binary_streams_two_commands_stdin_eof_and_short_io(self):
        for inject in (False, True):
            with self.subTest(inject=inject):
                session = self.session(**({"DGA_INJECT_SHORT_IO": "1"} if inject else {}))
                session.hello()
                session.execute(1, "/bin/agent-bytes")
                output, error, exit_status = session.finish(1)
                self.assertEqual(output, bytes(range(256)))
                self.assertEqual(error, bytes(reversed(range(256))))
                self.assertEqual(exit_status, bytes([0, 0, 0, 1, 0]))
                session.execute(2, "/bin/cat")
                self.assertEqual(session.finish(2), (b"", b"", bytes([0, 0, 0, 1, 0])))
                session.shutdown()

    def test_exit_one_missing_executable_and_exit143_are_not_signal15(self):
        session = self.session()
        session.hello()
        session.execute(1, "/bin/false")
        self.assertEqual(session.finish(1), (b"", b"", bytes([0, 1, 0, 1, 0])))
        session.execute(2, "/this-path-is-missing")
        output, error, status = session.finish(2)
        self.assertEqual(output, b"")
        self.assertIn(b"agent exec: errno 2", error)
        self.assertEqual(status, bytes([0, 127, 0, 1, 0]))
        session.execute(3, "/bin/sh", "-c", "exit 143")
        self.assertEqual(session.finish(3), (b"", b"", bytes([0, 143, 0, 1, 0])))
        session.shutdown()

    def test_cancel_term_blocked_job_and_escaped_descendant(self):
        session = self.session()
        session.hello()
        session.execute(1, "/bin/agent-escape")
        output, error = bytearray(), bytearray()
        while b"DESCENDANT_PID=" not in output or b"ESCAPED_DESCENDANT\n" not in error:
            kind, command, data = session.event()
            self.assertEqual(command, 1)
            self.assertIn(kind, ("OUT", "ERR"))
            (output if kind == "OUT" else error).extend(data)
        child = int(bytes(output).split(b"DESCENDANT_PID=", 1)[1].splitlines()[0])
        start = time.monotonic()
        session.send("CANCEL", 1)
        self.assertEqual(session.event(), ("CANCELLED", 1, b"\x01"))
        _, _, status = session.finish(1)
        self.assertEqual(status, bytes([1, 9, 1, 1, 0]))
        self.assertLess(time.monotonic() - start, 5)
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)
        session.shutdown()

    def test_late_cancel_race_ack_and_no_next_exec(self):
        session = self.session()
        session.hello()
        session.execute(1, "/bin/true")
        self.assertEqual(session.finish(1)[2], bytes([0, 0, 0, 1, 0]))
        session.send("CANCEL", 1)
        self.assertEqual(session.event(), ("CANCELLED", 1, b"\0"))
        session.send("EXEC", 2, b"/bin/true\0")
        self.assertEqual(session.event(), ("ERROR", 0, b"exec_after_cancel"))
        self.assertEqual(session.process.wait(timeout=5), 1)

    def test_coalesced_exec_cancel_and_active_shutdown(self):
        session = self.session()
        session.hello()
        session.process.stdin.write(frame("EXEC", 1, 2, b"/bin/agent-stubborn\0") + frame("CANCEL", 1, 3))
        session.outgoing = 4
        self.assertEqual(session.event()[:2], ("STARTED", 1))
        self.assertEqual(session.event(), ("CANCELLED", 1, b"\1"))
        self.assertEqual(session.finish(1)[2][2:], b"\1\1\0")
        session.shutdown()
        active = self.session()
        active.hello()
        active.execute(1, "/bin/agent-stubborn")
        active.send("SHUTDOWN")
        self.assertEqual(active.finish(1)[2][2:], b"\1\1\0")
        self.assertEqual(active.event(), ("SHUTDOWN", 0, b""))
        self.assertEqual(active.process.wait(timeout=5), 0)

    def test_combined_output_cap_drains_and_sets_incomplete_flag(self):
        session = self.session()
        session.hello()
        session.execute(1, "/bin/agent-flood")
        output, error, status = session.finish(1)
        self.assertEqual(len(output) + len(error), 1024 * 1024)
        self.assertEqual(status[3:], b"\1\1")
        session.send("EXEC", 2, b"/bin/true\0")
        self.assertEqual(session.event(), ("ERROR", 0, b"exec_after_limit"))
        self.assertEqual(session.process.wait(timeout=5), 1)

    def test_foreign_duplicate_stale_crc_and_oversized_input_never_exec(self):
        requests = [frame("EXEC", 1, 2, b"/bin/true\0", session="f" * 32),
                    frame("EXEC", 1, 1, b"/bin/true\0"), frame("EXEC", 2, 2, b"/bin/true\0"),
                    frame("EXEC", 1, 2, b"/bin/true\0")[:-2] + b"0\n", b"x" * 1024 + b"\n"]
        for request in requests:
            with self.subTest(request=request[:100]):
                session = self.session()
                session.hello()
                session.process.stdin.write(request)
                self.assertEqual(session.event()[0], "ERROR")
                self.assertEqual(session.process.wait(timeout=5), 1)
                self.assertNotIn("STARTED", [event[0] for event in session.events])

    def test_invalid_argv_launch_failure_and_unverified_cleanup_are_fatal(self):
        for payload in (b"", b"relative\0", b"/bin/echo", b"/bin/echo\0" + b"x\0" * 16):
            session = self.session()
            session.hello()
            session.send("EXEC", 1, payload)
            self.assertEqual(session.event(), ("ERROR", 0, b"exec_argv"))
        fork = self.session(DGA_FAIL_FORK="1")
        fork.hello()
        fork.send("EXEC", 1, b"/bin/true\0")
        self.assertEqual(fork.event(), ("ERROR", 0, b"launch_fork"))
        cleanup = self.session(DGA_FAIL_CLEANUP="1")
        cleanup.hello()
        cleanup.execute(1, "/bin/true")
        while True:
            kind, _, payload = cleanup.event(timeout=10)
            self.assertNotEqual(kind, "EXIT")
            if kind == "ERROR":
                self.assertEqual(payload, b"cleanup_timeout")
                break
        self.assertEqual(cleanup.process.wait(timeout=5), 1)


if __name__ == "__main__":
    unittest.main()
