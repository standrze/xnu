#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Arm the distinct 41-node batch recorder, then make at most one verified SSH reboot.

No retries. Child output and one-shot intent survive this launcher exiting.
The recorder has its own deadline and remains responsible for serial cleanup.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
import serial_root41_trial as recorder
from arm_pcie_trace_reboot import arm_once,reboot_source


def utc():return datetime.now(timezone.utc).isoformat()


def save(path,value):
    with path.open('x') as out:
        json.dump(value,out,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--installation',type=Path,required=True)
    p.add_argument('--device',required=True);p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--linux-boot-id',required=True)
    a=p.parse_args(argv);stage=recorder.staging
    plan=json.loads((a.installation/'plan.json').read_text())
    report=recorder.package.inspect(Path(plan['package']))
    installed=recorder.installation(a.installation,report)
    plan=json.loads((a.installation/'plan.json').read_text())
    if a.linux_boot_id!=plan['linux_boot_id']:raise ValueError('Reboot requires exact staged Linux boot')
    output=a.output.resolve();capture=a.capture.resolve()
    if output.parent!=stage.ROOT/'build/rpi5' or capture.parent!=stage.ROOT/'build/rpi5' or capture.exists():
        raise ValueError('Distinct fresh local launch and capture paths required')
    command=[sys.executable,str(Path(recorder.__file__).resolve()),a.device,str(capture),
        '--installation',installed['directory'],'--package',plan['package'],'--boot-wait-seconds','600']
    expected=recorder.armed_line(report)
    receipts=recorder.receipt_evidence_pins(a.installation)
    sources=recorder.source_pins()
    packages=recorder.package_evidence_pins(Path(plan['package']))
    def validate_armed(pid):
        armed=json.loads((capture/'armed.json').read_text())
        if (armed['pid']!=pid or armed['installation']!=installed or armed['transmitted_bytes']!=0 or
            armed['device']!=a.device or armed['baud']!=115200 or (capture/'state.json').exists() or
            armed.get('source_sha256')!=sources or armed.get('preflight')!=report or
            armed.get('checks')!=[] or armed.get('exchanges')!=[] or
            armed['receipt_evidence_sha256']!=receipts or armed['package_evidence_sha256']!=packages or
            any(stage.sha(Path(n))!=pin for n,pin in packages.items()) or
            any(stage.sha(Path(n))!=pin for n,pin in receipts.items()) or recorder.source_pins()!=sources):
            raise ValueError('Armed child/installation/source/receipt binding changed')
        return dict(pid=pid,armed_sha256=stage.sha(capture/'armed.json'),installation=installed,
            observed_utc=utc(),capture=str(capture))
    source=reboot_source(a.linux_boot_id,plan['identity_binding']['expected']['root'].split())
    def reboot():
        # The durable intent exists before SSH starts. Timeout/disconnect means
        # unknown outcome, not permission to issue another reboot.
        with (output/'reboot-source.py').open('x') as out:
            out.write(source);out.flush();os.fsync(out.fileno())
        try:
            r=subprocess.run(stage.SSH+['sudo -n python3 -'],input=source,text=True,capture_output=True,timeout=30)
            out,err,rc,timed_out=r.stdout,r.stderr,r.returncode,False
        except subprocess.TimeoutExpired as error:
            out=error.stdout or b'';err=error.stderr or b'';rc=None;timed_out=True
            out=out.decode(errors='replace') if isinstance(out,bytes) else out
            err=err.decode(errors='replace') if isinstance(err,bytes) else err
        (output/'reboot.stdout').write_text(out);(output/'reboot.stderr').write_text(err)
        witness='VERIFIED_SSD_LINUX_REBOOT_ONCE '
        return dict(returncode=rc,timed_out=timed_out,verification_marker_observed=out.count(witness)==1,
            reboot_outcome='unknown_until_serial_and_fresh_linux_return',no_retry=True,
            remote_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
            stdout_sha256=stage.sha(output/'reboot.stdout'),stderr_sha256=stage.sha(output/'reboot.stderr'))
    result=arm_once(output,command,expected,validate_armed,reboot)
    print(json.dumps(result,sort_keys=True))
    return 0 if result['result']['verification_marker_observed'] else 1


if __name__=='__main__':raise SystemExit(main())

