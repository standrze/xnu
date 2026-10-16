#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only replay of one installed RP1-ID/return/restoration chain.

Never opens a serial port, touches media, sends SSH, reboots or restores. Host
fixtures exercise these validators but are not physical acceptance evidence.
"""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_pcie_id_trial as stage
import serial_pcie_id_trial as recorder
import pcie_id_serial_core as protocol


def same(a,b):
    return stage.base.reference.same(a,b)


def zoned(value):
    if not isinstance(value,str):raise ValueError('Zoned UTC observation time required')
    result=datetime.fromisoformat(value)
    if result.tzinfo is None:raise ValueError('Unzoned observation time')
    return result


def number(value):
    return type(value) in (int,float) and math.isfinite(value)


def receive_journal(data,rows,armed):
    if not number(armed):raise ValueError('Actual armed monotonic timestamp required')
    if not isinstance(rows,list) or not rows:raise ValueError('Complete nonempty receive journal required')
    offset=0;previous=armed;previous_utc=None
    for row in rows:
        if (not isinstance(row,dict) or set(row)!={'offset','bytes','monotonic','utc'} or
            type(row['offset']) is not int or row['offset']!=offset or type(row['bytes']) is not int or
            not 0<row['bytes']<=4096 or not number(row['monotonic']) or row['monotonic']<previous):
            raise ValueError('Receive journal gap/overlap/type/bound/time failure')
        current=zoned(row['utc'])
        if previous_utc is not None and current<previous_utc:raise ValueError('Receive UTC regressed; inspect clock/capture')
        offset+=row['bytes'];previous=row['monotonic'];previous_utc=current
    if offset!=len(data):raise ValueError('Receive journal must cover every captured byte exactly')


def inspect_capture(data,rows,state,installed,expected_sources):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:raise ValueError('Bounded nonempty serial bytes required')
    if (state.get('status')!='captured' or state.get('continuous_capture') is not True or
        type(state.get('pid')) is not int or state['pid']<=0 or type(state.get('baud')) is not int or state['baud']!=115200 or
        not isinstance(state.get('device'),str) or not re.fullmatch(r'/dev/cu\.usbmodem[A-Za-z0-9_-]+',state['device']) or
        type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes']!=0 or
        type(state.get('bytes')) is not int or state['bytes']!=len(data) or
        state.get('serial_sha256')!=hashlib.sha256(data).hexdigest() or
        any(state.get(k) for k in ('error','restore_error','diagnostic_error'))):
        raise ValueError('Incomplete/error/non-zero-TX capture')
    if not same(state.get('installation'),installed) or not same(state.get('source_sha256'),expected_sources):
        raise ValueError('Capture installed pair/source binding changed')
    if any(state.get(k) is not False for k in ('physical_reset_return_proven','xnu_pe_runtime_proven','ethernet_proven')):
        raise ValueError('Recorder must not preclaim hardware/return/XNU/Ethernet acceptance')
    receive_journal(data,rows,state.get('armed_monotonic'))
    started,armed,ended=map(zoned,(state['started_utc'],state['armed_utc'],state['ended_utc']))
    if not started<=armed<=zoned(rows[0]['utc'])<=zoned(rows[-1]['utc'])<=ended:
        raise ValueError('Capture clock/arming/coverage order differs')
    parsed=protocol.inspect(data,installed['preflight'])
    if not same(state.get('diagnostic'),parsed) or not same(state.get('inventory'),recorder.inventory(data)):
        raise ValueError('Saved diagnostic/inventory differs from raw replay')
    entry=data.index(protocol.BEGIN);owned=data.index(protocol.PREPARED);stop=data.index(protocol.PREFIX+b'END')
    if data[:entry].count(b'Boot mode: SD (01)')!=1:raise ValueError('One fresh SD boot before diagnostic required')
    tail=data[stop:];tokens=(b'RPi: BOOTSYS release VERSION:',b'RPi: BOOTLOADER release VERSION:',b'Boot mode: NVME (06)')
    positions=[]
    for token in tokens:
        if tail.count(token)!=1:raise ValueError('Missing/duplicated bounded reset/normal NVMe sequence')
        positions.append(data.index(token,stop))
    if not entry<owned<stop<positions[0]<positions[1]<positions[2]:raise ValueError('Reset/boot ordering differs')
    between=data[positions[0]:positions[1]]
    if between.count(b'BOOT_ORDER override: 0x000000f6')!=1:raise ValueError('Actual next-boot f6 override missing/ambiguous')
    if b'Boot mode: SD (01)' in tail or b'Boot mode: USB' in tail:raise ValueError('Fallback/repeated boot after trial; inspect, no retry')
    def event(p):return next(r for r in rows if r['offset']<=p<r['offset']+r['bytes'])
    elapsed=event(positions[0])['monotonic']-event(owned)['monotonic']
    if not 10<elapsed<45:raise ValueError('Prepared-to-reset observation outside claimed watchdog window')
    transfer_elapsed=event(positions[0])['monotonic']-event(data.index(protocol.TRANSFER))['monotonic']
    if not 0<transfer_elapsed<150:raise ValueError('Transfer-to-reset observation outside bounded early boot window')
    return dict(rp1_id_capture_pass=True,diagnostic=parsed,serial_sha256=state['serial_sha256'],
        serial_bytes=len(data),prepared_to_bootsys_seconds=elapsed,transfer_to_bootsys_seconds=transfer_elapsed,nvme_selected_utc=event(positions[2])['utc'],
        timing_scope='Host receive interval including firmware startup, not exact watchdog expiry or reset-cause decoding',
        subsequent_normal_nvme_boot_observed=True,independent_linux_return_proven=False,
        restored_pair_proven=False,controller_initialization_admitted=False,ethernet_proven=False)


def inspect_return(returned,plan,installed,capture):
    boot=returned.get('boot_id')
    if (not isinstance(boot,str) or not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot) or
        boot==plan['linux_boot_id'] or returned.get('host')!=stage.HOST or
        not same(returned.get('installation'),installed) or returned.get('serial_sha256')!=capture['serial_sha256'] or
        not same(returned.get('root'),plan['identity_binding']['expected']['root'].split()) or
        not same(returned.get('identity'),dict(identity=plan['identity_binding']['expected'],boot_id=boot,hostname='kamidana')) or
        not same(returned.get('bootloader'),{'boot-mode':6,'partition':1,'tryboot':0}) or
        returned.get('read_only') is not True or not same(returned.get('return_source_sha256'),return_source_pins()) or
        returned.get('sd_partitions_unmounted') is not True or
        zoned(returned['observed_utc'])<=zoned(capture['nvme_selected_utc'])):
        raise ValueError('No distinct independently verified exact-card normal NVMe Linux return')
    return boot


def return_source_pins():
    paths=(Path(__file__).resolve(),stage.ROOT/'tools/rpi5/capture_pcie_id_linux_return.py',
        Path(stage.base.MODULES[0].__file__).resolve(),Path(stage.base.reference.__file__).resolve())
    return {str(p):stage.sha(p) for p in paths}


def local_child(path):
    path=path.resolve()
    if path.parent!=stage.ROOT/'build/rpi5':raise ValueError('Explicit local build/rpi5 evidence child required')
    return path


def archived_sources(directory,plan):
    for name,pin in plan['source_sha256'].items():
        if stage.sha(directory/'source-snapshots'/Path(name).name)!=pin:raise ValueError('Archived publication source changed')


def load_capture(installation,capture):
    installation,capture=map(local_child,(installation,capture))
    installed=recorder.installation(installation)
    plan=json.loads((installation/'plan.json').read_text());archived_sources(installation,plan)
    raw=(capture/'serial.bin').read_bytes();state=json.loads((capture/'state.json').read_text())
    rows=[json.loads(line) for line in (capture/'receive-events.jsonl').read_text().splitlines()]
    sources=stage.source_pins()|{str(Path(recorder.__file__).resolve()):stage.sha(Path(recorder.__file__)),
        str(Path(protocol.__file__).resolve()):stage.sha(Path(protocol.__file__)),
        str(Path(recorder.receipt_guard.__file__).resolve()):stage.sha(Path(recorder.receipt_guard.__file__))}
    observations=inspect_capture(raw,rows,state,installed,sources)
    armed=json.loads((capture/'armed.json').read_text())
    expected={k:state[k] for k in ('started_utc','pid','device','baud','transmitted_bytes','installation',
        'source_sha256','receipt_evidence_sha256','physical_reset_return_proven','xnu_pe_runtime_proven','ethernet_proven','armed_utc','armed_monotonic')}
    expected.update(status='failed',continuous_capture=False)
    if not same(armed,expected):raise ValueError('Armed snapshot differs from terminal receive record')
    if state.get('receipt_evidence_sha256')!=recorder.receipt_guard.receipt_evidence_pins(installation):raise ValueError('Receipt byte pins differ')
    return plan,installed,observations


def inspect(installation,capture,restoration):
    installation,capture,restoration=map(local_child,(installation,capture,restoration))
    plan,installed,observations=load_capture(installation,capture)
    returned=json.loads((capture/'linux-return.json').read_text())
    boot=inspect_return(returned,plan,installed,observations)
    restore_plan=json.loads((restoration/'plan.json').read_text());result=json.loads((restoration/'result.json').read_text())
    if restore_plan['profile']!='pcie-id-pair-restore-v1':raise ValueError('Explicit dual-pair restore receipt required')
    stage.validate_result(result,restore_plan);archived_sources(restoration,restore_plan)
    ancestry=dict(directory=str(installation),hashes={n:stage.sha(installation/n) for n in ('plan.json','result.json')})
    if (not same(restore_plan['ancestry'],ancestry) or restore_plan['linux_boot_id']!=boot or
        result['identity']['boot_id']!=boot or len(restore_plan['nvme_backups'])!=87):
        raise ValueError('Restoration not bound to this exact trial/new Linux return')
    paths=(*[d/n for d in (installation,restoration) for n in ('plan.json','result.json')],
        *[capture/n for n in ('armed.json','state.json','serial.bin','receive-events.jsonl','linux-return.json')])
    return dict(rp1_id_return_restore_evidence_pass=True,capture=observations,
        independent_normal_nvme_linux_return_proven=True,working_firmware_and_zsh_restored=True,
        returned_linux_boot_id=boot,restored_pair_sha256=result['pair_sha256'],
        next_inherited_artifact_count=len(stage.inherited(restore_plan,result,92)),
        files_sha256={str(p):stage.sha(p) for p in paths},
        verifier_source_sha256={str(Path(__file__).resolve()):stage.sha(Path(__file__))},
        controller_initialization_admitted=False,power_domain_ownership_proven=False,
        xnu_pe_runtime_proven=False,ethernet_proven=False,durability=False,
        scope='Exact controller/link/RP1-ID observations, bounded reset, independent normal Linux return and dual restoration; not full production ownership, IRQ delivery, DMA, GEM, packets or durable storage')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--installation',type=Path,required=True);p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--restoration',type=Path,required=True);a=p.parse_args()
    print(json.dumps(inspect(a.installation,a.capture,a.restoration),indent=2,sort_keys=True))

