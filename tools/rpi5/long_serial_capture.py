#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Receive-only, bounded serial capture that runs on the probe host."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import sys
import termios
import time
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--seconds", type=int, required=True)
    args = parser.parse_args()
    linux_probe = (sys.platform.startswith("linux") and
                   args.device.startswith("/dev/serial/by-id/usb-Raspberry_Pi_Debug_Probe_"))
    mac_probe = (sys.platform == "darwin" and
                 re.fullmatch(r"/dev/cu\.usbmodem[A-Za-z0-9_-]+", args.device))
    if not (linux_probe or mac_probe):
        parser.error("Raspberry Pi Debug Probe serial path required for this host")
    if not 1 <= args.seconds <= 9 * 60 * 60:
        parser.error("duration must be 1–32400 seconds")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    raw_path = args.output_dir / "serial.bin"
    state_path = args.output_dir / "state.json"
    started = utc_now()
    count = 0
    digest = hashlib.sha256()
    fd = None
    old = None
    status = "failed"
    error = None
    try:
        fd = os.open(args.device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        old = termios.tcgetattr(fd)
        config = termios.tcgetattr(fd)
        config[0] = config[1] = config[3] = 0
        config[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        config[4] = config[5] = termios.B115200
        config[6][termios.VMIN] = 0
        config[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, config)
        with raw_path.open("xb", buffering=0) as output:
            print("CAPTURE_READY 115200 8N1 RX_ONLY", flush=True)
            end = time.monotonic() + args.seconds
            next_sync = time.monotonic() + 60
            while time.monotonic() < end:
                wait = min(1.0, max(0.0, end - time.monotonic()))
                ready, _, _ = select.select([fd], [], [], wait)
                if ready:
                    data = os.read(fd, 4096)
                    if not data:
                        raise RuntimeError("serial disconnected")
                    output.write(data)
                    digest.update(data)
                    count += len(data)
                if time.monotonic() >= next_sync:
                    os.fsync(output.fileno())
                    next_sync = time.monotonic() + 60
            os.fsync(output.fileno())
        status = "finished"
    except Exception as exc:
        error = str(exc)
        print(f"CAPTURE_ERROR {error}", file=sys.stderr, flush=True)
    finally:
        if fd is not None:
            if old is not None:
                termios.tcsetattr(fd, termios.TCSANOW, old)
            os.close(fd)
        state = {
            "started_utc": started,
            "ended_utc": utc_now(),
            "device": args.device,
            "baud": 115200,
            "format": "8N1",
            "requested_seconds": args.seconds,
            "status": status,
            "error": error,
            "bytes": count,
            "sha256": digest.hexdigest(),
            "transmitted_bytes": 0,
        }
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        print(json.dumps(state), flush=True)
    return 0 if status == "finished" else 1


if __name__ == "__main__":
    raise SystemExit(main())
