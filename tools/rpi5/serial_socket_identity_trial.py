#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One pinned fresh boot: read-only root identity, then Unix/loopback payloads.

No sockets before full mounted-root replay; no old-image input, retries,
interface changes, persistent writes, reboot or soak. Installation is separate.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import termios
import time

try:
    from . import check_socket_identity_package as package
    from . import stage_socket_identity_trial as staging
    from . import socket_identity_trial_core as core
    from . import socket_identity_evidence as identity
except ImportError:
    import check_socket_identity_package as package
    import stage_socket_identity_trial as staging
    import socket_identity_trial_core as core
    import socket_identity_evidence as identity

t=core.t


def installation(directory,report):
    if not directory.resolve().is_relative_to(staging.ROOT/'build/rpi5'):
        raise ValueError('Project installation receipt required')
    plan=json.loads((directory/'plan.json').read_text()); result=json.loads((directory/'result.json').read_text())
    staging.validate_result(result,plan)
    if plan['preflight']!=report or result['image_sha256']!=staging.NEW_SHA:
        raise ValueError('Installed package differs from exact preflight')
    return dict(directory=str(directory.resolve()),plan_sha256=hashlib.sha256((directory/'plan.json').read_bytes()).hexdigest(),
                result_sha256=hashlib.sha256((directory/'result.json').read_bytes()).hexdigest())


def source_pins():
    return {str(Path(module.__file__).resolve()):hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
            for module in (core,identity,t,t.shell,package,staging)} | {
            str(Path(__file__).resolve()):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def trial(fd,output,seconds,state,revalidate):
    deadline,data=time.monotonic()+seconds,b''
    while time.monotonic()<deadline:
        data+=t.shell.receive(fd,output,deadline)
        if core.identity_query_ready(data): break
    else: raise TimeoutError('No exact fresh identity/socket payload boot; zero TX')
    revalidate()
    state['checks'].append('fresh_exact_payload_allows_identity_query_only')
    receipt=json.loads(package.INIT.with_name('manifest.json').read_text())
    core.commands(fd,output,state,receipt)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device'); parser.add_argument('output',type=Path)
    parser.add_argument('--package',type=Path,required=True); parser.add_argument('--installation',type=Path,required=True)
    parser.add_argument('--boot-wait-seconds',type=int,default=180)
    args=parser.parse_args()
    if not t.valid_probe_device(args.device) or not 30<=args.boot_wait_seconds<=3600:
        parser.error('Debug Probe callout and bounded boot wait required')
    report=package.inspect(args.package)
    if report['image_sha256']!=staging.NEW_SHA or report['image_bytes']!=core.IMAGE_BYTES:
        raise ValueError('Exact v2 identity/socket image required')
    installed=installation(args.installation,report); pins=source_pins()
    def revalidate():
        if package.inspect(args.package)!=report or installation(args.installation,report)!=installed or source_pins()!=pins:
            raise ValueError('Package, installation or recorder source changed before first TX')
    args.output.mkdir(parents=True,exist_ok=False)
    state=dict(status='failed',started_utc=t.utc_now(),device=args.device,baud=115200,
        checks=[],transmitted_bytes=0,preflight=report,installation=installed,recorder_source_sha256=pins,
        strict_historical_mount_marker_trial_waived=False,nic_ready=False,ssh=False,durability=False,
        scope='Phased runtime root identity and local socket traffic; not Ethernet or SSH')
    fd,original=None,None
    try:
        fd=os.open(args.device,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK); fcntl.ioctl(fd,termios.TIOCEXCL)
        original=termios.tcgetattr(fd); config=termios.tcgetattr(fd)
        config[0]=config[1]=config[3]=0; config[2]=termios.CS8|termios.CREAD|termios.CLOCAL
        config[4]=config[5]=termios.B115200; config[6][termios.VMIN]=config[6][termios.VTIME]=0
        termios.tcsetattr(fd,termios.TCSANOW,config); termios.tcflush(fd,termios.TCIFLUSH)
        with (args.output/'serial.bin').open('xb',buffering=0) as output:
            revalidate(); print('SOCKET_IDENTITY_TRIAL_ARMED ZERO_TX_UNTIL_EXACT_FRESH_PAYLOAD',flush=True)
            trial(fd,output,args.boot_wait_seconds,state,revalidate)
        state['status']='passed'
    except (Exception,KeyboardInterrupt) as error: state['error']=str(error) or 'interrupted'
    finally:
        if fd is not None:
            try:
                if original is not None: termios.tcsetattr(fd,termios.TCSANOW,original)
            except OSError as error: state['serial_restore_error']=str(error); state['status']='failed'
            finally: os.close(fd)
        raw=args.output/'serial.bin'
        state.update(ended_utc=t.utc_now(),bytes=raw.stat().st_size if raw.exists() else 0,
                     serial_sha256=hashlib.sha256(raw.read_bytes()).hexdigest() if raw.exists() else None)
        (args.output/'state.json').write_text(json.dumps(state,indent=2)+'\n')
        print(json.dumps(dict(status=state['status'],checks=state['checks'],error=state.get('error'),bytes=state['bytes'])),flush=True)
    return 0 if state['status']=='passed' else 1


if __name__=='__main__': raise SystemExit(main())
