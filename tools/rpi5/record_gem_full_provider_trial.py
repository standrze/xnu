#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bounded receive-only recorder for the full-provider board trial."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import struct
import subprocess
import termios
import time


def utc():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device")
    parser.add_argument("output", type=Path)
    parser.add_argument("--seconds", type=int, default=240)
    args = parser.parse_args()
    if not args.device.startswith("/dev/cu.usbmodem") or not 60 <= args.seconds <= 600:
        raise ValueError("explicit Debug Probe callout and bounded duration required")
    output = args.output.resolve()
    output.mkdir(exist_ok=False)
    existing = subprocess.run(["lsof", "-t", "--", args.device], capture_output=True, text=True)
    if existing.returncode != 1 or existing.stdout.strip() or existing.stderr.strip():
        raise ValueError("serial port is already open")
    state = {"status": "failed", "started_utc": utc(), "device": args.device,
        "baud": 115200, "transmitted_bytes": 0, "pid": os.getpid()}
    fd = None; original = None; received = b""
    try:
        fd = os.open(args.device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        original = termios.tcgetattr(fd); config = termios.tcgetattr(fd)
        config[0] = config[1] = config[3] = 0
        config[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        config[4] = config[5] = termios.B115200
        config[6][termios.VMIN] = config[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, config)
        required = termios.TIOCM_DTR | termios.TIOCM_RTS
        fcntl.ioctl(fd, termios.TIOCMBIS, struct.pack("=I", required))
        actual = struct.unpack("=I", fcntl.ioctl(fd, termios.TIOCMGET, struct.pack("=I", 0)))[0]
        if actual & required != required:
            raise ValueError("Debug Probe DTR/RTS assertion failed")
        termios.tcflush(fd, termios.TCIFLUSH)
        state["armed_utc"] = utc()
        (output / "armed.json").write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        print("FULL_PROVIDER_CAPTURE_ARMED ZERO_SERIAL_TX", flush=True)
        deadline = time.monotonic() + args.seconds
        with (output / "serial.bin").open("xb", buffering=0) as raw:
            while time.monotonic() < deadline:
                ready, _, _ = select.select([fd], [], [], 1)
                if not ready:
                    continue
                data = os.read(fd, 4096)
                if not data:
                    raise RuntimeError("serial disconnected")
                if len(received) + len(data) > 4 * 1024 * 1024:
                    raise ValueError("serial capture bound exceeded")
                raw.write(data); os.fsync(raw.fileno()); received += data
                end = received.find(b"RPI5XNU:PCIEID:END ")
                if end >= 0 and received.find(b"BOOTSYS", end) >= 0 and \
                        received.find(b"Boot mode: NVME", end) >= 0:
                    state["status"] = "captured"; break
            if state["status"] != "captured":
                raise TimeoutError("complete XNU-to-NVMe receive sequence not observed")
    except (Exception, KeyboardInterrupt) as error:
        state["error"] = str(error) or "interrupted"
    finally:
        if fd is not None:
            try:
                if original is not None:
                    termios.tcsetattr(fd, termios.TCSANOW, original)
            finally:
                os.close(fd)
        state.update(ended_utc=utc(), bytes=len(received),
            serial_sha256=hashlib.sha256(received).hexdigest(),
            full_provider_marker_count=received.count(b"RPI5XNU:FULL_PROVIDER:ENTRY"),
            end_count=received.count(b"RPI5XNU:PCIEID:END "),
            normal_nvme_return=(received.find(b"BOOTSYS", received.find(b"RPI5XNU:PCIEID:END ")) >= 0 and
                received.find(b"Boot mode: NVME", received.find(b"RPI5XNU:PCIEID:END ")) >= 0))
        (output / "state.json").write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        print(json.dumps(state, sort_keys=True), flush=True)
    return 0 if state["status"] == "captured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
