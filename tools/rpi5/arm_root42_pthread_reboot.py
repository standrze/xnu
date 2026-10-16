#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Arm sealed root42 recorder, then attempt one exact-root/boot SSH reboot.

Never retry an ambiguous attempt; the original bounded recorder owns cleanup.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import serial_root42_pthread_trial as recorder
from arm_pcie_trace_reboot import arm_once, reboot_source, utc

stage=recorder.staging


def launch(context, device, capture, output, boot):
    installed=context['installed']; report=installed['preflight']; media=context['plan']['media']
    if boot!=installed['original_linux_boot_id'] or boot!=media['linux_boot_id']:
        raise ValueError('Reboot requires exact staged Linux boot')
    capture,output=stage.local(capture),stage.local(output)
    if capture==output or capture.exists() or output.exists():
        raise ValueError('Distinct fresh launch/capture paths required')
    if not recorder.t.valid_probe_device(device):raise ValueError('Exact probe device required')
    recorder.revalidate(context)
    pins=recorder.bound_sources(context); packages=recorder.package_pins(context)
    command=[sys.executable,str(Path(recorder.__file__).resolve()),device,str(capture),
        '--installation',installed['directory'],'--seal-sha256',installed['checkpoint_sha256'],
        '--plan-sha256',installed['plan_sha256'],'--boot-wait-seconds','600']
    def validate_armed(pid):
        armed=json.loads((capture/'armed.json').read_text())
        expected=dict(pid=pid,device=device,baud=115200,installation=installed,preflight=report,
            status='failed',checks=[],exchanges=[],transmitted_bytes=0,source_sha256=pins,
            receipt_evidence_sha256=context['evidence'],package_evidence_sha256=packages,
            command_tests_passed=False,normal_nvme_boot_observed=False,
            independent_linux_return_verified=False,ssh_daemon=False,networking=False,
            controller_initialized=False,durability=False)
        if ((capture/'state.json').exists() or
            any(not stage.engine.same(armed.get(k),v) for k,v in expected.items())):
            raise ValueError('Exact live zero-TX root42 ARMED state required')
        recorder.revalidate(context)
        return dict(pid=pid,armed_sha256=stage.sha(capture/'armed.json'),installation=installed,
            capture=str(capture),observed_utc=utc())
    source=reboot_source(boot,media['identity_binding']['expected']['root'].split())
    def reboot():
        # arm_once persisted one-shot intent first; save exact program before SSH.
        stage.save_bytes(output/'reboot-source.py',source.encode())
        try:
            r=subprocess.run(stage.SSH+['sudo -n python3 -'],input=source,text=True,capture_output=True,timeout=30)
            out,err,rc,timed_out=r.stdout,r.stderr,r.returncode,False
        except subprocess.TimeoutExpired as e:
            out,err,rc,timed_out=e.stdout or b'',e.stderr or b'',None,True
        out=out.encode() if isinstance(out,str) else out;err=err.encode() if isinstance(err,str) else err
        stage.save_bytes(output/'reboot.stdout',out);stage.save_bytes(output/'reboot.stderr',err)
        return dict(returncode=rc,timed_out=timed_out,
            verification_marker_observed=out.count(b'VERIFIED_SSD_LINUX_REBOOT_ONCE ')==1,
            reboot_outcome='unknown_until_serial_and_fresh_linux_return',no_retry=True,
            remote_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
            stdout_sha256=stage.sha(output/'reboot.stdout'),stderr_sha256=stage.sha(output/'reboot.stderr'))
    return arm_once(output,command,recorder.armed_line(report),validate_armed,reboot)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--installation',type=Path,required=True)
    p.add_argument('--seal-sha256',required=True);p.add_argument('--plan-sha256',required=True)
    p.add_argument('--device',required=True);p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--linux-boot-id',required=True)
    a=p.parse_args(argv)
    context=stage.load_installation(a.installation,a.seal_sha256,a.plan_sha256)
    value=launch(context,a.device,a.capture,a.output,a.linux_boot_id)
    print(json.dumps(value,sort_keys=True))
    return 0 if value['result']['verification_marker_observed'] else 1


if __name__=='__main__':raise SystemExit(main())
