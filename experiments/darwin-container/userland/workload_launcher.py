#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Launch this private, versioned Darwin workload package without container services."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", help="Run this script using the guest's real Apple-source zsh, then stop")
    parser.add_argument("--data-disk", type=Path, help="Explicit existing RAW workload disk; defaults to this package's data.raw")
    parser.add_argument("--timeout-seconds", type=int, help="Safety deadline; default 3600 interactive, 60 managed")
    parser.add_argument("--output-dir", type=Path, help="New evidence directory; defaults to runs/<unique ID>")
    args = parser.parse_args()
    if args.timeout_seconds is not None and args.timeout_seconds <= 0:
        parser.error("timeout must be positive")
    package = Path(__file__).resolve().parent
    manifest = json.loads((package / "manifest.json").read_text())
    for name, expected in manifest["immutable_sha256"].items():
        path = package / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"versioned input changed: {name}")
    output = args.output_dir.absolute() if args.output_dir else package / "runs" / uuid.uuid4().hex
    data = args.data_disk.absolute() if args.data_disk else package / "data.raw"
    if data.is_symlink() or not data.is_file():
        parser.error("data disk must be an existing regular file")
    # Lock a sidecar, not the RAW image: Virtualization.framework takes its own
    # exclusive storage lock when starting the VM. The inherited descriptor
    # holds this launcher guard until the foreground CLI exits.
    lock_path = data.with_name(data.name + ".workload.lock")
    disk_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(disk_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error("data disk is already locked by another workload session")
    os.set_inheritable(disk_fd, True)
    command = [str(package / "bin/container"), "darwin", "run",
               "--boot-disk", str(package / ("efi-agent.img" if args.command is not None else "efi-interactive.img")),
               "--data-disk", str(data),
               "--variable-store", str(package / "efi-variables-template.bin"),
               "--output-dir", str(output), "--timeout-seconds",
               str(args.timeout_seconds or (60 if args.command is not None else 3600))]
    if args.command is not None:
        # Existing managed protocol has a 256-byte argv payload limit. CLI validates
        # before VM start; it must not silently truncate a longer user script.
        command += ["--managed-agent", "--agent-command", "/bin/zsh -f -c " + shlex.quote(args.command)]
    else:
        command.append("--interactive")
    print(f"Darwin workload {manifest['version']}; evidence: {output}", flush=True)
    os.execv(command[0], command)


if __name__ == "__main__":
    main()
