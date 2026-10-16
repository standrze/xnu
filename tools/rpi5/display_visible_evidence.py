# SPDX-License-Identifier: BSD-2-Clause
"""Actual DISPLAYVISIBLE/raw RX timing and independent NVMe identity, no XNU admission."""
import hashlib
import json
from pathlib import Path
import re
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_display_visible_trial as stage
import serial_display_visible_trial as recorder
import root42_pthread_evidence as base
import pcie_trace_evidence as identity
FORMAT='rpi5-display-visible-independent-return-v1'
def source_pins(context):return recorder.bound_sources(context)
def inspect_capture(data,rows,state,installed,sources):
    if (state.get('status')!='captured' or state.get('continuous_capture') is not True or state.get('normal_nvme_boot_observed') is not True or
        type(state.get('pid')) is not int or state['pid']<=0 or not recorder.valid_device(state.get('device')) or
        type(state.get('baud')) is not int or state['baud']!=115200 or type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes']!=0 or
        type(state.get('bytes')) is not int or state['bytes']!=len(data) or not 0<len(data)<=4*1024*1024 or
        state.get('serial_sha256')!=hashlib.sha256(data).hexdigest() or any(state.get(k) for k in ('error','restore_error','diagnostic_error')) or
        not stage.engine.same(state.get('installation'),installed) or not stage.engine.same(state.get('source_sha256'),sources)):
        raise ValueError('Incomplete, changed or non-zero-input observer capture')
    identity.receive_journal(data,rows,state.get('armed_monotonic'))
    started,armed,ended=map(identity.zoned,(state['started_utc'],state['armed_utc'],state['ended_utc']))
    if not started<=armed<=identity.zoned(rows[0]['utc'])<=identity.zoned(rows[-1]['utc'])<=ended:raise ValueError('Observer timestamp order differs')
    if not 0<(ended-started).total_seconds()<840:raise ValueError('Observer overall clock bound differs')
    parsed=recorder.protocol.inspect(data,installed['preflight'])
    if not stage.engine.same(state.get('diagnostic'),parsed) or parsed.get('diagnostic_pass') is not True or state.get('drawing') is not parsed.get('drawing') or state.get('framebuffer_memory_access') is not parsed.get('framebuffer_memory_access'):raise ValueError('Complete successful observation required')
    positions=recorder.return_positions(data)
    if positions is None:raise ValueError('No complete following NVMe selection')
    sd,bootsys,bootloader,nvme=positions;entry=data.index(recorder.ENTRY);armed_at=data.index(recorder.ARMED)
    stop=data.index(b'RPI5XNU:DISPLAYVISIBLE:STOP TAG=')
    if not sd<entry<armed_at<stop<bootsys<bootloader<nvme:raise ValueError('Fresh SD/observer/return order differs')
    if data.count(recorder.SD)!=1 or data[entry:].count(recorder.BOOTSYS)!=1 or data[entry:].count(recorder.BOOTLOADER)!=1 or data[entry:].count(recorder.NVME)!=1:
        raise ValueError('Repeated/ambiguous boot sequence')
    if data[bootsys:bootloader].count(b'BOOT_ORDER override: 0x000000f6')!=1 or b'Boot mode: USB' in data[stop:]:raise ValueError('Expected bounded normal f6 return absent')
    # Qualify every captured byte from entry through the final RX chunk. A
    # return-firmware fault is distinct from an observer fault, but both fail
    # this bounded trial; independent Linux recovery cannot rehabilitate it.
    fault=rb'(?i)(panic\(|panic:|Debugger message:|RPI5XNU:[^\r\n]*(?:FAULT|EXCEPTION))'
    if re.search(fault,data[entry:bootsys]):
        raise ValueError('Observer runtime fault before subsequent BOOTSYS')
    if re.search(fault,data[bootsys:]):
        raise ValueError('Return firmware fault in complete captured tail')
    def event(p):return next(row for row in rows if row['offset']<=p<row['offset']+row['bytes'])
    delta=event(bootsys)['monotonic']-event(armed_at)['monotonic'];sd_delta=event(nvme)['monotonic']-event(sd)['monotonic']
    if not 0<delta<30 or not 0<sd_delta<150:raise ValueError('Observed watchdog/return timing exceeded')
    return dict(capture_valid=True,diagnostic=parsed,serial_sha256=state['serial_sha256'],serial_bytes=len(data),
        armed_to_bootsys_seconds=delta,sd_to_nvme_seconds=sd_delta,nvme_selected_utc=event(nvme)['utc'],
        timing_scope='Host receive intervals including UART/firmware startup, not exact hardware reset expiry',
        independent_linux_return_proven=False,ownership_proven=False,scanout_cache_contract_proven=False)
def captured(context,directory):
    recorder.revalidate(context);directory=stage.local(directory)
    state=json.loads((directory/'state.json').read_text());armed=json.loads((directory/'armed.json').read_text())
    raw=(directory/'serial.bin').read_bytes();rows=[json.loads(line) for line in (directory/'receive-events.jsonl').read_text().splitlines()]
    expected=recorder.initial(context,state.get('device'),state.get('pid'),state.get('started_utc'))
    expected.update(armed_utc=state.get('armed_utc'),armed_monotonic=state.get('armed_monotonic'))
    if not stage.engine.same(armed,expected):raise ValueError('Exact zero-TX armed observer snapshot required')
    for k in ('installation','source_sha256','receipt_evidence_sha256','package_evidence_sha256'):
        if not stage.engine.same(state.get(k),expected[k]):raise ValueError('Observer receipt/source binding changed')
    if (state.get('status') not in ('captured','failed') or type(state.get('bytes')) is not int or state['bytes']!=len(raw) or
        state.get('serial_sha256')!=hashlib.sha256(raw).hexdigest() or type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes']!=0 or
        not recorder.valid_device(state.get('device')) or type(state.get('pid')) is not int or state['pid']<=0 or
        any(state.get(k) is not False for k in ('independent_linux_return_verified','ownership_proven','scanout_cache_contract_proven','physical_visibility_proven','mirror_enabled'))):
        raise ValueError('Changed/unsafe observer outcome; recovery cannot rehabilitate it')
    if state.get('framebuffer_store_phase_authored') is not True:raise ValueError('Exact authored visible phase required')
    diagnostic=error=None;selected=state.get('ended_utc')
    try:
        diagnostic=inspect_capture(raw,rows,state,context['installed'],recorder.bound_sources(context));selected=diagnostic['nvme_selected_utc']
    except (ValueError,KeyError,IndexError,StopIteration) as invalid:error=state.get('diagnostic_error') or str(invalid)
    observed=dict(capture_valid=diagnostic is not None,diagnostic=diagnostic,capture_error=error,
        serial_sha256=state['serial_sha256'],nvme_selected_utc=selected,independent_linux_return_proven=False,physical_visibility_proven=False,visual_confirmation_required=True,networking=False,ssh_daemon=False)
    return state,observed,{n:stage.sha(directory/n) for n in ('armed.json','state.json','serial.bin','receive-events.jsonl')}
scope={**vars(base),'stage':stage,'recorder':recorder,'FORMAT':FORMAT,'source_pins':source_pins,'captured':captured,
    '__file__':__file__,'__doc__':__doc__}
for name in ('inspect_return','collect_return','load_return','main'):
    fn=getattr(base,name);scope[name]=types.FunctionType(fn.__code__,scope,argdefs=fn.__defaults__);globals()[name]=scope[name]
if __name__=='__main__':raise SystemExit(main())


