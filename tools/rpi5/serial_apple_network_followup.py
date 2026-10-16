#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Separate same-boot diagnosis after zero-TX mount-line corruption.

Never passes/waives the strict trial. Requires recent exact loader/copy/commit
evidence and current installed receipt; no reboot, retry or media operation.
"""
import argparse
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import termios
import time

try:
    from . import serial_apple_network_trial as trial
except ImportError:
    import serial_apple_network_trial as trial

t = trial.t
ADMISSION = 'recent_zero_tx_exact_loader_copy_receipt_not_strict_mount_acceptance'


def payload_boot(raw):
    data = t.normalized(raw)
    # Existing wrong-root, wrong-extent, duplicate-boot and fault rejection
    # stays in force. Only the absent/corrupted mount line is unresolved.
    if t.boot_ready(raw,trial.IMAGE_BYTES,trial.ROOT_MARKER):
        raise ValueError('Strict mount was complete; this diagnostic is inapplicable')
    ordered = (b'Boot mode: SD (01)',b'Read probe.bin bytes 19334848 hnd ',t.ENTRY,
               t.TERMINAL_LOADER,trial.COPY,trial.KERNEL,t.package_check.TOPOLOGY_PASS,
               t.TRANSFER,trial.COMMIT,t.READY)
    if any(data.count(marker) != 1 for marker in ordered[:-1]) or t.READY not in data:
        raise ValueError('Missing/repeated exact fresh loader/copy evidence')
    positions = [data.index(marker) for marker in ordered]
    if positions != sorted(positions) or not t.shell.PROMPT.search(data[positions[-1]:]):
        raise ValueError('Loader/copy/transfer/recovery order differs')
    if b'FAILED_STOP' in data or b'RPI5XNU:RAMROOT:REJECT' in data:
        raise ValueError('Payload/root validation failed')
    return True


def evidence(directory,device,report,installed,require_recent=True):
    state_path = directory/'state.json'; raw = (directory/'serial.bin').read_bytes()
    state = json.loads(state_path.read_text())
    if (state.get('status') != 'failed' or state.get('checks') != [] or
            state.get('transmitted_bytes') != 0 or
            state.get('error') != 'No exact fresh Apple networking root; zero TX' or
            state.get('device') != device or state.get('baud') != 115200 or
            state.get('bytes') != len(raw) or state.get('serial_sha256') != hashlib.sha256(raw).hexdigest() or
            state.get('preflight') != report or state.get('installation') != installed or
            'serial_restore_error' in state):
        raise ValueError('Exact zero-TX timeout, fresh preflight and installation receipt required')
    start,end = [datetime.fromisoformat(state[key]) for key in ('started_utc','ended_utc')]
    if start.tzinfo is None or end.tzinfo is None or not 0 <= (end-start).total_seconds() <= 3720:
        raise ValueError('Invalid source times')
    if require_recent and not 0 <= (datetime.now(timezone.utc)-end).total_seconds() <= 900:
        raise ValueError('Same-boot evidence expired')
    payload_boot(raw)
    return dict(directory=str(directory.resolve()),state_sha256=hashlib.sha256(state_path.read_bytes()).hexdigest(),
                serial_sha256=state['serial_sha256'],installation=installed,
                strict_mounted_root_trial_passed=False,mounted_root_node_count_observed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device'); parser.add_argument('output',type=Path)
    parser.add_argument('--zero-tx-trial',type=Path,required=True)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--installation',type=Path,required=True)
    args = parser.parse_args()
    if not t.valid_probe_device(args.device): parser.error('Debug Probe callout required')
    report = trial.package_check.inspect(args.package)
    if report['image_sha256'] != trial.staging.NEW_SHA or report['image_bytes'] != trial.IMAGE_BYTES:
        raise ValueError('Exact installed diagnostic image required')
    installed = trial.installation(args.installation,report)
    source = evidence(args.zero_tx_trial,args.device,report,installed)
    args.output.mkdir(parents=True,exist_ok=False)
    state = dict(status='failed',started_utc=t.utc_now(),device=args.device,baud=115200,
                 checks=[ADMISSION],transmitted_bytes=0,preflight=report,installation=installed,source=source,
                 strict_mounted_root_trial_passed=False,mounted_root_node_count_observed=False,
                 networking=False,nic_ready=False,ssh=False,durability=False,
                 scope='Separate same-boot original Apple command diagnosis; strict mount-line trial remains failed')
    fd,original = None,None
    try:
        fd = os.open(args.device,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK); fcntl.ioctl(fd,termios.TIOCEXCL)
        original = termios.tcgetattr(fd); config = termios.tcgetattr(fd)
        config[0] = config[1] = config[3] = 0; config[2] = termios.CS8|termios.CREAD|termios.CLOCAL
        config[4] = config[5] = termios.B115200; config[6][termios.VMIN] = config[6][termios.VTIME] = 0
        termios.tcsetattr(fd,termios.TCSANOW,config)
        with (args.output/'serial.bin').open('xb',buffering=0) as output:
            # Retain queued bytes so a intervening reboot/fault cannot be hidden.
            deadline,queued = time.monotonic()+2,b''
            while time.monotonic() < deadline:
                queued += t.shell.receive(fd,output,deadline)
                if (len(queued)>65536 or t.ENTRY in queued or t.TERMINAL_LOADER in queued or
                        b'Boot mode:' in queued or any(marker in queued for marker in t.FORBIDDEN)):
                    raise RuntimeError('Reboot/fault/oversized queue before diagnostic input')
            if evidence(args.zero_tx_trial,args.device,report,installed) != source or trial.installation(args.installation,report) != installed:
                raise ValueError('Source/installation changed before first input')
            print('SAME_BOOT_APPLE_DIAGNOSIS_NOT_STRICT_TRIAL_ACCEPTANCE',flush=True)
            trial.run_commands(fd,output,state)
        state['status'] = 'diagnostic_completed'
    except (Exception,KeyboardInterrupt) as error: state['error'] = str(error) or 'interrupted'
    finally:
        if fd is not None:
            try:
                if original is not None: termios.tcsetattr(fd,termios.TCSANOW,original)
            except OSError as error:
                state['serial_restore_error'] = str(error); state['status'] = 'failed'
            finally: os.close(fd)
        raw = args.output/'serial.bin'
        state.update(ended_utc=t.utc_now(),bytes=raw.stat().st_size if raw.exists() else 0,
                     serial_sha256=hashlib.sha256(raw.read_bytes()).hexdigest() if raw.exists() else None)
        (args.output/'state.json').write_text(json.dumps(state,indent=2)+'\n')
        print(json.dumps(dict(status=state['status'],checks=state['checks'],error=state.get('error'))),flush=True)
    return 0 if state['status'] == 'diagnostic_completed' else 1


if __name__ == '__main__': raise SystemExit(main())
