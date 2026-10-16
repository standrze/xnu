# SPDX-License-Identifier: BSD-2-Clause
"""Full raw replay and independently witnessed return; no absolute clock claim."""
import hashlib
from pathlib import Path
_parent=Path(__file__).with_name('display_xnu_evidence.py')
_raw=_parent.read_bytes()
if hashlib.sha256(_raw).hexdigest()!='330895f6d3578a4b82aacdf0554959f365a32daf0f01109b12c95c0bd1a6d9e9':
    raise ValueError('Exact frozen display evidence required')
_text=_raw.decode()
for _old,_new in (
    ('import stage_display_xnu_trial as stage','import stage_restart_diagnostic_trial as stage'),
    ('import serial_display_xnu_trial as recorder','import serial_restart_diagnostic_trial as recorder'),
    ("FORMAT='rpi5-display-xnu-independent-return-v1'","FORMAT='rpi5-restart-diagnostic-independent-return-v1'"),
    ('if not 0<delta<240 or not 0<reset_delta<220:','if not 0<delta<300 or not 0<reset_delta<220:'),
    ("tx=sum(len(command.encode('ascii'))+1 for _,command,_,_ in expected)","tx=sum(len(command.encode('ascii'))+1 for _,command,_,_ in expected)+len(p.restart_command(nonce))+1"),
    ("max_tx=sum(len(v[1])+1 for v in recorder.protocol.exchanges('D'+'0'*16))","max_tx=sum(len(v[1])+1 for v in recorder.protocol.exchanges('D'+'0'*16))+len(recorder.protocol.restart_command('D'+'0'*16))+1"),
    ("if __name__=='__main__':raise SystemExit(main())",''),
):
    if _text.count(_old)!=1:raise ValueError('Exact diagnostic evidence derivation boundary')
    _text=_text.replace(_old,_new)
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
_inspect=inspect_capture

def inspect_capture(data,rows,state,installed,sources):
    expected=recorder.initial({'installed':installed,'evidence':state['receipt_evidence_sha256']},state['device'],state['pid'],state['started_utc'])
    if not stage.engine.same(state.get('host_return_window'),expected['host_return_window']) or state.get('physical_psci_causality_proven') is not False:
        raise ValueError('Exact host-only window and unproven physical causality required')
    result=_inspect(data,rows,state,installed,sources)
    request=state.get('reboot_request');last=state['exchanges'][-1];p=recorder.protocol
    keys={'command','offset','pending_offset','pending_bytes','pending_sha256','tx_started_monotonic','tx_ended_monotonic'}
    if not isinstance(request,dict) or set(request)!=keys or request['command']!=p.restart_command(state['nonce']):raise ValueError('One exact real reboot invocation required')
    start=last['offset']+last['bytes']
    if any(type(request[k]) is not int for k in ('offset','pending_offset','pending_bytes')) or request['pending_offset']!=start or request['pending_bytes']<0 or request['offset']!=start+request['pending_bytes']:
        raise ValueError('Exact final pending/reboot slices required')
    pending=data[start:request['offset']];p.pending_safe(pending)
    if hashlib.sha256(pending).hexdigest()!=request['pending_sha256']:raise ValueError('Final pending bytes changed')
    begin,end=request['tx_started_monotonic'],request['tx_ended_monotonic'];admitted=state['admitted_monotonic']
    if not number(begin) or not number(end) or not last['response_monotonic']<=begin<=end<=admitted+120 or begin>=admitted+75:
        raise ValueError('Reboot input absolute budget/reserve/order differs')
    positions=p.return_positions(data);bootsys=positions[1]
    if not request['offset']<bootsys:raise ValueError('Reboot invocation must precede fresh firmware')
    event=next(r for r in rows if r['offset']<=bootsys+len(p.BOOTSYS)-1<r['offset']+r['bytes'])
    if end>event['monotonic']:raise ValueError('Firmware return before actual complete command')
    observed=p.reboot_observation(data[request['offset']:],state['nonce'],begin,event['monotonic'])
    if not observed['nominal_early_return']:raise ValueError('Ordered path observed but early nominal countdown comparison not satisfied')
    result.update(observed,host_return_window=expected['host_return_window'],reboot_command=request['command'],
        reboot_command_transmitted_once=True,watchdog_fallback_retained=True,poweroff_supported=False)
    return result

if __name__=='__main__':raise SystemExit(main())
