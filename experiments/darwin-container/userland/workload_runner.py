#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Run one packaged Darwin workload per VM; retain data, logs and exact outcomes."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import select
import shutil
import signal
import stat
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent / "support"))
from workspace_launcher import digest, private_directory, prepare_boot, write_json


def name(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}", value):
        raise ValueError("names must be 1..48 letters, digits, underscores or hyphens")
    return value


def regular(path, size=None):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or (size is not None and info.st_size != size):
        raise RuntimeError(f"not an owned regular file of the expected size: {path}")


def lock(directory):
    path = directory / "run.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        regular(path)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise
    return fd


def package_manifest(package):
    manifest = json.loads((package / "manifest.json").read_text())
    if manifest.get("format") != "darwin-workload-package-1":
        raise RuntimeError("not a packaged Darwin workload")
    hashes = manifest["immutable_sha256"]
    if not {"container", "darwin", "support/workspace_launcher.py", "workload.json", "efi-template.img",
            "loader-template.efi", "kernel.macho", "ramdisk.bin", "data-template.raw"} <= set(hashes):
        raise RuntimeError("incomplete workload package")
    for relative, expected in hashes.items():
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or str(path) != relative:
            raise RuntimeError("unsafe package path")
        candidate = package
        for component in path.parts:
            candidate = candidate / component
            if candidate.is_symlink():
                raise RuntimeError(f"package symlink rejected: {relative}")
        if not candidate.is_file() or digest(candidate) != expected:
            raise RuntimeError(f"workload package input changed: {relative}")
    spec = json.loads((package / "workload.json").read_text())
    if spec["resources"]["cpus"] != 1 or spec["resources"]["memory_mib"] != 512:
        raise RuntimeError("unsupported workload resource profile")
    return manifest, spec


def clone_data(package, destination, expected_size):
    if not destination.exists() and not destination.is_symlink():
        with destination.open("xb") as output, (package / "data-template.raw").open("rb") as source:
            os.fchmod(output.fileno(), 0o600)
            shutil.copyfileobj(source, output)
            output.flush()
            os.fsync(output.fileno())
    regular(destination, expected_size)
    with destination.open("rb") as source:
        source.seek(1024)
        if source.read(2) not in (b"H+", b"HX"):
            raise RuntimeError("data image lacks an HFS+ volume header; refusing to replace or format it")


def outcome(result, native_code, requested=False):
    agent = result.get("agent") or {}
    commands = agent.get("commands") or []
    command = commands[0] if len(commands) == 1 else {}
    transport = bool(result.get("started") and result.get("guestStopped") and agent.get("protocolValid") and
                     agent.get("handshakeCompleted") and agent.get("shutdownAcknowledged") and not agent.get("error") and
                     command.get("terminalObserved") and command.get("cleanupVerified") and
                     command.get("stdoutEOF") and command.get("stderrEOF") and not command.get("outputLimit"))
    record = {"guest_stopped": bool(result.get("guestStopped")), "managed_completion_verified": transport,
              "native_exit_code": native_code, "exit_status": command.get("exitStatus"),
              "termination_signal": command.get("terminationSignal"), "cancel_requested": requested,
              "cancel_accepted": command.get("cancellationAccepted"), "termination": result.get("termination"),
              "error": result.get("error") or agent.get("error")}
    if not transport:
        state, code = "failed", 1
    elif result.get("termination") == "timedOut":
        state, code = "timed-out", 124
    elif command.get("cancelled") or command.get("cancellationRequested"):
        state, code = "cancelled", 130
    elif result.get("termination") != "guestStopped" or result.get("error"):
        state, code = "failed", 1
    elif command.get("terminationSignal") is not None:
        state, code = "signalled", 128 + command["terminationSignal"]
    elif type(command.get("exitStatus")) is int and native_code == command["exitStatus"]:
        state, code = ("succeeded" if command["exitStatus"] == 0 else "exited"), command["exitStatus"]
    else:
        state, code = "failed", 1
    return record | {"state": state, "runner_exit_code": code}


def status(directory):
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("run does not exist or is a symlink")
    record = json.loads((directory / "run.json").read_text())
    try:
        fd = lock(directory)
    except BlockingIOError:
        return record | {"state": "running"}
    os.close(fd)
    if record["state"] == "running":
        # A dead wrapper is not evidence that a VM completed cleanly.
        record["state"] = "incomplete"
    return record


def run(package, root, run_name=None, volume=None, timeout=None, cancel_after=None):
    manifest, spec = package_manifest(package)
    run_name = name(run_name or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8])
    if volume is not None:
        name(volume)
    deadline = timeout if timeout is not None else spec["resources"]["timeout_seconds"]
    if type(deadline) is not int or not 1 <= deadline <= 3600:
        raise ValueError("timeout must be 1..3600 seconds")
    if cancel_after is not None and (type(cancel_after) is not int or not 1 <= cancel_after <= 3600):
        raise ValueError("cancel-after must be 1..3600 seconds")
    private_directory(root)
    private_directory(root / "runs")
    directory = root / "runs" / run_name
    directory.mkdir(mode=0o700, exist_ok=False)  # Never reuse run logs or firmware.
    run_lock = lock(directory)
    volume_lock = None
    fifo_fd = None
    child = None
    handlers = {}
    record = {"name": run_name, "package": str(package), "package_manifest_sha256": digest(package / "manifest.json"),
              "workload": spec["name"], "version": spec["version"], "state": "preparing", "volume": volume,
              "network": spec["network"], "resources": spec["resources"] | {"timeout_seconds": deadline},
              "directory": str(directory)}
    write_json(directory / "run.json", record)
    try:
        if volume is not None:
            name(volume)
            private_directory(root / "volumes")
            volume_dir = root / "volumes" / volume
            private_directory(volume_dir)
            try:
                volume_lock = lock(volume_dir)
            except BlockingIOError:
                raise RuntimeError(f"volume {volume} is already attached to another workload") from None
            data = volume_dir / "data.raw"
        else:
            data = directory / "data.raw"
        clone_data(package, data, manifest["data_bytes"])
        boot = prepare_boot(package, manifest, directory)
        command = [str(package / "container"), "darwin", "run", "--managed-agent", "--agent-command",
                   "/bin/zsh -f /app/entry.zsh", "--boot-disk", str(boot), "--data-disk", str(data),
                   "--output-dir", str(directory / "session"), "--cpus", "1", "--memory-mib", "512",
                   "--timeout-seconds", str(deadline)]
        if spec["network"] == "nat":
            command.append("--network-nat")
        if cancel_after is not None:
            command += ["--cancel-after-seconds", str(cancel_after)]
        record |= {"state": "running", "data_disk": str(data), "started_at": datetime.now(timezone.utc).isoformat()}
        write_json(directory / "launch.json", {"command": command, "boot_sha256": digest(boot),
                   "entropy": "fresh host os.urandom(256); seed bytes not logged", "package_manifest_sha256": record["package_manifest_sha256"]})
        fifo = directory / "control.fifo"
        os.mkfifo(fifo, 0o600)
        fifo_fd = os.open(fifo, os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW)
        requested = False
        def interrupt(signum, frame):
            nonlocal requested
            if not requested:
                requested = True
                if child is not None and child.poll() is None:
                    child.send_signal(signal.SIGINT)
        handlers = {signum: signal.signal(signum, interrupt) for signum in (signal.SIGINT, signal.SIGTERM)}
        write_json(directory / "run.json", record)
        print(f"Darwin workload {spec['name']} -> {run_name}; evidence: {directory}", file=sys.stderr, flush=True)
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                 pass_fds=tuple(fd for fd in (run_lock, volume_lock) if fd is not None))
        if requested:
            child.send_signal(signal.SIGINT)
        while child.poll() is None:
            readable, _, _ = select.select([fifo_fd], [], [], 0.2)
            if readable and b"stop" in os.read(fifo_fd, 1024):
                interrupt(signal.SIGINT, None)
        result_path = directory / "session/result.json"
        result = json.loads(result_path.read_text()) if result_path.is_file() else {}
        record |= outcome(result, child.returncode, requested)
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(directory / "run.json", record)
        print(f"Darwin workload {run_name}: {record['state']} (exit {record['runner_exit_code']})", file=sys.stderr)
        return record["runner_exit_code"]
    except BaseException as error:
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGINT)
            # Native runner owns bounded managed cleanup and forced-stop fallback.
            child.wait(timeout=30)
        record |= {"state": "failed", "error": str(error), "runner_exit_code": 1}
        write_json(directory / "run.json", record)
        raise
    finally:
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
        if fifo_fd is not None:
            os.close(fifo_fd)
        for descriptor in (volume_lock, run_lock):
            if descriptor is not None:
                os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    launch = sub.add_parser("run", help="boot this package in a new exclusive XNU VM")
    launch.add_argument("--name", help="unique run name; never overwrites a previous run")
    launch.add_argument("--volume", help="persistent named /data disk, exclusively locked")
    launch.add_argument("--timeout-seconds", type=int)
    launch.add_argument("--cancel-after-seconds", type=int, help="request managed cancellation after STARTED")
    for action in ("status", "logs", "stop"):
        command = sub.add_parser(action)
        command.add_argument("name", type=name)
        if action == "logs":
            command.add_argument("--stderr", action="store_true")
    for command in sub.choices.values():
        command.add_argument("--state-root", type=Path, default=Path.cwd() / "darwin-workloads")
    args = parser.parse_args()
    root = args.state_root.absolute()
    if args.action == "run":
        return run(Path(__file__).resolve().parent, root, args.name, args.volume, args.timeout_seconds, args.cancel_after_seconds)
    directory = root / "runs" / args.name
    record = status(directory)
    if args.action == "status":
        print(json.dumps(record, indent=2))
    elif args.action == "logs":
        path = directory / "session" / ("command-1-stderr.bin" if args.stderr else "command-1-stdout.bin")
        with path.open("rb") as stream:
            shutil.copyfileobj(stream, sys.stdout.buffer)
    elif args.action == "stop":
        if record["state"] != "running":
            print(f"Darwin workload {args.name}: already {record['state']}")
            return 0
        fifo = directory / "control.fifo"
        info = fifo.lstat()
        if not stat.S_ISFIFO(info.st_mode) or info.st_uid != os.getuid():
            raise RuntimeError("unsafe control FIFO")
        descriptor = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        try:
            os.write(descriptor, b"stop\n")
        finally:
            os.close(descriptor)
        print("Managed cancellation requested; use status to verify completion and guest stop.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"darwin-workload: {error}", file=sys.stderr)
        raise SystemExit(1)
