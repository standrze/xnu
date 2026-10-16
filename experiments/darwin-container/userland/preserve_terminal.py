#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserve the incremental real-PTY/ZLE trial; never claims the full follow-on goal."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, type=Path)
    parser.add_argument("--loader", required=True, type=Path)
    parser.add_argument("--ramroot", required=True, type=Path)
    parser.add_argument("--zsh-build", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = json.loads((args.session / "result.json").read_text())
    serial = (args.session / "serial.bin").read_bytes().replace(b"\r", b"")
    markers = (b"\nZLE_EDIT\n", b"\nPTY_MONITOR_ON\n", b"suspended  /bin/sleep 20\n",
               b"continued  /bin/sleep 20\n", b"\nPTY_JOB_STATUS:130\n",
               b"DARWIN:INIT:ZSH_STOPPED:WAIT_STATUS=0\n", b"DARWIN:POWEROFF:REQUEST\n")
    if not (result["started"] and result["guestStopped"] and result["termination"] == "guestStopped"
            and all(marker in serial for marker in markers)
            and serial.count(b"\nZLE_HISTORY_RECALL\n") == 2):
        raise RuntimeError("missing actual ZLE/job-control/shutdown output")
    root = json.loads((args.ramroot / "manifest.json").read_text())
    loader = json.loads((args.loader / "manifest.json").read_text())
    link = json.loads((args.zsh_build / "manifest.json").read_text())
    if not (root["pty_relay"] and root["writable_storage"]
            and root["sha256"] == loader["inputs"]["ramrootSHA256"]
            and root["apple_zsh"]["executable"]["sha256"] == link["sha256"]):
        raise RuntimeError("PTY/root/zsh provenance mismatch")
    args.output.mkdir(parents=True, exist_ok=False)
    for source in args.session.iterdir():
        if source.is_file() and source.name != "efi-variables.bin":
            shutil.copy2(source, args.output / source.name)
    for source, name in ((args.loader / "manifest.json", "loader-manifest.json"),
                         (args.ramroot / "manifest.json", "root-manifest.json"),
                         (args.zsh_build / "manifest.json", "zsh-link-manifest.json"),
                         (HERE / "apple-zsh-source.json", "apple-zsh-source.json")):
        shutil.copy2(source, args.output / name)
    for name in ("darwin-terminal-host-tests-3.log", "darwin-network-config-tests.log", "darwin-metal-host-check.log"):
        shutil.copy2(Path("/private/tmp") / name, args.output / name)
    report = {
        "outcome": "incremental-terminal-trial-passed-not-full-goal",
        "proved_in_guest": ["real controlling PTY", "Apple-source static ZLE arrow editing", "history recall",
                            "job suspension/listing/foreground resume", "Ctrl-C exit 130", "normal unmount and stop"],
        "host_only": ["raw-mode restoration and pipe handling", "explicit VirtIO NAT attachment configuration",
                      "real Metal vector calculation; not connected to guest"],
        "remaining": ["dynamic window sizing/SIGWINCH", "byte-preserving terminal transport",
                      "guest VirtIO NIC driver and IP/DNS/TCP proof", "guest GPU bridge/client and returned Metal result"],
        "zsh_sha256": link["sha256"], "kernel_sha256": loader["inputs"]["kernelSHA256"],
        "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(args.output.iterdir()) if p.is_file()},
    }
    (args.output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(args.output / "verification.json")


if __name__ == "__main__":
    main()
