#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bounded zero-transmit recorder for one RP1 USB0/xHCI capability boot."""
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

from tools.rpi5 import check_usb_xhci_caps_trial as package_check
from tools.rpi5 import parse_usb_xhci_caps_trial as evidence

MARKER_PREFIX = "RPI5XNU:USB_XHCI_CAPS:ENTRY TAG="
ARMED_MESSAGE = "USB_XHCI_CAPS_CAPTURE_ARMED ZERO_SERIAL_TX"

def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device")
    parser.add_argument("package", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--seconds", type=int, default=240)
    args = parser.parse_args()
    if not args.device.startswith("/dev/cu.usbmodem") or not 60 <= args.seconds <= 600:
        raise ValueError("explicit Debug Probe callout and bounded duration required")
    package = args.package.resolve()
    checked = package_check.check(package)
    manifest_path = package / "manifest.json"
    if not checked.get("accepted") or sha(manifest_path) != args.manifest_sha256:
        raise ValueError("exact offline-qualified USB capability package required")
    manifest = json.loads(manifest_path.read_text())
    marker = manifest.get("trial_marker", "")
    if not marker.startswith(MARKER_PREFIX):
        raise ValueError("exact USB trial marker absent")

    output = args.output.resolve()
    output.mkdir(exist_ok=False)
    existing = subprocess.run(["lsof", "-t", "--", args.device], capture_output=True, text=True)
    if existing.returncode != 1 or existing.stdout.strip() or existing.stderr.strip():
        raise ValueError("serial port is already open")
    state = {
        "status": "failed", "started_utc": utc(), "device": args.device,
        "baud": 115200, "transmitted_bytes": 0, "pid": os.getpid(),
        "package": str(package), "manifest_sha256": args.manifest_sha256,
        "image_sha256": manifest["image_sha256"], "trial_marker": marker,
    }
    fd = None
    original = None
    received = b""
    parsed = None
    try:
        fd = os.open(args.device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        original = termios.tcgetattr(fd)
        config = termios.tcgetattr(fd)
        config[0] = config[1] = config[3] = 0
        config[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        config[4] = config[5] = termios.B115200
        config[6][termios.VMIN] = config[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, config)
        required = termios.TIOCM_DTR | termios.TIOCM_RTS
        fcntl.ioctl(fd, termios.TIOCMBIS, struct.pack("=I", required))
        actual = struct.unpack("=I", fcntl.ioctl(
            fd, termios.TIOCMGET, struct.pack("=I", 0)))[0]
        if actual & required != required:
            raise ValueError("Debug Probe DTR/RTS assertion failed")
        termios.tcflush(fd, termios.TCIFLUSH)
        state["armed_utc"] = utc()
        (output / "armed.json").write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        print(ARMED_MESSAGE, flush=True)
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
                raw.write(data)
                os.fsync(raw.fileno())
                received += data
                end = received.find(b"RPI5XNU:PCIEID:END ")
                if end >= 0 and received.find(b"BOOTSYS", end) >= 0 and \
                        received.find(b"Boot mode: NVME", end) >= 0:
                    parsed = evidence.parse(received.decode(errors="replace"), marker)
                    (output / "parsed.json").write_text(
                        json.dumps(parsed, indent=2, sort_keys=True) + "\n")
                    state["status"] = "captured"
                    break
            if state["status"] != "captured":
                raise TimeoutError("complete parsed XNU-to-NVMe receive sequence not observed")
    except (Exception, KeyboardInterrupt) as error:
        state["error"] = str(error) or "interrupted"
    finally:
        if fd is not None:
            try:
                if original is not None:
                    termios.tcsetattr(fd, termios.TCSANOW, original)
            finally:
                os.close(fd)
        end_offset = received.find(b"RPI5XNU:PCIEID:END ")
        state.update(
            ended_utc=utc(), bytes=len(received),
            serial_sha256=hashlib.sha256(received).hexdigest(),
            trial_marker_count=received.count(marker.encode()),
            usb_state_count=received.count(b"RPI5XNU:USB_XHCI_CAPS:STATE "),
            usb_decode_count=received.count(b"RPI5XNU:USB_XHCI_CAPS:DECODE "),
            usb_lifecycle_count=received.count(b"RPI5XNU:USB_XHCI_LIFECYCLE:STATE "),
            end_count=received.count(b"RPI5XNU:PCIEID:END "),
            parser_passed=parsed is not None,
            normal_nvme_return=(end_offset >= 0 and
                received.find(b"BOOTSYS", end_offset) >= 0 and
                received.find(b"Boot mode: NVME", end_offset) >= 0),
        )
        (output / "state.json").write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        print(json.dumps(state, sort_keys=True), flush=True)
    return 0 if state["status"] == "captured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
