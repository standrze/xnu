# SPDX-License-Identifier: BSD-2-Clause
"""Offline 41-node command protocol; no port access until an external recorder admits it.

Identity is a separate first query. A single bounded zsh invocation then runs
eight read-only tests, with independently framed outputs and statuses. A final
recovery command measures the actual batch process exit (not an early expansion
of $? on the same recovery-shell command line).
"""
import hashlib
import os
import re
import secrets
import select
import time
try:
    from . import root96_trial_core as previous
    from . import socket_identity_evidence as identity
    from . import serial_statprobe_trial as statprobe
    from . import serial_zsh_metadata_trial as metadata
except ImportError:
    import root96_trial_core as previous
    import socket_identity_evidence as identity
    import serial_statprobe_trial as statprobe
    import serial_zsh_metadata_trial as metadata

t=previous.t
DEVICE=b'RPI5XNU:BL33:PCIE_DEVICE_HANDOFF RANGES=3 PAGES=5 DECLARATIONS_ONLY PCIE_MMIO=0 IRQ=0 DMA=0'
FDT=b'RPI5XNU:BL33:FIRMWARE_FDT RETAINED_DESCRIPTOR_ONLY NO_RAW_TREE_OR_SEED_PUBLISHED PCIE_MMIO=0'
WATCHDOG=b'RPI5XNU:TERMINAL:WATCHDOG_READY SECONDS=180'
WATCHDOG_PROFILE='root96-terminal-ready-delay-kernel-v2'
IDENTITY=previous.IDENTITY
CRYPTO_BEGIN=b'RPI5XNU:SSHCRYPTO:BEGIN ORIGINAL_CHACHA_POLY1305 PUBLIC_VECTORS NO_KEYS'
CRYPTO_PASS=b'RPI5XNU:SSHCRYPTO:PASS TWO_KATS BOUNDARIES IN_PLACE NOT_SSH_ENTROPY_OR_AEAD_PROOF'
STEPS=(('zsh','/bin/zsh -f /etc/zsh-smoke.zsh'),
       ('buffer','/usr/local/libexec/xnu/sshbufferprobe'),
       ('crypto','/usr/local/libexec/xnu/sshcryptoprobe'),
       ('pwd','/bin/pwd -P'),('uname','/usr/bin/uname'),
       ('wc','/usr/bin/wc /etc/motd'),('hex','/usr/bin/hexdump /etc/motd'),
       ('stat','/usr/local/libexec/xnu/statprobe'))
CHECKS=['fresh_exact_41node_boot_after_delayed_watchdog_reload','complete_29file_identity_and_self_hash',
        'fresh_nonce_batched_eight_results_and_zero_statuses','real_batch_zsh_zero_exit_and_live_recovery']
pending_safe=previous.pending_safe
drain_pending=previous.drain_pending
returned=previous.returned


def boot_ready(raw,report):
    data=t.normalized(raw)
    if (len(data)>t.MAX_BYTES or any(marker in data for marker in
        (*t.FORBIDDEN,b'FAILED_STOP',b'RPI5XNU:RAMROOT:REJECT')) or
        data.count(t.ENTRY)>1 or data.count(b'Boot mode:')>1):
        raise RuntimeError('Unsafe/repeated boot; zero TX')
    if (report.get('watchdog_ready_marker')!=WATCHDOG.decode() or
        report.get('watchdog_ready_profile')!=WATCHDOG_PROFILE or
        not all(report.get('handoff',{}).get(k) is True for k in
            ('required_by_kernel','linked_loader_handoff','descriptor_not_confused_with_kernel_string'))):
        raise RuntimeError('Exact linked delayed-watchdog/FDT contract required; zero TX')
    trial_marker=report.get('trial_marker','').encode()
    if not re.fullmatch(rb'RPI5XNU:BL33:ROOT96_BATCH_TRIAL TAG=[0-9a-f]{32} CPUS=4 ROOT_NODES=41 WATCHDOG_READY_V2',trial_marker):
        raise RuntimeError('Exact unique four-core batch loader tag required; zero TX')
    for prefix,expected in ((b'RPI5XNU:TERMINAL:WATCHDOG_READY',WATCHDOG),
                            (b'RPI5XNU:BL33:ROOT96_BATCH_TRIAL',trial_marker)):
        complete=re.findall(re.escape(prefix)+rb'[^\n]*\n',data)
        if complete and complete!=[expected+b'\n']:raise RuntimeError('Non-exact/duplicate readiness or unique tag line')
        if expected in data and expected+b'\n' not in data:return False
    reads=re.findall(rb'Read probe\.bin bytes (\d+) hnd ',data)
    if reads and reads!=[str(report['image_bytes']).encode()]:raise RuntimeError('Wrong fresh firmware extent')
    mount=report['root_mount_marker'].encode()
    if not re.fullmatch(rb'RPI5XNU:RAMROOT:MOUNT NODES=41 BYTES=[1-9][0-9]* READONLY',mount):
        raise RuntimeError('Exact 41-node root contract required')
    mounts=re.findall(rb'RPI5XNU:RAMROOT:MOUNT[^\n]*\n',data)
    if mounts and mounts!=[mount+b'\n']:raise RuntimeError('Contradictory/torn/repeated root mount')
    ordered=(b'Boot mode: SD (01)',b'Read probe.bin bytes '+str(report['image_bytes']).encode()+b' hnd ',
        t.ENTRY,trial_marker,t.TERMINAL_LOADER,DEVICE,FDT,report['root_copy_marker'].encode(),
        report['kernel_copy_marker'].encode(),t.package_check.TOPOLOGY_PASS,t.TRANSFER,previous.prior.COMMIT)
    if any(data.count(m)>1 for m in (*ordered,WATCHDOG,mount)):
        raise RuntimeError('Repeated exact boot/root/watchdog marker')
    if any(m not in data for m in (*ordered,mount,WATCHDOG)):return False
    places=[data.index(m) for m in ordered]
    if places!=sorted(places) or min(data.index(mount),data.index(WATCHDOG))<=places[-1]:
        raise RuntimeError('Materialization/commit/readiness order differs')
    # The initial READY may legitimately precede the first 5-second reload.
    # Admit only a later complete READY line followed by its actual prompt.
    minimum=max(data.index(WATCHDOG)+len(WATCHDOG),data.index(mount)+len(mount))
    ready=re.search(rb'(?:^|\n)'+re.escape(t.READY)+rb'\n',data[minimum:])
    if ready is None:return False
    return re.search(rb'(?:^|\n)xnu:/# ',data[minimum+ready.end():]) is not None


def nonce_valid(nonce):
    if not isinstance(nonce,str) or not re.fullmatch('B[0-9a-f]{16}',nonce):raise ValueError('Exact fresh batch nonce required')


def script(nonce):
    nonce_valid(nonce)
    return ('n='+nonce+'; print -r -- B41:$n:BEGIN; '
        'r(){ local k=$1 s; shift; print -r -- B41:$n:$k:B; "$@"; s=$?; '
        'print -r -- B41:$n:$k:E:$s; ((s==0)) || exit $s; }; '+
        '; '.join('r '+name+' '+command for name,command in STEPS)+
        '; print -r -- B41:$n:END:0; exit 0')


def batch_command(nonce):
    value=script(nonce)
    if "'" in value or '\n' in value:raise ValueError('Batch cannot escape recovery single-quote framing')
    command="/bin/zsh -f -c '"+value+"'"
    if len(command.encode('ascii'))>1023:raise ValueError('Batch exceeds actual recovery line[1024]')
    return command


def recovery_command(nonce):
    nonce_valid(nonce)
    return 'echo B41:'+nonce+':RECOVERY_STATUS:$?'


def markers(nonce):
    nonce_valid(nonce)
    return [('B41:'+nonce+':'+v).encode() for v in
        ('BEGIN',*(part for name,_ in STEPS for part in (name+':B',name+':E:0')),'END:0')]


def clean_lines(raw):
    lines=t.normalized(raw).splitlines()
    return [line for line in lines if not re.fullmatch(rb'RPI5XNU:TERMINAL:WATCHDOG_KICK RELOADS=[1-9][0-9]{0,5}',line)]


def validate_root(receipt,files):
    rows=receipt.get('identity_catalog',[])
    expected={row['path']:row for row in rows if row.get('sha256')}
    if receipt.get('output_nodes')!=41 or len(rows)!=41 or len(expected)!=29 or set(files)!=set(expected):
        raise ValueError('Exact 41-node/29-file payload/catalog pair required')
    for path,(content,permission) in files.items():
        row=expected[path]
        if (row['bytes']!=len(content) or row['mode']!=permission|0o100000 or
            row['sha256']!=hashlib.sha256(content).hexdigest()):
            raise ValueError('Actual expected command file differs from mounted identity catalog')


def inspect_batch(raw,nonce,files):
    lines=clean_lines(raw);expected=markers(nonce)
    if [line for line in lines if line.startswith(b'B41:')]!=expected:
        raise ValueError('Missing/duplicate/reordered/nonzero batch result or wrong nonce')
    if any(m in raw for m in (*t.FORBIDDEN,b'RPI5XNU:SSHBUFFER:FAIL',b'RPI5XNU:SSHCRYPTO:FAIL')):
        raise ValueError('Failed batch executable')
    bodies={name:lines[lines.index(expected[1+2*i])+1:lines.index(expected[2+2*i])]
            for i,(name,_) in enumerate(STEPS)}
    def exact(name,required):
        if bodies[name]!=required:raise ValueError('Actual '+name+' output differs')
    previous.exact_lines(b'\n'.join(bodies['zsh']),t.SMOKE_LINES)
    previous.exact_lines(b'\n'.join(bodies['buffer']),[previous.BEGIN,previous.PASS])
    previous.exact_lines(b'\n'.join(bodies['crypto']),[CRYPTO_BEGIN,CRYPTO_PASS])
    exact('pwd',[b'/']);exact('uname',[b'Darwin'])
    motd=files['/etc/motd'][0]
    words=len(re.findall(rb'[^ \t\n\r\v\f]+',motd))
    exact('wc',[f'{motd.count(bytes([10]))} {words} {len(motd)}'.encode()])
    hexed=b''.join(f'{value:02x}'.encode()+(b'\n' if (i+1)%16==0 else b' ') for i,value in enumerate(motd))
    if len(motd)%16:hexed+=b'\n'
    exact('hex',hexed.splitlines())
    observed=statprobe.parse_diagnostic(b'\n'.join(bodies['stat']))
    accepted=metadata.accept_metadata(observed,files)
    return dict(batch_framing_and_all_eight_statuses_zero=True,nonce=nonce,
        commands=[dict(name=name,command=command,status=0,output_sha256=hashlib.sha256(b'\n'.join(bodies[name])).hexdigest()) for name,command in STEPS],
        actual_zsh_smoke=True,actual_ssh_buffer=True,actual_chacha_poly1305_public_kats=True,
        actual_apple_pwd_physical_root=True,canonical_multicall_utilities=True,metadata=accepted,
        batch_process_exit_verified=False,ssh_daemon=False,ssh_transport=False,networking=False,
        crypto_scope='Public primitive KATs/boundaries only; not SSH, entropy or AEAD proof')


def unsafe_response(raw):
    return any(marker in raw for marker in
        (*t.FORBIDDEN,t.ENTRY,t.TERMINAL_LOADER,b'RPi: BOOTSYS',b'Boot mode:',b'Linux version ',b' login:'))


def bounded_exchange(fd,output,command,expected,state,deadline):
    encoded=(command+'\n').encode('ascii');data=b''
    if len(encoded)>1024:raise ValueError('Actual recovery line bound exceeded')
    for byte in encoded:
        if time.monotonic()>=deadline:raise TimeoutError('Absolute serial TX deadline exhausted')
        if select.select([fd],[],[],0)[0]:
            data+=t.shell.receive(fd,output,deadline)
            if len(data)>65536 or unsafe_response(data):raise RuntimeError('Reset/fault/response overflow during TX; no further input')
        _,ready,_=select.select([],[fd],[],min(2,max(0,deadline-time.monotonic())))
        if not ready or time.monotonic()>=deadline or os.write(fd,bytes([byte]))!=1:
            raise RuntimeError('Bounded serial transmit failed')
        state['transmitted_bytes']+=1;time.sleep(0.025)
    response_deadline=min(deadline,time.monotonic()+30)
    while time.monotonic()<response_deadline:
        if len(data)>65536 or unsafe_response(data):raise RuntimeError('Unbounded/faulted command response')
        if t.response_complete(data,expected,t.shell.PROMPT):return data
        data+=t.shell.receive(fd,output,response_deadline)
    raise TimeoutError('Command result/prompt missing before absolute deadline')


def commands(fd,output,state,receipt,files,revalidate,deadline):
    """Three exchanges, never recursive historical/package validation per byte.

    The recorder must pass a cheap immutable-receipt/source byte-pin revalidator
    after its one complete package/ancestry preflight, not rerun old builds.
    """
    validate_root(receipt,files)
    def exchange(name,command,expected):
        revalidate()
        if time.monotonic()>=deadline-45:raise TimeoutError('Reserve 45 seconds before final command; no TX')
        before=output.tell();pending=drain_pending(fd,output,deadline);pending_safe(pending)
        if time.monotonic()>=deadline-45:raise TimeoutError('Budget expired during pending RX; no TX')
        start=output.tell();raw=bounded_exchange(fd,output,command,expected,state,deadline)
        previous.exact_lines(raw,expected)
        state['exchanges'].append(dict(name=name,command=command,offset=start,bytes=output.tell()-start,
            response_sha256=hashlib.sha256(raw).hexdigest(),pending_offset=before,pending_bytes=len(pending),
            pending_sha256=hashlib.sha256(pending).hexdigest()))
        return raw
    raw=exchange('identity',IDENTITY,[b'ROOTIDENTITY:PASS:COMPARE_SELF_AND_EXTENT_EXTERNALLY',b'ROOT_IDENTITY_STATUS:0'])
    observed=identity.validate(raw,receipt)
    if observed['nodes']!=41 or observed['file_hashes']!=29:raise ValueError('Exact mounted 41-node/29-file identity required')
    state['runtime_identity']=observed;state['checks'].append(CHECKS[1])
    nonce='B'+secrets.token_hex(8);state['nonce']=nonce
    raw=exchange('batch',batch_command(nonce),markers(nonce))
    state['batch']=inspect_batch(raw,nonce,files);state['checks'].append(CHECKS[2])
    exchange('recovery_status',recovery_command(nonce),[('B41:'+nonce+':RECOVERY_STATUS:0').encode()])
    state['batch']['batch_process_exit_verified']=True;state['checks'].append(CHECKS[3])
