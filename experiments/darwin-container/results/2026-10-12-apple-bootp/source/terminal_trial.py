#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One bounded real-VM PTY trial: editing/jobs, resize, byte roundtrip and exit.

Uses only supplied local VM images. No physical serial, SSH or Pi operations.
The CLI creates a fresh evidence directory; this harness never overwrites it.
"""
import argparse
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import select
import socket
import struct
import subprocess
import termios
import threading
import time


class NetworkFixture:
    """Short-lived nonce-bound DNS/TCP servers on the host's own NAT address."""
    def __init__(self, host, guest, resolver=False, libinfo=False):
        self.host, self.guest = host, guest
        self.libinfo = libinfo
        self.token = secrets.token_hex(12)
        self.events, self.errors = [], []
        self.route = subprocess.run(["/sbin/route", "-n", "get", guest], capture_output=True, text=True, timeout=5).stdout
        self.stopping = threading.Event()
        self.dns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.dns_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM) if resolver else None
        self.dns.bind((host, 0))
        if self.dns_tcp:
            self.dns_tcp.bind((host, self.dns.getsockname()[1]))
            self.dns_tcp.listen(1)
            self.dns_tcp.settimeout(0.2)
        self.tcp.bind((host, 0))
        self.tcp.listen(1)
        self.dns.settimeout(0.2)
        self.tcp.settimeout(0.2)
        self.threads = [threading.Thread(target=self.serve_dns, daemon=True), threading.Thread(target=self.serve_tcp, daemon=True)]
        if self.dns_tcp:
            self.threads.append(threading.Thread(target=self.serve_dns_tcp, daemon=True))
        for thread in self.threads:
            thread.start()

    def serve_dns(self):
        name = bytes([len(self.token)]) + self.token.encode() + b"\x06darwin\x04test\0\0\x01\0\x01"
        while not self.stopping.is_set():
            try:
                data, peer = self.dns.recvfrom(512)
            except socket.timeout:
                continue
            except OSError:
                return
            if peer[0] != self.guest or len(data) != 12 + len(name) or data[12:] != name:
                continue
            reply = data[:2] + b"\x81\x80\0\x01\0\x01\0\0\0\0" + name
            reply += b"\xc0\x0c\0\x01\0\x01\0\0\0\x01\0\x04" + socket.inet_aton(self.host)
            self.dns.sendto(reply, peer)
            self.events.append({"type": "dns", "guest": peer[0], "name": self.token + ".darwin.test", "answer": self.host})
            if not self.dns_tcp:
                return

    def serve_dns_tcp(self):
        name = bytes([len(self.token)]) + self.token.encode() + b"\x06darwin\x04test\0\0\x01\0\x01"
        while not self.stopping.is_set():
            try:
                connection, peer = self.dns_tcp.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with connection:
                if peer[0] != self.guest:
                    continue
                connection.settimeout(4)
                try:
                    def exact(count):
                        data = b""
                        while len(data) < count:
                            piece = connection.recv(count - len(data))
                            if not piece:
                                raise RuntimeError("short DNS TCP input")
                            data += piece
                        return data
                    size = struct.unpack("!H", exact(2))[0]
                    if size > 512:
                        raise RuntimeError("oversized DNS TCP input")
                    data = exact(size)
                    if len(data) != 12 + len(name) or data[12:] != name:
                        raise RuntimeError("unexpected DNS TCP query")
                    reply = data[:2] + b"\x81\x80\0\x01\0\x01\0\0\0\0" + name
                    reply += b"\xc0\x0c\0\x01\0\x01\0\0\0\x01\0\x04" + socket.inet_aton(self.host)
                    connection.sendall(struct.pack("!H", len(reply)) + reply)
                    self.events.append({"type": "dns_tcp", "guest": peer[0], "name": self.token + ".darwin.test", "answer": self.host})
                except Exception as error:
                    self.errors.append(str(error))
            return

    def serve_tcp(self):
        while not self.stopping.is_set():
            try:
                connection, peer = self.tcp.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with connection:
                if peer[0] != self.guest:
                    continue
                connection.settimeout(4)
                data = b""
                try:
                    while len(data) < len(self.token):
                        chunk = connection.recv(len(self.token) - len(data))
                        if not chunk:
                            raise RuntimeError("guest closed before nonce")
                        data += chunk
                    if data != self.token.encode():
                        raise RuntimeError("unexpected guest TCP nonce")
                    connection.sendall(data)
                    self.events.append({"type": "tcp", "guest": peer[0], "echo": data.decode()})
                except Exception as error:
                    self.errors.append(str(error))
            if not self.libinfo:
                return

    def close(self):
        self.stopping.set()
        self.dns.close()
        self.tcp.close()
        if self.dns_tcp:
            self.dns_tcp.close()
        for thread in self.threads:
            thread.join(timeout=1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cli", "boot-disk", "data-disk", "variable-store", "output-dir"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--verify-persistence", action="store_true", help="Require note and saved history from a prior completed trial on this copied disk")
    parser.add_argument("--network", action="store_true", help="Enable the opt-in VM NAT NIC and require guest en0/DHCP diagnostics")
    parser.add_argument("--shared-gpu", action="store_true", help="Require typed guest requests to execute on host Metal and return verified results")
    parser.add_argument("--apple-dns", action="store_true", help="Require original Apple libresolv wire parser marker; implies no full resolver claim")
    parser.add_argument("--apple-resolver", action="store_true", help="Require standalone original Apple res_ninit/res_nquery UDP and TCP queries")
    parser.add_argument("--apple-libinfo", action="store_true", help="Require original Apple getaddrinfo and interface lookup, then guest TCP through its result")
    args = parser.parse_args()
    if args.apple_dns and not args.network:
        parser.error("--apple-dns requires --network")
    if args.apple_resolver and not args.network:
        parser.error("--apple-resolver requires --network")
    if args.apple_libinfo and not args.apple_resolver:
        parser.error("--apple-libinfo requires --apple-resolver")
    if args.output_dir.exists():
        parser.error("output directory must not exist")
    master, slave = os.openpty()
    original = termios.tcgetattr(slave)
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 35, 120, 0, 0))

    def child_terminal():
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        os.tcsetpgrp(0, os.getpgrp())

    command = [str(args.cli.resolve()), "darwin", "run", "--interactive", "--framed-terminal",
               "--timeout-seconds", "90", "--boot-disk", str(args.boot_disk.resolve()),
               "--data-disk", str(args.data_disk.resolve()), "--variable-store", str(args.variable_store.resolve()),
               "--output-dir", str(args.output_dir.resolve())]
    if args.network:
        command.append("--network-nat")
    if args.shared_gpu:
        command.append("--shared-gpu")
    process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, preexec_fn=child_terminal)
    os.set_blocking(master, False)
    capture = bytearray()
    deadline = time.monotonic() + 100
    cursor = 0
    passed = []
    fixture = None
    gpu_seeds = [secrets.randbelow(60000) + 1000 for _ in range(2)] if args.shared_gpu else []

    def collect(timeout=0.1):
        if select.select([master], [], [], timeout)[0]:
            try:
                data = os.read(master, 65536)
                capture.extend(data)
            except OSError as error:
                if error.errno not in (errno.EIO, errno.EAGAIN):
                    raise

    def wait(marker):
        nonlocal cursor
        limit = min(deadline, time.monotonic() + 18)
        while time.monotonic() < limit:
            found = capture.find(marker, cursor)
            if found >= 0:
                # Adjacent output lines share their CRLF delimiter.
                cursor = found + len(marker) - (2 if marker.endswith(b"\r\n") else 0)
                return
            diagnostic_failure = re.search(rb"\r\nNET_(?:INFO|DHCP|EXCHANGE)_STATUS:([1-9][0-9]*)\r\n", capture[cursor:])
            if args.network and diagnostic_failure:
                raise RuntimeError(f"guest network diagnostic failed: {diagnostic_failure[0]!r}; tail: {bytes(capture[-1800:])!r}")
            if args.shared_gpu and re.search(rb"\r\nGPU_STATUS:([1-9][0-9]*)\r\n", capture[cursor:]):
                raise RuntimeError(f"guest GPU diagnostic failed; tail: {bytes(capture[-1800:])!r}")
            if process.poll() is not None:
                collect(0)
                raise RuntimeError(f"CLI stopped before {marker!r}: {process.returncode}")
            collect()
        raise RuntimeError(f"missing actual terminal output {marker!r}; tail: {bytes(capture[-1800:])!r}")

    def send(data):
        os.write(master, data)

    failure = None
    restoration = "not reached"
    try:
        wait(b"darwin-zsh#")
        if args.shared_gpu:
            for seed in gpu_seeds:
                send(f"/bin/gpuctl selftest {seed}; print -r -- GPU_STATUS:$?\n".encode())
                wait(f"\r\nDARWIN:GPU:ADD OK seed={seed} count=16\r\n".encode())
                wait(b"\r\nGPU_STATUS:0\r\n")
            send(b"/bin/gpuctl unsupported; print -r -- GPU_STATUS:$?\n")
            wait(b"\r\nDARWIN:GPU:UNSUPPORTED status=1\r\n")
            wait(b"\r\nGPU_STATUS:0\r\n")
            passed.append("typed guest vector requests returned verified results and explicit unsupported-operation status")
        if args.network:
            send(b"/bin/netctl info; print -r -- NET_INFO_STATUS:$?\n")
            wait(b"\r\nDARWIN:NET:INTERFACE en0 INDEX=")
            wait(b"\r\nNET_INFO_STATUS:0\r\n")
            passed.append("real XNU en0 interface and MAC via guest routing sysctl")
            send(b"/bin/netctl dhcp; print -r -- NET_DHCP_STATUS:$?\n")
            wait(b"\r\nDARWIN:NET:DHCP IP=")
            wait(b"\r\nNET_DHCP_STATUS:0\r\n")
            passed.append("guest BPF/UDP DHCP discover/offer/request/ACK and address/default-route setup")
            lease = re.search(rb"DARWIN:NET:DHCP IP=([0-9.]+) MASK=([0-9.]+) ROUTER=([0-9.]+) DNS=([0-9.]+)", capture)
            if not lease:
                raise RuntimeError("missing actual DHCP lease values")
            fixture = NetworkFixture(lease[3].decode(), lease[1].decode(), args.apple_resolver, args.apple_libinfo)
            send(f"/bin/netctl exchange {fixture.host} {fixture.dns.getsockname()[1]} {fixture.tcp.getsockname()[1]} {fixture.token}; print -r -- NET_EXCHANGE_STATUS:$?\n".encode())
            if args.apple_dns:
                wait(b"\r\nDARWIN:NET:APPLE_DNS_WIRE libresolv-96\r\n")
            wait(f"\r\nDARWIN:NET:DNS {fixture.token}.darwin.test A={fixture.host}\r\n".encode())
            wait(f"\r\nDARWIN:NET:TCP ECHO={fixture.token}\r\n".encode())
            wait(b"\r\nNET_EXCHANGE_STATUS:0\r\n")
            if fixture.errors or sorted(e["type"] for e in fixture.events) != ["dns", "tcp"]:
                raise RuntimeError("host fixture lacks matching guest-originated DNS/TCP evidence")
            passed.append("guest-originated DNS A lookup and TCP nonce echo, independently witnessed on host NAT interface")
            if args.apple_dns:
                passed.append("original pinned Apple libresolv-96 DNS wire parser executed in guest; not full resolver service")
            if args.apple_resolver:
                send(f"print -r -- 'nameserver {fixture.host}' > /data/resolv.conf\n".encode())
                for transport in ("udp", "tcp"):
                    send(f"/bin/resolverctl {transport} {fixture.dns.getsockname()[1]} {fixture.token}.darwin.test; print -r -- APPLE_QUERY_STATUS:$?\n".encode())
                    wait(f"\r\nDARWIN:NET:APPLE_QUERY {transport} {fixture.token}.darwin.test {fixture.host} libresolv-96\r\n".encode())
                    wait(b"\r\nAPPLE_QUERY_STATUS:0\r\n")
                if fixture.errors or sorted(event["type"] for event in fixture.events) != ["dns", "dns", "dns_tcp", "tcp"]:
                    raise RuntimeError("missing independent original Apple UDP/TCP DNS evidence")
                passed.append("original Apple res_ninit file config and res_nquery/res_nsend UDP plus TCP queries independently witnessed")
            if args.apple_libinfo:
                send(f"/bin/resolverctl gai {fixture.dns.getsockname()[1]} {fixture.token}.darwin.test {fixture.tcp.getsockname()[1]} {fixture.token}; print -r -- APPLE_GAI_STATUS:$?\n".encode())
                wait(b"\r\nDARWIN:NET:APPLE_LIBINFO_NUMERIC IPv4 IPv6 errors en0=")
                wait(f"\r\nDARWIN:NET:APPLE_GETADDRINFO {fixture.token}.darwin.test {fixture.host} Libinfo-542.40.3\r\n".encode())
                wait(f"\r\nDARWIN:NET:APPLE_GAI_TCP ECHO={fixture.token}\r\n".encode())
                wait(b"\r\nAPPLE_GAI_STATUS:0\r\n")
                if fixture.errors or sorted(event["type"] for event in fixture.events) != ["dns", "dns", "dns", "dns_tcp", "tcp", "tcp"]:
                    raise RuntimeError("missing independent Apple Libinfo DNS/resolved TCP evidence")
                passed.append("original Apple Libinfo getaddrinfo numeric IPv4/IPv6/error handling, original interface lookup, hostname DNS and TCP via resolved sockaddr")
        if args.verify_persistence:
            send(b'print -r -- READBACK_BEGIN; /bin/cat /data/framed-note; print -r -- READBACK_END; fc -ln -20\n')
            wait(b"\r\nREADBACK_BEGIN\r\n")
            wait(b"\r\nFRAME_SAVED\r\n")
            wait(b"\r\nREADBACK_END\r\n")
            wait(b"print -r -- FRAME_SAVED >> /data/framed-note; exit")
            passed.append("prior-boot persistent file and real zsh saved history loaded")
        send(b'[[ -t 0 && -t 1 && -o monitor ]] && print -r -- TERMINAL_TTY_JOB_OK; print -r -- SIZE_INITIAL:$LINES:$COLUMNS\n')
        wait(b"\r\nTERMINAL_TTY_JOB_OK\r\n")
        wait(b"\r\nSIZE_INITIAL:35:120\r\n")
        passed.append("real PTY, job control enabled and initial host window size")
        send(b"print -r -- ZLE_EIT\x1b[D\x1b[DD\n")
        wait(b"\r\nZLE_EDIT\r\n")
        send(b"print -r -- FRAME_HISTORY_RECALL\n")
        wait(b"\r\nFRAME_HISTORY_RECALL\r\n")
        send(b"\x1b[A\n")
        wait(b"\r\nFRAME_HISTORY_RECALL\r\n")
        passed.append("Apple ZLE editing and up-arrow history")
        send(b"print -r -- JOB_STARTED; /bin/sleep 20\n")
        wait(b"\r\nJOB_STARTED\r\n")
        collect(0.15)
        send(b"\x1a")
        wait(b"suspended")
        send(b"jobs\nfg\n")
        wait(b"continued")
        send(b"\x03")
        wait(b"darwin-zsh#")
        send(b"print -r -- JOB_STATUS:$?\n")
        wait(b"\r\nJOB_STATUS:130\r\n")
        passed.append("Ctrl-Z/jobs/fg and Ctrl-C status 130")
        send(b'TRAPWINCH() { print -r -- "SIZE_CHANGED:$LINES:$COLUMNS"; }; print -r -- RESIZE_ARMED\n')
        wait(b"\r\nRESIZE_ARMED\r\n")
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 47, 132, 0, 0))
        wait(b"SIZE_CHANGED:47:132")
        passed.append("host SIGWINCH -> XNU TIOCSWINSZ -> zsh trap and dimensions")
        send(b'read -r -k 2 pair; print -rn -- "BYTE_ROUNDTRIP:$pair:END"\n')
        collect(0.15)
        send(bytes([128, 255]))
        wait(b"BYTE_ROUNDTRIP:\x80\xff:END")
        passed.append("high-bit bytes from host input through guest read and output")
        send(b'print -r -- FRAME_SAVED >> /data/framed-note; exit\n')
        while process.poll() is None and time.monotonic() < deadline:
            collect()
        if process.poll() is None:
            raise RuntimeError("CLI exceeded bounded trial deadline")
        collect(0)
        if process.returncode:
            raise RuntimeError(f"CLI exit {process.returncode}")
        result = json.loads((args.output_dir / "result.json").read_text())
        terminal = result.get("terminal", {})
        if not (result["guestStopped"] and result["termination"] == "guestStopped" and not result.get("error")
                and terminal.get("handshakeCompleted") and terminal.get("exitStatus") == 0
                and not terminal.get("error") and terminal.get("acknowledgedSizes") == [[35, 120], [47, 132]]):
            raise RuntimeError("missing successful guest/terminal exit and resize acknowledgements")
        output = (args.output_dir / "terminal-output.bin").read_bytes()
        if b"BYTE_ROUNDTRIP:\x80\xff:END" not in output:
            raise RuntimeError("binary output capture lost high bits")
        if args.shared_gpu:
            gpu = result.get("gpu", {})
            if not (gpu.get("enabled") and gpu.get("deviceName") and not gpu.get("error")
                    and gpu.get("submitted") == 3 and gpu.get("completed") == 2 and gpu.get("rejected") == 1):
                raise RuntimeError("missing independent host Metal/session evidence")
            operations = gpu.get("operations", [])
            if len(operations) != 3 or operations[-1]["status"] != 1:
                raise RuntimeError("missing bounded host request observations")
            for index, seed in enumerate(gpu_seeds):
                a = [(seed + i) * 0.5 for i in range(16)]
                b = [-i * 0.25 for i in range(16)]
                op = operations[index]
                if not (op["id"] == index + 1 and op["status"] == 0 and op["left"] == a and op["right"] == b
                        and op["result"] == [x + y for x, y in zip(a, b)]):
                    raise RuntimeError("host Metal operands/results do not match fresh guest seed")
            passed.append("independent host Metal execution/returned operands match both fresh guest requests; session teardown")
        try:
            restored = termios.tcgetattr(slave)
        except termios.error as error:
            if error.args[0] != errno.ENOTTY:
                raise
            # macOS revokes a controlling PTY after its session leader exits.
            # Restoration itself is covered by DarwinHostTerminalTests.
            restoration = "not observable after macOS controlling PTY revocation; native restoration check applies"
        else:
            restored[3] &= ~termios.PENDIN
            original[3] &= ~termios.PENDIN
            if restored != original:
                raise RuntimeError("host terminal attributes not restored")
            restoration = "attributes match original"
        passed.append("guest history-save exit/unmount/poweroff")
    except Exception as error:
        failure = str(error)
        if process.poll() is None:
            # Prefer normal guest unmount over host-stop when the shell is usable.
            send(b"\x03exit\n")
            cleanup_deadline = time.monotonic() + 5
            while process.poll() is None and time.monotonic() < cleanup_deadline:
                collect()
        if process.poll() is None:
            process.terminate()
            cleanup_deadline = time.monotonic() + 20
            while process.poll() is None and time.monotonic() < cleanup_deadline:
                collect()
            if process.poll() is None:
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
                      "host_restoration_observation": restoration,
                      "cli_sha256": hashlib.sha256(args.cli.read_bytes()).hexdigest(),
                      "gpu_seeds": gpu_seeds,
                      "network_fixture": {"events": fixture.events, "errors": fixture.errors, "host_route": fixture.route} if fixture else None,
                      "scope": "one real VM PTY trial" + (" + guest en0/DHCP/DNS/TCP" if args.network else "")
                               + (" + typed shared host Metal requests" if args.shared_gpu else "; no GPU evidence") + "; no Pi evidence"}
            (args.output_dir / "terminal-trial.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": passed, "error": failure, "output": str(args.output_dir)}))
    if failure:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
