# SPDX-License-Identifier: BSD-2-Clause
"""Twelve-command API-observation successor; no entropy-quality claim.

Only exact schema tokens are adapted from immutable engines. The linked
watchdog profile remains root42's; crypto names/vectors are never renumbered.
"""
import hashlib
import inspect
from pathlib import Path
import re
import secrets
import time
import types
try:
    from . import root42_pthread_trial_core as original
    from . import root43_packet_trial_core as packet
    from . import root42_ready_trial_core as old_ready
except ImportError:
    import root42_pthread_trial_core as original
    import root43_packet_trial_core as packet
    import root42_ready_trial_core as old_ready

helpers=old_ready.helpers
replace=packet.replace
t=original.t
previous,identity,statprobe,metadata=(getattr(original,n) for n in ('previous','identity','statprobe','metadata'))
DEVICE,FDT,WATCHDOG,IDENTITY,CRYPTO_BEGIN,CRYPTO_PASS,PWD_STARTUP,PTHREAD_LINES=(getattr(original,n) for n in
    ('DEVICE','FDT','WATCHDOG','IDENTITY','CRYPTO_BEGIN','CRYPTO_PASS','PWD_STARTUP','PTHREAD_LINES'))
WATCHDOG_PROFILE=old_ready.WATCHDOG_PROFILE
PACKET_LINES=packet.PACKET_LINES
RUNTIME_FAULTS=packet.RUNTIME_FAULTS
STEPS=packet.prior.STEPS+(('entropy','/usr/local/libexec/xnu/entropyprobe'),
    ('rand','/usr/local/libexec/xnu/kernel_randprobe'))
CHECKS=['fresh_exact_45node_state_confirmed_root_after_watchdog_reload','complete_33file_identity_and_self_hash',
    'fresh_nonce_batched_twelve_results_and_zero_statuses','real_batch_zsh_zero_exit_and_live_recovery']
COUNTERS=(('kern.entropy.health.startup_done',1),
    ('kern.entropy.health.repetition_count_test.reset_count',2**32-1),
    ('kern.entropy.health.repetition_count_test.failure_count',0),
    ('kern.entropy.health.repetition_count_test.max_observation_count',2**32-1),
    ('kern.entropy.health.adaptive_proportion_test.reset_count',2**32-1),
    ('kern.entropy.health.adaptive_proportion_test.failure_count',0),
    ('kern.entropy.health.adaptive_proportion_test.max_observation_count',2**32-1),
    ('kern.entropy.filter.total_sample_count',2**64-1),
    ('kern.entropy.filter.accepted_sample_count',2**64-1),
    ('kern.entropy.filter.rejected_sample_count',2**64-1))
ENTROPY_END=b'RPI5XNU:ENTROPY:API_OK CALLS=5 COUNTERS=10 UNAVAILABLE=0 HEALTH_FAILURE=0 QUALITY_NOT_PROVEN'
RAND_LINES=(*PTHREAD_LINES,b'RPI5XNU:RAND:API_OK REQUESTS=5 KERNEL_GETENTROPY_ADAPTER NO_RANDOM_OUTPUT QUALITY_NOT_PROVEN')
pending_safe,drain_pending,returned,bounded_exchange,clean_lines,nonce_valid=(getattr(original,n) for n in
    ('pending_safe','drain_pending','returned','bounded_exchange','clean_lines','nonce_valid'))
unsafe_response=packet.unsafe_response


def script(nonce):
    nonce_valid(nonce)
    return ('n='+nonce+'; print -r -- B45:$n:BEGIN; '
        'r(){ local k=$1 s; shift; print -r -- B45:$n:$k:B; "$@"; s=$?; '
        'print -r -- B45:$n:$k:E:$s; ((s==0)) || exit $s; }; '+
        '; '.join('r '+name+' '+command for name,command in STEPS)+
        '; print -r -- B45:$n:END:0; exit 0')


batch_command=helpers.private(original.batch_command,script=script)


def recovery_command(nonce):
    nonce_valid(nonce)
    return 'echo B45:'+nonce+':RECOVERY_STATUS:$?'


def markers(nonce):
    nonce_valid(nonce)
    return [('B45:'+nonce+':'+v).encode() for v in
        ('BEGIN',*(p for name,_ in STEPS for p in (name+':B',name+':E:0')),'END:0')]


def validate_root(receipt,files):
    rows=receipt.get('identity_catalog',[]);expected={r['path']:r for r in rows if r.get('sha256')}
    if (type(receipt.get('output_nodes')) is not int or receipt['output_nodes']!=45 or
        len(rows)!=45 or len(expected)!=33 or set(files)!=set(expected)):
        raise ValueError('Exact 45-node/33-file catalog required')
    for path,(raw,mode) in files.items():
        row=expected[path]
        if row['bytes']!=len(raw) or row['mode']!=mode|0o100000 or row['sha256']!=hashlib.sha256(raw).hexdigest():
            raise ValueError('Actual file differs from 45-node identity')


def entropy_values(lines):
    if len(lines)!=len(PTHREAD_LINES)+11 or lines[:3]!=list(PTHREAD_LINES) or lines[-1]!=ENTROPY_END:
        raise ValueError('Exact entropy startup, counter count and API-only ending required')
    values={}
    for row,(name,limit) in zip(lines[3:-1],COUNTERS):
        match=re.fullmatch(rb'RPI5XNU:ENTROPY:COUNTER NAME='+re.escape(name.encode())+rb' VALUE=(0|[1-9][0-9]{0,19})',row)
        if not match or int(match[1])>limit:raise ValueError('Ordered typed entropy observation differs: '+name)
        values[name]=int(match[1])
    # Separate sysctl reads are not an atomic snapshot. Do not invent cross-row
    # arithmetic invariants or mistake startup_done=0/1 for quality approval.
    return values


text=inspect.getsource(original.inspect_batch)
text=replace(text,"(b'B42:',b'B41:')","(b'B45:',b'B43:',b'B42:',b'B41:')",1)
text=replace(text,'batch_framing_and_all_nine_statuses_zero','batch_framing_and_all_twelve_statuses_zero',1)
inspect_scope={**globals(),'t':types.SimpleNamespace(**{**vars(t),'FORBIDDEN':tuple(v for v in t.FORBIDDEN if v!=b'REJECTED')})}
exec(compile(text,str(Path(__file__).resolve()),'exec'),inspect_scope)
_inspect=inspect_scope['inspect_batch']


def inspect_batch(raw,nonce,files):
    if unsafe_response(raw):raise ValueError('Unsafe entropy batch response')
    result=helpers.private(_inspect,clean_lines=clean_lines)(raw,nonce,files)
    lines=clean_lines(raw)
    def body(name):
        start=('B45:'+nonce+':'+name+':B').encode();end=('B45:'+nonce+':'+name+':E:0').encode()
        return lines[lines.index(start)+1:lines.index(end)]
    if body('packet')!=list(PACKET_LINES):raise ValueError('Actual packet startup/cipher diagnostic output differs')
    counters=entropy_values(body('entropy'))
    if body('rand')!=list(RAND_LINES):raise ValueError('Actual kernel-backed RAND API output differs')
    result.update(actual_original_ssh_libressl_packet_cipher_diagnostic=True,valid_packet_cases=48,rejected_packet_cases=5036,
        actual_kernel_getentropy_api_checks=True,actual_libressl_rand_kernel_adapter=True,
        entropy_counter_observations=counters,entropy_startup_done_observed=counters[COUNTERS[0][0]],
        random_bytes_or_hashes_recorded=False,entropy_qualified=False,keys_generated=False,
        entropy_scope='API return/error behavior and separate read-only counters; no entropy-quality or key-safety proof',
        crypto_scope='Public primitive and packet cipher diagnostics; not SSH transport, key exchange or entropy proof')
    return result


text=inspect.getsource(original.commands)
text=replace(text,"observed['nodes']!=42 or observed['file_hashes']!=30","observed['nodes']!=45 or observed['file_hashes']!=33",1)
text=replace(text,"'B42:'","'B45:'",1)
text=replace(text,'Exact mounted 42-node identity required','Exact mounted 45-node identity required',1)
command_scope=globals().copy();exec(compile(text,str(Path(__file__).resolve()),'exec'),command_scope)
commands=command_scope['commands']
prior=types.SimpleNamespace(**{**globals(),'prior':types.SimpleNamespace(**{**vars(original.prior),'unsafe_response':unsafe_response})})

text=Path(old_ready.__file__).read_text()
for old,new,count in (
    ('fresh_exact_42node_state_confirmed_root_after_watchdog_reload','fresh_exact_45node_state_confirmed_root_after_watchdog_reload',1),
    ('MOUNT NODES=42','MOUNT NODES=45',1),("(b'180',b'42',mount[1])","(b'180',b'45',mount[1])",1),
    ('ROOT42_READY_TRIAL','ROOT45_ENTROPY_TRIAL',2),('ROOT_NODES=42','ROOT_NODES=45',1),
    ("report.get('root_nodes')!=42 or report.get('root_files')!=30","report.get('root_nodes')!=45 or report.get('root_files')!=33",1)):
    text=replace(text,old,new,count)
ready=packet.module('root45_entropy_ready_private',text)
ready.prior=prior;ready.CHECKS=CHECKS;ready.batch_command=batch_command;ready.recovery_command=recovery_command
contract,snapshots,_boot_ready=ready.contract,ready.snapshots,ready.boot_ready


def validate_report(report):
    contract(report)
    if (type(report.get('root_nodes')) is not int or report['root_nodes']!=45 or
        type(report.get('root_files')) is not int or report['root_files']!=33 or
        report.get('watchdog_ready_profile')!=WATCHDOG_PROFILE or report.get('watchdog_ready_marker')!=WATCHDOG.decode() or
        any(report.get('handoff',{}).get(k) is not True for k in
            ('required_by_kernel','linked_loader_handoff','descriptor_not_confused_with_kernel_string'))):
        raise ValueError('Exact unchanged kernel/33-file linked report required')


def boot_ready(raw,report):
    if any(marker in raw for marker in RUNTIME_FAULTS):raise RuntimeError('Runtime fault before admission; zero TX')
    return _boot_ready(raw,report)
ready.boot_ready=boot_ready


def bind(report):
    validate_report(report)
    return ready.bind(report)
