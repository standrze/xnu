# SPDX-License-Identifier: BSD-2-Clause
"""Phased boot/root/socket admission, separate from historical strict trials.

Phase 1 admits ONLY the fixed read-only identity query. Phase 2 requires full
runtime filesystem/catalog/self-hash replay before any socket payload command.
The serial front end must first validate installed-package receipts and bind
the exact package report. This module alone authorizes no device access.
"""
import re
import secrets

try:
    from . import serial_zsh_trial as t
    from . import socket_identity_evidence as identity
except ImportError:
    import serial_zsh_trial as t
    import socket_identity_evidence as identity

IMAGE_BYTES=19384000
ROOT_BYTES=1916928
COPY=b'RPI5XNU:BL33:RAMDISK_MATERIALIZED PA=0000000008198000 BYTES=00000000001d4000 VERIFIED'
KERNEL=b'RPI5XNU:BL33:KERNEL_MATERIALIZED BYTES=000000000118c000 FULL_ENVELOPE_VERIFIED NO_BOOT_ARGS_WRITTEN NO_TRANSFER'
COMMIT=b'RPI5XNU:BL33:BOOT_DATA_COMMITTED TRANSFER_NEXT'
HELPER='/usr/local/libexec/xnu/socketprobe'
IDENTITY_COMMAND="zsh -f -c '"+HELPER+" identity; print -r -- ROOT_IDENTITY_STATUS:$?'"


def identity_query_ready(raw):
    data=t.normalized(raw)
    if len(data)>t.MAX_BYTES or any(marker in data for marker in (*t.FORBIDDEN,b'FAILED_STOP',b'RPI5XNU:RAMROOT:REJECT')):
        raise RuntimeError('Unsafe boot; identity query refused')
    if data.count(t.ENTRY)>1 or data.count(b'Boot mode:')>1:
        raise RuntimeError('Repeated boot; identity query refused')
    reads=re.findall(rb'Read probe\.bin bytes (\d+) hnd ',data)
    if reads and reads!=[str(IMAGE_BYTES).encode()]:
        raise RuntimeError('Wrong or repeated firmware image extent')
    # A fully readable contradictory root is a hard rejection. Torn text is
    # neither success nor mount proof: only the subsequent raw statfs/catalog
    # query can resolve it. Old strict recorders continue to reject it.
    mounts=re.findall(rb'RPI5XNU:RAMROOT:MOUNT NODES=(\d+) BYTES=(\d+) READONLY',data)
    if mounts and mounts!=[(b'32',str(ROOT_BYTES).encode())]:
        raise RuntimeError('Contradictory or repeated root mount')
    ordered=(b'Boot mode: SD (01)',b'Read probe.bin bytes '+str(IMAGE_BYTES).encode()+b' hnd ',
             t.ENTRY,t.TERMINAL_LOADER,COPY,KERNEL,t.package_check.TOPOLOGY_PASS,
             t.TRANSFER,COMMIT,t.READY)
    for marker in ordered[:-1]:
        if data.count(marker)>1: raise RuntimeError('Repeated payload/transfer marker')
    if any(marker not in data for marker in ordered): return False
    positions=[data.index(marker) for marker in ordered]
    if positions!=sorted(positions): raise RuntimeError('Boot/copy/transfer/readiness order differs')
    return bool(t.shell.PROMPT.search(data[positions[-1]:]))


def socket_result(raw,mode):
    lines=t.normalized(raw).splitlines()
    expected_mode=b'unix' if mode=='unix' else b'inet_LOOPBACK_ONLY'
    if (mode not in ('unix','inet') or lines.count(b'SOCKETPROBE:BEGIN:RAW_DARWIN_V1')!=1 or
            lines.count(b'SOCKETPROBE:MODE='+expected_mode)!=1 or
            lines.count(b'SOCKETPROBE:PASS')!=1 or b'SOCKETPROBE:FAIL' in lines or
            lines.count(b'SOCKETPROBE:END:NOT_ETHERNET_OR_SSH_PROOF')!=1 or
            lines.count(b'SOCKET_STATUS:0')!=1 or
            lines.count(b'SOCKETPROBE:STREAM_PAYLOAD_MATCH=32')!=3 or
            lines.count(b'SOCKETPROBE:STREAM_EOF=0')!=1):
        raise ValueError('Socket payload/half-close or zero exit not proven')
    operations=[int(line.split(b'=')[1]) for line in lines if re.fullmatch(rb'SOCKETPROBE:OPERATIONS=\d+',line)]
    if len(operations)!=1 or not 1<=operations[0]<=256: raise ValueError('Socket operation bound differs')
    if mode=='inet' and (lines.count(b'SOCKETPROBE:UDP_PAYLOAD_AND_PEER_MATCH=32')!=2 or
                        lines.count(b'SOCKETPROBE:UDP_PASS')!=1 or lines.count(b'SOCKETPROBE:TCP_PASS')!=1):
        raise ValueError('UDP/TCP payload proof incomplete')
    return dict(mode=mode,operations=operations[0],ethernet=False,ssh=False)


def commands(fd,output,state,receipt):
    """Called only after current installed receipt and identity_query_ready.

    Exactly one root query precedes payloads. Failures propagate; no retries,
    interface setup, route changes, reboot, filesystem mutation or soak.
    """
    raw=t.exchange(fd,output,IDENTITY_COMMAND,
                   [b'ROOTIDENTITY:PASS:COMPARE_SELF_AND_EXTENT_EXTERNALLY',b'ROOT_IDENTITY_STATUS:0'],
                   t.shell.PROMPT,state)
    state['runtime_identity']=identity.validate(raw,receipt)
    state['checks'].append('runtime_readonly_mount_all_fixed_paths_and_self_digest')
    nonce='S'+secrets.token_hex(8); state['nonce']=nonce
    t.exchange(fd,output,'echo '+nonce,[nonce.encode()],t.shell.PROMPT,state)
    state['checks'].append('fresh_recovery_nonce')
    t.exchange(fd,output,'zsh -f /etc/zsh-smoke.zsh',t.SMOKE_LINES,t.shell.PROMPT,state)
    t.exchange(fd,output,'echo $?',[b'0'],t.shell.PROMPT,state)
    state['checks'].append('preserved_original_zsh_script')
    state['socket_results']=[]
    for mode in ('unix','inet'):
        command="zsh -f -c '"+HELPER+' '+mode+"; print -r -- SOCKET_STATUS:$?'"
        raw=t.exchange(fd,output,command,[b'SOCKETPROBE:END:NOT_ETHERNET_OR_SSH_PROOF'],t.shell.PROMPT,state)
        state['socket_results'].append(socket_result(raw,mode))
        state['checks'].append('socket_'+mode+'_payload_and_halfclose')
    t.exchange(fd,output,'echo RECOVERED_'+nonce,[('RECOVERED_'+nonce).encode()],t.shell.PROMPT,state)
    state['checks'].append('live_recovery')
