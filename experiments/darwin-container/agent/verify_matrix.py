#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Recheck the preserved DC3 matrix; does not launch a VM or rebuild anything."""
import hashlib
import json
from pathlib import Path

from check_evidence import audit

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
RESULTS = EXPERIMENT / "results"
KERNEL = "b3a0d9f49e2af4bfe28ac716111b05a030d1c8fb273c1e4ffe103e2a36582d53"
RAMROOT = "42804e015930e1af5b0e6ba1341813a754dbe5351b893c4efcc4104f8ad7e342"


def read(name):
    directory = RESULTS / ("2026-10-12-dc3-" + name)
    preservation = json.loads((directory / "preservation.json").read_text())
    for filename, expected in preservation["files"].items():
        assert hashlib.sha256((directory / filename).read_bytes()).hexdigest() == expected, "preserved file drift"
    manifest = json.loads((directory / "loader-manifest.json").read_text())
    assert manifest["inputs"]["kernelSHA256"] == KERNEL, "wrong final kernel"
    return directory, json.loads((directory / "result.json").read_text()), manifest


def main():
    names = ("binary-final", "exit-one-final", "direct-exec-final", "api-cancel-final",
             "orphan-final", "timeout-final", "cap-final-1", "cap-final-2")
    records, payloads = [], set()
    for name in names:
        directory, result, manifest = read(name)
        assert manifest["inputs"]["ramrootSHA256"] == RAMROOT, "wrong managed RAM root"
        assert manifest["payloadSHA256"] not in payloads, "reused EFI payload"
        payloads.add(manifest["payloadSHA256"])
        audit(directory)
        records.append({"scenario": name, "directory": str(directory.relative_to(EXPERIMENT)),
                        "sessionID": result["sessionID"], "elapsedSeconds": result["elapsedSeconds"],
                        "commandSucceeded": result["commandSucceeded"], "actualGuestStopped": result["guestStopped"],
                        "termination": result["termination"], "payloadSHA256": manifest["payloadSHA256"]})
        commands = result["agent"]["commands"]
        if name == "binary-final":
            assert result["commandSucceeded"] and len(commands) == 2
            assert (directory / "command-1-stdout.bin").read_bytes() == bytes(range(256))
            assert (directory / "command-1-stderr.bin").read_bytes() == bytes(reversed(range(256)))
            assert (directory / "command-2-stdout.bin").read_bytes() == b"Darwin  12377.121.6 arm64\nsecond-command-ok\n"
        elif name in ("exit-one-final", "direct-exec-final"):
            assert commands[0]["exitStatus"] == (1 if name == "exit-one-final" else 127)
            assert not result["commandSucceeded"]
        elif name in ("api-cancel-final", "timeout-final"):
            first = commands[0]
            assert first["cancellationRequested"] and first["cancellationAccepted"] and first["cancelled"]
            assert not result["commandSucceeded"]
            assert result["termination"] == ("interrupted" if name == "api-cancel-final" else "timedOut")
            if name == "api-cancel-final":
                assert first["terminationSignal"] == 9 and result["elapsedSeconds"] < 10
                assert b"ESCAPED_DESCENDANT\n" in (directory / "command-1-stderr.bin").read_bytes()
        elif name == "orphan-final":
            assert result["commandSucceeded"] and len(commands) == 2 and commands[0]["cleanupVerified"]
            assert (directory / "command-1-stderr.bin").read_bytes() == b"ESCAPED_DESCENDANT\n"
            assert (directory / "command-2-stdout.bin").read_bytes() == b"after-orphan-cleanup\n"
        else:
            assert commands[0]["outputLimit"] and not commands[1]["terminalObserved"]
            assert "processID" not in commands[1] and not result["commandSucceeded"]
            for stream in ("stdout", "stderr"):
                assert (directory / f"command-1-{stream}.bin").read_bytes() == bytes(range(256)) * 2048

    directory, shell, _ = read("shell-final")
    assert shell["commandSucceeded"] and shell["guestStopped"] and shell["commandExitStatus"] == 0
    directory, forced, _ = read("forced-stop-final")
    assert forced["termination"] == "timedOut" and not forced["commandSucceeded"] and not forced["guestStopped"]
    assert not forced["agent"]["readyObserved"] and "processID" not in forced["agent"]["commands"][0]
    assert forced["elapsedSeconds"] < 12 and b"MUST_NOT_EXECUTE" not in (directory / "serial.bin").read_bytes()
    binaries = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in (
        ("signedCLI", EXPERIMENT / "container/.build/out/Products/Debug/container"),
        ("signedAPIHarness", HERE / "host-trial/.build/host-trial"))}
    print(json.dumps({"outcome": "DC3 narrow managed-command matrix passed", "verifiedDateUTC": "2026-10-12",
                      "kernelSHA256": KERNEL, "agentRAMRootSHA256": RAMROOT, "binaries": binaries,
                      "managedTrials": records, "legacyShellRegression": "passed",
                      "noAgentFailureControl": "bounded host-stop fallback; no agent readiness, input or success",
                      "limitations": ["no PTY or managed stdin", "no OCI, networking or writable root",
                                      "bootstrap shell/agent, not Apple zsh or LibSystem",
                                      "per-image seed and inherited seed-clear defect remain unhardened",
                                      "focused tests and bounded VM trials, not production/security qualification"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
