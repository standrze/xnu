#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserve the focused managed-zsh VM result, without publishing private EFI state."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--loader", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads((args.session / "result.json").read_text())
    agent = report["agent"]
    commands = agent["commands"]
    if not (report["guestStopped"] and report["termination"] == "guestStopped"
            and agent["handshakeCompleted"] and agent["protocolValid"] and agent["shutdownAcknowledged"]
            and [c["exitStatus"] for c in commands] == [0, 7]
            and all(c["cleanupVerified"] and c["terminalObserved"] for c in commands)):
        raise RuntimeError("managed command/lifecycle proof is incomplete")
    stdout = (args.session / "command-1-stdout.bin").read_bytes()
    stderr = (args.session / "command-1-stderr.bin").read_bytes()
    if not (b"MANAGED_ZSH:5.9\n" in stdout and b"BUILTINS:zsh:42\n" in stdout
            and b"Darwin  12377.121.6 arm64\n" in stdout and b"ZSH_STDERR\n" in stderr):
        raise RuntimeError("missing actual Apple-zsh output")
    args.output.mkdir(parents=True, exist_ok=False)
    for source in args.session.iterdir():
        if source.is_file() and source.name != "efi-variables.bin":
            shutil.copy2(source, args.output / source.name)
    shutil.copy2(args.loader / "manifest.json", args.output / "loader-manifest.json")
    shutil.copy2(HERE / "build/agent-zsh-1/manifest.json", args.output / "root-manifest.json")
    verification = {
        "outcome": "passed", "scope": "two managed commands in the actual XNU guest, not storage qualification",
        "firstCommandExit": 0, "secondCommandExit": 7, "cliExit": 7,
        "stdoutAndStderrSeparate": True, "guestStopped": True,
        "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(args.output.iterdir()) if p.is_file()},
    }
    (args.output / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
