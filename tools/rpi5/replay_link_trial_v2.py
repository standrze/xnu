#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only v2 chain replay; deliberately outside the original admission seal.

Only the sealed controller modules run inside an isolated Python subprocess.
This new reporting wrapper cannot authorize hardware or amend old receipts.
No SSH, serial, block-device, mount, reboot, compiler or historical audit calls.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
PROGRAM=r'''
import json,sys
from pathlib import Path
from tools.rpi5 import stage_link_trial_v2 as stage
from tools.rpi5 import link_trial_evidence_v2 as evidence
args=json.loads(sys.argv[1])
def forbidden(*a,**kw):raise AssertionError('Read-only replay attempted a full audit or hardware operation')
stage.full_install_audit=forbidden
stage.prior.validate_result=forbidden
stage.subprocess.run=forbidden
context=stage.load_installation(args['installation'],args['seal_sha256'],args['plan_sha256'])
context['descriptor']['checker'].inspect=forbidden
returned,boot=evidence.load_return(context,args['capture'])
# Reconstruct the exact restoration seal through the already sealed return
# validator. This is byte-only; it does not rerun the historical/package audit.
expected,expected_sha,metrics=stage.prepare_restore(args['installation'],args['seal_sha256'],args['plan_sha256'],args['capture'])
if expected_sha!=args['restore_seal_sha256']:raise ValueError('Restoration seal does not derive from this installation/capture/return')
directory=stage.local(args['restoration'])
checkpoint=json.loads((directory/'checkpoint.json').read_text())
payload=stage.seals.revalidate(checkpoint,args['restore_seal_sha256'])
if not stage.engine.same(checkpoint,expected):raise ValueError('Restoration checkpoint differs')
plan=json.loads((directory/'plan.json').read_text());result=json.loads((directory/'result.json').read_text())
if plan['media']['profile']!=stage.engine.RESTORE:raise ValueError('Explicit original-pair restoration required')
exact,pin=stage.engine.plan_from_seal(checkpoint,args['restore_seal_sha256'],stage.engine.RESTORE,
    plan['tag'],plan['media']['run'],payload['media_plan'])
if pin!=args['restore_plan_sha256'] or not stage.engine.same(plan,exact):raise ValueError('Restoration plan differs from retained digest')
stage.engine.validate_result(result,plan,args['restore_plan_sha256'])
if result['publication']['identity']['boot_id']!=boot:raise ValueError('Restoration does not use independently observed Linux boot')
if len(context['plan']['historical_catalog'])!=128 or len(context['result']['next_catalog'])!=133 or len(result['next_catalog'])!=138:
    raise ValueError('Exact128 to133 to138 archival metadata transition required')
if result['publication']['pair_sha256']!={n:v[1] for n,v in stage.GOOD.items()}:raise ValueError('Original pair not restored')
paths=[Path(args['installation'])/n for n in ('checkpoint.json','plan.json','result.json')]
paths += [Path(args['capture'])/n for n in ('armed.json','state.json','serial.bin','receive-events.jsonl','return.json')]
paths += [directory/n for n in ('checkpoint.json','plan.json','result.json')]
diagnostic=returned['diagnostic']
report=dict(format='rpi5-next-link-v2-read-only-chain-replay',publication_return_restoration_receipts_verified=True,
    capture_valid=returned['capture_valid'],diagnostic=diagnostic,capture_error=returned['capture_error'],
    rp1_id_trial_pass=bool(diagnostic and diagnostic.get('rp1_id_trial_pass') is True),
    zero_serial_tx=True,independent_normal_nvme_linux_return_verified=True,returned_linux_boot_id=boot,
    working_firmware_and_zsh_restored=True,restored_pair_sha256=result['publication']['pair_sha256'],
    historical_catalog_counts=[128,133,138],historical_archives_reverified=False,
    active_baseline_archive_count=len(result['active_baseline_archives_verified']),current_rollback_archive_count=len(result['newly_created_rollback_archives_verified']),
    fresh_hardware_observation=False,ethernet_proven=False,compiler_calls=0,historical_semantic_audit_calls=0,
    files_sha256={str(p.resolve()):stage.sha(p) for p in paths})
print(json.dumps(report,sort_keys=True))
'''


def run(arguments):
    result=subprocess.run([sys.executable,'-c',PROGRAM,json.dumps(arguments)],cwd=ROOT,text=True,capture_output=True,timeout=90)
    if result.returncode:raise ValueError('Read-only chain replay failed: '+result.stderr[-12000:])
    report=json.loads(result.stdout)
    report['replay_wrapper_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['isolated_program_sha256']=hashlib.sha256(PROGRAM.encode()).hexdigest()
    report['wrapper_part_of_original_admission_seal']=False
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('installation','capture','restoration','seal-sha256','plan-sha256','restore-seal-sha256','restore-plan-sha256'):
        p.add_argument('--'+flag,required=True)
    args=vars(p.parse_args(argv));print(json.dumps(run(args),indent=2))


if __name__=='__main__':main()
