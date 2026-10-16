#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserve the actual zero-TX failed write image before a diagnostic replacement.

Local validation by default. Fresh SSD/card/HFS evidence and a freshly inspected
new package are mandatory. The historical installation is pinned to its actual
immutable artifacts, not rescreened against later edited source files.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

import stage_hfs_write_trial as installer
from check_hfs_write_package import WRITE_LOADER
from serial_terminal_trial import TERMINAL_LOADER

PREVIOUS_IMAGE='dd8eecb8f6fd989d8d29ce8c5b2837a3c6c49dd67a62bb0b40bec67f90397506'
PREVIOUS_PLAN='d02f05628fb93717bb4391fa2cb9974b3701dfbde008cdfd31763e71191f23b6'
PREVIOUS_RESULT='f32cdc1db19f0703bc6fdc5dc1819da62516158927c6fa4b421f2c18c7c18ba0'
PREVIOUS_STATE='151c45f7f699e5ff131ee5dab8cf2727a30287495ed08ac31d7a7b9ef3d96dda'
PREVIOUS_RAW='7439b383feaa7c0869daaf1abac99d8e2266ece80fce161f3fe83f238e7fb4bb'


def validate_failure(path,plan,result,hashes):
    state=json.loads(path.read_text()); raw_path=installer.evidence_path(str(path.with_name('serial.bin')))
    if raw_path.stat().st_size>2*1024*1024:
        raise ValueError('Oversized failed startup capture')
    raw=raw_path.read_bytes()
    expected=dict(status='failed',error='No complete fresh write-image admission/HFS/shell boot; zero input',
        image_sha256=PREVIOUS_IMAGE,checks=[],reads=[],transmitted_bytes=0,write_batch_attempts=0,
        hfs_mounted=False,durability_verified=False,partition='/dev/disk0s2',baud=115200,
        linux_boot_id_before_write=plan['linux_boot_id'])
    if (installer.checker.sha256(path)!=PREVIOUS_STATE or hashlib.sha256(raw).hexdigest()!=PREVIOUS_RAW
            or any(type(state.get(k)) is not type(v) or state[k]!=v for k,v in expected.items())
            or state.get('write_input_sha256')!=plan['evidence_sha256']
            or state.get('evidence_sha256',{}).get('plan')!=hashes['previous_plan']
            or state.get('evidence_sha256',{}).get('result')!=hashes['previous_result']
            or type(state.get('bytes')) is not int or state['bytes']!=len(raw)
            or state.get('serial_sha256')!=hashlib.sha256(raw).hexdigest()
            or any(raw.count(marker)!=1 for marker in (TERMINAL_LOADER,WRITE_LOADER,b'RPI5XNU:HFS:REGISTERED'))
            or raw.count(b'RPI5XNU:SHELL:READY')<2
            or any(marker in raw for marker in (*installer.boot.trial.ABORT_MARKERS,
                b'RPI5XNU:SD:WRITE_ADMITTED',b'RPI5XNU:HFSRW:',b'RPI5XNU:HFSWRITE:'))):
        raise ValueError('Not the exact preserved zero-TX missing-admission failure')
    return dict(state_sha256=installer.checker.sha256(path),serial_sha256=hashlib.sha256(raw).hexdigest())


def load_plan(inputs,now=None):
    spec=json.loads(inputs.read_text())
    required={'current_inputs','previous_plan','previous_result','previous_trial'}
    if not isinstance(spec,dict) or set(spec)!=required:
        raise ValueError('Exact diagnostic evidence bundle required')
    paths={key:installer.evidence_path(value) for key,value in spec.items()}
    hashes={key:installer.checker.sha256(path) for key,path in paths.items()}
    if hashes['previous_plan']!=PREVIOUS_PLAN or hashes['previous_result']!=PREVIOUS_RESULT:
        raise ValueError('Historical write installation artifacts changed')
    previous=json.loads(paths['previous_plan'].read_text())
    result=json.loads(paths['previous_result'].read_text())
    if (previous.get('profile')!='write-trial' or previous.get('new_image_sha256')!=PREVIOUS_IMAGE
            or not re.fullmatch(r'/home/sandrzej/xnu-gate4-hfs-write-[a-z0-9_]{8}',previous.get('run',''))):
        raise ValueError('Not the actual previous write installation')
    installer.validate_result(result,previous)
    physical=validate_failure(paths['previous_trial'],previous,result,hashes)
    current=installer.load_plan(paths['current_inputs'],now=now)
    for key in ('host','expected','fixture_sha256','current_mbr_sha256','backup_run','boot_backup_sha256',
                'original_mbr_sha256','prior_boot_run','prior_correction_run','passed_sd_image_sha256','failed_hfs_image_sha256'):
        if current[key]!=previous[key]:
            raise ValueError('Fresh identity/prerequisite differs from original installation: '+key)
    if (current['linux_boot_id']==previous['linux_boot_id']
            or current['old_image_sha256']!=previous['old_image_sha256']
            or current['new_image_sha256']==PREVIOUS_IMAGE):
        raise ValueError('New SSD boot, preserved RO image and distinct diagnostic image required')
    kernel=Path(json.loads(paths['current_inputs'].read_text())['write_preflight'])
    if not kernel.is_absolute(): kernel=installer.ROOT/kernel
    package=json.loads(kernel.read_text())
    build=json.loads(Path(package['kernel_build_manifest']).read_text())
    actual=Path(build['kernel_artifact']['path']).read_bytes()
    diagnostics=(b'RPI5XNU:SD:WRITE_START_BEGIN',b'RPI5XNU:SD:WRITE_INIT_BEGIN',
        b'RPI5XNU:SD:WRITE_INIT_FAIL STAGE=',b'RPI5XNU:SD:WRITE_START_FAIL STAGE=',
        b'RPI5XNU:SD:WRITE_CACHE_OBSERVED CACHE=')
    if any(marker not in actual for marker in diagnostics):
        raise ValueError('Actual linked kernel lacks first-failed-stage diagnostics')
    current.update(profile='write-diagnostic',old_image_sha256=PREVIOUS_IMAGE,
        readonly_image_sha256=previous['old_image_sha256'],prior_write_run=previous['run'],
        expected_boot_before_sha256=result['write_trial_backups']['after']['boot']['sha256'],
        prior_write_backup_sha256={row['saved_as']:row['sha256'] for row in result['write_trial_backups']['before']},
        diagnostic_evidence_sha256=hashes,previous_failed_physical_capture=physical)
    if any(installer.checker.sha256(path)!=hashes[key] for key,path in paths.items()):
        raise ValueError('Diagnostic installation evidence changed during validation')
    return current


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',required=True,type=Path); parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--execute',action='store_true'); args=parser.parse_args()
    if not args.output.resolve().is_relative_to(installer.ROOT/'build/rpi5'):
        parser.error('Use a fresh build/rpi5 output directory')
    return installer.run_install(args.inputs,args.output,args.execute,plan_loader=load_plan)


if __name__=='__main__': raise SystemExit(main())
