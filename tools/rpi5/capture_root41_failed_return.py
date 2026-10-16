#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only independent SSD return after an explicitly FAILED bounded trial.

This never turns an unsuccessful boot into root41/SSH acceptance. It preserves
the incomplete UART evidence and binds a new independent Linux observation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import serial_root41_trial as recorder
import audit_root41_trial as audit


def source_pins():
    return audit.return_source_pins()|{str(Path(__file__).resolve()):recorder.staging.sha(Path(__file__))}


def load_failed(directory):
    directory=audit.local_child(directory)
    state=json.loads((directory/'state.json').read_text());raw=(directory/'serial.bin').read_bytes()
    armed=json.loads((directory/'armed.json').read_text())
    if (state.get('status')!='failed' or type(state.get('transmitted_bytes')) is not int or not 0<=state['transmitted_bytes']<=631 or
        not isinstance(state.get('error'),str) or not state['error'] or
        type(state.get('command_tests_passed')) is not bool or type(state.get('normal_nvme_boot_observed')) is not bool or
        state.get('independent_linux_return_verified') is not False or state.get('bytes')!=len(raw) or
        state.get('serial_sha256')!=hashlib.sha256(raw).hexdigest() or state.get('source_sha256')!=recorder.source_pins()):
        raise ValueError('Exact failed bounded state required')
    report=recorder.package.inspect(Path(state['preflight']['image']).parent)
    installed=recorder.installation(Path(state['installation']['directory']),report)
    if state['preflight']!=report or state['installation']!=installed:raise ValueError('Failed candidate/installation differs')
    for key in ('started_utc','pid','device','baud','installation','preflight','source_sha256','receipt_evidence_sha256','package_evidence_sha256','armed_utc','armed_monotonic'):
        if state.get(key)!=armed.get(key):raise ValueError('Armed failed-trial binding differs')
    if armed.get('transmitted_bytes')!=0 or armed.get('checks')!=[] or armed.get('exchanges')!=[]:
        raise ValueError('Failed trial did not start at zero TX')
    if state['receipt_evidence_sha256']!=recorder.receipt_evidence_pins(Path(installed['directory'])):
        raise ValueError('Failed receipt ancestry changed')
    if state.get('package_evidence_sha256')!=recorder.package_evidence_pins(Path(report['image']).parent):
        raise ValueError('Failed exact package closure changed')
    plan=json.loads((Path(installed['directory'])/'plan.json').read_text())
    bound={name:recorder.staging.sha(directory/name) for name in ('armed.json','state.json','serial.bin')}
    return plan,installed,state,bound


def validate_return(value,plan,installed,state):
    # Reuse exact normal SSD/card/boot-mode verifier with its unchanged pins;
    # our own source/file binding is separately included in the result.
    return audit.inspect_return(value,plan,installed,{'serial_sha256':state['serial_sha256']})


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('capture',type=Path)
    args=parser.parse_args(argv);directory=audit.local_child(args.capture)
    target=directory/'failed-linux-return.json'
    if target.exists() or target.is_symlink():raise ValueError('Failed return evidence exists; never overwrite')
    with recorder.lease.hold(recorder.staging.ROOT,'failed-root41-independent-return'):
        plan,installed,state,bound=load_failed(directory);pins=source_pins()
        program=audit.return_program.remote_source(plan,installed,state['serial_sha256'],audit.return_source_pins())
        result=subprocess.run(recorder.staging.SSH+['sudo -n python3 -'],input=program,text=True,capture_output=True,timeout=60)
        result.check_returncode();returned=json.loads(result.stdout);boot=validate_return(returned,plan,installed,state)
        if source_pins()!=pins or load_failed(directory)!=(plan,installed,state,bound):raise ValueError('Failed-trial evidence changed during observation')
        returned['remote_program_sha256']=hashlib.sha256(program.encode()).hexdigest()
        report=dict(status='failed_trial_independent_linux_return_verified',trial_status='failed',
            failure=state['error'],zero_serial_tx=state['transmitted_bytes']==0,transmitted_bytes=state['transmitted_bytes'],
            command_tests_passed=False,root41_runtime_pass=False,
            ssh_buffer_runtime_pass=False,normal_nvme_serial_boot_proven=False,
            independent_normal_nvme_linux_return_verified=True,linux_boot_id=boot,observation=returned,
            failed_capture_sha256=bound,source_sha256=pins,ssh_daemon=False,networking=False,
            scope='Independent normal NVMe Linux/card return after a failed bounded boot; not root41, zsh or SSH-buffer runtime success')
        with target.open('x') as out:json.dump(report,out,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())
    print(json.dumps(dict(status=report['status'],trial_status='failed',linux_boot_id=boot,output=str(target))));return 0


if __name__=='__main__':raise SystemExit(main())

