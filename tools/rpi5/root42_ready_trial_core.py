# SPDX-License-Identifier: BSD-2-Clause
"""Strict late mounted-root admission and bounded consistent status repeats.

The early printf mount banner is diagnostic only for this new exact image.
Admission instead requires a state-derived late snapshot after a real reload.
Partial/interleaved snapshot lines never constitute proof. Structurally complete
contradictory snapshots, excess repeats, resets and runtime faults fail closed.
"""
from pathlib import Path
import re
import types
try:
    from . import root42_pthread_trial_core as prior
    from . import stage_pcie_trial_v3 as helpers
except ImportError:
    import root42_pthread_trial_core as prior
    import stage_pcie_trial_v3 as helpers

t=prior.t
PREFIX=b'RPI5XNU:TERMINAL:ROOT_READY'
ROW=rb'RPI5XNU:TERMINAL:ROOT_READY SECONDS=([0-9]+) NODES=([0-9]+) BYTES=([0-9]+) READONLY'
CHECKS=['fresh_exact_42node_state_confirmed_root_after_watchdog_reload',*prior.CHECKS[1:]]
WATCHDOG_PROFILE='root42-state-confirmed-watchdog-kernel-v1'
IDENTITY=prior.IDENTITY
batch_command,recovery_command=prior.batch_command,prior.recovery_command


def contract(report):
    marker=report.get('root_ready_marker','').encode()
    match=re.fullmatch(ROW,marker)
    mount=re.fullmatch(rb'RPI5XNU:RAMROOT:MOUNT NODES=42 BYTES=([1-9][0-9]*) READONLY',report.get('root_mount_marker','').encode())
    if (not match or not mount or match.groups()!=(b'180',b'42',mount[1]) or
        type(report.get('root_ready_max_reports')) is not int or report['root_ready_max_reports']!=3 or
        any(report.get(k) is not True for k in ('root_ready_requires_mounted_readonly','root_ready_requires_successful_reload'))):
        raise ValueError('Exact state-derived root/readiness report required')
    tag=report.get('trial_marker','').encode()
    if not re.fullmatch(rb'RPI5XNU:BL33:ROOT42_READY_TRIAL TAG=[0-9a-f]{32} CPUS=4 ROOT_NODES=42 WATCHDOG_READY_V2',tag):
        raise ValueError('Exact unique mounted-root trial tag required')
    return marker


def snapshots(raw,report):
    expected=contract(report);data=t.normalized(raw)
    prefixed=re.findall(rb'(?m)^'+re.escape(PREFIX)+rb'[^\n]*\n',data)
    if len(prefixed)>3:raise ValueError('Bounded root snapshot report count exceeded')
    rows=list(re.finditer(rb'(?m)^('+ROW+rb')\n',data))
    if any(row[1]!=expected for row in rows):raise ValueError('Contradictory mounted-root snapshot')
    return rows


def boot_ready(raw,report):
    data=t.normalized(raw);rows=snapshots(data,report)
    if (len(data)>t.MAX_BYTES or any(m in data for m in (*t.FORBIDDEN,b'FAILED_STOP',b'RPI5XNU:RAMROOT:REJECT')) or
        data.count(t.ENTRY)>1 or data.count(b'Boot mode:')>1):raise RuntimeError('Unsafe/repeated boot; zero TX')
    if (report.get('root_nodes')!=42 or report.get('root_files')!=30 or
        report.get('watchdog_ready_marker')!=prior.WATCHDOG.decode() or report.get('watchdog_ready_profile')!=WATCHDOG_PROFILE or
        not all(report.get('handoff',{}).get(k) is True for k in ('required_by_kernel','linked_loader_handoff','descriptor_not_confused_with_kernel_string'))):
        raise RuntimeError('Exact linked root/readiness/FDT profile required')
    tag=report['trial_marker'].encode();watchdog=prior.WATCHDOG
    for prefix,expected in ((b'RPI5XNU:TERMINAL:WATCHDOG_READY',watchdog),(b'RPI5XNU:BL33:ROOT42_READY_TRIAL',tag)):
        complete=re.findall(re.escape(prefix)+rb'[^\n]*\n',data)
        if complete and complete!=[expected+b'\n']:raise RuntimeError('Changed/repeated watchdog or loader tag')
    reads=re.findall(rb'Read probe\.bin bytes (\d+) hnd ',data)
    if reads and reads!=[str(report['image_bytes']).encode()]:raise RuntimeError('Wrong firmware extent')
    # A complete contradictory old diagnostic still rejects; a corrupted early
    # line cannot supply or contradict the new state-confirmed proof by itself.
    old=re.findall(rb'(?:^|\n)(RPI5XNU:RAMROOT:MOUNT NODES=[0-9]+ BYTES=[0-9]+ READONLY)\n',data)
    if any(v!=report['root_mount_marker'].encode() for v in old):raise RuntimeError('Contradictory early mounted root')
    ordered=(b'Boot mode: SD (01)',b'Read probe.bin bytes '+str(report['image_bytes']).encode()+b' hnd ',
        t.ENTRY,tag,t.TERMINAL_LOADER,prior.DEVICE,prior.FDT,report['root_copy_marker'].encode(),
        report['kernel_copy_marker'].encode(),t.package_check.TOPOLOGY_PASS,t.TRANSFER,prior.previous.prior.COMMIT,watchdog)
    if any(data.count(v)>1 for v in ordered):raise RuntimeError('Repeated boot materialization marker')
    if any(v not in data for v in ordered) or not rows:return False
    positions=[data.index(v) for v in ordered]
    if positions!=sorted(positions) or any(row.start()<=positions[-1] for row in rows):
        raise RuntimeError('Root/readiness before committed fresh boot')
    minimum=rows[0].end()
    ready=re.search(rb'(?:^|\n)'+re.escape(t.READY)+rb'\n',data[minimum:])
    return ready is not None and re.search(rb'(?:^|\n)xnu:/# ',data[minimum+ready.end():]) is not None


def bind(report):
    expected=contract(report)
    def strip(raw):
        snapshots(raw,report)
        return re.sub(rb'(?m)^'+re.escape(expected)+rb'\n',b'',t.normalized(raw))
    def pending(raw):return prior.pending_safe(strip(raw))
    def clean(raw):return prior.clean_lines(strip(raw))
    def returned(raw):
        snapshots(raw,report)
        if any(v in raw for v in (*t.FORBIDDEN,b'Debugger message: panic',b'panic(',b'panic:')):
            raise ValueError('Post-command runtime fault; recovery is not clean acceptance')
        return prior.returned(raw)
    scope={**vars(prior),'CHECKS':CHECKS,'clean_lines':clean,'pending_safe':pending,'returned':returned,
        'boot_ready':boot_ready,'unsafe_response':prior.prior.unsafe_response}
    scope['drain_pending']=helpers.private(prior.drain_pending,pending_safe=pending)
    scope['inspect_batch']=helpers.private(prior.inspect_batch,**scope)
    def commands(fd,output,state,receipt,files,revalidate,deadline):
        def whole():
            raw=output.getvalue() if hasattr(output,'getvalue') else Path(output.name).read_bytes()
            snapshots(raw,report)
        def guard():revalidate();whole()
        def unsafe(raw):
            try:whole();snapshots(raw,report)
            except ValueError:return True
            return prior.prior.unsafe_response(raw)
        exchange=helpers.private(prior.bounded_exchange,unsafe_response=unsafe)
        actual=helpers.private(prior.commands,**{**scope,'bounded_exchange':exchange})
        actual(fd,output,state,receipt,files,guard,deadline);whole()
    return types.SimpleNamespace(**{**scope,'commands':commands})
