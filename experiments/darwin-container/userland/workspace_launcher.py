#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Open a named, persistent Darwin workspace on this Apple-silicon Mac."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import uuid


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError(f"workspace directory must be owned by you and cannot be a symlink: {path}")
    path.chmod(0o700)


def write_json(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def lock_instance(directory):
    descriptor = os.open(directory / "workspace.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(descriptor)
        raise RuntimeError("this workspace is already running; use a different name") from None
    return descriptor


def validate_package(package):
    manifest = json.loads((package / "manifest.json").read_text())
    if manifest.get("format") != "darwin-workspace-1":
        raise RuntimeError("unsupported workspace package")
    for name, expected in manifest["immutable_sha256"].items():
        path = package / name
        if Path(name).is_absolute() or ".." in Path(name).parts or path.is_symlink() or digest(path) != expected:
            raise RuntimeError(f"workspace package input changed: {name}")
    return manifest


def prepare_boot(package, manifest, output):
    """Provision only the authenticated template's reserved zero seed slot."""
    image = bytearray((package / "efi-template.img").read_bytes())
    slot = manifest["boot_entropy_slot"]
    offset, count = slot["diskOffset"], slot["bytes"]
    if count != 256 or not 0 <= offset <= len(image) - count or any(image[offset:offset + count]):
        raise RuntimeError("invalid or already provisioned template entropy slot")
    seed = os.urandom(count)
    if not any(seed):
        raise RuntimeError("host entropy generation failed")
    image[offset:offset + count] = seed
    path = output / "boot.img"
    with path.open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(image)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def inspect_status(directory):
    if directory.is_symlink():
        raise RuntimeError("workspace cannot be a symlink")
    try:
        descriptor = lock_instance(directory)
    except RuntimeError:
        return {"name": directory.name, "state": "running"}
    os.close(descriptor)
    metadata = directory / "workspace.json"
    record = json.loads(metadata.read_text()) if metadata.is_file() else {}
    # A crashed launcher can leave a 'running' record; the held lock is authority.
    return {"name": directory.name, "state": "stopped", "last_run": record.get("last_run"),
            "last_outcome": record.get("last_outcome")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", nargs="?", default="default", help="workspace name; created on first use")
    parser.add_argument("--workspace-root", type=Path, help="directory containing named workspaces")
    parser.add_argument("--timeout-seconds", type=int, default=3600, help="session deadline, 1..3600; exit normally to save")
    parser.add_argument("--list", action="store_true", help="list workspaces without booting")
    parser.add_argument("--status", action="store_true", help="show this workspace's current state without booting")
    parser.add_argument("--create", action="store_true", help="create a workspace disk without booting")
    parser.add_argument("--shared-gpu", action="store_true", help="enable the existing bounded Metal compute interface")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}", args.name):
        parser.error("name must be 1..48 letters, digits, underscores or hyphens, starting with a letter or digit")
    if not 1 <= args.timeout_seconds <= 3600:
        parser.error("timeout must be 1..3600 seconds")
    package = Path(__file__).resolve().parent
    root = args.workspace_root.absolute() if args.workspace_root else package.parents[2] / "workspaces"
    private_directory(root)
    if args.list:
        records = [inspect_status(path) for path in sorted(root.iterdir())
                   if path.is_dir() and not path.is_symlink() and (path / "workspace.json").is_file()]
        print(json.dumps(records, indent=2))
        return 0
    instance = root / args.name
    if args.status:
        if not instance.is_dir():
            parser.error("workspace does not exist")
        print(json.dumps(inspect_status(instance), indent=2))
        return 0
    manifest = validate_package(package)
    private_directory(instance)
    lock = lock_instance(instance)
    try:
        data = instance / "data.raw"
        metadata = instance / "workspace.json"
        if not data.exists() and not data.is_symlink():
            # An incomplete creation remains a diagnostic artifact; never silently
            # replace an existing writable disk, including after an interrupted run.
            with data.open("xb") as destination, (package / "data-template.raw").open("rb") as source:
                os.fchmod(destination.fileno(), 0o600)
                shutil.copyfileobj(source, destination)
                destination.flush()
                os.fsync(destination.fileno())
        info = data.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size != manifest["data_bytes"]:
            raise RuntimeError("workspace data image is not an owned regular file of the expected size")
        with data.open("rb") as stream:
            stream.seek(1024)
            if stream.read(2) not in (b"H+", b"HX"):
                raise RuntimeError("workspace disk lacks its HFS+ volume header")
        if args.create:
            if not metadata.exists():
                write_json(metadata, {"name": args.name, "package_version": manifest["version"],
                                      "data_disk": str(data), "last_outcome": "created"})
            print(f"Darwin workspace {args.name}: {data}")
            return 0
        private_directory(instance / "runs")
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
        output = instance / "runs" / run_id
        output.mkdir(mode=0o700)
        boot = prepare_boot(package, manifest, output)
        # The existing VZ CLI creates a fresh variable store if no template is
        # supplied. Firmware state is private to this boot; /data is persistent.
        command = [str(package / "container"), "darwin", "run", "--interactive", "--framed-terminal",
                   "--network-nat", "--boot-disk", str(boot), "--data-disk", str(data),
                   "--output-dir", str(output / "session"), "--timeout-seconds", str(args.timeout_seconds)]
        if args.shared_gpu:
            command.append("--shared-gpu")
        record = {"name": args.name, "package_version": manifest["version"], "data_disk": str(data),
                  "last_run": str(output), "last_outcome": "running"}
        write_json(metadata, record)
        write_json(output / "launch.json", {"workspace": args.name, "package_version": manifest["version"],
            "boot_sha256": digest(boot), "entropy": "fresh host os.urandom(256); seed bytes never logged",
            "data_disk": str(data), "command": command})
        print(f"Darwin workspace {args.name}; files/history: {data}\nType exit for clean shutdown. Run: {output}", flush=True)
        # Keep both launcher and child holding the sidecar lock, even if the
        # supervising launcher is interrupted. VZ holds its own image lock too.
        child = None
        pending_signal = None
        def interrupt(signum, frame):
            nonlocal pending_signal
            if pending_signal is None:
                pending_signal = signum
                if child is not None and child.poll() is None:
                    child.send_signal(signum)
        previous_handlers = {signum: signal.signal(signum, interrupt)
                             for signum in (signal.SIGINT, signal.SIGTERM)}
        try:
            child = subprocess.Popen(command, pass_fds=(lock,))
            if pending_signal is not None:
                child.send_signal(pending_signal)
            code = child.wait()
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)
        result_path = output / "session/result.json"
        outcome = json.loads(result_path.read_text()) if result_path.is_file() else {}
        terminal = outcome.get("terminal", {})
        clean = bool(code == 0 and outcome.get("guestStopped") and
                     outcome.get("termination") == "guestStopped" and not outcome.get("error") and
                     terminal.get("handshakeCompleted") and terminal.get("exitStatus") == 0 and not terminal.get("error"))
        record["last_outcome"] = "clean-shutdown" if clean else "failed-or-forced-stop"
        record["last_exit_code"] = code
        write_json(metadata, record)
        if not clean:
            print(f"Workspace did not finish with a verified clean shutdown; inspect {output}", file=sys.stderr)
        return code if code else (0 if clean else 1)
    finally:
        os.close(lock)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"darwin-workspace: {error}", file=sys.stderr)
        raise SystemExit(1)
