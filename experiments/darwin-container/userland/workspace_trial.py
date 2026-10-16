#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Verify the named launcher with one shell/network session and one clean restart."""
import argparse
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import select
import signal
import struct
import subprocess
import termios
import time

from terminal_trial import NetworkFixture
from workspace_launcher import digest, validate_package


class Session:
    def __init__(self, launcher, root, name):
        self.master, self.slave = os.openpty()
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", 35, 120, 0, 0))
        def terminal():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
            os.tcsetpgrp(0, os.getpgrp())
        self.process = subprocess.Popen([str(launcher), name, "--workspace-root", str(root),
            "--timeout-seconds", "120"], stdin=self.slave, stdout=self.slave, stderr=self.slave,
            preexec_fn=terminal)
        os.set_blocking(self.master, False)
        self.capture = bytearray()
        self.cursor = 0
        self.deadline = time.monotonic() + 140
        self.directory = None

    def collect(self, timeout=0.1):
        if select.select([self.master], [], [], timeout)[0]:
            try:
                self.capture.extend(os.read(self.master, 65536))
            except OSError as error:
                if error.errno not in (errno.EIO, errno.EAGAIN):
                    raise

    def wait(self, marker, seconds=30):
        end = min(self.deadline, time.monotonic() + seconds)
        while time.monotonic() < end:
            position = self.capture.find(marker, self.cursor)
            if position >= 0:
                self.cursor = position + len(marker) - (2 if marker.endswith(b"\r\n") else 0)
                return
            if self.process.poll() is not None:
                self.collect(0)
                raise RuntimeError(f"launcher exited {self.process.returncode} before {marker!r}: {bytes(self.capture[-1500:])!r}")
            self.collect()
        raise RuntimeError(f"missing {marker!r}: {bytes(self.capture[-1500:])!r}")

    def send(self, command):
        data = memoryview(command.encode() if isinstance(command, str) else command)
        while data:
            if time.monotonic() > self.deadline:
                raise RuntimeError("terminal input deadline")
            if select.select([], [self.master], [], 0.1)[1]:
                try:
                    count = os.write(self.master, data)
                    data = data[count:]
                except BlockingIOError:
                    self.collect(0)

    def stop(self):
        self.send("exit\n")
        while self.process.poll() is None and time.monotonic() < self.deadline:
            self.collect()
        if self.process.poll() is None:
            raise RuntimeError("normal guest shutdown deadline")
        self.collect(0)
        result = json.loads((self.directory / "session/result.json").read_text())
        terminal = result.get("terminal", {})
        if not (self.process.returncode == 0 and result.get("guestStopped") and
                result.get("termination") == "guestStopped" and not result.get("error") and
                terminal.get("handshakeCompleted") and terminal.get("exitStatus") == 0 and not terminal.get("error")):
            raise RuntimeError("workspace did not shut down cleanly")

    def close(self):
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except PermissionError:
                # Some managed macOS callers permit signaling the owned
                # launcher but not its entire group. It forwards TERM to VZ.
                self.process.terminate()
            try:
                self.process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except PermissionError:
                    self.process.kill()
                self.process.wait(timeout=5)
        self.collect(0)
        if self.directory:
            (self.directory / "trial-terminal.bin").write_bytes(self.capture)
        os.close(self.master)
        os.close(self.slave)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher", required=True, type=Path)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    root = output / "workspaces"
    token = secrets.token_hex(12)
    passed, runs, fixture = [], [], None
    failure = None
    package_manifest = validate_package(args.package)
    try:
        subprocess.run([str(args.launcher.resolve()), "other", "--create", "--workspace-root", str(root)], check=True)
        other = root / "other/data.raw"
        other_hash = digest(other)
        for boot in (1, 2):
            session = Session(args.launcher.resolve(), root, "verification")
            try:
                session.wait(b"darwin-zsh#", 100)
                metadata = json.loads((root / "verification/workspace.json").read_text())
                session.directory = Path(metadata["last_run"])
                runs.append(str(session.directory))
                serial = (session.directory / "session/serial.bin").read_bytes().replace(b"\r", b"")
                if b"DARWIN:WORKSPACE:NETWORK_READY\n" not in serial:
                    raise RuntimeError("automatic network startup did not report success")
                lease = re.search(rb"DARWIN:NET:DHCP IP=([0-9.]+) MASK=([0-9.]+) ROUTER=([0-9.]+) DNS=([0-9.]+)", serial)
                if not lease:
                    raise RuntimeError("automatic DHCP lease missing")
                session.send("print -r -- WS_READY:$DARWIN_NETWORK_STATUS:$ZSH_VERSION:$PWD:$HOME\n")
                session.wait(b"\r\nWS_READY:ready:5.9:/data:/data\r\n")
                passed.append(f"boot {boot}: real zsh, PTY and automatic DHCP/DNS configuration")
                if boot == 1:
                    collision = subprocess.run([str(args.launcher.resolve()), "verification", "--workspace-root", str(root)], capture_output=True, timeout=10)
                    if collision.returncode != 1 or b"already running" not in collision.stderr:
                        raise RuntimeError("concurrent writable disk attachment was not rejected")
                    state = subprocess.run([str(args.launcher.resolve()), "verification", "--status", "--workspace-root", str(root)], capture_output=True, check=True)
                    if json.loads(state.stdout)["state"] != "running":
                        raise RuntimeError("running status does not reflect held instance lock")
                    passed.append("running status and same-workspace collision guard")
                    session.send(f"print -r -- {token} > /data/workspace-proof; print -r -- WS_WRITE:$?\n")
                    session.wait(b"\r\nWS_WRITE:0\r\n")
                    session.send(f"print -r -- HISTORY_{token}\n")
                    session.wait(f"\r\nHISTORY_{token}\r\n".encode())
                    session.wait(b"darwin-zsh#")
                    session.send("/bin/sleep 20\n")
                    session.wait(b"/bin/sleep 20")
                    session.collect(0.2)
                    session.send(b"\x03")
                    session.wait(b"darwin-zsh#")
                    session.send("print -r -- WS_INTERRUPT:$?\n")
                    session.wait(b"\r\nWS_INTERRUPT:130\r\n")
                    passed.append("real foreground interrupt through workspace terminal")
                    fixture = NetworkFixture(lease[3].decode(), lease[1].decode())
                    session.send(f"print -r -- 'nameserver {fixture.host}' > /data/resolv.conf\n")
                    session.send(f"/bin/resolverctl gai {fixture.dns.getsockname()[1]} {fixture.token}.darwin.test {fixture.tcp.getsockname()[1]} {fixture.token}; print -r -- WS_TCP:$?\n")
                    session.wait(f"\r\nDARWIN:NET:APPLE_GAI_TCP ECHO={fixture.token}\r\n".encode())
                    session.wait(b"\r\nWS_TCP:0\r\n")
                    if fixture.errors or sorted(event["type"] for event in fixture.events) != ["dns", "tcp"]:
                        raise RuntimeError("missing independently witnessed guest DNS/TCP traffic")
                    session.send(f"print -r -- 'nameserver {lease[4].decode()}' > /data/resolv.conf\n")
                    passed.append("Apple-source resolver DNS/TCP exchange using the automatically configured interface")
                else:
                    session.send(f"[[ $(</data/workspace-proof) == {token} && $(</data/.zsh_history) == *HISTORY_{token}* ]]; print -r -- WS_RESTORED:$?\n")
                    session.wait(b"\r\nWS_RESTORED:0\r\n")
                    passed.append("same named workspace restored its saved file and real zsh history")
                session.stop()
                passed.append(f"boot {boot}: normal exit, HFS unmount and actual guest stop")
            finally:
                session.close()
        slot = package_manifest["boot_entropy_slot"]
        seeds = []
        for run in runs:
            with (Path(run) / "boot.img").open("rb") as image:
                image.seek(slot["diskOffset"])
                seeds.append(image.read(slot["bytes"]))
        if len(seeds) != 2 or not all(any(seed) for seed in seeds) or seeds[0] == seeds[1]:
            raise RuntimeError("successive boots reused or omitted entropy")
        if digest(other) != other_hash or os.stat(other).st_ino == os.stat(root / "verification/data.raw").st_ino:
            raise RuntimeError("different named workspaces did not retain independent disks")
        validate_package(args.package)
        passed += ["fresh distinct boot entropy, unchanged zero-seed package template", "independent named workspace disks"]
        metadata = json.loads((root / "verification/workspace.json").read_text())
        if metadata["last_outcome"] != "clean-shutdown":
            raise RuntimeError("persistent workspace outcome omitted clean shutdown")
    except Exception as error:
        failure = str(error)
    finally:
        if fixture:
            fixture.close()
        report = {"passed": passed, "error": failure, "workspace_runs": runs, "package": str(args.package),
                  "package_manifest_sha256": digest(args.package / "manifest.json"),
                  "network_fixture": {"events": fixture.events, "errors": fixture.errors} if fixture else None,
                  "scope": "two actual launcher boots: shell/network then clean persistence restart; no soak"}
        (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if failure:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
