# SPDX-License-Identifier: BSD-2-Clause
"""Sealed link UART replay and independent read-only return, never inferred success."""
import hashlib
import json
from pathlib import Path
import subprocess
import types
import re
try:
    from . import stage_link_trial_v2 as stage
    from . import serial_link_trial_v2 as recorder
    from . import pcie_trace_evidence as original
    from . import capture_pcie_trace_linux_return as remote
except ImportError:
    import stage_link_trial_v2 as stage
    import serial_link_trial_v2 as recorder
    import pcie_trace_evidence as original
    import capture_pcie_trace_linux_return as remote


def return_source_pins():
    return stage.source_pins()|{str(Path(m.__file__).resolve()):stage.sha(Path(m.__file__)) for m in (original,remote)}


def inspect_return(value,context,observed):
    globals_=dict(original.__dict__,stage=stage,return_source_pins=return_source_pins,same=stage.engine.same)
    fn=types.FunctionType(original.inspect_return.__code__,globals_)
    return fn(value,context['plan']['media'],context['installed'],observed)


def captured(context,directory):
    directory=stage.local(directory);recorder.revalidate(context)
    state=json.loads((directory/'state.json').read_text());armed=json.loads((directory/'armed.json').read_text())
    raw=(directory/'serial.bin').read_bytes();rows=[json.loads(v) for v in (directory/'receive-events.jsonl').read_text().splitlines()]
    sources=recorder.bound_sources(context)
    if (not stage.engine.same(state.get('installation'),context['installed']) or
        not stage.engine.same(state.get('source_sha256'),sources) or
        not stage.engine.same(state.get('receipt_evidence_sha256'),context['evidence']) or
        type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes']!=0 or
        type(state.get('bytes')) is not int or state['bytes']!=len(raw) or len(raw)>4*1024*1024 or
        type(state.get('pid')) is not int or state['pid']<=0 or type(state.get('baud')) is not int or state['baud']!=115200 or
        not isinstance(state.get('device'),str) or not re.fullmatch(r'/dev/cu\.usbmodem[A-Za-z0-9_-]+',state['device']) or
        any(state.get(k) is not False for k in ('physical_reset_return_proven','xnu_pe_runtime_proven','ethernet_proven')) or
        state.get('serial_sha256')!=hashlib.sha256(raw).hexdigest()):raise ValueError('Exact sealed zero-TX capture required')
    for key in ('started_utc','pid','device','baud','installation','source_sha256','receipt_evidence_sha256','armed_utc','armed_monotonic'):
        if not stage.engine.same(state.get(key),armed.get(key)):raise ValueError('Armed binding differs')
    expected={k:state[k] for k in ('started_utc','pid','device','baud','transmitted_bytes','installation',
        'source_sha256','receipt_evidence_sha256','physical_reset_return_proven','xnu_pe_runtime_proven','ethernet_proven',
        'armed_utc','armed_monotonic')}
    expected.update(status='failed',continuous_capture=False)
    if not stage.engine.same(armed,expected):raise ValueError('Exact zero-TX armed receipt required')
    if not original.zoned(state['started_utc'])<=original.zoned(state['armed_utc'])<=original.zoned(state['ended_utc']):
        raise ValueError('Failed capture clock order differs')
    protocol=context['descriptor']['protocol']
    globals_=dict(original.__dict__,stage=stage,protocol=protocol,recorder=types.SimpleNamespace(inventory=protocol.inventory),same=stage.engine.same)
    fn=types.FunctionType(original.inspect_capture.__code__,globals_)
    try:observed=fn(raw,rows,state,context['installed'],sources)
    except (ValueError,KeyError,TypeError) as error:
        if state.get('status') not in ('failed','captured'):raise ValueError('Unknown recorder outcome')
        if raw:original.receive_journal(raw,rows,state['armed_monotonic'])
        elif rows:raise ValueError('Empty capture has unexpected receive journal')
        observed=dict(trace_capture_valid=False,serial_sha256=state['serial_sha256'],nvme_selected_utc=state['ended_utc'],
            diagnostic_error=str(error),rp1_id_trial_pass=False,ethernet_proven=False)
    return state,observed,{n:stage.sha(directory/n) for n in ('armed.json','state.json','serial.bin','receive-events.jsonl')}


def collect_return(context,directory):
    directory=stage.local(directory)
    if (directory/'return.json').exists():raise ValueError('Return exists; never overwrite/retry implicitly')
    state,observed,bound=captured(context,directory);pins=return_source_pins()
    program=remote.remote_source(context['plan']['media'],context['installed'],state['serial_sha256'],pins)
    result=subprocess.run(stage.SSH+['sudo -n python3 -'],input=program,text=True,capture_output=True,timeout=60)
    result.check_returncode();value=json.loads(result.stdout);boot=inspect_return(value,context,observed)
    if captured(context,directory)!=(state,observed,bound) or return_source_pins()!=pins:raise ValueError('Evidence changed during observation')
    result=dict(format='rpi5-next-link-independent-return-v2',capture_valid=observed['trace_capture_valid'],
        diagnostic=observed.get('diagnostic'),capture_error=observed.get('diagnostic_error'),
        observation=value,linux_boot_id=boot,capture_sha256=bound,installation=context['installed'],
        source_sha256=pins,remote_source_sha256=hashlib.sha256(program.encode()).hexdigest(),
        zero_serial_tx=True,independent_normal_nvme_linux_return_verified=True,ethernet_proven=False)
    stage.save(directory/'return.json',result)
    return result


def load_return(context,directory):
    directory=stage.local(directory);value=json.loads((directory/'return.json').read_text())
    state,observed,bound=captured(context,directory)
    if (value.get('format')!='rpi5-next-link-independent-return-v2' or value.get('installation')!=context['installed'] or
        value.get('source_sha256')!=return_source_pins() or value.get('capture_sha256')!=bound or
        value.get('capture_valid') is not observed['trace_capture_valid'] or
        value.get('diagnostic')!=observed.get('diagnostic') or value.get('capture_error')!=observed.get('diagnostic_error') or
        value.get('zero_serial_tx') is not True or value.get('independent_normal_nvme_linux_return_verified') is not True or
        value.get('ethernet_proven') is not False):raise ValueError('Exact independent return receipt required')
    boot=inspect_return(value['observation'],context,observed)
    if value.get('linux_boot_id')!=boot:raise ValueError('Return boot differs')
    program=remote.remote_source(context['plan']['media'],context['installed'],state['serial_sha256'],return_source_pins())
    if value.get('remote_source_sha256')!=hashlib.sha256(program.encode()).hexdigest():
        raise ValueError('Exact independent observation program differs')
    return value,boot
