# SPDX-License-Identifier: BSD-2-Clause
"""Exact ten-command successor over frozen batch and late-state engines.

Fixed source substitutions change only this namespace's root geometry/frame.
The tenth executable has an exact oracle; output never substitutes for the
separate recovery-shell process status. No source, port or board is mutated.
"""
from pathlib import Path
import types
try:
    from . import root42_pthread_trial_core as old_commands
    from . import root42_ready_trial_core as old_ready
except ImportError:
    import root42_pthread_trial_core as old_commands
    import root42_ready_trial_core as old_ready


def replace(text,old,new,count):
    if text.count(old)!=count:raise ValueError('Frozen packet protocol derivation boundary changed: '+old)
    return text.replace(old,new)


def module(name,text):
    result=types.ModuleType(name);result.__file__=str(Path(__file__).resolve());result.__package__=old_commands.__package__
    exec(compile(text,result.__file__,'exec'),result.__dict__)
    return result


text=Path(old_commands.__file__).read_text()
for old,new,count in (('42','43',23),('30','31',6),('nine','ten',3),
    ("(b'B43:',b'B41:')","(b'B43:',b'B42:',b'B41:')",1)):
    text=replace(text,old,new,count)
prior=module('root43_packet_commands_private',text)
prior.STEPS=prior.STEPS+(('packet','/usr/local/libexec/xnu/sshpacketprobe'),)
PACKET_LINES=(*prior.PTHREAD_LINES,
    b'RPI5XNU:SSHPACKET:PASS CASES=48 REJECTED=5036 NO_TRANSPORT_OR_ENTROPY_PROOF')
_inspect=prior.inspect_batch
clean_lines=prior.clean_lines
helpers=old_ready.helpers
_old_unsafe=prior.prior.unsafe_response
RUNTIME_FAULTS=(b'Debugger message: panic',b'panic(',b'panic:')


def unsafe_response(raw):
    # The genuine PASS diagnostic includes the word REJECTED. Mask only its
    # exact whole row (or a still-valid trailing UART prefix while receiving).
    # Every other rejection, mismatch, reset and fault remains fatal. Exact
    # final output and process status are checked separately below.
    if any(marker in raw for marker in RUNTIME_FAULTS):return True
    rows=prior.t.normalized(raw).splitlines(keepends=True);masked=[]
    for index,row in enumerate(rows):
        if row==PACKET_LINES[-1]+b'\n':continue
        if index==len(rows)-1 and not row.endswith(b'\n') and PACKET_LINES[-1].startswith(row):continue
        masked.append(row)
    return _old_unsafe(b''.join(masked))


prior.prior=types.SimpleNamespace(**{**vars(prior.prior),'unsafe_response':unsafe_response})
_batch_t=types.SimpleNamespace(**{**vars(prior.t),'FORBIDDEN':tuple(v for v in prior.t.FORBIDDEN if v!=b'REJECTED')})


def inspect_packet_batch(raw,nonce,files):
    if unsafe_response(raw):raise ValueError('Unsafe packet batch response')
    result=helpers.private(_inspect,clean_lines=clean_lines,t=_batch_t)(raw,nonce,files)
    lines=clean_lines(raw);begin=('B43:'+nonce+':packet:B').encode();end=('B43:'+nonce+':packet:E:0').encode()
    if lines[lines.index(begin)+1:lines.index(end)]!=list(PACKET_LINES):raise ValueError('Actual packet startup/cipher diagnostic output differs')
    result.update(actual_original_ssh_libressl_packet_cipher_diagnostic=True,valid_packet_cases=48,rejected_packet_cases=5036,
        crypto_scope='Public primitive and packet cipher diagnostics; not SSH transport, key exchange or entropy proof')
    return result


prior.inspect_batch=inspect_packet_batch
text=Path(old_ready.__file__).read_text()
for old,new,count in (('42','43',10),('30','31',1),
    ('root43_pthread_trial_core as prior','root42_pthread_trial_core as prior',2),
    ('ROOT43_READY_TRIAL','ROOT43_PACKET_TRIAL',2)):
    text=replace(text,old,new,count)
ready=module('root43_packet_ready_private',text)
ready.prior=prior
# Root namespace changed; the actual linked kernel and its profile did not.
ready.WATCHDOG_PROFILE=old_ready.WATCHDOG_PROFILE
ready.CHECKS=['fresh_exact_43node_state_confirmed_root_after_watchdog_reload',*prior.CHECKS[1:]]
ready.batch_command,ready.recovery_command=prior.batch_command,prior.recovery_command
t=ready.t
CHECKS,WATCHDOG_PROFILE,IDENTITY=ready.CHECKS,ready.WATCHDOG_PROFILE,ready.IDENTITY
batch_command,recovery_command=prior.batch_command,prior.recovery_command
contract,snapshots,_boot_ready=ready.contract,ready.snapshots,ready.boot_ready


def boot_ready(raw,report):
    if any(marker in raw for marker in RUNTIME_FAULTS):raise RuntimeError('Runtime fault before admission; zero TX')
    return _boot_ready(raw,report)
ready.boot_ready=boot_ready


def validate_report(report):
    contract(report)
    if (type(report.get('root_nodes')) is not int or report['root_nodes']!=43 or
        type(report.get('root_files')) is not int or report['root_files']!=31 or
        report.get('watchdog_ready_profile')!=old_ready.WATCHDOG_PROFILE or
        report.get('watchdog_ready_marker')!=prior.WATCHDOG.decode() or
        any(report.get('handoff',{}).get(k) is not True for k in
            ('required_by_kernel','linked_loader_handoff','descriptor_not_confused_with_kernel_string'))):
        raise ValueError('Exact unchanged kernel/31-file linked report required')


def bind(report):
    # The frozen binder rebinds clean_lines for both the ten-body inspector
    # and the exact packet-body check. No closure or frozen module is mutated.
    validate_report(report)
    return ready.bind(report)
