# SPDX-License-Identifier: BSD-2-Clause
"""Exact root33 PID1 shutdown successor; panic and error stops stay fatal."""
import hashlib
from pathlib import Path
_parent=Path(__file__).with_name('restart_diagnostic_serial.py')
_raw=_parent.read_bytes()
if hashlib.sha256(_raw).hexdigest()!='2041a4dffacf4210ef0a25e59877d00e2bbff75c2bcc7e3b94d1e04271b0ca20':raise ValueError('Frozen diagnostic grammar required')
_text=_raw.decode().replace('RPI5XNU:DISPLAYRESTART_DIAG:ENTRY TAG=','RPI5XNU:DISPLAYRESTART_INIT:ENTRY TAG=')
if _text==_raw.decode():raise ValueError('Exact new tag boundary')
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
INIT_READY=b'RPI5XNU:INIT:SHUTDOWN_READY SIGTERM_BLOCKED POLLED NO_RESPAWN_AFTER_OBSERVATION'
STOP_PREFIX=b'RPI5XNU:INIT:STOPPING'
STOP=b'RPI5XNU:INIT:STOPPING SIGTERM NO_RESPAWN'
_base_healthy=healthy
_base_ready=boot_ready
_base_reboot=reboot_observation

def healthy(raw):
    _base_healthy(raw)
    data=normalized(raw);lines=data.splitlines()
    rows=[line for line in lines if line.startswith(STOP_PREFIX)]
    # In-progress RX may end in a partial line. Complete stop rows are strict;
    # no error-stop or stop before the actual fresh execution may be admitted.
    if rows and not data.endswith(b'\n') and lines[-1].startswith(STOP_PREFIX):rows=rows[:-1]
    if len(rows)>1 or any(line!=STOP for line in rows):raise ValueError('PID1 error/duplicate shutdown stop')
    if rows:
        execute=[line for line in lines if re.fullmatch(rb'DR:D[0-9a-f]{16}:EXEC_REBOOT',line)]
        if len(execute)!=1 or data.index(execute[0])>=data.index(STOP):raise ValueError('PID1 stop before actual reboot execution')

def boot_ready(raw,report):
    if report.get('init_shutdown_ready_marker')!=INIT_READY.decode():raise ValueError('Actual PID1 shutdown source report required')
    if STOP_PREFIX in raw:raise ValueError('PID1 stopped before input admission')
    ready=_base_ready(raw,report)
    data=normalized(raw);rows=[line for line in data.splitlines() if line.startswith(b'RPI5XNU:INIT:SHUTDOWN_READY')]
    if rows and rows!=[INIT_READY]:raise ValueError('Malformed/duplicate PID1 shutdown readiness')
    if not rows or not ready:return False
    if data.index(INIT_READY)<=data.index(COMMIT):raise ValueError('PID1 readiness before kernel commit')
    after=data[data.index(INIT_READY)+len(INIT_READY):]
    match=re.search(rb'(?:^|\n)'+re.escape(zsh.READY)+rb'\n',after)
    return match is not None and PROMPT.search(after[match.end():]) is not None

def reboot_observation(raw,n,command_start,bootsys_received):
    result=_base_reboot(raw,n,command_start,bootsys_received)
    data=normalized(raw);lines=data.splitlines();rows=[line for line in lines if line.startswith(STOP_PREFIX)]
    if rows and (rows!=[STOP] or not data.index(('DR:'+n+':EXEC_REBOOT').encode())<data.index(STOP)<data.index(PRE_PREFIX)):
        raise ValueError('Optional exact SIGTERM stop must be between execution and reset path')
    result.update(pid1_sigterm_stop_observed=bool(rows),pid1_stop_required=False,
        no_respawn_after_observation_source_policy=True,arrival_fork_atomicity_claimed=False)
    return result
