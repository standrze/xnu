#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bounded, quiet SSH wait for the exact Pi's SSD Linux fallback.

No serial access, SD access, sudo, reboot or power changes. A successful SSH
connection with a different root/hostname is an error, never permission to
continue. Keep this process handle: a state file alone is not a live wait.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time

HOST = 'sandrzej@192.168.4.23'
COMMAND = 'hostname; findmnt -no SOURCE,FSTYPE,UUID /; cat /proc/sys/kernel/random/boot_id'
ROOT = '/dev/nvme0n1p2 ext4 04570742-280b-43cb-9564-73d454243b1c'


def identity(output):
    lines = output.strip().splitlines()
    if (len(lines) != 3 or lines[0] != 'kamidana' or ' '.join(lines[1].split()) != ROOT
            or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', lines[2])):
        raise ValueError('SSH answered, but not the exact verified SSD Linux identity')
    return dict(hostname=lines[0], root=ROOT, boot_id=lines[2])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--seconds', type=int, default=3600)
    parser.add_argument('--interval', type=int, default=60)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 5400 or not 15 <= args.interval <= 60:
        parser.error('Bound wait to 1..5400 seconds and polling to 15..60 seconds')
    args.output.mkdir(parents=True, exist_ok=False)
    state = dict(status='waiting',host=HOST,started_utc=datetime.now(timezone.utc).isoformat(),
                 requested_seconds=args.seconds, interval_seconds=args.interval, attempts=0,
                 serial_accesses=0,sd_accesses=0,remote_write_operations=0)
    (args.output/'state.json').write_text(json.dumps(state,indent=2)+'\n')
    print('WAIT_FOR_VERIFIED_NVME_LINUX_STARTED SSH_READ_ONLY',flush=True)
    end = time.monotonic() + args.seconds
    try:
        while time.monotonic() < end:
            state['attempts'] += 1
            try:
                result = subprocess.run(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
                                         '-o','ConnectTimeout=3',HOST,COMMAND],text=True,
                                        capture_output=True,timeout=8)
            except subprocess.TimeoutExpired:
                result = None
            if result is not None and result.returncode == 0:
                state.update(status='ready',identity=identity(result.stdout))
                break
            if result is not None and result.returncode != 255:
                raise RuntimeError('Remote diagnostic command failed; inspect before continuing')
            time.sleep(min(args.interval,max(0,end-time.monotonic())))
        else:
            state['status'] = 'timeout'
    except (Exception,KeyboardInterrupt) as error:
        state.update(status='failed',error=str(error) or 'interrupted')
    finally:
        state['ended_utc'] = datetime.now(timezone.utc).isoformat()
        (args.output/'state.json').write_text(json.dumps(state,indent=2)+'\n')
        print(json.dumps(state),flush=True)
    return 0 if state['status']=='ready' else 1


if __name__=='__main__':
    raise SystemExit(main())
