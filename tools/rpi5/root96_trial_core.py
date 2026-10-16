# SPDX-License-Identifier: BSD-2-Clause
"""Guarded complete mounted-root identity, real zsh and SSH-buffer execution."""
import hashlib
import re
import secrets
import os
import select
import time
import types
try:
    from . import socket_identity_trial_core as prior
    from . import socket_identity_evidence as identity
except ImportError:
    import socket_identity_trial_core as prior
    import socket_identity_evidence as identity
t=prior.t
BEGIN=b'RPI5XNU:SSHBUFFER:BEGIN ORIGINAL_BUFFERS RESET_OVERLAY NO_NETWORK NO_KEYS'
PASS=b'RPI5XNU:SSHBUFFER:PASS ROUNDTRIP LOW_MAX_RESET REUSE NOT_SSH_OR_CRYPTO_PROOF'
IDENTITY=prior.IDENTITY_COMMAND
SMOKE="zsh -f -c '/bin/zsh -f /etc/zsh-smoke.zsh; print -r -- ROOT96_ZSH_STATUS:$?'"
BUFFER="zsh -f -c '/usr/local/libexec/xnu/sshbufferprobe; print -r -- ROOT96_SSHBUFFER_STATUS:$?'"
CHECKS=['fresh_bounded_combined_boot','all_22_mounted_files_and_identity_self_hash',
        'fresh_nonce','real_zsh_script_and_zero_exit','real_ssh_buffer_and_zero_exit','recovery_prompt']


def boot_ready(raw,report):
    data=t.normalized(raw)
    if len(data)>t.MAX_BYTES or any(m in data for m in (*t.FORBIDDEN,b'FAILED_STOP',b'RPI5XNU:RAMROOT:REJECT')):
        raise RuntimeError('Unsafe combined boot; zero TX')
    if data.count(t.ENTRY)>1 or data.count(b'Boot mode:')>1:raise RuntimeError('Duplicate/foreign boot; zero TX')
    reads=re.findall(rb'Read probe\.bin bytes (\d+) hnd ',data)
    if reads and reads!=[str(report['image_bytes']).encode()]:raise RuntimeError('Wrong firmware image extent')
    mounts=re.findall(rb'RPI5XNU:RAMROOT:MOUNT NODES=(\d+) BYTES=(\d+) READONLY',data)
    expected=re.search(rb'NODES=(\d+) BYTES=(\d+)',report['root_mount_marker'].encode()).groups()
    if mounts and mounts!=[expected]:raise RuntimeError('Contradictory root geometry')
    ordered=(b'Boot mode: SD (01)',b'Read probe.bin bytes '+str(report['image_bytes']).encode()+b' hnd ',
        t.ENTRY,t.TERMINAL_LOADER,report['root_copy_marker'].encode(),report['kernel_copy_marker'].encode(),
        t.package_check.TOPOLOGY_PASS,t.TRANSFER,prior.COMMIT,
        b'RPI5XNU:TERMINAL:WATCHDOG SECONDS=180',t.READY)
    if any(data.count(m)>1 for m in ordered[:-1]):raise RuntimeError('Duplicate copy/transfer/watchdog markers')
    if any(m not in data for m in ordered):return False
    places=[data.index(m) for m in ordered]
    if places!=sorted(places):raise RuntimeError('Boot materialization/transfer order differs')
    return bool(t.shell.PROMPT.search(data[places[-1]:]))


def exact_lines(raw,required):
    lines=t.normalized(raw).splitlines()
    if any(lines.count(v)!=1 for v in required):raise ValueError('Missing/duplicate actual command result')
    order=[lines.index(v) for v in required]
    if order!=sorted(order):raise ValueError('Command result ordering differs')


def pending_safe(raw):
    data=t.normalized(raw)
    data=data.replace(b'\nRPI5XNU:SHELL:READY\nxnu:/# ',b'')
    data=re.sub(rb'RPI5XNU:TERMINAL:WATCHDOG_KICK RELOADS=[1-9][0-9]{0,5}\n',b'',data)
    if data.strip():raise ValueError('Unexpected pending UART output; no further TX')


def drain_pending(fd,output,deadline):
    pending=b'';end=min(deadline,time.monotonic()+0.5)
    while time.monotonic()<end:
        ready=select.select([fd],[],[],min(0.1,max(0,end-time.monotonic())))[0]
        if ready:
            pending+=t.shell.receive(fd,output,end)
            if len(pending)>65536:raise ValueError('Pending UART extent exceeded')
        elif not pending:return pending
        else:
            try:pending_safe(pending)
            except ValueError:continue
            return pending
    pending_safe(pending)
    return pending


def bounded_exchange(fd,output,command,expected,state,deadline):
    def send(port,text,progress):
        for byte in (text+'\n').encode('ascii'):
            if time.monotonic()>=deadline:raise TimeoutError('Command TX deadline exhausted')
            _,ready,_=select.select([],[port],[],min(2,max(0,deadline-time.monotonic())))
            if not ready or time.monotonic()>=deadline or os.write(port,bytes([byte]))!=1:raise RuntimeError('Bounded serial transmit failed')
            progress['transmitted_bytes']+=1;time.sleep(0.025)
    namespace=dict(t.exchange.__globals__,send=send)
    operation=types.FunctionType(t.exchange.__code__,namespace,argdefs=t.exchange.__defaults__)
    return operation(fd,output,command,expected,t.shell.PROMPT,state)


def commands(fd,output,state,receipt,revalidate,deadline):
    def exchange(name,command,expected):
        revalidate()
        if time.monotonic()>=deadline-45:raise TimeoutError('Insufficient bounded command budget; zero further TX')
        pending_start=output.tell();pending=drain_pending(fd,output,deadline)
        pending_safe(pending)
        if time.monotonic()>=deadline-45:raise TimeoutError('Command budget exhausted after pending RX')
        start=output.tell()
        raw=bounded_exchange(fd,output,command,expected,state,deadline)
        end=output.tell();exact_lines(raw,expected)
        state['exchanges'].append(dict(name=name,command=command,offset=start,bytes=end-start,
            response_sha256=hashlib.sha256(raw).hexdigest(),pending_offset=pending_start,
            pending_bytes=len(pending),pending_sha256=hashlib.sha256(pending).hexdigest()))
        return raw
    raw=exchange('identity',IDENTITY,[b'ROOTIDENTITY:PASS:COMPARE_SELF_AND_EXTENT_EXTERNALLY',b'ROOT_IDENTITY_STATUS:0'])
    state['runtime_identity']=identity.validate(raw,receipt)
    if state['runtime_identity']['file_hashes']!=22 or state['runtime_identity']['nodes']!=33:
        raise ValueError('Complete expanded root was not measured')
    state['checks'].append(CHECKS[1])
    nonce='R'+secrets.token_hex(8);state['nonce']=nonce
    exchange('nonce','echo '+nonce,[nonce.encode()]);state['checks'].append(CHECKS[2])
    exchange('zsh',SMOKE,t.SMOKE_LINES+[b'ROOT96_ZSH_STATUS:0']);state['checks'].append(CHECKS[3])
    raw=exchange('buffer',BUFFER,[BEGIN,PASS,b'ROOT96_SSHBUFFER_STATUS:0'])
    if b'RPI5XNU:SSHBUFFER:FAIL' in raw:raise ValueError('SSH buffer diagnostic failed')
    state['checks'].append(CHECKS[4])
    exchange('recovery','echo RECOVERED_'+nonce,[('RECOVERED_'+nonce).encode()]);state['checks'].append(CHECKS[5])


def returned(raw):
    data=t.normalized(raw)
    tokens=(b'RPi: BOOTSYS release VERSION:',b'BOOT_ORDER override: 0x000000f6',
            b'RPi: BOOTLOADER release VERSION:',b'Boot mode: NVME (06)')
    if any(data.count(v)>1 for v in tokens) or b'Boot mode: SD (01)' in data or b'Boot mode: USB' in data:
        raise ValueError('Repeated or wrong post-trial boot; no retry')
    if not all(v in data for v in tokens):return False
    positions=[data.index(v) for v in tokens]
    if positions!=sorted(positions):raise ValueError('Post-trial reset/normal NVMe ordering differs')
    return True
