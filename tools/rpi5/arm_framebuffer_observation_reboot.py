#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact live FBOBS recorder then one same-process verified SSD reboot."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import serial_framebuffer_observation_trial as recorder
from arm_pcie_trace_reboot import arm_once,reboot_source,utc
stage=recorder.stage
def launch(context,device,capture,output,boot):
    installed=context['installed'];media=context['plan']['media'];report=installed['preflight']
    if boot!=installed['original_linux_boot_id'] or boot!=media['linux_boot_id']:raise ValueError('Exact staged boot required')
    capture,output=stage.local(capture),stage.local(output)
    if capture==output or capture.exists() or output.exists() or not recorder.valid_device(device):raise ValueError('Fresh distinct capture/launch and probe required')
    recorder.revalidate(context)
    command=[sys.executable,str(Path(recorder.__file__).resolve()),device,str(capture),'--installation',installed['directory'],
        '--seal-sha256',installed['checkpoint_sha256'],'--plan-sha256',installed['plan_sha256'],'--seconds','600']
    def validate_armed(pid):
        armed=json.loads((capture/'armed.json').read_text());expected=recorder.initial(context,device,pid,armed.get('started_utc'))
        expected.update(armed_utc=armed.get('armed_utc'),armed_monotonic=armed.get('armed_monotonic'))
        if (capture/'state.json').exists() or not stage.engine.same(armed,expected):raise ValueError('Exact active observer ARMED schema required')
        recorder.revalidate(context)
        return dict(pid=pid,armed_sha256=stage.sha(capture/'armed.json'),installation=installed,capture=str(capture),observed_utc=utc())
    source=reboot_source(boot,media['identity_binding']['expected']['root'].split())
    def reboot():
        stage.save_bytes(output/'reboot-source.py',source.encode())
        try:
            r=subprocess.run(stage.SSH+['sudo -n python3 -'],input=source,text=True,capture_output=True,timeout=30)
            out,err,rc,timed_out=r.stdout,r.stderr,r.returncode,False
        except subprocess.TimeoutExpired as e:out,err,rc,timed_out=e.stdout or b'',e.stderr or b'',None,True
        out=out.encode() if isinstance(out,str) else out;err=err.encode() if isinstance(err,str) else err
        stage.save_bytes(output/'reboot.stdout',out);stage.save_bytes(output/'reboot.stderr',err)
        return dict(returncode=rc,timed_out=timed_out,verification_marker_observed=out.count(b'VERIFIED_SSD_LINUX_REBOOT_ONCE ')==1,
            reboot_outcome='unknown_until_serial_and_fresh_linux_return',no_retry=True,remote_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
            stdout_sha256=stage.sha(output/'reboot.stdout'),stderr_sha256=stage.sha(output/'reboot.stderr'))
    return arm_once(output,command,recorder.armed_line(report),validate_armed,reboot)
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('installation','capture','output'):p.add_argument('--'+name,type=Path,required=True)
    for name in ('seal-sha256','plan-sha256','device','linux-boot-id'):p.add_argument('--'+name,required=True)
    a=p.parse_args(argv);context=stage.load_installation(a.installation,a.seal_sha256,a.plan_sha256)
    result=launch(context,a.device,a.capture,a.output,a.linux_boot_id);print(json.dumps(result,sort_keys=True))
    return 0 if result['result']['verification_marker_observed'] else 1
if __name__=='__main__':raise SystemExit(main())
