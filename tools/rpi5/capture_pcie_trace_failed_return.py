#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Independent Linux witness after failed RP1 trace capture; never marks ID passed."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import pcie_trace_evidence as evidence
import capture_pcie_trace_linux_return as normal
stage,recorder=evidence.stage,evidence.recorder


def failed(directory):
    directory=evidence.local_child(directory);state=json.loads((directory/'state.json').read_text())
    raw=(directory/'serial.bin').read_bytes();installed=recorder.installation(Path(state['installation']['directory']))
    sources=stage.source_pins()|{str(Path(m.__file__).resolve()):stage.sha(Path(m.__file__)) for m in
        (recorder,recorder.protocol,recorder.receipt_guard)}
    valid_failure=False
    if 'diagnostic' in state:
        _,_,observed=evidence.load_capture(Path(installed['directory']),directory)
        valid_failure=observed['diagnostic']['rp1_id_trial_pass'] is False
        if not valid_failure:raise ValueError('Failed collector cannot accept RP1-ID success')
    if (state.get('status') not in ('failed','captured') or type(state.get('transmitted_bytes')) is not int or
        state['transmitted_bytes']!=0 or not (valid_failure or state.get('error') or state.get('diagnostic_error')) or
        not raw or state.get('bytes')!=len(raw) or state.get('serial_sha256')!=hashlib.sha256(raw).hexdigest() or
        not evidence.same(state.get('installation'),installed) or not evidence.same(state.get('source_sha256'),sources) or
        state.get('receipt_evidence_sha256')!=recorder.receipt_guard.receipt_evidence_pins(Path(installed['directory']))):
        raise ValueError('Exact failed zero-TX RP1 trace evidence required')
    armed=json.loads((directory/'armed.json').read_text())
    for key in ('started_utc','pid','device','baud','installation','source_sha256','receipt_evidence_sha256','armed_utc','armed_monotonic'):
        if not evidence.same(armed.get(key),state.get(key)):raise ValueError('Failed capture armed binding differs')
    if armed.get('transmitted_bytes')!=0:raise ValueError('Nonzero armed TX')
    plan=json.loads((Path(installed['directory'])/'plan.json').read_text())
    evidence.archived_sources(Path(installed['directory']),plan)
    bound={name:stage.sha(directory/name) for name in ('armed.json','state.json','serial.bin','receive-events.jsonl')}
    return plan,installed,state,bound


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('capture',type=Path);args=parser.parse_args(argv)
    directory=evidence.local_child(args.capture);target=directory/'failed-linux-return.json'
    if target.exists() or target.is_symlink():raise ValueError('Failed return already recorded; never overwrite')
    with recorder.lease.hold(stage.ROOT,'failed-rp1-trace-linux-return'):
        plan,installed,state,bound=failed(directory)
        sources=evidence.return_source_pins();own=stage.sha(Path(__file__))
        program=normal.remote_source(plan,installed,state['serial_sha256'],sources)
        result=subprocess.run(stage.SSH+['sudo -n python3 -'],input=program,text=True,capture_output=True,timeout=60)
        result.check_returncode();returned=json.loads(result.stdout)
        observations={'serial_sha256':state['serial_sha256'],'nvme_selected_utc':state['ended_utc']}
        boot=evidence.inspect_return(returned,plan,installed,observations)
        if sources!=evidence.return_source_pins() or stage.sha(Path(__file__))!=own or failed(directory)!=(plan,installed,state,bound):
            raise ValueError('Failed evidence/source changed during independent return')
        returned['remote_program_sha256']=hashlib.sha256(program.encode()).hexdigest()
        report=dict(status='failed_trace_independent_linux_return_verified',rp1_id_trial_pass=False,
            trial_failure=state.get('diagnostic',state.get('diagnostic_error',state.get('error'))),zero_serial_tx=True,
            independent_normal_nvme_linux_return_verified=True,normal_nvme_serial_boot_proven=False,
            linux_boot_id=boot,observation=returned,failed_capture_sha256=bound,
            failed_collector_sha256=own,ethernet_proven=False,dma=False,irq_delivery=False)
        with target.open('x') as out:json.dump(report,out,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())
    print(json.dumps(dict(status=report['status'],linux_boot_id=boot,output=str(target))));return 0


if __name__=='__main__':raise SystemExit(main())

