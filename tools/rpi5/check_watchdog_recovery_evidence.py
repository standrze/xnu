#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Replay this exact physical recovery/restore chain; not PCIe or Ethernet acceptance."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_watchdog_recovery_trial as staging
import watchdog_recovery_serial_core as protocol
import serial_watchdog_recovery_trial as recorder

ROOT = staging.ROOT
CAPTURE = ROOT/'build/rpi5/mac-watchdog-recovery-trial-20261012'
INSTALL = ROOT/'build/rpi5/watchdog-recovery-installed-20261012'
RESTORE = ROOT/'build/rpi5/watchdog-recovery-restored-20261012'
RECEIPTS = {
    INSTALL/'plan.json':'d9fc2e230ecba051faba423b40016e1016dff063c0348841afbddf483a4fc6e6',
    INSTALL/'result.json':'2220db0f24336b6d9805336db8d73b05efdff4274dba3962bd1f4ec9b3c63b44',
    RESTORE/'plan.json':'3662df934079044577eb5147c4b907118587e32f42e82fa8f88084505c8d4468',
    RESTORE/'result.json':'bd0f0e29a6d6c11a7f4df372880fb05866d7d6d3686100e0ccd070f06181212f',
}


def journal(data, rows):
    offset, previous = 0, -math.inf
    for row in rows:
        if (type(row.get('offset')) is not int or row['offset'] != offset or type(row.get('bytes')) is not int or
                not 0 < row['bytes'] <= 4096 or type(row.get('monotonic')) not in (float,int) or
                not math.isfinite(row['monotonic']) or row['monotonic'] < previous):
            raise ValueError('Receive journal gap/regression/type/bound failure')
        if datetime.fromisoformat(row['utc']).tzinfo is None: raise ValueError('Unzoned event time')
        offset += row['bytes']; previous = row['monotonic']
    if not rows or offset != len(data): raise ValueError('Journal does not cover exact serial bytes')


def inspect():
    if any(staging.sha(path) != pin for path,pin in RECEIPTS.items()): raise ValueError('Accepted installation/restore receipt changed')
    plan = json.loads((INSTALL/'plan.json').read_text()); installed = json.loads((INSTALL/'result.json').read_text())
    restore_plan = json.loads((RESTORE/'plan.json').read_text()); restored = json.loads((RESTORE/'result.json').read_text())
    staging.validate_result(installed, plan); staging.validate_result(restored, restore_plan)
    for directory, receipt in ((INSTALL,plan),(RESTORE,restore_plan)):
        for name,pin in receipt['source_sha256'].items():
            if staging.sha(directory/'source-snapshots'/Path(name).name) != pin: raise ValueError('Archived installer source changed')
    state = json.loads((CAPTURE/'state.json').read_text()); data = (CAPTURE/'serial.bin').read_bytes()
    rows = [json.loads(line) for line in (CAPTURE/'receive-events.jsonl').read_text().splitlines()]
    journal(data, rows)
    if (state.get('status') != 'captured' or state.get('continuous_capture') is not True or
            type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes'] != 0 or
            state.get('bytes') != len(data) or state.get('serial_sha256') != hashlib.sha256(data).hexdigest() or
            state.get('error') or state.get('restore_error')): raise ValueError('Incomplete continuous zero-TX capture')
    sources = staging.source_pins() | {str(Path(recorder.__file__).resolve()):staging.sha(Path(recorder.__file__)),
        str(Path(protocol.__file__).resolve()):staging.sha(Path(protocol.__file__))}
    if state['source_sha256'] != sources: raise ValueError('Recorder source changed')
    if state['installation'] != recorder.installation(INSTALL): raise ValueError('Recorder installation binding changed')
    tag = state['installation']['preflight']['trial_tag']
    parsed = protocol.inspect(data, tag)
    if state.get('diagnostic') != parsed: raise ValueError('Saved diagnostic differs from replay')
    start, stop = data.index(protocol.PREFIX+b'ARMED'), data.index(protocol.PREFIX+b'STOP')
    tail = data[stop:]
    tokens = (b'RPi: BOOTSYS release VERSION:',b'RPi: BOOTLOADER release VERSION:',b'Boot mode: NVME (06)')
    positions = []
    for token in tokens:
        if tail.count(token) != 1: raise ValueError('Missing/ambiguous autonomous reset/boot sequence')
        positions.append(data.index(token, stop))
    if not start < stop < positions[0] < positions[1] < positions[2]: raise ValueError('Reset/boot ordering differs')
    if b'BOOT_ORDER override: 0x000000f6' not in data[positions[0]:positions[1]]:
        raise ValueError('No actual next-reset NVMe override observation')
    def event(position): return next(row for row in rows if row['offset'] <= position < row['offset']+row['bytes'])
    armed_time, bootsys_time, bootloader_time = (event(p)['monotonic'] for p in (start,positions[0],positions[1]))
    if not 10 < bootsys_time-armed_time < 45: raise ValueError('Reset sequence outside bounded diagnostic recovery window')
    returned = json.loads((CAPTURE/'linux-return.json').read_text())
    expected_root = plan['identity_binding']['expected']['root'].split()
    if (returned['boot_id'] == plan['linux_boot_id'] or returned['boot_id'] != restored['identity']['boot_id'] or
            returned['root'] != expected_root or returned['bootloader'] != {'boot-mode':6,'partition':1,'tryboot':0} or
            returned['sd_partitions_unmounted'] is not True or
            datetime.fromisoformat(returned['observed_utc']) <= datetime.fromisoformat(event(positions[2])['utc'])):
        raise ValueError('No fresh independent normal NVMe Linux return')
    if restored['image_sha256'] != staging.prior.NEW_SHA or installed['image_sha256'] != staging.IMAGE_SHA:
        raise ValueError('Wrong restored/tested image')
    return dict(recovery_trial_pass=True, watchdog_only_physical_execution=True,
        autonomous_reset_and_nvme_return_observed=True, working_zsh_image_restored=True,
        raw_reset_status_line_observed=b'AON_RESET: 00000003 PM_RSTS 00000020' in tail,
        reset_cause_register_independently_decoded=False, trial_tag=tag, diagnostic=parsed,
        host_uart_armed_to_bootsys_seconds=bootsys_time-armed_time,
        host_uart_armed_to_bootloader_seconds=bootloader_time-armed_time,
        timing_scope='Host receive timestamps including firmware startup; not exact hardware countdown duration',
        original_linux_boot_id=plan['linux_boot_id'], returned_linux_boot_id=returned['boot_id'],
        transmitted_bytes=0, installed_prior_backups=44, restored_prior_backups=48,
        next_inherited_artifact_count=52, serial_bytes=len(data), serial_sha256=staging.sha(CAPTURE/'serial.bin'),
        files_sha256={str(p.relative_to(ROOT)):staging.sha(p) for p in (*RECEIPTS,
            CAPTURE/'state.json',CAPTURE/'serial.bin',CAPTURE/'receive-events.jsonl',CAPTURE/'linux-return.json',
            INSTALL/'remote.stderr',INSTALL/'finalize-source.py',INSTALL/'finalize.stdout')},
        pcie_access_admitted=False, ethernet_ready=False, durability=False,
        scope='Single autonomous watchdog-only reset/normal SSD return and explicit verified zsh restoration; no controller/DMA/IRQ/Ethernet acceptance')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.parse_args()
    print(json.dumps(inspect(),indent=2,sort_keys=True))
