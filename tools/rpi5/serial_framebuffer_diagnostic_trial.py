#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One receive-only FBOBS capture; no retry, input, reboot or media operation."""
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
import struct
import sys
import termios
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_framebuffer_diagnostic_trial as stage
from tools.rpi5 import framebuffer_diagnostic_serial as protocol
ENTRY=b'RPI5XNU:FBOBS:ENTRY TAG='
ARMED=b'RPI5XNU:FBOBS:ARMED WATCHDOG=15 SOFTWARE=8 NO_RELOAD'
SD=b'Boot mode: SD (01)'
BOOTSYS=b'RPi: BOOTSYS release VERSION:'
BOOTLOADER=b'RPi: BOOTLOADER release VERSION:'
NVME=b'Boot mode: NVME (06)'
def utc():return datetime.now(timezone.utc).isoformat()
def valid_device(value):return isinstance(value,str) and re.fullmatch(r'/dev/cu\.usbmodem[A-Za-z0-9_-]+',value) is not None
def bound_sources(context):
    current=stage.source_pins()
    if any(context['evidence'].get(n)!=v for n,v in current.items()):raise ValueError('Observer transport source changed/omitted since sealing')
    return {n:context['evidence'][n] for n in current}
def package_pins(context):
    path=stage.PACKAGE/'manifest.json'
    if context['evidence'].get(str(path))!=stage.MANIFEST_SHA or stage.sha(path)!=stage.MANIFEST_SHA:raise ValueError('Exact observer package seal required')
    m=json.loads(path.read_text());pins={str(path):stage.MANIFEST_SHA}
    for key in ('inputs_sha256','headers_sha256','generated_sha256'):
        pins=stage.prior.merge_pins(pins,m[key])
    if any(context['evidence'].get(n)!=v for n,v in pins.items()):raise ValueError('Complete package closure absent from seal')
    return pins
def revalidate(context):
    stage.seals.check_pins(context['evidence']);bound_sources(context);package_pins(context);stage.valid_report(context['installed']['preflight'])
def armed_line(report):return 'FBOBS_CAPTURE_ARMED ZERO_SERIAL_TX IMAGE_SHA='+report['image_sha256']+' TAG='+report['tag']
def initial(context,device,pid=None,started=None):
    return dict(status='failed',started_utc=started or utc(),pid=pid or os.getpid(),device=device,baud=115200,transmitted_bytes=0,
        installation=context['installed'],source_sha256=bound_sources(context),receipt_evidence_sha256=context['evidence'],
        package_evidence_sha256=package_pins(context),continuous_capture=False,normal_nvme_boot_observed=False,
        independent_linux_return_verified=False,ownership_proven=False,scanout_cache_contract_proven=False,drawing=False,mirror_enabled=False)
def return_positions(data):
    sd=data.find(SD)
    if sd<0:return None
    a=data.find(BOOTSYS,sd+len(SD));b=data.find(BOOTLOADER,a+len(BOOTSYS)) if a>=0 else -1
    c=data.find(NVME,b+len(BOOTLOADER)) if b>=0 else -1
    return (sd,a,b,c) if c>=0 else None
def capture(context,device,output,seconds=600):
    if not valid_device(device) or type(seconds) is not int or not 60<=seconds<=600:raise ValueError('Exact device and bounded wait required')
    revalidate(context);output=stage.local(output)
    with stage.lease.hold(stage.ROOT,'framebuffer-diagnostic-receive-only-v1'):
        existing=subprocess.run(['lsof','-t','--',device],text=True,capture_output=True,timeout=15)
        if existing.returncode!=1 or existing.stdout.strip() or existing.stderr.strip():raise ValueError('Serial owned or ownership lookup failed')
        output.mkdir(exist_ok=False);state=initial(context,device);fd=original=None
        try:
            fd=os.open(device,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK);fcntl.ioctl(fd,termios.TIOCEXCL)
            original=termios.tcgetattr(fd);config=termios.tcgetattr(fd)
            config[0]=config[1]=config[3]=0;config[2]=termios.CS8|termios.CREAD|termios.CLOCAL
            config[4]=config[5]=termios.B115200;config[6][termios.VMIN]=config[6][termios.VTIME]=0
            termios.tcsetattr(fd,termios.TCSANOW,config)
            # Probe v2.3.1 gates its UART task on DTR. This is explicit modem
            # control, not UART payload TX or proof that receive wiring works.
            required=termios.TIOCM_DTR|termios.TIOCM_RTS
            fcntl.ioctl(fd,termios.TIOCMBIS,struct.pack('=I',required))
            actual=struct.unpack('=I',fcntl.ioctl(fd,termios.TIOCMGET,struct.pack('=I',0)))[0]
            if actual&required!=required:raise ValueError('DTR and RTS must be asserted before ARMED; RX remains unqualified')
            termios.tcflush(fd,termios.TCIFLUSH)
            with (output/'serial.bin').open('xb',buffering=0) as raw,(output/'receive-events.jsonl').open('x') as events:
                revalidate(context);start=time.monotonic();deadline=start+seconds;received=b'';sd_time=None;returned=False
                state.update(armed_utc=utc(),armed_monotonic=start);stage.save(output/'armed.json',state)
                print(armed_line(context['installed']['preflight']),flush=True)
                while time.monotonic()<deadline:
                    if sd_time is not None and time.monotonic()-sd_time>150:raise TimeoutError('Fresh SD boot to NVMe capture deadline exhausted')
                    ready,_,_=select.select([fd],[],[],min(1,max(0,deadline-time.monotonic())))
                    if not ready:continue
                    data=os.read(fd,4096)
                    if not data:raise RuntimeError('Serial disconnected; no reopen or retry')
                    if len(received)+len(data)>4*1024*1024:raise ValueError('Raw capture bound exceeded')
                    raw.write(data);os.fsync(raw.fileno());stamp=time.monotonic()
                    events.write(json.dumps(dict(offset=len(received),bytes=len(data),monotonic=stamp,utc=utc()))+'\n');events.flush();os.fsync(events.fileno())
                    received+=data
                    if sd_time is None and SD in received:sd_time=stamp
                    if return_positions(received) is not None:returned=True;break
                if not returned:raise TimeoutError('No complete observed normal NVMe selection')
                revalidate(context);state.update(status='captured',continuous_capture=True,normal_nvme_boot_observed=True)
        except (Exception,KeyboardInterrupt) as error:state['error']=str(error) or 'interrupted'
        finally:
            if fd is not None:
                try:
                    if original is not None:termios.tcsetattr(fd,termios.TCSANOW,original)
                except OSError as error:state.update(status='failed',continuous_capture=False,restore_error=str(error))
                finally:os.close(fd)
            data=(output/'serial.bin').read_bytes() if (output/'serial.bin').exists() else b''
            state.update(ended_utc=utc(),bytes=len(data),serial_sha256=hashlib.sha256(data).hexdigest())
            try:
                state['diagnostic']=protocol.inspect(data,context['installed']['preflight'])
                if state['status']=='captured':
                    rows=[json.loads(line) for line in (output/'receive-events.jsonl').read_text().splitlines()]
                    stage.transport().inspect_capture(data,rows,state,context['installed'],bound_sources(context))
            except (ValueError,KeyError,IndexError,StopIteration) as error:state['diagnostic_error']=str(error)
            stage.save(output/'state.json',state)
            print(json.dumps({k:state.get(k) for k in ('status','bytes','continuous_capture','diagnostic','diagnostic_error','error')}),flush=True)
        return 0 if state['status']=='captured' and not state.get('diagnostic_error') and state.get('diagnostic',{}).get('diagnostic_pass') is True else 1
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('device');p.add_argument('output',type=Path)
    p.add_argument('--installation',type=Path,required=True);p.add_argument('--seal-sha256',required=True);p.add_argument('--plan-sha256',required=True)
    p.add_argument('--seconds',type=int,default=600);a=p.parse_args(argv)
    return capture(stage.load_installation(a.installation,a.seal_sha256,a.plan_sha256),a.device,a.output,a.seconds)
if __name__=='__main__':raise SystemExit(main())
