#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One exact display-XNU boot, guarded zsh input, complete bounded return RX."""
import argparse
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import select
import struct
import subprocess
import sys
import termios
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_display_xnu_trial as stage
from tools.rpi5 import display_xnu_serial as protocol
SD,BOOTSYS,BOOTLOADER,NVME,ENTRY=(getattr(protocol,n) for n in ('SD','BOOTSYS','BOOTLOADER','NVME','ENTRY'))
return_positions=protocol.return_positions
def utc():return datetime.now(timezone.utc).isoformat()
def valid_device(value):return isinstance(value,str) and re.fullmatch(r'/dev/cu\.usbmodem[A-Za-z0-9_-]+',value) is not None
def bound_sources(context):
    current=stage.source_pins()
    if any(context['evidence'].get(n)!=v for n,v in current.items()):raise ValueError('Display transport differs from sealed source closure')
    return {n:context['evidence'][n] for n in current}
def package_pins(context):
    path=stage.PACKAGE/'manifest.json'
    if context['evidence'].get(str(path))!=stage.MANIFEST_SHA or stage.sha(path)!=stage.MANIFEST_SHA:raise ValueError('Exact display package seal required')
    m=json.loads(path.read_text());pins={str(path):stage.MANIFEST_SHA}
    for key in ('inputs_sha256','actual_headers_sha256','generated_sha256'):pins=stage.prior.merge_pins(pins,m[key])
    if any(context['evidence'].get(n)!=v for n,v in pins.items()):raise ValueError('Complete package closure absent from seal')
    return pins
def revalidate(context):
    stage.seals.check_pins(context['evidence']);bound_sources(context);package_pins(context);stage.valid_report(context['installed']['preflight'])
def armed_line(report):return 'DISPLAYXNU_CAPTURE_ARMED ZERO_TX_UNTIL_FRESH_MIRROR_ROOT_PROMPT IMAGE_SHA='+report['image_sha256']+' TAG='+report['tag']
def initial(context,device,pid=None,started=None):
    return dict(status='failed',started_utc=started or utc(),pid=pid or os.getpid(),device=device,baud=115200,
        transmitted_bytes=0,exchanges=[],command_tests_passed=False,installation=context['installed'],
        source_sha256=bound_sources(context),receipt_evidence_sha256=context['evidence'],package_evidence_sha256=package_pins(context),
        continuous_capture=False,normal_nvme_boot_observed=False,independent_linux_return_verified=False,
        physical_visibility_proven=False,networking=False,ssh_daemon=False)

def capture(context,device,output,seconds=600):
    if not valid_device(device) or type(seconds) is not int or not 60<=seconds<=600:raise ValueError('Exact device and bounded initial wait required')
    revalidate(context);output=stage.local(output)
    with stage.lease.hold(stage.ROOT,'display-xnu-guarded-serial-v1'):
        owner=subprocess.run(['lsof','-t','--',device],text=True,capture_output=True,timeout=15)
        if owner.returncode!=1 or owner.stdout.strip() or owner.stderr.strip():raise ValueError('Serial owned or lookup failed')
        output.mkdir(exist_ok=False);state=initial(context,device);fd=original=None
        try:
            fd=os.open(device,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK);fcntl.ioctl(fd,termios.TIOCEXCL)
            original=termios.tcgetattr(fd);config=termios.tcgetattr(fd)
            config[0]=config[1]=config[3]=0;config[2]=termios.CS8|termios.CREAD|termios.CLOCAL
            config[4]=config[5]=termios.B115200;config[6][termios.VMIN]=config[6][termios.VTIME]=0
            termios.tcsetattr(fd,termios.TCSANOW,config)
            required=termios.TIOCM_DTR|termios.TIOCM_RTS
            fcntl.ioctl(fd,termios.TIOCMBIS,struct.pack('=I',required))
            actual=struct.unpack('=I',fcntl.ioctl(fd,termios.TIOCMGET,struct.pack('=I',0)))[0]
            if actual&required!=required:raise ValueError('DTR/RTS must be asserted before ARMED; RX unqualified')
            termios.tcflush(fd,termios.TCIFLUSH)
            with (output/'serial.bin').open('xb',buffering=0) as raw,(output/'receive-events.jsonl').open('x') as events:
                revalidate(context);start=time.monotonic();initial_deadline=start+seconds
                received=b'';sd_time=None;returned=False;attempted=False
                state.update(armed_utc=utc(),armed_monotonic=start);stage.save(output/'armed.json',state)
                print(armed_line(context['installed']['preflight']),flush=True)
                def receive(until,wait=1):
                    nonlocal received,sd_time
                    ready,_,_=select.select([fd],[],[],min(wait,max(0,until-time.monotonic())))
                    if not ready:return b''
                    data=os.read(fd,4096)
                    if not data:raise RuntimeError('Serial disconnected; no reopen/retry')
                    if len(received)+len(data)>protocol.MAX_BYTES:raise ValueError('Raw capture bound exceeded')
                    raw.write(data);os.fsync(raw.fileno());stamp=time.monotonic()
                    events.write(json.dumps(dict(offset=len(received),bytes=len(data),monotonic=stamp,utc=utc()))+'\n');events.flush();os.fsync(events.fileno())
                    received+=data
                    if sd_time is None and SD in received:sd_time=stamp
                    return data
                def safe_active():
                    protocol.healthy(received);protocol.runtime_lines(received)
                    if BOOTSYS in received[received.index(SD)+len(SD):] or received.count(b'Boot mode:')!=1:
                        raise ValueError('Return/new boot observed; no more serial input')
                def command_run():
                    deadline=state['admitted_monotonic']+120
                    nonce='D'+secrets.token_hex(8);state['nonce']=nonce
                    for name,command,expected,prompt in protocol.exchanges(nonce):
                        revalidate(context)
                        if time.monotonic()>=deadline-45:raise TimeoutError('Insufficient absolute TX budget')
                        pending_start=len(received);quiet=min(deadline,time.monotonic()+0.5)
                        while time.monotonic()<quiet:
                            chunk=receive(quiet,0.1)
                            safe_active()
                            if not chunk:
                                try:protocol.pending_safe(received[pending_start:])
                                except ValueError:continue
                                break
                        protocol.pending_safe(received[pending_start:]);safe_active()
                        if time.monotonic()>=deadline-45:raise TimeoutError('TX budget consumed by pending RX')
                        offset=len(received);tx_start=time.monotonic()
                        for byte in (command+'\n').encode('ascii'):
                            if time.monotonic()>=deadline:raise TimeoutError('Absolute per-byte TX deadline exhausted')
                            while select.select([fd],[],[],0)[0]:
                                if time.monotonic()>=deadline:raise TimeoutError('Absolute pending-RX TX deadline exhausted')
                                receive(deadline,0);safe_active()
                            _,ready,_=select.select([],[fd],[],min(2,max(0,deadline-time.monotonic())))
                            if not ready or time.monotonic()>=deadline or os.write(fd,bytes([byte]))!=1:raise RuntimeError('Bounded serial write failed')
                            state['transmitted_bytes']+=1;time.sleep(0.025)
                        tx_end=time.monotonic();response_deadline=min(deadline,tx_end+30)
                        while time.monotonic()<response_deadline:
                            safe_active();response=received[offset:]
                            if len(response)>65536:raise ValueError('Unbounded command response')
                            if protocol.response_complete(response,expected,prompt):break
                            receive(response_deadline)
                        else:raise TimeoutError('Actual zsh output/prompt deadline exhausted')
                        checked=protocol.inspect_exchange(received[offset:],name,nonce)
                        state['exchanges'].append(dict(checked,offset=offset,bytes=len(received)-offset,
                            pending_offset=pending_start,pending_bytes=offset-pending_start,
                            pending_sha256=hashlib.sha256(received[pending_start:offset]).hexdigest(),
                            tx_started_monotonic=tx_start,tx_ended_monotonic=tx_end,response_monotonic=time.monotonic()))
                    state['command_tests_passed']=True
                while True:
                    deadline=sd_time+240 if sd_time is not None else initial_deadline
                    if time.monotonic()>=deadline:raise TimeoutError('Fresh SD through normal NVMe return deadline exhausted')
                    receive(deadline)
                    if return_positions(received) is not None:returned=True;break
                    if not attempted and not state.get('trial_error'):
                        try:
                            if protocol.boot_ready(received,context['installed']['preflight']):
                                # The deadline starts before any potentially slow byte revalidation.
                                attempted=True;state.update(admitted_monotonic=time.monotonic(),admission_bytes=len(received))
                                command_run()
                        except (ValueError,RuntimeError,TimeoutError) as error:
                            state['trial_error']=str(error)
                            # Continue RX only through the return. No retry or re-admission.
                if not returned:raise TimeoutError('Normal return not observed')
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
                rows=[json.loads(line) for line in (output/'receive-events.jsonl').read_text().splitlines()] if (output/'receive-events.jsonl').exists() else []
                state['diagnostic']=stage.transport().inspect_capture(data,rows,state,context['installed'],bound_sources(context))
            except (ValueError,KeyError,IndexError,StopIteration) as error:state['diagnostic_error']=str(error)
            stage.save(output/'state.json',state)
            print(json.dumps({k:state.get(k) for k in ('status','bytes','transmitted_bytes','command_tests_passed','diagnostic_error','trial_error','error')}),flush=True)
        return 0 if state['status']=='captured' and not state.get('diagnostic_error') else 1
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('device');p.add_argument('output',type=Path)
    p.add_argument('--installation',type=Path,required=True);p.add_argument('--seal-sha256',required=True);p.add_argument('--plan-sha256',required=True)
    p.add_argument('--seconds',type=int,default=600);a=p.parse_args(argv)
    return capture(stage.load_installation(a.installation,a.seal_sha256,a.plan_sha256),a.device,a.output,a.seconds)
if __name__=='__main__':raise SystemExit(main())
