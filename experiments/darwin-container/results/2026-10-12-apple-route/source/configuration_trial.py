#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One finite VM Apple-bootp configuration trial, without repeating PTY/GPU proof.

Uses copied VM disks only. No physical Pi, serial-port, SSH or power operations.
The DNS server override is solely a fresh-nonce host fixture, not internet proof.
"""
import argparse
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import struct
import subprocess
import termios
import time

from terminal_trial import NetworkFixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cli", "boot-disk", "data-disk", "variable-store", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--apple-route", action="store_true", help="replace the disposable guest default route using original Apple route and inspect it")
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("output directory must not exist")
    master, slave = os.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 35, 120, 0, 0))

    def child_terminal():
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        os.tcsetpgrp(0, os.getpgrp())

    command = [str(args.cli.resolve()), "darwin", "run", "--interactive", "--framed-terminal",
               "--network-nat", "--timeout-seconds", "120", "--boot-disk", str(args.boot_disk.resolve()),
               "--data-disk", str(args.data_disk.resolve()), "--variable-store", str(args.variable_store.resolve()),
               "--output-dir", str(args.output_dir.resolve())]
    process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, preexec_fn=child_terminal)
    os.set_blocking(master, False)
    capture = bytearray()
    deadline = time.monotonic() + 130
    cursor = 0
    passed = []
    fixture = None
    failure = None

    def collect(timeout=0.1):
        if select.select([master], [], [], timeout)[0]:
            try:
                capture.extend(os.read(master, 65536))
            except OSError as error:
                if error.errno not in (errno.EIO, errno.EAGAIN):
                    raise

    def wait(marker, seconds=18):
        nonlocal cursor
        limit = min(deadline, time.monotonic() + seconds)
        while time.monotonic() < limit:
            found = capture.find(marker, cursor)
            if found >= 0:
                cursor = found + len(marker) - (2 if marker.endswith(b"\r\n") else 0)
                return
            if re.search(rb"\r\n(?:APPLE_BOOTP|APPLE_GAI|CONFIG_DNS|APPLE_ROUTE)_STATUS:[1-9][0-9]*\r\n", capture[cursor:]):
                raise RuntimeError(f"guest configuration failed; tail: {bytes(capture[-2000:])!r}")
            if process.poll() is not None:
                collect(0)
                raise RuntimeError(f"CLI stopped before {marker!r}: {process.returncode}")
            collect()
        raise RuntimeError(f"missing guest output {marker!r}; tail: {bytes(capture[-2000:])!r}")

    def send(data):
        # Commands are small, but preserve partial-write and EAGAIN semantics.
        view = memoryview(data)
        while view:
            if time.monotonic() >= deadline:
                raise RuntimeError("terminal input deadline")
            if not select.select([], [master], [], 0.1)[1]:
                collect(0)
                continue
            try:
                count = os.write(master, view)
                if not count:
                    raise RuntimeError("terminal input closed")
                view = view[count:]
            except BlockingIOError:
                collect(0)

    try:
        wait(b"darwin-zsh#")
        send(b"/bin/dhcpctl; print -r -- APPLE_BOOTP_STATUS:$?\n")
        wait(b"\r\nDARWIN:NET:APPLE_BOOTP bootp-268.1 options match BPF checksum IPv4\r\n", 65)
        wait(b"\r\nDARWIN:NET:DHCP IP=")
        wait(b"\r\nAPPLE_BOOTP_STATUS:0\r\n")
        lease = re.search(rb"DARWIN:NET:DHCP IP=([0-9.]+) MASK=([0-9.]+) ROUTER=([0-9.]+) DNS=([0-9.]+) LEASE=([0-9]+)", capture)
        if not lease:
            raise RuntimeError("missing actual DHCP lease")
        passed.append("original Apple bootp options/match/BPF/checksum and IPv4 routines configured en0; project route ACK confirmed")
        send(f"[[ $(</data/resolv.conf) == 'nameserver {lease[4].decode()}' ]]; print -r -- CONFIG_DNS_STATUS:$?\n".encode())
        wait(b"\r\nCONFIG_DNS_STATUS:0\r\n")
        passed.append("DHCP-provided DNS address persisted in real resolver configuration")
        if args.apple_route:
            send(f"/bin/route -n delete default && /bin/route -n add default {lease[3].decode()} && /bin/route -n get default; print -r -- APPLE_ROUTE_STATUS:$?\n".encode())
            wait(b"delete net default\r\n")
            wait(f"add net default: gateway {lease[3].decode()}\r\n".encode())
            wait(b"   route to: default\r\n")
            wait(f"    gateway: {lease[3].decode()}\r\n".encode())
            wait(b"  interface: en0\r\n")
            wait(b"\r\nAPPLE_ROUTE_STATUS:0\r\n")
            passed.append("original Apple route delete/add/get replaced and inspected the actual guest default route")
        # The previously qualified original Libinfo binary is an integration
        # witness here; no new full resolver/terminal/GPU qualification claimed.
        fixture = NetworkFixture(lease[3].decode(), lease[1].decode())
        send(f"print -r -- 'nameserver {fixture.host}' > /data/resolv.conf\n".encode())
        send(f"/bin/resolverctl gai {fixture.dns.getsockname()[1]} {fixture.token}.darwin.test {fixture.tcp.getsockname()[1]} {fixture.token}; print -r -- APPLE_GAI_STATUS:$?\n".encode())
        wait(b"\r\nDARWIN:NET:APPLE_LIBINFO_NUMERIC IPv4 IPv6 errors en0=")
        wait(f"\r\nDARWIN:NET:APPLE_GETADDRINFO {fixture.token}.darwin.test {fixture.host} Libinfo-542.40.3\r\n".encode())
        wait(f"\r\nDARWIN:NET:APPLE_GAI_TCP ECHO={fixture.token}\r\n".encode())
        wait(b"\r\nAPPLE_GAI_STATUS:0\r\n")
        if fixture.errors or sorted(event["type"] for event in fixture.events) != ["dns", "tcp"]:
            raise RuntimeError("missing independent guest-originated DNS/TCP nonce evidence")
        passed.append("fresh guest DNS and resolved TCP exchange after Apple-source DHCP, independently witnessed on host")
        # Restore the actual lease's DNS value before clean shutdown.
        send(f"print -r -- 'nameserver {lease[4].decode()}' > /data/resolv.conf; exit\n".encode())
        while process.poll() is None and time.monotonic() < deadline:
            collect()
        if process.poll() is None:
            raise RuntimeError("CLI exceeded bounded configuration deadline")
        collect(0)
        result = json.loads((args.output_dir / "result.json").read_text())
        terminal = result.get("terminal", {})
        if process.returncode or not (result.get("guestStopped") and result.get("termination") == "guestStopped"
                and not result.get("error") and terminal.get("handshakeCompleted")
                and terminal.get("exitStatus") == 0 and not terminal.get("error")):
            raise RuntimeError("missing successful guest exit/unmount/stop")
        passed.append("normal zsh exit and clean guest shutdown")
    except Exception as error:
        failure = str(error)
        if process.poll() is None:
            try:
                send(b"\x03exit\n")
            except (OSError, RuntimeError):
                pass
            cleanup = time.monotonic() + 5
            while process.poll() is None and time.monotonic() < cleanup:
                collect()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
    finally:
        if fixture:
            fixture.close()
        os.close(master)
        os.close(slave)
        if args.output_dir.is_dir():
            (args.output_dir / "host-terminal.bin").write_bytes(capture)
            report = {"passed": passed, "error": failure, "cli_exit": process.returncode,
                      "cli_sha256": hashlib.sha256(args.cli.read_bytes()).hexdigest(),
                      "apple_route": args.apple_route,
                      "network_fixture": {"events": fixture.events, "errors": fixture.errors,
                                          "host_route": fixture.route, "token": fixture.token} if fixture else None,
                      "scope": "one bounded Apple-bootp VM configuration/integration trial; no repeated PTY/GPU proof; no Pi evidence"}
            (args.output_dir / "configuration-trial.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": passed, "error": failure, "output": str(args.output_dir)}))
    if failure:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
