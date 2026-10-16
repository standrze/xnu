# SPDX-License-Identifier: BSD-2-Clause
"""Actual mirrored-zsh command replay, complete RX tail and independent Linux.

Successful UART proof does not assert physical visibility or a production OS.
Recovery from an incomplete/failed trial remains failed runtime evidence.
"""
import hashlib
import json
import math
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_display_xnu_trial as stage
import serial_display_xnu_trial as recorder
import root42_pthread_evidence as base
import pcie_trace_evidence as identity
FORMAT='rpi5-display-xnu-independent-return-v1'
def source_pins(context):return recorder.bound_sources(context)
def number(value):return type(value) in (int,float) and math.isfinite(value) and value>=0

def inspect_capture(data,rows,state,installed,sources):
    p=recorder.protocol
    if (state.get('status')!='captured' or state.get('continuous_capture') is not True or state.get('normal_nvme_boot_observed') is not True or
        state.get('command_tests_passed') is not True or type(state.get('pid')) is not int or state['pid']<=0 or
        not recorder.valid_device(state.get('device')) or type(state.get('baud')) is not int or state['baud']!=115200 or
        type(state.get('bytes')) is not int or state['bytes']!=len(data) or not 0<len(data)<=p.MAX_BYTES or
        state.get('serial_sha256')!=hashlib.sha256(data).hexdigest() or any(state.get(k) for k in ('error','restore_error','trial_error')) or
        not stage.engine.same(state.get('installation'),installed) or not stage.engine.same(state.get('source_sha256'),sources)):
        raise ValueError('Incomplete/changed/faulted display-zsh capture')
    identity.receive_journal(data,rows,state.get('armed_monotonic'))
    started,armed,ended=map(identity.zoned,(state['started_utc'],state['armed_utc'],state['ended_utc']))
    if not started<=armed<=identity.zoned(rows[0]['utc'])<=identity.zoned(rows[-1]['utc'])<=ended or not 0<(ended-started).total_seconds()<900:
        raise ValueError('Bounded ordered capture timestamps required')
    p.healthy(data);p.runtime_lines(data)
    positions=p.return_positions(data)
    if positions is None:raise ValueError('Complete following BOOTSYS/BOOTLOADER/NVMe required')
    sd,bootsys,bootloader,nvme=positions
    if data.count(p.SD)!=1 or data[sd:].count(p.BOOTSYS)!=1 or data[sd:].count(p.BOOTLOADER)!=1 or data[sd:].count(p.NVME)!=1:
        raise ValueError('Repeated/ambiguous return boot')
    if data[bootsys:bootloader].count(b'BOOT_ORDER override: 0x000000f6')!=1 or b'Boot mode: USB' in data[bootsys:]:
        raise ValueError('Expected bounded f6/NVMe return absent')
    admitted=state.get('admitted_monotonic');extent=state.get('admission_bytes')
    if not number(admitted) or type(extent) is not int or not 0<extent<=bootsys or not p.boot_ready(data[:extent],installed['preflight']):
        raise ValueError('Actual exact fresh readiness prefix required before any TX')
    def event(position):return next(r for r in rows if r['offset']<=position<r['offset']+r['bytes'])
    if not event(extent-1)['monotonic']<=admitted:raise ValueError('Admission predates received readiness')
    delta=event(nvme)['monotonic']-event(sd)['monotonic']
    reset_delta=event(bootsys)['monotonic']-event(data.index(p.WATCHDOG))['monotonic']
    if not 0<delta<240 or not 0<reset_delta<220:raise ValueError('Bounded180s terminal/15s watchdog return exceeded')
    nonce=state.get('nonce');expected=p.exchanges(nonce);exchanges=state.get('exchanges')
    if not isinstance(exchanges,list) or len(exchanges)!=4:raise ValueError('All four real interactive exchanges required')
    tx=sum(len(command.encode('ascii'))+1 for _,command,_,_ in expected)
    if type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes']!=tx:raise ValueError('Exact bounded total UART input differs')
    last=extent;proof=[];last_time=admitted
    for row,(name,command,_,_) in zip(exchanges,expected):
        if (row.get('name')!=name or row.get('command')!=command or
            any(type(row.get(k)) is not int for k in ('offset','bytes','pending_offset','pending_bytes')) or
            row['pending_offset']!=last or row['pending_bytes']<0 or row['offset']!=last+row['pending_bytes'] or
            row['bytes']<=0 or row['offset']+row['bytes']>bootsys):raise ValueError('Actual response/pending slices differ')
        pending=data[last:row['offset']];p.pending_safe(pending)
        if row.get('pending_sha256')!=hashlib.sha256(pending).hexdigest():raise ValueError('Pending RX changed')
        response=data[row['offset']:row['offset']+row['bytes']]
        checked=p.inspect_exchange(response,name,nonce)
        if any(not stage.engine.same(row.get(k),v) for k,v in checked.items()):raise ValueError('Actual zsh output proof changed')
        times=[row.get(k) for k in ('tx_started_monotonic','tx_ended_monotonic','response_monotonic')]
        if not all(number(v) for v in times) or not last_time<=times[0]<=times[1]<=times[2]<=admitted+120 or times[0]>=admitted+75:
            raise ValueError('Actual TX absolute budget/reserve/order differs')
        if event(row['offset']+row['bytes']-1)['monotonic']>times[2]:raise ValueError('Response proof predates bytes')
        proof.append(checked);last=row['offset']+row['bytes'];last_time=times[2]
    return dict(capture_valid=True,diagnostic_pass=True,actual_zsh_version='5.9',interactive_zsh=True,
        actual_version_builtins_external_exec_smoke_verified=True,actual_interactive_exit_zero=True,
        fresh_nonce=nonce,commands=proof,serial_sha256=state['serial_sha256'],serial_bytes=len(data),
        uart_transmitted_bytes=tx,admission_to_final_response_seconds=last_time-admitted,
        watchdog_ready_to_bootsys_seconds=reset_delta,sd_to_nvme_seconds=delta,
        nvme_selected_utc=event(nvme)['utc'],kernel_mirror_ready_observed=True,
        physical_visibility_proven=False,visual_confirmation_required=True,networking=False,ssh_daemon=False,
        timing_scope='Host RX timing; unchanged180s service deadline plus15s hardware expiry, not a15s standalone run',
        independent_linux_return_proven=False)

def captured(context,directory):
    recorder.revalidate(context);directory=stage.local(directory)
    state=json.loads((directory/'state.json').read_text());armed=json.loads((directory/'armed.json').read_text())
    raw=(directory/'serial.bin').read_bytes();rows=[json.loads(s) for s in (directory/'receive-events.jsonl').read_text().splitlines()]
    expected=recorder.initial(context,state.get('device'),state.get('pid'),state.get('started_utc'))
    expected.update(armed_utc=state.get('armed_utc'),armed_monotonic=state.get('armed_monotonic'))
    if not stage.engine.same(armed,expected):raise ValueError('Exact zero-TX pre-admission ARMED snapshot required')
    for key in ('installation','source_sha256','receipt_evidence_sha256','package_evidence_sha256'):
        if not stage.engine.same(state.get(key),expected[key]):raise ValueError('Sealed recorder receipt/source binding changed')
    max_tx=sum(len(v[1])+1 for v in recorder.protocol.exchanges('D'+'0'*16))
    if (state.get('status') not in ('captured','failed') or type(state.get('bytes')) is not int or state['bytes']!=len(raw) or len(raw)>recorder.protocol.MAX_BYTES or
        state.get('serial_sha256')!=hashlib.sha256(raw).hexdigest() or type(state.get('transmitted_bytes')) is not int or not 0<=state['transmitted_bytes']<=max_tx or
        any(state.get(k) is not False for k in ('independent_linux_return_verified','physical_visibility_proven','networking','ssh_daemon'))):
        raise ValueError('Unsafe/changed outcome cannot authorize restoration')
    diagnostic=error=None;selected=state.get('ended_utc')
    try:
        diagnostic=inspect_capture(raw,rows,state,context['installed'],recorder.bound_sources(context))
        if not stage.engine.same(state.get('diagnostic'),diagnostic):raise ValueError('Saved capture diagnostic differs')
        selected=diagnostic['nvme_selected_utc']
    except (ValueError,KeyError,IndexError,StopIteration) as invalid:
        diagnostic=None;error=state.get('diagnostic_error') or str(invalid)
    observed=dict(capture_valid=diagnostic is not None,diagnostic=diagnostic,capture_error=error,
        serial_sha256=state['serial_sha256'],nvme_selected_utc=selected,independent_linux_return_proven=False,
        physical_visibility_proven=False,networking=False,ssh_daemon=False)
    return state,observed,{n:stage.sha(directory/n) for n in ('armed.json','state.json','serial.bin','receive-events.jsonl')}

scope={**vars(base),'stage':stage,'recorder':recorder,'FORMAT':FORMAT,'source_pins':source_pins,'captured':captured,'__file__':__file__,'__doc__':__doc__}
for name in ('inspect_return','collect_return','load_return','main'):
    fn=getattr(base,name);scope[name]=types.FunctionType(fn.__code__,scope,argdefs=fn.__defaults__);globals()[name]=scope[name]
if __name__=='__main__':raise SystemExit(main())
