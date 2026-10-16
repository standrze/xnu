#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One exact boot, original Apple read-only networking probes, live recovery.

No UART TX until ordered exact image/root/copy markers and installed receipt.
No interface/route configuration, PCIe access, retries, reboot or soak.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import termios
import time

try:
    from . import check_apple_network_package as package_check
    from . import stage_apple_network_trial as staging
    from . import serial_zsh_trial as t
except ImportError:
    import check_apple_network_package as package_check
    import stage_apple_network_trial as staging
    import serial_zsh_trial as t

IMAGE_BYTES = 19334848
ROOT_MARKER = b'RPI5XNU:RAMROOT:MOUNT NODES=27 BYTES=1867776 READONLY'
COPY = b'RPI5XNU:BL33:RAMDISK_MATERIALIZED PA=0000000008198000 BYTES=00000000001c8000 VERIFIED'
KERNEL = b'RPI5XNU:BL33:KERNEL_MATERIALIZED BYTES=000000000118c000 FULL_ENVELOPE_VERIFIED NO_BOOT_ARGS_WRITTEN NO_TRANSFER'
COMMIT = b'RPI5XNU:BL33:BOOT_DATA_COMMITTED TRANSFER_NEXT'
IFCONFIG = "zsh -f -c '/sbin/ifconfig -l; print -r -- NET_IFCONFIG_STATUS:$?'"
ROUTE = "zsh -f -c '/sbin/route -n; print -r -- NET_ROUTE_STATUS:$?'"
USAGE = b'usage: route [-dnqtv] command [[modifiers] args]'
CHECKS = ['fresh_exact_apple_network_root_boot','recovery_nonce',
          'preserved_original_zsh_script','apple_ifconfig_names_and_zero_exit',
          'apple_route_socket_usage_and_expected_exit','live_recovery']


def boot_ready(raw):
    data = t.normalized(raw)
    if not t.boot_ready(raw,IMAGE_BYTES,ROOT_MARKER): return False
    if b'FAILED_STOP' in data or b'RPI5XNU:RAMROOT:REJECT' in data:
        raise RuntimeError('Payload/root admission failed')
    ordered = (b'Boot mode: SD (01)',b'Read probe.bin bytes 19334848 hnd ',t.ENTRY,
               t.TERMINAL_LOADER,COPY,KERNEL,t.package_check.TOPOLOGY_PASS,t.TRANSFER,
               COMMIT,ROOT_MARKER,t.READY)
    if any(data.count(marker) != 1 for marker in ordered[:-1]):
        raise RuntimeError('Missing or duplicate exact payload markers')
    positions = [data.index(marker) for marker in ordered]
    if positions != sorted(positions): raise RuntimeError('Payload markers out of order')
    return True


def installation(directory,report):
    if not directory.resolve().is_relative_to(staging.ROOT/'build/rpi5'):
        raise ValueError('Project installation receipt required')
    plan = json.loads((directory/'plan.json').read_text())
    result = json.loads((directory/'result.json').read_text())
    staging.validate_result(result,plan)
    if plan['preflight'] != report or result['image_sha256'] != staging.NEW_SHA:
        raise ValueError('Installed receipt differs from exact package')
    return dict(directory=str(directory.resolve()),
                plan_sha256=hashlib.sha256((directory/'plan.json').read_bytes()).hexdigest(),
                result_sha256=hashlib.sha256((directory/'result.json').read_bytes()).hexdigest())


def interfaces(raw):
    lines = t.normalized(raw).splitlines()
    if lines.count(b'NET_IFCONFIG_STATUS:0') != 1:
        raise ValueError('ifconfig did not exit zero exactly once')
    candidates = [line.split() for line in lines
                  if t.re.fullmatch(rb'[a-z][a-z0-9]*[0-9](?: [a-z][a-z0-9]*[0-9])* *',line)]
    if len(candidates) != 1 or b'lo0' not in candidates[0]:
        raise ValueError('No unique interface-name list containing lo0')
    return [name.decode('ascii') for name in candidates[0]]


def trial(fd,output,seconds,state):
    deadline,data = time.monotonic()+seconds,b''
    while time.monotonic() < deadline:
        data += t.shell.receive(fd,output,deadline)
        if boot_ready(data): break
    else: raise TimeoutError('No exact fresh Apple networking root; zero TX')
    state['checks'].append(CHECKS[0])
    run_commands(fd,output,state)


def run_commands(fd,output,state):
    """Fixed read-only commands, after the caller's separate admission check."""
    nonce = 'N'+secrets.token_hex(8); state['nonce'] = nonce
    t.exchange(fd,output,'echo '+nonce,[nonce.encode()],t.shell.PROMPT,state)
    state['checks'].append(CHECKS[1])
    t.exchange(fd,output,'zsh -f /etc/zsh-smoke.zsh',t.SMOKE_LINES,t.shell.PROMPT,state)
    t.exchange(fd,output,'echo $?',[b'0'],t.shell.PROMPT,state)
    state['checks'].append(CHECKS[2])
    response = t.exchange(fd,output,IFCONFIG,[b'NET_IFCONFIG_STATUS:0'],t.shell.PROMPT,state)
    state['interface_names'] = interfaces(response)
    state['checks'].append(CHECKS[3])
    t.exchange(fd,output,ROUTE,[USAGE,b'NET_ROUTE_STATUS:64'],t.shell.PROMPT,state)
    state['checks'].append(CHECKS[4])
    t.exchange(fd,output,'echo RECOVERED_'+nonce,[('RECOVERED_'+nonce).encode()],t.shell.PROMPT,state)
    state['checks'].append(CHECKS[5])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device'); parser.add_argument('output',type=Path)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--installation',type=Path,required=True)
    parser.add_argument('--boot-wait-seconds',type=int,default=180)
    args = parser.parse_args()
    if not t.valid_probe_device(args.device) or not 30 <= args.boot_wait_seconds <= 3600:
        parser.error('Debug Probe callout and bounded boot wait required')
    report = package_check.inspect(args.package)
    if report['image_sha256'] != staging.NEW_SHA or report['image_bytes'] != IMAGE_BYTES:
        raise ValueError('Exact Apple network image required')
    installed = installation(args.installation,report)
    args.output.mkdir(parents=True,exist_ok=False)
    state = dict(status='failed',started_utc=t.utc_now(),device=args.device,baud=115200,
                 checks=[],transmitted_bytes=0,preflight=report,installation=installed,
                 networking=False,nic_ready=False,ssh=False,durability=False,
                 scope='Original Apple command enumeration/routing-socket usage only, not packet traffic')
    fd,original = None,None
    try:
        fd = os.open(args.device,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
        fcntl.ioctl(fd,termios.TIOCEXCL)
        original = termios.tcgetattr(fd); config = termios.tcgetattr(fd)
        config[0] = config[1] = config[3] = 0
        config[2] = termios.CS8|termios.CREAD|termios.CLOCAL
        config[4] = config[5] = termios.B115200
        config[6][termios.VMIN] = config[6][termios.VTIME] = 0
        termios.tcsetattr(fd,termios.TCSANOW,config); termios.tcflush(fd,termios.TCIFLUSH)
        with (args.output/'serial.bin').open('xb',buffering=0) as output:
            if installation(args.installation,report) != installed:
                raise ValueError('Installation evidence changed before arming')
            print('APPLE_NETWORK_TRIAL_ARMED ZERO_TX_UNTIL_EXACT_FRESH_BOOT',flush=True)
            trial(fd,output,args.boot_wait_seconds,state)
        state['status'] = 'passed'
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
        print(json.dumps(dict(status=state['status'],checks=state['checks'],
                              error=state.get('error'),bytes=state['bytes'])),flush=True)
    return 0 if state['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
