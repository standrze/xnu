#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserve the exact failed W2 before a cache-buffer diagnostic replacement.

Local plan only by default. Historical failed artifacts are pinned, not freshly
rescreened against changed source. Only the new package is freshly inspected.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

import stage_hfs_write_diagnostic as previous

installer=previous.installer
PREVIOUS_IMAGE='65347b15c3852991556b6f324ff7b9fc77ccb00552fc2b17431d46b0946e70ed'
PREVIOUS_PLAN='1270baccb7b92ffc2743520ae0bc05d654d50b317e5c8a6f5fefe044f1902121'
PREVIOUS_RESULT='2bb67c22787b84417e08daec36597f7b87bd39f5d038a0e9bd464391eac0a06e'
PREVIOUS_STATE='8dc8c2e4e122c314999f488200da0946ab419abd7141bbc238b97afb661c9c6d'
PREVIOUS_RAW='f7decb76a3a6b654b6e27cfc2908766504b6b1606459a9a9de39399c155c778d'
FAILURE=b'RPI5XNU:SD:WRITE_INIT_FAIL STAGE=CACHE_PROBE RC=-5 CMD=13 STATUS=0x1 CACHE=0 SPEC=0'
DIAGNOSTICS=(b'RPI5XNU:SD:CACHE_PROBE_FAIL STAGE=',b'RPI5XNU:SD:CACHE_PROBE_BYTES OFFSET=')


def validate_failure(path,plan,result,hashes):
    state=json.loads(path.read_text())
    raw_path=installer.evidence_path(str(path.with_name('serial.bin')))
    if raw_path.stat().st_size>2*1024*1024: raise ValueError('Oversized failed cache capture')
    raw=raw_path.read_bytes(); raw_sha=hashlib.sha256(raw).hexdigest()
    expected=dict(status='failed',error='Unsafe, old or failed boot before write input',
        image_sha256=PREVIOUS_IMAGE,checks=[],reads=[],transmitted_bytes=0,write_batch_attempts=0,
        hfs_mounted=False,durability_verified=False,partition='/dev/disk0s2',baud=115200,
        linux_boot_id_before_write=plan['linux_boot_id'])
    if (installer.checker.sha256(path)!=PREVIOUS_STATE or raw_sha!=PREVIOUS_RAW
            or any(type(state.get(k)) is not type(v) or state[k]!=v for k,v in expected.items())
            or state.get('write_input_sha256')!=plan['evidence_sha256']
            or state.get('evidence_sha256',{}).get('plan')!=hashes['previous_plan']
            or state.get('evidence_sha256',{}).get('result')!=hashes['previous_result']
            or type(state.get('bytes')) is not int or state['bytes']!=len(raw)
            or state.get('serial_sha256')!=raw_sha
            or any(raw.count(marker)!=1 for marker in (previous.TERMINAL_LOADER,previous.WRITE_LOADER,
                b'RPI5XNU:HFS:REGISTERED',b'RPI5XNU:SD:WRITE_START_BEGIN',
                b'RPI5XNU:SD:WRITE_INIT_BEGIN',FAILURE,
                b'RPI5XNU:SD:WRITE_START_FAIL STAGE=INITIALIZE'))
            or not re.search(rb'(?m)^'+re.escape(FAILURE)+rb'\r{0,2}\n',raw)
            or raw.count(b'RPI5XNU:SHELL:READY')<2
            or any(marker in raw for marker in (*installer.boot.trial.ABORT_MARKERS,
                b'RPI5XNU:SD:WRITE_ADMITTED',b'RPI5XNU:HFSRW:',b'RPI5XNU:HFSWRITE:',
                b'RPI5XNU:SD:WRITE_CACHE_OBSERVED'))):
        raise ValueError('Not the exact preserved unsupported cache-probe zero-input failure')
    return dict(state_sha256=installer.checker.sha256(path),serial_sha256=raw_sha)


def load_plan(inputs,now=None):
    spec=json.loads(inputs.read_text())
    if not isinstance(spec,dict) or set(spec)!={'current_inputs','previous_plan','previous_result','previous_trial'}:
        raise ValueError('Exact cache diagnostic evidence bundle required')
    paths={key:installer.evidence_path(value) for key,value in spec.items()}
    hashes={key:installer.checker.sha256(path) for key,path in paths.items()}
    if hashes['previous_plan']!=PREVIOUS_PLAN or hashes['previous_result']!=PREVIOUS_RESULT:
        raise ValueError('Historical W2 installation artifacts changed')
    old=json.loads(paths['previous_plan'].read_text()); result=json.loads(paths['previous_result'].read_text())
    if (old.get('profile')!='write-diagnostic' or old.get('new_image_sha256')!=PREVIOUS_IMAGE
            or old.get('old_image_sha256')!=previous.PREVIOUS_IMAGE
            or old.get('readonly_image_sha256')!=installer.checker.HFS_READ_BASELINE_SHA256
            or not re.fullmatch(r'/home/sandrzej/xnu-gate4-hfs-write-[a-z0-9_]{8}',old.get('run',''))):
        raise ValueError('Not the actual W2 installation and preserved W1/RO chain')
    installer.validate_result(result,old)
    physical=validate_failure(paths['previous_trial'],old,result,hashes)
    current=installer.load_plan(paths['current_inputs'],now=now)
    for key in ('host','expected','fixture_sha256','current_mbr_sha256','backup_run','boot_backup_sha256',
                'original_mbr_sha256','prior_boot_run','prior_correction_run','passed_sd_image_sha256','failed_hfs_image_sha256'):
        if current[key]!=old[key]: raise ValueError('Fresh identity/prerequisite differs: '+key)
    if (current['linux_boot_id']==old['linux_boot_id']
            or current['old_image_sha256']!=old['readonly_image_sha256']
            or current['new_image_sha256'] in (PREVIOUS_IMAGE,previous.PREVIOUS_IMAGE)):
        raise ValueError('New SSD boot, preserved RO and distinct cache diagnostic image required')
    inner=json.loads(paths['current_inputs'].read_text())
    package=json.loads(installer.evidence_path(inner['write_preflight']).read_text())
    build=json.loads(Path(package['kernel_build_manifest']).read_text())
    actual=Path(build['kernel_artifact']['path']).read_bytes()
    if any(marker not in actual for marker in DIAGNOSTICS):
        raise ValueError('Actual linked kernel lacks cache stage/buffer diagnostics')
    current.update(profile='write-cache-diagnostic',old_image_sha256=PREVIOUS_IMAGE,
        readonly_image_sha256=old['readonly_image_sha256'],
        no_admission_image_sha256=old['old_image_sha256'],prior_write_run=old['prior_write_run'],
        prior_write_backup_sha256=old['prior_write_backup_sha256'],prior_cache_run=old['run'],
        prior_cache_backup_sha256={row['saved_as']:row['sha256'] for row in result['write_trial_backups']['before']},
        expected_boot_before_sha256=result['write_trial_backups']['after']['boot']['sha256'],
        cache_diagnostic_evidence_sha256=hashes,previous_failed_physical_capture=physical)
    if any(installer.checker.sha256(path)!=hashes[key] for key,path in paths.items()):
        raise ValueError('Cache diagnostic evidence changed during validation')
    raw_path=installer.evidence_path(str(paths['previous_trial'].with_name('serial.bin')))
    if installer.checker.sha256(raw_path)!=physical['serial_sha256']:
        raise ValueError('Historical cache serial bytes changed during validation')
    return current


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',required=True,type=Path); parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--execute',action='store_true'); args=parser.parse_args()
    if not args.output.resolve().is_relative_to(installer.ROOT/'build/rpi5'):
        parser.error('Use a fresh build/rpi5 output directory')
    return installer.run_install(args.inputs,args.output,args.execute,plan_loader=load_plan)


if __name__=='__main__': raise SystemExit(main())
