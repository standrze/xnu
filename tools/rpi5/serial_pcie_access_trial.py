#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Receive-only continuous read-only PCIe access trial capture, no serial TX or reboot."""
import argparse
from datetime import datetime, timezone
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_pcie_access_trial as staging
import pcie_access_serial_core as core


def utc(): return datetime.now(timezone.utc).isoformat()


def installation(directory):
    directory = directory.resolve()
    if directory.parent != staging.ROOT/'build/rpi5': raise ValueError('Local installation receipt required')
    plan = json.loads((directory/'plan.json').read_text()); result = json.loads((directory/'result.json').read_text())
    staging.validate_result(result, plan)
    report = staging.package.inspect(staging.PACKAGE)
    if plan['profile'] != 'pcie-access-trial' or plan['preflight'] != report or result['image_sha256'] != staging.IMAGE_SHA:
        raise ValueError('Exact installed read-only access image required')
    return dict(directory=str(directory), plan_sha256=staging.sha(directory/'plan.json'),
        result_sha256=staging.sha(directory/'result.json'), preflight=report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device'); parser.add_argument('output', type=Path)
    parser.add_argument('--installation', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=120)
    args = parser.parse_args(argv)
    if not re.fullmatch(r'/dev/cu\.usbmodem[A-Za-z0-9_-]+', args.device) or not 60 <= args.seconds <= 600:
        raise ValueError('Explicit Mac Debug Probe callout and bounded capture required')
    installed = installation(args.installation)
    sources = {str(Path(__file__).resolve()):staging.sha(Path(__file__)), str(Path(core.__file__)):staging.sha(Path(core.__file__))}
    sources.update(staging.source_pins())
    def revalidate():
        if installation(args.installation) != installed or any(staging.sha(Path(p)) != pin for p,pin in sources.items()):
            raise ValueError('Image/receipt/recorder source changed')
    output = args.output.resolve()
    if output.parent != staging.ROOT/'build/rpi5': raise ValueError('Separate local evidence directory required')
    output.mkdir(exist_ok=False)
    state = dict(status='failed', started_utc=utc(), device=args.device, baud=115200, transmitted_bytes=0,
        installation=installed, source_sha256=sources, continuous_capture=False, reset_return_proven=False)
    fd, original = None, None
    try:
        fd = os.open(args.device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK); fcntl.ioctl(fd, termios.TIOCEXCL)
        original = termios.tcgetattr(fd); config = termios.tcgetattr(fd)
        config[0] = config[1] = config[3] = 0; config[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        config[4] = config[5] = termios.B115200; config[6][termios.VMIN] = config[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, config); termios.tcflush(fd, termios.TCIFLUSH)
        with (output/'serial.bin').open('xb', buffering=0) as raw, (output/'receive-events.jsonl').open('x') as events:
            revalidate(); start = time.monotonic(); deadline = start+args.seconds; total = 0
            state.update(armed_utc=utc(), armed_monotonic=start)
            (output/'armed.json').write_text(json.dumps(state, indent=2)+'\n')
            print('PCIE_ACCESS_CAPTURE_ARMED ZERO_SERIAL_TX IMAGE_SHA='+installed['preflight']['image_sha256'], flush=True)
            while time.monotonic() < deadline:
                ready, _, _ = select.select([fd], [], [], min(1, max(0, deadline-time.monotonic())))
                if not ready: continue
                data = os.read(fd, 4096)
                if not data: raise RuntimeError('Serial disconnected; continuity not proven')
                if total+len(data) > 4*1024*1024: raise ValueError('Capture bound exceeded')
                raw.write(data); os.fsync(raw.fileno())
                events.write(json.dumps(dict(offset=total, bytes=len(data), monotonic=time.monotonic(), utc=utc()))+'\n')
                events.flush(); os.fsync(events.fileno()); total += len(data)
            revalidate(); state.update(status='captured', continuous_capture=True)
    except (Exception, KeyboardInterrupt) as error: state['error'] = str(error) or 'interrupted'
    finally:
        if fd is not None:
            try:
                if original is not None: termios.tcsetattr(fd, termios.TCSANOW, original)
            except OSError as error: state.update(status='failed', continuous_capture=False, restore_error=str(error))
            finally: os.close(fd)
        raw = output/'serial.bin'; data = raw.read_bytes() if raw.exists() else b''
        state.update(ended_utc=utc(), bytes=len(data), serial_sha256=hashlib.sha256(data).hexdigest(), access_inventory=core.inventory(data))
        try: state['diagnostic'] = core.inspect(data, installed['preflight']['image_sha256'])
        except ValueError as error: state['diagnostic_error'] = str(error)
        (output/'state.json').write_text(json.dumps(state, indent=2)+'\n')
        print(json.dumps({k:state.get(k) for k in ('status', 'bytes', 'continuous_capture', 'diagnostic', 'diagnostic_error', 'error')}), flush=True)
    return 0 if state['status'] == 'captured' else 1


if __name__ == '__main__': raise SystemExit(main())
