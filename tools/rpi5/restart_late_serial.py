# SPDX-License-Identifier: BSD-2-Clause
"""Bounded late real-PID1 readiness, with full raw capture fault rejection."""
import hashlib
from pathlib import Path
_parent=Path(__file__).with_name('restart_init_serial.py')
_raw=_parent.read_bytes()
if hashlib.sha256(_raw).hexdigest()!='7954da9cc1b060999f4865bb0cce89b46e8f6bcf0f8e206d7b3f026760f1bd65':
    raise ValueError('Frozen PID1 restart protocol required')
_text=_raw.decode().replace('RPI5XNU:DISPLAYRESTART_INIT:ENTRY TAG=','RPI5XNU:DISPLAYRESTART_LATE:ENTRY TAG=')
if _text==_raw.decode():raise ValueError('Exact successor tag boundary')
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
MAX_INIT_REPORTS=3
INIT_PREFIX=b'RPI5XNU:INIT:SHUTDOWN_READY'
_old_healthy=healthy
_old_pending=pending_safe

def readiness_rows(raw):
    data=normalized(raw);lines=data.splitlines();positions=[];offset=0
    for i,line in enumerate(lines):
        if b'INIT:SHUTDOWN' in line:
            partial=i==len(lines)-1 and not data.endswith(b'\n')
            if partial and INIT_READY.startswith(line):
                if len(positions)>=MAX_INIT_REPORTS:raise ValueError('Fourth PID1 report begun')
            else:
                if line!=INIT_READY:raise ValueError('Malformed/corrupt PID1 shutdown readiness')
                positions.append(offset)
        offset+=len(line)+1
    if len(positions)>MAX_INIT_REPORTS:raise ValueError('Unbounded PID1 readiness reports')
    for stop in (STOP_PREFIX,PRE_PREFIX,BOOTSYS):
        index=data.find(stop,data.find(COMMIT)+len(COMMIT)) if COMMIT in data else data.find(stop)
        if index>=0 and any(pos>index for pos in positions):raise ValueError('PID1 readiness after stop/reset')
    return positions

def healthy(raw):
    _old_healthy(raw)
    readiness_rows(raw)

def boot_ready(raw,report):
    if (report.get('init_shutdown_ready_marker')!=INIT_READY.decode() or
            type(report.get('init_shutdown_ready_max_reports')) is not int or
            report['init_shutdown_ready_max_reports']!=MAX_INIT_REPORTS):
        raise ValueError('Actual bounded delayed PID1 report required')
    if STOP_PREFIX in raw:raise ValueError('PID1 stopped before input admission')
    healthy(raw)
    ready=_base_ready(raw,report)
    data=normalized(raw);rows=readiness_rows(raw)
    if not rows or not ready:return False
    if rows[0]<=data.index(COMMIT):raise ValueError('PID1 readiness before kernel commit')
    after=data[rows[0]+len(INIT_READY):]
    match=re.search(rb'(?:^|\n)'+re.escape(zsh.READY)+rb'\n',after)
    return match is not None and PROMPT.search(after[match.end():]) is not None

def pending_safe(raw):
    healthy(raw)
    # Only whole validated lines can be omitted from pending-output admission;
    # raw bytes remain in the capture and global health enforces total <=3.
    data=normalized(raw)
    rows=readiness_rows(data)
    for pos in reversed(rows):
        if data[pos:pos+len(INIT_READY)+1]!=INIT_READY+b'\n':raise ValueError('Incomplete pending PID1 report')
        data=data[:pos]+data[pos+len(INIT_READY)+1:]
    _old_pending(data)
