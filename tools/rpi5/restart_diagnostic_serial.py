# SPDX-License-Identifier: BSD-2-Clause
"""Real restart observations; nominal timing is not physical oscillator proof."""
import hashlib
import math
from pathlib import Path
import re

_old=Path(__file__).with_name('display_xnu_serial.py')
_raw=_old.read_bytes()
if hashlib.sha256(_raw).hexdigest()!='f3ef90a54697daaf153a3b5595861ba6ceaec53d6909a0b801689fd9872fdd3c':
    raise ValueError('Exact frozen mirrored-zsh grammar required')
_text=_raw.decode()
for _before,_after,_count in (
    ('RPI5XNU:DISPLAYXNU:ENTRY TAG=','RPI5XNU:DISPLAYRESTART_DIAG:ENTRY TAG=',2),
    ('NODES=32 BYTES=1916928','NODES=33 BYTES=2031616',1),
):
    if _text.count(_before)!=_count:raise ValueError('Exact restart grammar derivation changed')
    _text=_text.replace(_before,_after)
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
_display_boot_ready=boot_ready
READY=b'RPI5XNU:RESTART:READY OPTIN=1 PSCI=00010001 RESET_SUPPORTED=1 WATCHDOG_UNCHANGED'
PRE_PREFIX=b'RPI5XNU:RESTART:PRE_SMC '
PRE=re.compile(rb'RPI5XNU:RESTART:PRE_SMC COUNT=([0-9a-f]{8}) COUNTER=([0-9a-f]{16}) FREQ=([0-9a-f]{16}) DEADLINE=([0-9a-f]{16}) NOMINAL_HZ=00010000 RATE_BOUND=0')


def boot_ready(raw,report):
    if report.get('restart_ready_marker')!=READY.decode():raise ValueError('Actual diagnostic readiness report required')
    if not _display_boot_ready(raw,report):return False
    data=normalized(raw);rows=[v for v in data.splitlines() if v.startswith(b'RPI5XNU:RESTART:READY')]
    if rows and rows!=[READY]:raise ValueError('Contradictory or duplicate restart eligibility')
    if not rows:return False
    if data.index(READY)<=data.index(COMMIT):raise ValueError('Restart eligibility before actual kernel commit')
    after=data[data.index(READY)+len(READY):]
    match=re.search(rb'(?:^|\n)'+re.escape(zsh.READY)+rb'\n',after)
    return match is not None and PROMPT.search(after[match.end():]) is not None


def restart_command(n):
    nonce_valid(n)
    # Recovery shell passes one quoted argument to real zsh. The unexpanded
    # command echo contains quotes/semicolon and cannot equal its output line.
    body='print -r -- "DR:'+n+':EXEC_REBOOT"; /sbin/reboot; print -r -- "DR:'+n+':RETURNED:$?"'
    command="/bin/zsh -f -c '"+body+"'"
    if len(command)>1023:raise ValueError('Recovery command bound')
    return command


def reboot_observation(raw,n,command_start,bootsys_received):
    nonce_valid(n);healthy(raw)
    if (type(command_start) not in (int,float) or type(bootsys_received) not in (int,float) or
        not math.isfinite(command_start) or not math.isfinite(bootsys_received) or
        not 0<=command_start<bootsys_received):raise ValueError('Exact bounded host command/boot timing required')
    data=normalized(raw);lines=data.splitlines();execute=('DR:'+n+':EXEC_REBOOT').encode()
    if lines.count(execute)!=1 or any(v.startswith(b'DR:') and v!=execute for v in lines):
        raise ValueError('Actual fresh executed reboot nonce required; echo/return is not success')
    if b'RPI5XNU:RESTART:RETURNED' in data or b'reboot: restart syscall returned' in data:
        raise ValueError('Reset returned; no physical reset proven')
    observed=[v for v in lines if v.startswith(PRE_PREFIX)]
    if len(observed)!=1 or not (match:=PRE.fullmatch(observed[0])):raise ValueError('One exact checked pre-SMC observation required')
    count,counter,frequency,deadline=(int(v,16) for v in match.groups())
    if not 0<count<=0xfffff or not 0<frequency or not counter<deadline:raise ValueError('Fresh supported watchdog snapshot required')
    order=[data.find(execute),data.find(b'PTHREAD:KERNEL_READY'),data.find(b'PTHREAD:MAIN_READY'),data.find(observed[0]),data.find(BOOTSYS)]
    if min(order)<0 or order!=sorted(order) or len(set(order))!=len(order):raise ValueError('Command/startup/pre-SMC/fresh firmware order differs')
    for value in (b'PTHREAD:KERNEL_READY',b'PTHREAD:MAIN_READY'):
        if lines.count(value)!=1:raise ValueError('Exact genuine reboot runtime startup required')
    elapsed=bootsys_received-command_start
    # Round count down to whole seconds and reserve another second. This is
    # an engineering comparison against nominal encoding, not a qualified
    # maximum watchdog clock rate. TX START precedes the physical snapshot,
    # so USB batching cannot artificially shorten the comparison interval.
    nominal_lower_seconds=max(0,(count>>16)-1)
    return dict(ordered_real_reboot_path_observed=True,psci_path_marker_observed=True,
        watchdog_remaining_ticks=count,watchdog_nominal_hz=65536,watchdog_rate_bound_proven=False,
        command_tx_start_to_bootsys_seconds=elapsed,nominal_countdown_margin_seconds=nominal_lower_seconds,
        nominal_early_return=elapsed<nominal_lower_seconds,unconditional_not_watchdog_proven=False,
        physical_psci_causality_proven=False,watchdog_fallback_removal_authorized=False,
        independent_linux_new_boot_required=True)
