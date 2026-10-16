# SPDX-License-Identifier: BSD-2-Clause
"""Pure offline replay for the three-exchange 41-node protocol; no hardware IO.

The future installed-image adapter must validate exact package/receipt/source
pins before invoking this function. It does not infer Linux return or storage
restoration from a serial boot banner.
"""
import hashlib
import math
try:
    from . import root41_batch_trial_core as core
except ImportError:
    import root41_batch_trial_core as core


def replay_commands(state,raw,report,receipt,files):
    core.validate_root(receipt,files)
    nonce=state.get('nonce');core.nonce_valid(nonce)
    expected_commands=(core.IDENTITY,core.batch_command(nonce),core.recovery_command(nonce))
    expected_lines=([b'ROOTIDENTITY:PASS:COMPARE_SELF_AND_EXTENT_EXTERNALLY',b'ROOT_IDENTITY_STATUS:0'],
        core.markers(nonce),[('B41:'+nonce+':RECOVERY_STATUS:0').encode()])
    if (state.get('checks')!=core.CHECKS or type(state.get('transmitted_bytes')) is not int or
        state['transmitted_bytes']!=sum(len(v)+1 for v in expected_commands) or
        state.get('serial_sha256')!=hashlib.sha256(raw).hexdigest() or state.get('bytes')!=len(raw)):
        raise ValueError('Incomplete command checks/byte transcript/TX extent')
    duration=state.get('commands_complete_seconds_after_admission')
    if type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<120:
        raise ValueError('Actual bounded command completion time absent')
    exchanges=state.get('exchanges')
    if not isinstance(exchanges,list) or len(exchanges)!=3:raise ValueError('Exactly three exchanges required')
    cursor=exchanges[0].get('pending_offset')
    if type(cursor) is not int or not 0<cursor<len(raw) or not core.boot_ready(raw[:cursor],report):
        raise ValueError('No exact new ready-after-watchdog boot before first TX')
    observed=batch=None
    for index,(row,name,command,expected) in enumerate(zip(exchanges,
        ('identity','batch','recovery_status'),expected_commands,expected_lines)):
        pending_bytes=row.get('pending_bytes')
        if (row.get('pending_offset')!=cursor or type(pending_bytes) is not int or not 0<=pending_bytes<=65536 or
            cursor+pending_bytes>len(raw)):raise ValueError('Pending RX ranges differ')
        pending=raw[cursor:cursor+pending_bytes];cursor+=pending_bytes
        if row.get('pending_sha256')!=hashlib.sha256(pending).hexdigest():raise ValueError('Pending RX digest differs')
        core.pending_safe(pending)
        length=row.get('bytes')
        if (row.get('name')!=name or row.get('command')!=command or row.get('offset')!=cursor or
            type(length) is not int or not 0<length<=65536 or cursor+length>len(raw)):
            raise ValueError('Actual command/range differs')
        chunk=raw[cursor:cursor+length];cursor+=length
        if row.get('response_sha256')!=hashlib.sha256(chunk).hexdigest() or core.unsafe_response(chunk):
            raise ValueError('Changed or unsafe command bytes')
        core.previous.exact_lines(chunk,expected)
        if not core.t.response_complete(chunk,expected,core.t.shell.PROMPT):raise ValueError('Missing subsequent command prompt')
        if index==0:observed=core.identity.validate(chunk,receipt)
        if index==1:batch=core.inspect_batch(chunk,nonce,files)
    batch['batch_process_exit_verified']=True
    if state.get('runtime_identity')!=observed or state.get('batch')!=batch:
        raise ValueError('Declared identity/batch does not reproduce from raw results')
    if state.get('return_capture_offset')!=cursor:raise ValueError('Unaccounted UART bytes between commands and return')
    return dict(command_protocol_replayed=True,command_end_offset=cursor,runtime_identity=observed,batch=batch,
        ssh_daemon=False,ssh_transport=False,networking=False,independent_linux_return=False,
        scope='Exact fresh-boot 29-file identity, eight command outputs/statuses and actual zero zsh exit/recovery; return and restoration require separate witnesses')
