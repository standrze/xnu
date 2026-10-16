# SPDX-License-Identifier: BSD-2-Clause
"""Fresh 42-node nine-command protocol; no port or board action on import.

The eight prior commands retain the strict fixed-v2 pwd oracle. The ninth is
genuine pthread startup/create/join. Marker output alone is never process-exit
proof: a separate recovery-shell status exchange remains required.
"""
import hashlib
import re
import secrets
import time
try:
    from . import root41_batch_trial_core as prior
    from . import root41_batch_trial_v2 as v2
except ImportError:
    import root41_batch_trial_core as prior
    import root41_batch_trial_v2 as v2

t=prior.t
previous=prior.previous
identity=prior.identity
statprobe=prior.statprobe
metadata=prior.metadata
DEVICE=prior.DEVICE
FDT=prior.FDT
WATCHDOG=prior.WATCHDOG
WATCHDOG_PROFILE=prior.WATCHDOG_PROFILE
IDENTITY=prior.IDENTITY
CRYPTO_BEGIN=prior.CRYPTO_BEGIN
CRYPTO_PASS=prior.CRYPTO_PASS
PWD_STARTUP=v2.PWD_STARTUP
STEPS=prior.STEPS+(('pthread','/usr/local/libexec/xnu/pthreadprobe'),)
PTHREAD_LINES=(b'PTHREAD:KERNEL_READY',b'PTHREAD:MAIN_READY',
    b'PTHREAD:SMOKE PASS CTOR=1 THREADS=4 JOIN=4 MUTEX=2048 TSD_DTORS=4 ONCE=1 ERRNO=4 ALLOC=2048')
CHECKS=['fresh_exact_42node_boot_after_delayed_watchdog_reload','complete_30file_identity_and_self_hash',
        'fresh_nonce_batched_nine_results_and_zero_statuses','real_batch_zsh_zero_exit_and_live_recovery']
pending_safe=prior.pending_safe
drain_pending=prior.drain_pending
returned=prior.returned
bounded_exchange=prior.bounded_exchange
clean_lines=prior.clean_lines
nonce_valid=prior.nonce_valid


def boot_ready(raw,report):
    data=t.normalized(raw)
    if (len(data)>t.MAX_BYTES or any(m in data for m in (*t.FORBIDDEN,b'FAILED_STOP',b'RPI5XNU:RAMROOT:REJECT')) or
        data.count(t.ENTRY)>1 or data.count(b'Boot mode:')>1):raise RuntimeError('Unsafe/repeated boot; zero TX')
    if (report.get('root_nodes')!=42 or report.get('root_files')!=30 or
        report.get('watchdog_ready_marker')!=WATCHDOG.decode() or report.get('watchdog_ready_profile')!=WATCHDOG_PROFILE or
        not all(report.get('handoff',{}).get(k) is True for k in
                ('required_by_kernel','linked_loader_handoff','descriptor_not_confused_with_kernel_string'))):
        raise RuntimeError('Exact 42-node linked readiness/FDT contract required; zero TX')
    trial=report.get('trial_marker','').encode()
    if not re.fullmatch(rb'RPI5XNU:BL33:ROOT42_PTHREAD_TRIAL TAG=[0-9a-f]{32} CPUS=4 ROOT_NODES=42 WATCHDOG_READY_V2',trial):
        raise RuntimeError('Exact unique pthread trial tag required; zero TX')
    for prefix,expected in ((b'RPI5XNU:TERMINAL:WATCHDOG_READY',WATCHDOG),(b'RPI5XNU:BL33:ROOT42_PTHREAD_TRIAL',trial)):
        complete=re.findall(re.escape(prefix)+rb'[^\n]*\n',data)
        if complete and complete!=[expected+b'\n']:raise RuntimeError('Non-exact/repeated readiness or trial marker')
        if expected in data and expected+b'\n' not in data:return False
    reads=re.findall(rb'Read probe\.bin bytes (\d+) hnd ',data)
    if reads and reads!=[str(report['image_bytes']).encode()]:raise RuntimeError('Wrong firmware extent')
    mount=report['root_mount_marker'].encode()
    if not re.fullmatch(rb'RPI5XNU:RAMROOT:MOUNT NODES=42 BYTES=[1-9][0-9]* READONLY',mount):raise RuntimeError('Exact mounted 42-node root required')
    mounts=re.findall(rb'RPI5XNU:RAMROOT:MOUNT[^\n]*\n',data)
    if mounts and mounts!=[mount+b'\n']:raise RuntimeError('Contradictory/repeated root mount')
    ordered=(b'Boot mode: SD (01)',b'Read probe.bin bytes '+str(report['image_bytes']).encode()+b' hnd ',
        t.ENTRY,trial,t.TERMINAL_LOADER,DEVICE,FDT,report['root_copy_marker'].encode(),report['kernel_copy_marker'].encode(),
        t.package_check.TOPOLOGY_PASS,t.TRANSFER,previous.prior.COMMIT)
    if any(data.count(m)>1 for m in (*ordered,WATCHDOG,mount)):raise RuntimeError('Repeated boot/root/watchdog marker')
    if any(m not in data for m in (*ordered,mount,WATCHDOG)):return False
    places=[data.index(m) for m in ordered]
    if places!=sorted(places) or min(data.index(mount),data.index(WATCHDOG))<=places[-1]:raise RuntimeError('Materialization/commit/readiness order differs')
    minimum=max(data.index(WATCHDOG)+len(WATCHDOG),data.index(mount)+len(mount))
    ready=re.search(rb'(?:^|\n)'+re.escape(t.READY)+rb'\n',data[minimum:])
    return ready is not None and re.search(rb'(?:^|\n)xnu:/# ',data[minimum+ready.end():]) is not None


def script(nonce):
    nonce_valid(nonce)
    return ('n='+nonce+'; print -r -- B42:$n:BEGIN; '
        'r(){ local k=$1 s; shift; print -r -- B42:$n:$k:B; "$@"; s=$?; '
        'print -r -- B42:$n:$k:E:$s; ((s==0)) || exit $s; }; '+
        '; '.join('r '+name+' '+command for name,command in STEPS)+
        '; print -r -- B42:$n:END:0; exit 0')


def batch_command(nonce):
    value=script(nonce)
    if "'" in value or '\n' in value:raise ValueError('Unsafe recovery quoting')
    command="/bin/zsh -f -c '"+value+"'"
    if len(command.encode('ascii'))>1023:raise ValueError('Actual recovery line capacity exceeded')
    return command


def recovery_command(nonce):
    nonce_valid(nonce)
    return 'echo B42:'+nonce+':RECOVERY_STATUS:$?'


def markers(nonce):
    nonce_valid(nonce)
    return [('B42:'+nonce+':'+v).encode() for v in ('BEGIN',*(p for name,_ in STEPS for p in (name+':B',name+':E:0')),'END:0')]


def validate_root(receipt,files):
    rows=receipt.get('identity_catalog',[]);expected={r['path']:r for r in rows if r.get('sha256')}
    if receipt.get('output_nodes')!=42 or len(rows)!=42 or len(expected)!=30 or set(files)!=set(expected):
        raise ValueError('Exact 42-node/30-file catalog required')
    for path,(raw,mode) in files.items():
        row=expected[path]
        if row['bytes']!=len(raw) or row['mode']!=mode|0o100000 or row['sha256']!=hashlib.sha256(raw).hexdigest():
            raise ValueError('Actual file differs from 42-node identity')


def inspect_batch(raw,nonce,files):
    lines=clean_lines(raw);expected=markers(nonce)
    if [line for line in lines if line.startswith((b'B42:',b'B41:'))]!=expected:
        raise ValueError('Missing/duplicate/old/reordered/nonzero batch result or wrong nonce')
    if any(m in raw for m in (*t.FORBIDDEN,b'RPI5XNU:SSHBUFFER:FAIL',b'RPI5XNU:SSHCRYPTO:FAIL')):
        raise ValueError('Failed batch executable')
    bodies={name:lines[lines.index(expected[1+2*i])+1:lines.index(expected[2+2*i])] for i,(name,_) in enumerate(STEPS)}
    def exact(name,required):
        if bodies[name]!=list(required):raise ValueError('Actual '+name+' output differs')
    previous.exact_lines(b'\n'.join(bodies['zsh']),t.SMOKE_LINES)
    previous.exact_lines(b'\n'.join(bodies['buffer']),[previous.BEGIN,previous.PASS])
    previous.exact_lines(b'\n'.join(bodies['crypto']),[CRYPTO_BEGIN,CRYPTO_PASS])
    exact('pwd',(*PWD_STARTUP,b'/'));exact('uname',[b'Darwin']);exact('pthread',PTHREAD_LINES)
    motd=files['/etc/motd'][0];words=len(re.findall(rb'[^ \t\n\r\v\f]+',motd))
    exact('wc',[f'{motd.count(bytes([10]))} {words} {len(motd)}'.encode()])
    hexed=b''.join(f'{v:02x}'.encode()+(b'\n' if (i+1)%16==0 else b' ') for i,v in enumerate(motd))
    if len(motd)%16:hexed+=b'\n'
    exact('hex',hexed.splitlines())
    accepted=metadata.accept_metadata(statprobe.parse_diagnostic(b'\n'.join(bodies['stat'])),files)
    return dict(batch_framing_and_all_nine_statuses_zero=True,nonce=nonce,
        commands=[dict(name=n,command=c,status=0,output_sha256=hashlib.sha256(b'\n'.join(bodies[n])).hexdigest()) for n,c in STEPS],
        actual_zsh_smoke=True,actual_ssh_buffer=True,actual_chacha_poly1305_public_kats=True,
        actual_apple_pwd_physical_root=True,canonical_multicall_utilities=True,metadata=accepted,
        actual_pthread_startup_constructor_create_join_mutex_tsd_errno=True,batch_process_exit_verified=False,
        ssh_daemon=False,ssh_transport=False,networking=False,entropy_qualified=False,
        pthread_scope='Exact four-thread diagnostic workload; not full libSystem, general dyld or multi-zone allocator proof',
        crypto_scope='Public primitive KATs only; not SSH, entropy or AEAD proof')


def commands(fd,output,state,receipt,files,revalidate,deadline):
    validate_root(receipt,files)
    def exchange(name,command,expected):
        revalidate()
        if time.monotonic()>=deadline-45:raise TimeoutError('Reserve 45 seconds before command; zero TX')
        before=output.tell();pending=drain_pending(fd,output,deadline);pending_safe(pending)
        if time.monotonic()>=deadline-45:raise TimeoutError('Budget expired during pending RX; zero TX')
        start=output.tell();raw=bounded_exchange(fd,output,command,expected,state,deadline)
        previous.exact_lines(raw,expected)
        state['exchanges'].append(dict(name=name,command=command,offset=start,bytes=output.tell()-start,
            response_sha256=hashlib.sha256(raw).hexdigest(),pending_offset=before,pending_bytes=len(pending),pending_sha256=hashlib.sha256(pending).hexdigest()))
        return raw
    observed=identity.validate(exchange('identity',IDENTITY,[b'ROOTIDENTITY:PASS:COMPARE_SELF_AND_EXTENT_EXTERNALLY',b'ROOT_IDENTITY_STATUS:0']),receipt)
    if observed['nodes']!=42 or observed['file_hashes']!=30:raise ValueError('Exact mounted 42-node identity required')
    state['runtime_identity']=observed;state['checks'].append(CHECKS[1])
    nonce='B'+secrets.token_hex(8);state['nonce']=nonce
    state['batch']=inspect_batch(exchange('batch',batch_command(nonce),markers(nonce)),nonce,files)
    state['checks'].append(CHECKS[2])
    exchange('recovery_status',recovery_command(nonce),[('B42:'+nonce+':RECOVERY_STATUS:0').encode()])
    state['batch']['batch_process_exit_verified']=True;state['checks'].append(CHECKS[3])
