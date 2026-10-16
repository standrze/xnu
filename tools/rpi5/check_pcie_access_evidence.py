#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Replay exact physical read-only access, continuous recovery and zsh restore."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_pcie_access_trial as stage
import serial_pcie_access_trial as recorder
import pcie_access_serial_core as protocol
from check_watchdog_recovery_evidence import journal

ROOT=stage.ROOT
INSTALL=ROOT/'build/rpi5/pcie-access-installed-20261012'
RESTORE=ROOT/'build/rpi5/pcie-access-restored-20261012'
CAPTURE=ROOT/'build/rpi5/mac-pcie-access-trial-20261012'
RECEIPTS={
    INSTALL/'plan.json':'a9f0221690bf6f86ea513cbd76bc90dba598dd855a3cb60e6004f7245fa3f075',
    INSTALL/'result.json':'c7f3291048eb640d888e39c55020b88ab2f78beb0c7f63b721be75945bf18cf5',
    RESTORE/'plan.json':'b61c5f43270dd15f9195939dca5eaaa5de5ecf26a845adb8e561bf8e80e5c546',
    RESTORE/'result.json':'0dd7f83b3b63906ca03128d90a71befa00b4afa90ae2aaef3c0b769593f04f80',
}


def inspect():
    if any(stage.sha(p)!=pin for p,pin in RECEIPTS.items()):raise ValueError('Accepted access/restore receipt changed')
    plan=json.loads((INSTALL/'plan.json').read_text());installed=json.loads((INSTALL/'result.json').read_text())
    restore_plan=json.loads((RESTORE/'plan.json').read_text());restored=json.loads((RESTORE/'result.json').read_text())
    stage.validate_result(installed,plan);stage.validate_result(restored,restore_plan)
    for directory,receipt in ((INSTALL,plan),(RESTORE,restore_plan)):
        for name,pin in receipt['source_sha256'].items():
            if stage.sha(directory/'source-snapshots'/Path(name).name)!=pin:raise ValueError('Archived source changed')
    state=json.loads((CAPTURE/'state.json').read_text());data=(CAPTURE/'serial.bin').read_bytes()
    rows=[json.loads(line) for line in (CAPTURE/'receive-events.jsonl').read_text().splitlines()];journal(data,rows)
    if (state.get('status')!='captured' or state.get('continuous_capture') is not True or
            type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes']!=0 or
            state.get('bytes')!=len(data) or state.get('serial_sha256')!=hashlib.sha256(data).hexdigest() or
            state.get('error') or state.get('restore_error')):raise ValueError('Incomplete uninterrupted zero-TX capture')
    sources=stage.source_pins()|{str(Path(recorder.__file__).resolve()):stage.sha(Path(recorder.__file__)),
        str(Path(protocol.__file__).resolve()):stage.sha(Path(protocol.__file__))}
    if state['source_sha256']!=sources or state['installation']!=recorder.installation(INSTALL):
        raise ValueError('Recorder/image/installation binding changed')
    parsed=protocol.inspect(data,stage.IMAGE_SHA)
    if state.get('diagnostic')!=parsed or state.get('access_inventory')!=protocol.inventory(data):
        raise ValueError('Saved access observations differ from actual replay')
    entry=data.index(protocol.PREFIX+b'ENTRY');armed=data.index(protocol.PREFIX+b'ARMED');stop=data.index(protocol.PREFIX+b'STOP')
    if b'Boot mode: SD (01)' not in data[:entry]:raise ValueError('No fresh SD boot before access image')
    tail=data[stop:];tokens=(b'RPi: BOOTSYS release VERSION:',b'RPi: BOOTLOADER release VERSION:',b'Boot mode: NVME (06)')
    positions=[]
    for token in tokens:
        if tail.count(token)!=1:raise ValueError('Missing/ambiguous subsequent recovery boot')
        positions.append(data.index(token,stop))
    if not entry<armed<stop<positions[0]<positions[1]<positions[2]:raise ValueError('Recovery ordering differs')
    if b'BOOT_ORDER override: 0x000000f6' not in data[positions[0]:positions[1]]:raise ValueError('Actual reset override absent')
    def event(p):return next(r for r in rows if r['offset']<=p<r['offset']+r['bytes'])
    elapsed=event(positions[0])['monotonic']-event(armed)['monotonic']
    if not 10<elapsed<45:raise ValueError('Reset outside bounded recovery window')
    returned=json.loads((CAPTURE/'linux-return.json').read_text())
    if (returned['boot_id']==plan['linux_boot_id'] or returned['boot_id']!=restored['identity']['boot_id'] or
            returned['root']!=plan['identity_binding']['expected']['root'].split() or
            returned['bootloader']!={'boot-mode':6,'partition':1,'tryboot':0} or returned['sd_partitions_unmounted'] is not True or
            datetime.fromisoformat(returned['observed_utc'])<=datetime.fromisoformat(event(positions[2])['utc'])):
        raise ValueError('No new independently verified normal NVMe Linux return')
    values=parsed['register_values'];status=values[3]['value'];control=values[4]['value']
    return dict(read_only_access_trial_pass=True,autonomous_recovery_observed=True,working_zsh_image_restored=True,
        diagnostic=parsed,pass_values_equal=all(values[i]['value']==values[15+i]['value'] for i in range(15)),
        controller_status=status,controller_control=control,
        project_link_up_predicate_observed=(status&0xf0)==0xb0,
        project_rc_down_predicate_observed=(status&0xf0)==0x80,
        status_scope='Existing project link.c mask predicates only; stale link-status fields are not a negotiated live link',
        host_uart_armed_to_bootsys_seconds=elapsed,
        timing_scope='Host receive timestamps including firmware startup, not exact watchdog expiry time',
        original_linux_boot_id=plan['linux_boot_id'],returned_linux_boot_id=returned['boot_id'],
        transmitted_bytes=0,serial_bytes=len(data),serial_sha256=stage.sha(CAPTURE/'serial.bin'),
        installed_prior_backups=52,restored_prior_backups=56,next_inherited_artifact_count=60,
        restored_image_sha256=restored['image_sha256'],restored_fat_sha256=restored['protected_after']['boot']['sha256'],
        files_sha256={str(p.relative_to(ROOT)):stage.sha(p) for p in (*RECEIPTS,CAPTURE/'state.json',CAPTURE/'serial.bin',
            CAPTURE/'receive-events.jsonl',CAPTURE/'linux-return.json')},
        controller_initialization_admitted=False,rp1_enumerated=False,irq_delivery_proven=False,dma=False,nic_ready=False,durability=False,
        scope='Single actual bounded 30-register read trial plus autonomous normal SSD return and explicit verified restoration; not controller writes or Ethernet')


if __name__=='__main__':print(json.dumps(inspect(),indent=2,sort_keys=True))
