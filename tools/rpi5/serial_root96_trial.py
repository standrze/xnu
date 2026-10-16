#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One 180-second kernel trial: exact identity, zsh, buffer, automatic return."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import termios
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
import check_root96_ssh_package as package
import stage_root96_trial as staging
import root96_trial_core as core
import rpi5_board_lease as lease
t=core.t


def source_pins():
    return staging.source_pins()|{str(Path(m.__file__).resolve()):staging.sha(Path(m.__file__)) for m in
        (core,core.identity,t,t.shell,core.prior)}


def installation(directory,report):
    directory=directory.resolve()
    if directory.parent!=staging.ROOT/'build/rpi5':raise ValueError('Installed local receipt required')
    plan=json.loads((directory/'plan.json').read_text());result=json.loads((directory/'result.json').read_text())
    staging.validate_result(result,plan)
    if plan['profile']!='root96-install-v1' or plan['preflight']!=report or result['protected_files_sha256']['probe.bin']!=report['image_sha256']:
        raise ValueError('Exact installed bounded candidate required')
    return dict(directory=str(directory),plan_sha256=staging.sha(directory/'plan.json'),result_sha256=staging.sha(directory/'result.json'))


def receipt_evidence_pins(directory):
    """Pin already validated receipt bytes without replaying history before TX."""
    pins={};seen=set()
    def visit(path):
        path=path.resolve()
        if path in seen:return
        if path.parent!=staging.ROOT/'build/rpi5':raise ValueError('Nonlocal receipt ancestry')
        seen.add(path)
        plan=json.loads((path/'plan.json').read_text())
        for name in ('plan.json','result.json'):pins[str(path/name)]=staging.sha(path/name)
        for source,digest in plan.get('source_sha256',{}).items():
            snapshot=path/'source-snapshots'/Path(source).name
            if snapshot.exists():
                if staging.sha(snapshot)!=digest:raise ValueError('Receipt source snapshot drift')
                pins[str(snapshot)]=digest
        ancestor=plan.get('ancestry')
        if ancestor:
            parent=Path(ancestor['directory']).resolve()
            for name,digest in ancestor['hashes'].items():
                artifact=parent/name
                if artifact.parent!=parent or staging.sha(artifact)!=digest:raise ValueError('Receipt ancestry drift')
                pins[str(artifact)]=digest
            visit(parent)
    visit(directory)
    return pins


def trial(fd,output,seconds,report,state,revalidate):
    deadline=time.monotonic()+seconds;data=b''
    while time.monotonic()<deadline:
        data+=t.shell.receive(fd,output,deadline)
        if core.boot_ready(data,report):break
    else:raise TimeoutError('No exact fresh bounded root boot; zero TX')
    revalidate();state['checks'].append(core.CHECKS[0]);admitted=time.monotonic()
    state['admitted_monotonic']=admitted
    receipt=json.loads(Path(report['root_manifest']).read_text())
    core.commands(fd,output,state,receipt,revalidate,admitted+120)
    state['commands_complete_seconds_after_admission']=time.monotonic()-admitted
    if state['commands_complete_seconds_after_admission']>=120:raise TimeoutError('Command budget exceeded')
    state['command_tests_passed']=True
    state['return_capture_offset']=output.tell()
    print('ROOT96_COMMAND_TESTS_PASS WAITING_BOUNDED_AUTOMATIC_NVME_RETURN',flush=True)
    tail=b'';deadline=admitted+225
    while time.monotonic()<deadline:
        tail+=t.shell.receive(fd,output,deadline)
        if len(tail)>t.MAX_BYTES:raise ValueError('Return capture exceeded bound')
        if core.returned(tail):
            elapsed=time.monotonic()-admitted
            if not 120<elapsed<225:raise ValueError('Return occurred outside bounded terminal deadline')
            state['normal_nvme_boot_observed']=True;state['return_seconds_after_admission']=elapsed
            return
    raise TimeoutError('No bounded automatic normal NVMe return observed')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('device');p.add_argument('output',type=Path)
    p.add_argument('--package',type=Path,required=True);p.add_argument('--installation',type=Path,required=True)
    p.add_argument('--boot-wait-seconds',type=int,default=180);args=p.parse_args(argv)
    if not t.valid_probe_device(args.device) or not 30<=args.boot_wait_seconds<=600:raise ValueError('Exact probe/bounded boot wait required')
    report=package.inspect(args.package);installed=installation(args.installation,report);pins=source_pins()
    receipts=receipt_evidence_pins(args.installation)
    def revalidate():
        if (package.inspect(args.package)!=report or source_pins()!=pins or
            any(staging.sha(Path(path))!=digest for path,digest in receipts.items())):
            raise ValueError('Candidate/receipt/source changed; no further TX')
    output=args.output.resolve()
    if output.parent!=staging.ROOT/'build/rpi5':raise ValueError('Fresh local trial output required')
    with lease.hold(staging.ROOT,'root96-bounded-serial-trial'):
        opened=subprocess.run(['lsof','-t','--',args.device],text=True,capture_output=True,timeout=15)
        if opened.returncode!=1 or opened.stdout.strip() or opened.stderr.strip():raise ValueError('Existing serial owner or lookup failure')
        output.mkdir(exist_ok=False)
        state=dict(status='failed',started_utc=t.utc_now(),pid=os.getpid(),device=args.device,baud=115200,
            checks=[],exchanges=[],transmitted_bytes=0,preflight=report,installation=installed,source_sha256=pins,
            receipt_evidence_sha256=receipts,
            command_tests_passed=False,normal_nvme_boot_observed=False,independent_linux_return_verified=False,
            ssh_daemon=False,networking=False,controller_initialized=False,durability=False)
        fd=original=None
        try:
            fd=os.open(args.device,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK);fcntl.ioctl(fd,termios.TIOCEXCL)
            original=termios.tcgetattr(fd);config=termios.tcgetattr(fd)
            config[0]=config[1]=config[3]=0;config[2]=termios.CS8|termios.CREAD|termios.CLOCAL
            config[4]=config[5]=termios.B115200;config[6][termios.VMIN]=config[6][termios.VTIME]=0
            termios.tcsetattr(fd,termios.TCSANOW,config);termios.tcflush(fd,termios.TCIFLUSH)
            with (output/'serial.bin').open('xb',buffering=0) as raw:
                revalidate();state.update(armed_utc=t.utc_now(),armed_monotonic=time.monotonic())
                with (output/'armed.json').open('x') as f:json.dump(state,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
                print('ROOT96_ARMED ZERO_TX_UNTIL_EXACT_FRESH_BOOT WATCHDOG_180_SECONDS',flush=True)
                trial(fd,raw,args.boot_wait_seconds,report,state,revalidate)
            state['status']='passed'
        except (Exception,KeyboardInterrupt) as error:state['error']=str(error) or 'interrupted'
        finally:
            if fd is not None:
                try:
                    if original is not None:termios.tcsetattr(fd,termios.TCSANOW,original)
                except OSError as error:state.update(status='failed',serial_restore_error=str(error))
                finally:os.close(fd)
            raw=output/'serial.bin';data=raw.read_bytes() if raw.exists() else b''
            state.update(ended_utc=t.utc_now(),bytes=len(data),serial_sha256=hashlib.sha256(data).hexdigest())
            with (output/'state.json').open('x') as f:json.dump(state,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
            print(json.dumps({k:state.get(k) for k in ('status','command_tests_passed','normal_nvme_boot_observed','error','bytes')}),flush=True)
        return 0 if state['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
