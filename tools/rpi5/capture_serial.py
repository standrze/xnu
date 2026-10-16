#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bounded receive-only SSH serial capture. Does not reboot or transmit."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
from datetime import datetime, timezone

REMOTE = r'''
import os,sys,termios,select,time,fcntl
path=sys.argv[1]; duration=float(sys.argv[2])
fd=os.open(path,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
old=None
try:
 fcntl.ioctl(fd,termios.TIOCEXCL)
 old=termios.tcgetattr(fd)
 c=termios.tcgetattr(fd)
 c[0]=0; c[1]=0; c[2]=termios.CS8|termios.CREAD|termios.CLOCAL
 c[3]=0; c[4]=c[5]=termios.B115200
 c[6][termios.VMIN]=0; c[6][termios.VTIME]=0
 termios.tcsetattr(fd,termios.TCSANOW,c)
 print('CAPTURE_READY 115200 8N1 RX_ONLY',file=sys.stderr,flush=True)
 end=time.monotonic()+duration
 while time.monotonic()<end:
  ready,_,_=select.select([fd],[],[],max(0,end-time.monotonic()))
  if ready:
   data=os.read(fd,4096)
   if not data: raise RuntimeError('serial disconnected')
   sys.stdout.buffer.write(data); sys.stdout.buffer.flush()
 print('CAPTURE_FINISHED',file=sys.stderr,flush=True)
finally:
 if old is not None: termios.tcsetattr(fd,termios.TCSANOW,old)
 os.close(fd)
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('host')
    p.add_argument('device',help='Exact /dev/serial/by-id/ path on the capture host')
    p.add_argument('--seconds',type=int,default=45)
    a=p.parse_args()
    if a.host.startswith('-') or not a.device.startswith('/dev/serial/by-id/'):
        p.error('explicit host and stable serial device path required')
    if not 1<=a.seconds<=600: p.error('duration must be 1–600 seconds')
    base=Path(__file__).resolve().parents[2]/'build/rpi5'
    base.mkdir(parents=True,exist_ok=True)
    output=Path(tempfile.mkdtemp(prefix='serial-capture-',dir=base))
    command=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
             '-o','ConnectTimeout=8','-o','ServerAliveInterval=5',
             '-o','ServerAliveCountMax=2',a.host,
             'python3 - '+shlex.quote(a.device)+' '+str(a.seconds)]
    started=datetime.now(timezone.utc).isoformat()
    print(output,flush=True)
    status='failed'; code=None
    try:
        with (output/'serial.bin').open('wb') as raw, (output/'receiver.log').open('wb') as log:
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=raw,stderr=log)
            try:
                process.communicate(REMOTE.encode(),timeout=a.seconds+25)
            except subprocess.TimeoutExpired:
                process.kill(); process.communicate(); status='timeout'
            code=process.returncode
            if code==0: status='finished'
    finally:
        data=(output/'serial.bin').read_bytes()
        manifest={'started_utc':started,'ended_utc':datetime.now(timezone.utc).isoformat(),
                  'host':a.host,'device':a.device,'baud':115200,'format':'8N1',
                  'requested_seconds':a.seconds,'status':status,'ssh_exit_code':code,
                  'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                  'transmitted_bytes':0,'reboot_requested':False,
                  'gate1_pass':False}
        (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        print(json.dumps(manifest),flush=True)
    if status!='finished': raise SystemExit(1)


if __name__=='__main__': main()
