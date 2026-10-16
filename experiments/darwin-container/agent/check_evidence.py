#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Independently cross-check managed VZ result/stream files against raw serial."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import zlib

if not __debug__:
    raise RuntimeError("evidence assertions require Python without -O")


def audit(directory):
    result = json.loads((directory / "result.json").read_text())
    agent = result["agent"]
    session = result["sessionID"]
    assert result["started"] and agent["readyObserved"], "guest/agent not started"
    assert 1 <= len(agent["commands"]) <= 16, "invalid command count"
    assert [x["commandID"] for x in agent["commands"]] == list(range(1, len(agent["commands"]) + 1)), "invalid command IDs"
    assert agent["protocolValid"] and agent["handshakeCompleted"], "invalid/incomplete protocol"
    assert agent["shutdownAcknowledged"] and result["guestStopped"], "no acknowledged actual stop"
    assert result["termination"] in ("guestStopped", "interrupted", "timedOut"), "abnormal VZ termination"
    serial = (directory / "serial.bin").read_bytes()
    tail = serial.rsplit(b"\n", 1)[-1]
    assert not tail or not (b"DGA".startswith(tail) or tail.startswith(b"DGA")), "truncated protocol tail"
    frames, sequence = [], 1
    streams, ended, terminals, started, acknowledgements = {}, set(), {}, {}, {}
    for raw in serial.split(b"\n"):
        line = raw.rstrip(b"\r")
        if not line.startswith(b"DGA"):
            continue
        assert len(raw) <= 1024, "oversized protocol record"
        parts = line.split(b"|")
        assert len(parts) == 9 and parts[0] == b"DGA1", "invalid envelope"
        assert parts[1] in (b"H", b"G") and parts[2].decode() == session, "wrong direction/session"
        for value, width in ((parts[2], 32), (parts[3], 8), (parts[4], 8), (parts[6], 4), (parts[8], 8)):
            assert re.fullmatch(b"[0-9a-f]{" + str(width).encode() + b"}", value), "noncanonical hex"
        assert zlib.crc32(b"|".join(parts[:-1])) == int(parts[8], 16), "CRC mismatch"
        size = int(parts[6], 16)
        assert size <= 256 and len(parts[7]) == size * 2 and re.fullmatch(b"[0-9a-f]*", parts[7]), "invalid payload"
        payload = bytes.fromhex(parts[7].decode())
        if parts[1] == b"H":
            continue
        assert int(parts[4], 16) == sequence, "guest sequence gap/replay"
        sequence += 1
        command, kind = int(parts[3], 16), parts[5].decode()
        frames.append(kind)
        if kind == "HELLO":
            assert sequence == 2 and command == 0 and payload == b"exec,streams,cancel,shutdown", "bad HELLO"
        elif kind == "STARTED":
            assert command not in started and len(payload) == 4, "duplicate/bad STARTED"
            started[command] = int.from_bytes(payload, "big")
            assert started[command] > 1, "invalid child PID"
        elif kind in ("OUT", "ERR"):
            key = (command, kind)
            assert command in started and command not in terminals and key not in ended and payload, "out-of-order data"
            streams.setdefault(key, bytearray()).extend(payload)
        elif kind in ("OUT_EOF", "ERR_EOF"):
            key = (command, kind.removesuffix("_EOF"))
            assert command in started and command not in terminals and key not in ended and not payload, "duplicate/bad EOF"
            ended.add(key)
        elif kind == "EXIT":
            assert command in started and command not in terminals and len(payload) == 5, "bad EXIT"
            assert all((command, stream) in ended for stream in ("OUT", "ERR")), "EXIT before EOF"
            assert payload[0] in (0, 1) and all(x in (0, 1) for x in payload[2:]), "bad EXIT fields"
            assert payload[0] == 0 or 1 <= payload[1] <= 31, "invalid signal"
            terminals[command] = payload
        elif kind == "CANCELLED":
            assert command not in acknowledgements and payload in (b"\0", b"\1"), "bad cancellation ACK"
            assert command in started and (command in terminals) == (payload == b"\0"), "ACK ordering mismatch"
            acknowledgements[command] = payload[0]
        elif kind == "SHUTDOWN":
            assert command == 0 and not payload, "bad shutdown"
        else:
            raise AssertionError("unexpected guest message: " + kind)
    assert frames and frames[0] == "HELLO" and frames[-1] == "SHUTDOWN", "missing boundary frames"
    reports = []
    reported = set()
    for record in agent["commands"]:
        command = record["commandID"]
        if not record["terminalObserved"]:
            assert command not in started, "started command lacks terminal evidence"
            continue
        terminal = terminals.pop(command)
        reported.add(command)
        assert record["processID"] == started[command], "PID mismatch"
        assert record.get("exitStatus") == (terminal[1] if terminal[0] == 0 else None), "exit mismatch"
        assert record.get("terminationSignal") == (terminal[1] if terminal[0] == 1 else None), "signal mismatch"
        for field, byte in (("cancelled", 2), ("cleanupVerified", 3), ("outputLimit", 4)):
            assert record[field] == bool(terminal[byte]), field + " mismatch"
        assert record["cancellationAcknowledged"] == (command in acknowledgements), "raw ACK mismatch"
        assert record["cancellationRequested"] == record["cancellationAcknowledged"], "unacknowledged cancellation"
        assert not record["cancelled"] or record["cancellationRequested"], "unattributed cancellation"
        assert record["cancellationAcknowledged"] or record.get("cancellationAccepted") is None, "acceptance without ACK"
        if record["cancellationAcknowledged"]:
            assert bool(acknowledgements[command]) == record["cancellationAccepted"] == record["cancelled"], "ACK/EXIT mismatch"
        report = {"commandID": command}
        for stream, prefix in (("OUT", "stdout"), ("ERR", "stderr")):
            name = record[prefix + "Path"]
            assert name == f"command-{command}-{prefix}.bin", "unexpected stream path"
            data = (directory / name).read_bytes()
            assert data == streams.get((command, stream), b""), "captured stream differs from wire"
            assert len(data) == record[prefix + "ByteCount"] and record[prefix + "EOF"], "stream evidence mismatch"
            report[prefix] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        count = record["stdoutByteCount"] + record["stderrByteCount"]
        assert count <= 1048576 and (not record["outputLimit"] or count == 1048576), "output cap evidence mismatch"
        reports.append(report)
    assert not terminals, "unreported terminal record"
    assert set(started) == reported and set(acknowledgements) <= reported, "unreported command evidence"
    expected_success = result["termination"] == "guestStopped" and not result.get("error") and all(x["terminalObserved"] and x.get("exitStatus") == 0 and not x["cancelled"]
                           and not x["cancellationRequested"] and x["cleanupVerified"] and not x["outputLimit"]
                           for x in agent["commands"])
    assert result["commandSucceeded"] == expected_success, "success classification mismatch"
    return {"audit": "passed", "sessionID": session, "guestFrames": len(frames),
            "serialSHA256": hashlib.sha256(serial).hexdigest(), "commandSucceeded": expected_success, "commands": reports}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.directory), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
