#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One receive-only RP1 trace firmware/kernel trial capture; never reboot, retry or restore."""
import argparse
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import termios
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_pcie_trace_trial as staging
import pcie_trace_serial_core as protocol
import rpi5_board_lease as lease
import serial_root96_trial as receipt_guard


def utc():return datetime.now(timezone.utc).isoformat()


def installation(directory):
    directory=directory.resolve()
    if directory.parent!=staging.ROOT/'build/rpi5':raise ValueError('Local pair installation receipt required')
    plan=json.loads((directory/'plan.json').read_text());result=json.loads((directory/'result.json').read_text())
    if plan['profile']!='pcie-trace-pair-trial-v1':raise ValueError('Installed trial pair, not a restored pair, required')
    staging.validate_result(result,plan)
    return dict(directory=str(directory),plan_sha256=staging.sha(directory/'plan.json'),
        result_sha256=staging.sha(directory/'result.json'),preflight=plan['preflight'],
        pair_sha256=result['pair_sha256'],original_linux_boot_id=plan['linux_boot_id'])


def inventory(data):return protocol.inventory(data)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('device');p.add_argument('output',type=Path)
    p.add_argument('--installation',type=Path,required=True);p.add_argument('--seconds',type=int,default=240)
    args=p.parse_args(argv)
    if not re.fullmatch(r'/dev/cu\.usbmodem[A-Za-z0-9_-]+',args.device) or not 60<=args.seconds<=600:
        raise ValueError('Explicit Mac Debug Probe callout and bounded capture required')
    installed=installation(args.installation)
    sources=staging.source_pins()|{str(Path(__file__).resolve()):staging.sha(Path(__file__)),
        str(Path(protocol.__file__).resolve()):staging.sha(Path(protocol.__file__)),
        str(Path(receipt_guard.__file__).resolve()):staging.sha(Path(receipt_guard.__file__))}
    receipts=receipt_guard.receipt_evidence_pins(args.installation)
    def revalidate():
        if (any(staging.sha(Path(n))!=pin for n,pin in receipts.items()) or
            any(staging.sha(Path(n))!=pin for n,pin in sources.items())):
            raise ValueError('Trial pair/receipt/recorder source changed')
    output=args.output.resolve()
    if output.parent!=staging.ROOT/'build/rpi5':raise ValueError('Fresh local evidence child required')
    with lease.hold(staging.ROOT,'receive-only-pcie-trace-pair-trial-v1'):
        # TIOCEXCL prevents future opens but cannot expel preexisting handles.
        existing=subprocess.run(['lsof','-t','--',args.device],text=True,capture_output=True,timeout=15)
        if existing.returncode!=1 or existing.stdout.strip() or existing.stderr.strip():
            raise ValueError('Port already open or ownership lookup failed; no automatic kill')
        output.mkdir(exist_ok=False)
        state=dict(status='failed',started_utc=utc(),pid=os.getpid(),device=args.device,baud=115200,
            transmitted_bytes=0,installation=installed,source_sha256=sources,receipt_evidence_sha256=receipts,continuous_capture=False,
            physical_reset_return_proven=False,xnu_pe_runtime_proven=False,ethernet_proven=False)
        fd=original=None
        try:
            fd=os.open(args.device,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK);fcntl.ioctl(fd,termios.TIOCEXCL)
            original=termios.tcgetattr(fd);config=termios.tcgetattr(fd)
            config[0]=config[1]=config[3]=0;config[2]=termios.CS8|termios.CREAD|termios.CLOCAL
            config[4]=config[5]=termios.B115200;config[6][termios.VMIN]=config[6][termios.VTIME]=0
            termios.tcsetattr(fd,termios.TCSANOW,config);termios.tcflush(fd,termios.TCIFLUSH)
            with (output/'serial.bin').open('xb',buffering=0) as raw,(output/'receive-events.jsonl').open('x') as events:
                revalidate();start=time.monotonic();deadline=start+args.seconds;total=0;received=b'';transfer_time=None;returned=False
                state.update(armed_utc=utc(),armed_monotonic=start)
                with (output/'armed.json').open('x') as armed:
                    armed.write(json.dumps(state,indent=2)+'\n');armed.flush();os.fsync(armed.fileno())
                print('RP1_TRACE_CAPTURE_ARMED ZERO_SERIAL_TX IMAGE_SHA='+installed['pair_sha256']['probe.bin']+
                    ' FIRMWARE_SHA='+installed['pair_sha256']['bl31.bin'],flush=True)
                while time.monotonic()<deadline:
                    if transfer_time is not None and time.monotonic()-transfer_time>150:raise TimeoutError('Transfer-to-return budget exhausted')
                    ready,_,_=select.select([fd],[],[],min(1,max(0,deadline-time.monotonic())))
                    if not ready:continue
                    data=os.read(fd,4096)
                    if not data:raise RuntimeError('Serial disconnected; no reopen/retry')
                    if total+len(data)>4*1024*1024:raise ValueError('Serial capture bound exceeded')
                    raw.write(data);os.fsync(raw.fileno())
                    events.write(json.dumps(dict(offset=total,bytes=len(data),monotonic=time.monotonic(),utc=utc()))+'\n')
                    events.flush();os.fsync(events.fileno());total+=len(data);received+=data
                    if transfer_time is None and protocol.TRANSFER in received:transfer_time=time.monotonic()
                    if protocol.return_positions(received) is not None:returned=True;break
                    if transfer_time is not None and time.monotonic()-transfer_time>150:raise TimeoutError('Transfer-to-return budget exhausted')
                if not returned:raise TimeoutError('No bounded complete normal NVMe return')
                revalidate();state.update(status='captured',continuous_capture=True)
        except (Exception,KeyboardInterrupt) as error:state['error']=str(error) or 'interrupted'
        finally:
            if fd is not None:
                try:
                    if original is not None:termios.tcsetattr(fd,termios.TCSANOW,original)
                except OSError as error:state.update(status='failed',continuous_capture=False,restore_error=str(error))
                finally:os.close(fd)
            raw=output/'serial.bin';data=raw.read_bytes() if raw.exists() else b''
            state.update(ended_utc=utc(),bytes=len(data),serial_sha256=hashlib.sha256(data).hexdigest(),inventory=inventory(data))
            try:
                state['diagnostic']=protocol.inspect(data,installed['preflight'])
            except ValueError as error:state['diagnostic_error']=str(error)
            with (output/'state.json').open('x') as out:
                out.write(json.dumps(state,indent=2)+'\n');out.flush();os.fsync(out.fileno())
            print(json.dumps({k:state.get(k) for k in ('status','bytes','continuous_capture','diagnostic','diagnostic_error','error')}),flush=True)
        # Capturing a stream or a reboot without the full RP1 trace sequence is not
        # diagnostic success. Even full RP1 trace success doesn't prove SSD return.
        return 0 if state['status']=='captured' and 'diagnostic' in state else 1


if __name__=='__main__':raise SystemExit(main())


