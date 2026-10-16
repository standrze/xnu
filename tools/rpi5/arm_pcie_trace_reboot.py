#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Arm the distinct passive recorder, then make at most one verified SSH reboot.

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
import serial_pcie_trace_trial as recorder


def utc():return datetime.now(timezone.utc).isoformat()


def save(path,value):
    with path.open('x') as out:
        json.dump(value,out,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())


def arm_once(output,command,expected_line,validate_armed,reboot,timeout=90,popen=subprocess.Popen):
    """Test seam: callbacks are invoked only after exact live-child ARMED evidence."""
    if not 0<timeout<=120:raise ValueError('Bounded arming timeout required')
    output.mkdir(exist_ok=False)
    save(output/'intent.json',dict(command=command,expected_armed=expected_line,created_utc=utc(),no_retry=True))
    stdout=output/'recorder.stdout';stderr=output/'recorder.stderr'
    with stdout.open('xb',buffering=0) as out,stderr.open('xb',buffering=0) as err:
        child=popen(command,stdout=out,stderr=err,start_new_session=True)
    save(output/'process.json',dict(pid=child.pid,started_utc=utc(),command=command))
    deadline=time.monotonic()+timeout
    try:
        while True:
            data=stdout.read_bytes()
            if len(data)>256*1024:raise ValueError('Unexpected recorder output volume')
            lines=data.decode('utf-8',errors='strict').splitlines()
            armed=[line for line in lines if 'CAPTURE_ARMED' in line]
            if armed:
                if armed!=[expected_line] or child.poll() is not None:raise ValueError('Recorder not uniquely armed and alive')
                witness=validate_armed(child.pid)
                # Check again after receipt validation, before even starting SSH.
                if child.poll() is not None or time.monotonic()>=deadline:raise ValueError('Recorder expired during validation')
                save(output/'reboot-intent.json',dict(armed=witness,observed_utc=utc(),one_shot=True))
                result=reboot()
                save(output/'reboot-result.json',result)
                return dict(recorder_pid=child.pid,reboot_attempted=True,result=result)
            if child.poll() is not None:raise ValueError('Recorder exited before ARMED; no reboot')
            if time.monotonic()>=deadline:raise TimeoutError('Recorder did not arm in time; no reboot')
            time.sleep(0.05)
    except BaseException as error:
        save(output/'launcher-failure.json',dict(error=str(error),observed_utc=utc(),
            reboot_attempted=(output/'reboot-intent.json').exists(),no_retry=True,
            recorder_pid=child.pid,recorder_left_to_own_bounded_deadline=True))
        raise


def reboot_source(boot,root):
    # Verification and the single reboot occur in the SAME SSH process. There
    # is no gap in which a separate unchecked reboot is issued.
    return ('import json,os,subprocess\nfrom pathlib import Path\n'+
        'expected_boot='+repr(boot)+'\nexpected_root='+repr(root)+'\n'+
        'actual_boot=Path("/proc/sys/kernel/random/boot_id").read_text().strip()\n'+
        'actual_root=subprocess.check_output(["findmnt","-no","SOURCE,FSTYPE,UUID","/"],text=True).split()\n'+
        'if actual_boot!=expected_boot or actual_root!=expected_root:raise SystemExit("Linux boot/root mismatch; no reboot")\n'+
        'if Path("/proc/sys/kernel/random/boot_id").read_text().strip()!=actual_boot:raise SystemExit("Boot changed; no reboot")\n'+
        'print("VERIFIED_SSD_LINUX_REBOOT_ONCE "+json.dumps(dict(boot_id=actual_boot,root=actual_root),sort_keys=True),flush=True)\n'+
        'os.execv("/usr/sbin/reboot",["reboot"])\n')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--installation',type=Path,required=True)
    p.add_argument('--device',required=True);p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--linux-boot-id',required=True)
    a=p.parse_args(argv);stage=recorder.staging
    installed=recorder.installation(a.installation)
    plan=json.loads((a.installation/'plan.json').read_text())
    if a.linux_boot_id!=installed['original_linux_boot_id']:raise ValueError('Reboot requires exact staged Linux boot')
    output=a.output.resolve();capture=a.capture.resolve()
    if output.parent!=stage.ROOT/'build/rpi5' or capture.parent!=stage.ROOT/'build/rpi5' or capture.exists():
        raise ValueError('Distinct fresh local launch and capture paths required')
    command=[sys.executable,str(Path(recorder.__file__).resolve()),a.device,str(capture),
        '--installation',installed['directory'],'--seconds','600']
    expected='RP1_TRACE_CAPTURE_ARMED ZERO_SERIAL_TX IMAGE_SHA='+installed['pair_sha256']['probe.bin']+' FIRMWARE_SHA='+installed['pair_sha256']['bl31.bin']
    receipts=recorder.receipt_guard.receipt_evidence_pins(a.installation)
    sources=stage.source_pins()
    def validate_armed(pid):
        armed=json.loads((capture/'armed.json').read_text())
        if (armed['pid']!=pid or armed['installation']!=installed or armed['transmitted_bytes']!=0 or
            armed['device']!=a.device or armed['baud']!=115200 or (capture/'state.json').exists() or
            armed['receipt_evidence_sha256']!=receipts or
            any(stage.sha(Path(n))!=pin for n,pin in receipts.items()) or stage.source_pins()!=sources):
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
